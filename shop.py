"""Laqino shared cart groundwork (isolated rollout).

Additive module only. Disabled unless settings.cart_enabled='1'. It does not create
delivery orders yet: checkout stays deliberately unavailable until atomic
multi-pharmacy dispatch is wired to the existing delivery lifecycle.
"""
import json, time, sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS carts (
 id INTEGER PRIMARY KEY,
 customer_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
 region_id INTEGER REFERENCES regions(id),
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','checked_out','abandoned')),
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cart_items (
 id INTEGER PRIMARY KEY,
 cart_id INTEGER NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
 item_type TEXT NOT NULL CHECK(item_type IN ('product','rx_quote')),
 source_id INTEGER NOT NULL,
 provider_id INTEGER NOT NULL REFERENCES providers(user_id),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 99),
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 UNIQUE(cart_id,item_type,source_id,provider_id)
);
CREATE INDEX IF NOT EXISTS ix_cart_items_cart ON cart_items(cart_id,id);
"""

def enabled(c):
    row = c.execute("SELECT value FROM settings WHERE key='cart_enabled'").fetchone()
    return bool(row and str(row[0]) == "1")

def install(c):
    c.executescript(SCHEMA)
    c.commit()

def _cart(c, uid, region_id=None):
    now = int(time.time())
    row = c.execute("SELECT * FROM carts WHERE customer_id=?", (uid,)).fetchone()
    if row:
        if row["status"] != "open":
            c.execute("UPDATE carts SET status='open',updated_at=? WHERE id=?", (now,row["id"]))
            row = c.execute("SELECT * FROM carts WHERE id=?", (row["id"],)).fetchone()
        return row
    user = c.execute("SELECT region_id FROM users WHERE id=?", (uid,)).fetchone()
    rid = region_id or (user["region_id"] if user else None)
    cur = c.execute("INSERT INTO carts(customer_id,region_id,created_at,updated_at) VALUES(?,?,?,?)", (uid,rid,now,now))
    return c.execute("SELECT * FROM carts WHERE id=?", (cur.lastrowid,)).fetchone()

def _item_info(c, kind, source_id, provider_id, region_id):
    if kind == "product":
        r = c.execute("""SELECT o.id,o.provider_id,o.title,o.price,o.available,o.status,o.confirmed_at,
                         p.name_ar pharmacy,p.region_id provider_region,p.status provider_status
                         FROM product_offers o JOIN providers p ON p.user_id=o.provider_id
                         WHERE o.id=? AND o.provider_id=?""", (source_id,provider_id)).fetchone()
        if not r or r["status"] != "approved" or not r["available"] or r["provider_status"] != "approved":
            raise ValueError("العرض غير متاح حاليًا")
        if int(time.time()) - int(r["confirmed_at"] or 0) > 14*86400:
            raise ValueError("يجب على الصيدلية تأكيد توفر المنتج من جديد")
        if region_id and r["provider_region"] != region_id:
            # Region coverage is validated again during checkout; don't silently change the customer's region.
            parent = c.execute("""WITH RECURSIVE ancestors(id,parent_id) AS
                                  (SELECT id,parent_id FROM regions WHERE id=?
                                   UNION ALL SELECT r.id,r.parent_id FROM regions r JOIN ancestors a ON r.id=a.parent_id)
                                  SELECT 1 FROM ancestors WHERE id=? LIMIT 1""", (region_id,r["provider_region"])).fetchone()
            if not parent:
                raise ValueError("الصيدلية خارج نطاق منطقة العميل")
        return dict(id=r["id"],item_type=kind,source_id=r["id"],provider_id=r["provider_id"],
                    pharmacy=r["pharmacy"],title=r["title"],unit_price=round(float(r["price"]),2))
    raise ValueError("نوع الصنف غير مدعوم في هذا المسار")

def handle(h, c, u, method, path, q):
    if not (path == "/api/cart" or path == "/api/cart/items" or __import__("re").fullmatch(r"/api/cart/items/\d+",path) or path == "/api/cart/checkout"):
        return False
    install(c)
    if not enabled(c):
        h.send(404, {"error":"السلة غير مفعّلة بعد"}); return True
    if not u:
        h.send(401, {"error":"سجّل الدخول أولًا"}); return True
    if u["role"] not in ("customer",):
        h.send(403, {"error":"السلة متاحة لحساب العميل فقط"}); return True
    if path == "/api/cart/checkout":
        h.send(409, {"error":"إتمام السلة غير متاح حتى اكتمال ربط الطلبات المتعددة بدورة التوصيل الحالية"}); return True
    cart = _cart(c,u["id"])
    if method == "GET" and path == "/api/cart":
        rows = c.execute("""SELECT i.id,i.item_type,i.source_id,i.provider_id,i.quantity,p.name_ar pharmacy,
                            CASE WHEN i.item_type='product' THEN o.title ELSE 'روشتة #'||i.source_id END title,
                            CASE WHEN i.item_type='product' THEN o.price ELSE rr.price END unit_price
                            FROM cart_items i JOIN providers p ON p.user_id=i.provider_id
                            LEFT JOIN product_offers o ON i.item_type='product' AND o.id=i.source_id AND o.provider_id=i.provider_id
                            LEFT JOIN prescription_responses rr ON i.item_type='rx_quote' AND rr.prescription_id=i.source_id AND rr.provider_id=i.provider_id
                            WHERE i.cart_id=? ORDER BY p.name_ar,i.id""", (cart["id"],)).fetchall()
        items=[]; total=0
        for r in rows:
            if r["unit_price"] is None: continue
            d=dict(r); d["line_total"]=round(float(r["unit_price"])*d["quantity"],2); total += d["line_total"]; items.append(d)
        return h.send(200, {"id":cart["id"],"region_id":cart["region_id"],"items":items,"total":round(total,2)})
    if method == "POST" and path == "/api/cart/items":
        d=h.body()
        kind=d.get("item_type"); sid=d.get("source_id"); pid=d.get("provider_id"); qty=d.get("quantity",1)
        if kind not in ("product","rx_quote") or isinstance(sid,bool) or not isinstance(sid,int) or sid<=0 or isinstance(pid,bool) or not isinstance(pid,int) or pid<=0 or isinstance(qty,bool) or not isinstance(qty,int) or not 1<=qty<=99:
            return h.send(400,{"error":"بيانات الصنف غير صالحة"})
        if kind == "product":
            try: info=_item_info(c,kind,sid,pid,cart["region_id"])
            except ValueError as e: return h.send(409,{"error":str(e)})
        else:
            # Restrict prescription quote to the authenticated customer; use prescription id as source_id.
            r=c.execute("""SELECT rr.prescription_id,rr.provider_id,rr.price,rr.status,rr.review,rx.status rx_status,
                           p.status provider_status FROM prescription_responses rr
                           JOIN prescriptions rx ON rx.id=rr.prescription_id JOIN providers p ON p.user_id=rr.provider_id
                           WHERE rr.prescription_id=? AND rr.provider_id=? AND rx.customer_id=?""",(sid,pid,u["id"])).fetchone()
            if not r or r["provider_status"]!="approved" or r["rx_status"]=="closed" or r["status"] not in ("available","quoted","responded") or r["review"] not in (None,"approved") or not r["price"] or float(r["price"])<=0:
                return h.send(409,{"error":"رد الروشتة غير معتمد أو غير متاح"})
        now=int(time.time())
        try:
            c.execute("INSERT INTO cart_items(cart_id,item_type,source_id,provider_id,quantity,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(cart_id,item_type,source_id,provider_id) DO UPDATE SET quantity=excluded.quantity,updated_at=excluded.updated_at",
                      (cart["id"],kind,sid,pid,qty,now,now))
            c.execute("UPDATE carts SET updated_at=? WHERE id=?",(now,cart["id"])); c.commit()
        except sqlite3.Error:
            c.rollback(); return h.send(409,{"error":"تعذر تحديث السلة، حاول مرة أخرى"})
        return h.send(200,{"ok":True,"cart_id":cart["id"]})
    import re
    m=re.fullmatch(r"/api/cart/items/(\d+)",path)
    if method == "DELETE" and m:
        cur=c.execute("DELETE FROM cart_items WHERE id=? AND cart_id=?",(int(m[1]),cart["id"]))
        c.execute("UPDATE carts SET updated_at=? WHERE id=?",(int(time.time()),cart["id"])); c.commit()
        return h.send(200,{"ok":True,"removed":bool(cur.rowcount)})
    return h.send(405,{"error":"طريقة غير مدعومة"})
