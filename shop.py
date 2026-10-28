"""Laqino pharmacy-first shared cart.

Additive module only, disabled unless settings.cart_enabled='1'. Checkout creates
one ordinary delivery order per pharmacy in a single transaction and dispatches
only through the existing server push/offer/accept/commission lifecycle.
"""
import json, time, sqlite3, re, secrets
import gsearch, products

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
CREATE TABLE IF NOT EXISTS cart_checkouts (
 id INTEGER PRIMARY KEY,
 customer_id INTEGER NOT NULL REFERENCES users(id),
 cart_id INTEGER NOT NULL REFERENCES carts(id),
 request_key TEXT NOT NULL,
 order_ids TEXT NOT NULL DEFAULT '[]',
 status TEXT NOT NULL DEFAULT 'created' CHECK(status IN ('creating','created')),
 created_at INTEGER NOT NULL,
 UNIQUE(customer_id,request_key)
);
CREATE INDEX IF NOT EXISTS ix_cart_checkouts_cart ON cart_checkouts(cart_id,id);
"""

def _send(h, *args, **kwargs):
    h.send(*args, **kwargs)
    return True

def enabled(c):
    row = c.execute("SELECT value FROM settings WHERE key='cart_enabled'").fetchone()
    return bool(row and str(row[0]) == "1")

# These callbacks reuse the existing server dispatch/notification and audit path.
_H = {}

def bind(push_new_order, audit, count_orders_sql, max_open_orders, resolve_region=None):
    _H.update(push=push_new_order, audit=audit, count_orders_sql=count_orders_sql,
              max_open_orders=int(max_open_orders), resolve_region=resolve_region)

def install(c):
    c.executescript(SCHEMA)
    c.commit()

def _cart(c, uid, region_id=None):
    now = int(time.time())
    row = c.execute("SELECT * FROM carts WHERE customer_id=?", (uid,)).fetchone()
    if row:
        if row["status"] != "open":
            # A checked-out cart starts a fresh empty cart on the customer's next visit.
            c.execute("DELETE FROM cart_items WHERE cart_id=?", (row["id"],))
            c.execute("UPDATE carts SET status='open',region_id=COALESCE(?,region_id),updated_at=? WHERE id=?", (region_id,now,row["id"]))
            c.commit()
            row = c.execute("SELECT * FROM carts WHERE id=?", (row["id"],)).fetchone()
        return row
    user = c.execute("SELECT region_id FROM users WHERE id=?", (uid,)).fetchone()
    rid = region_id or (user["region_id"] if user else None)
    cur = c.execute("INSERT INTO carts(customer_id,region_id,created_at,updated_at) VALUES(?,?,?,?)", (uid,rid,now,now))
    c.commit()
    return c.execute("SELECT * FROM carts WHERE id=?", (cur.lastrowid,)).fetchone()

def _item_info(c, kind, source_id, provider_id, region_id):
    if kind == "product":
        if not products.enabled(c):
            raise ValueError("قسم المنتجات غير مفعّل حاليًا")
        r = c.execute("""SELECT o.id,o.provider_id,o.title,o.price,o.available,o.status,o.confirmed_at,
                         p.name_ar pharmacy,p.region_id provider_region,p.status provider_status
                         FROM product_offers o JOIN providers p ON p.user_id=o.provider_id
                         WHERE o.id=? AND o.provider_id=?""", (source_id,provider_id)).fetchone()
        if not r or r["status"] != "approved" or not r["available"] or r["provider_status"] != "approved":
            raise ValueError("العرض غير متاح حاليًا")
        if int(time.time()) - int(r["confirmed_at"] or 0) > 14*86400:
            raise ValueError("يجب على الصيدلية تأكيد توفر المنتج من جديد")
        if region_id and r["provider_region"] not in gsearch._related(c, region_id):
            # Match the same regional relation used by the existing product search.
            raise ValueError("الصيدلية خارج نطاق منطقة العميل")
        return dict(id=r["id"],item_type=kind,source_id=r["id"],provider_id=r["provider_id"],
                    pharmacy=r["pharmacy"],title=r["title"],unit_price=round(float(r["price"]),2))
    raise ValueError("نوع الصنف غير مدعوم في هذا المسار")


def _checkout_item(c, item, customer_id, cart_region):
    """Revalidate every cart line at checkout; never trust prices/status cached by the client."""
    if item["item_type"] == "product":
        if not products.enabled(c):
            raise ValueError("قسم المنتجات غير مفعّل حاليًا")
        r = c.execute("""SELECT o.id,o.provider_id,o.title,o.price,o.available,o.status,o.confirmed_at,
                         p.name_ar pharmacy,p.address,p.region_id provider_region,p.status provider_status
                         FROM product_offers o JOIN providers p ON p.user_id=o.provider_id
                         WHERE o.id=? AND o.provider_id=?""", (item["source_id"],item["provider_id"])).fetchone()
        if not r or r["status"] != "approved" or not r["available"] or r["provider_status"] != "approved":
            raise ValueError("أحد المنتجات لم يعد متاحًا")
        if int(time.time()) - int(r["confirmed_at"] or 0) > 14*86400:
            raise ValueError("يجب على الصيدلية تأكيد توفر أحد المنتجات من جديد")
        price = float(r["price"])
        if price < 0 or price != price or price == float("inf"):
            raise ValueError("سعر المنتج غير صالح")
        title = str(r["title"])
    elif item["item_type"] == "rx_quote":
        if int(item["quantity"]) != 1:
            raise ValueError("كمية الروشتة يجب أن تكون 1")
        r = c.execute("""SELECT rr.prescription_id,rr.provider_id,rr.price,rr.status,rr.review,
                           rx.status rx_status,p.name_ar pharmacy,p.address,p.region_id provider_region,
                           p.status provider_status
                         FROM prescription_responses rr
                         JOIN prescriptions rx ON rx.id=rr.prescription_id
                         JOIN providers p ON p.user_id=rr.provider_id
                         WHERE rr.prescription_id=? AND rr.provider_id=? AND rx.customer_id=?""",
                      (item["source_id"],item["provider_id"],customer_id)).fetchone()
        if (not r or r["provider_status"] != "approved" or r["rx_status"] == "closed"
            or r["status"] not in ("available","quoted","responded")
            or r["review"] not in (None,"approved") or not r["price"] or float(r["price"]) <= 0):
            raise ValueError("أحد عروض الروشتة لم يعد معتمدًا أو متاحًا")
        price = float(r["price"])
        title = "روشتة #%s" % item["source_id"]
    else:
        raise ValueError("نوع الصنف غير مدعوم")
    if cart_region and r["provider_region"] not in gsearch._related(c, cart_region):
        raise ValueError("إحدى الصيدليات خارج نطاق منطقة العميل")
    return {"provider_id": int(r["provider_id"]), "provider_region": int(r["provider_region"]),
            "pharmacy": str(r["pharmacy"]), "address": str(r["address"] or ""),
            "title": title, "price": price, "quantity": int(item["quantity"])}

def _checkout(h, c, u, cart, d):
    if not isinstance(d, dict):
        return _send(h, 400, {"error":"بيانات إتمام الطلب غير صالحة"})
    request_key = d.get("request_key")
    dropoff = str(d.get("dropoff_text", "")).strip()[:300]
    if not isinstance(request_key, str) or not 8 <= len(request_key.strip()) <= 64:
        return _send(h, 400, {"error":"مفتاح الطلب مطلوب من 8 إلى 64 حرفًا"})
    request_key = request_key.strip()
    if len(dropoff) < 3:
        return _send(h, 400, {"error":"عنوان التسليم مطلوب"})
    if not cart["region_id"] or not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (cart["region_id"],)).fetchone():
        return _send(h, 409, {"error":"اختَر منطقة توصيل مفعّلة قبل إتمام الطلب"})
    try:
        c.commit()
        c.execute("BEGIN IMMEDIATE")
        dup = c.execute("SELECT id,order_ids,status FROM cart_checkouts WHERE customer_id=? AND request_key=?",
                        (u["id"],request_key)).fetchone()
        if dup:
            ids = json.loads(dup["order_ids"] or "[]")
            orders = []
            for oid in ids:
                row = c.execute("SELECT id,status,region_id FROM delivery_orders WHERE id=? AND customer_id=?", (oid,u["id"])).fetchone()
                if row: orders.append(dict(row))
            c.commit()
            return _send(h, 200, {"checkout_id":dup["id"],"orders":orders,"duplicate":True})
        current = c.execute("SELECT * FROM carts WHERE id=? AND customer_id=? AND status='open'", (cart["id"],u["id"])).fetchone()
        if not current:
            c.rollback()
            return _send(h, 409, {"error":"السلة تغيّرت، حدّثها وحاول مرة أخرى"})
        rows = c.execute("SELECT * FROM cart_items WHERE cart_id=? ORDER BY id", (cart["id"],)).fetchall()
        if not rows:
            c.rollback()
            return _send(h, 400, {"error":"السلة فارغة"})
        # Validate every line again and group one delivery per pharmacy.
        groups = {}
        for item in rows:
            info = _checkout_item(c,item,u["id"],cart["region_id"])
            group = groups.setdefault(info["provider_id"], {"provider_region":info["provider_region"],
                "pharmacy":info["pharmacy"],"address":info["address"],"lines":[]})
            if group["provider_region"] != info["provider_region"]:
                raise ValueError("بيانات منطقة الصيدلية غير متسقة")
            group["lines"].append(info)
        if not groups:
            c.rollback()
            return _send(h, 400, {"error":"السلة فارغة"})
        # Respect the same open-order cap as the ordinary delivery endpoint.
        open_count = int(c.execute(_H["count_orders_sql"], (u["id"],)).fetchone()[0])
        if open_count + len(groups) > _H["max_open_orders"]:
            c.rollback()
            return _send(h, 429, {"error":"عدد طلبات التوصيل المفتوحة لا يسمح بطلب من كل الصيدليات الآن"})
        now = int(time.time())
        settings = {r["key"]:r["value"] for r in c.execute("SELECT key,value FROM settings")}
        comm_type = settings.get("commission_type","fixed")
        try: comm_value = float(settings.get("commission_value",0) or 0)
        except (TypeError,ValueError): comm_value = 0.0
        if comm_value < 0 or comm_value != comm_value or comm_value == float("inf"):
            raise ValueError("إعداد عمولة لاقينو غير صالح")
        cur = c.execute("INSERT INTO cart_checkouts(customer_id,cart_id,request_key,order_ids,status,created_at) VALUES(?,?,?,'[]','creating',?)",
                        (u["id"],cart["id"],request_key,now))
        checkout_id = cur.lastrowid
        created = []
        dla = d.get("dropoff_lat"); dln = d.get("dropoff_lng")
        try:
            dla = float(dla) if dla not in (None,"") else None
            dln = float(dln) if dln not in (None,"") else None
        except (TypeError,ValueError):
            raise ValueError("موقع التسليم غير صالح")
        if (dla is None) != (dln is None) or (dla is not None and (not -90 <= dla <= 90 or not -180 <= dln <= 180)):
            raise ValueError("إحداثيات التسليم غير صالحة")
        if dla is not None and _H.get("resolve_region"):
            gps_region, _distance, _source = _H["resolve_region"](c,dla,dln)
            if gps_region and int(gps_region["id"]) != int(cart["region_id"]) and not bool(d.get("confirm_region_mismatch")):
                selected = c.execute("SELECT name_ar FROM regions WHERE id=?", (cart["region_id"],)).fetchone()
                selected_name = selected["name_ar"] if selected else str(cart["region_id"])
                c.rollback()
                return _send(h,409,{"error":"REGION_MISMATCH|%s|%s|%s|%s" % (cart["region_id"],gps_region["id"],selected_name,gps_region["name_ar"])})
        for provider_id, group in sorted(groups.items()):
            pickup = ("صيدلية " + group["pharmacy"] + ((" — " + group["address"]) if group["address"] else ""))[:300]
            details = "طلب من السلة المشتركة: " + "؛ ".join(
                ("%s × %s (%.2f ج)" % (line["title"],line["quantity"],line["price"]*line["quantity"]))
                for line in group["lines"])
            details = details[:1000]
            commission = round(comm_value * (0 if comm_type == "percent" else 1), 2)
            child_key = "cart%d-p%d" % (checkout_id,provider_id)
            order_cur = c.execute("""INSERT INTO delivery_orders
                (customer_id,region_id,pickup_text,dropoff_text,details,fee,commission,created_at,updated_at,
                 search_started_at,delivery_code,request_key,dropoff_lat,dropoff_lng,fare_status,comm_type,comm_value)
                VALUES(?,?,?,?,?,0,?,?,?,?,?,?,?,?, 'none',?,?)""",
                (u["id"],group["provider_region"],pickup,dropoff,details,commission,now,now,now,
                 "%06d" % secrets.randbelow(10**6),child_key,dla,dln,comm_type,comm_value))
            oid = order_cur.lastrowid
            c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)",
                      (oid,u["id"],None,"searching",now))
            created.append({"id":oid,"status":"searching","provider_id":provider_id,"pharmacy":group["pharmacy"],
                            "region_id":group["provider_region"]})
        ids = [o["id"] for o in created]
        c.execute("UPDATE cart_checkouts SET order_ids=?,status='created' WHERE id=?", (json.dumps(ids),checkout_id))
        c.execute("DELETE FROM cart_items WHERE cart_id=?", (cart["id"],))
        c.execute("UPDATE carts SET status='checked_out',updated_at=? WHERE id=?", (now,cart["id"]))
        _H["audit"](c,u["id"],"cart.checkout",str(checkout_id),{"order_ids":ids,"pharmacy_count":len(ids)})
        c.commit()
    except ValueError as e:
        if c.in_transaction: c.rollback()
        return _send(h, 409, {"error":str(e)})
    except sqlite3.IntegrityError:
        if c.in_transaction: c.rollback()
        # A simultaneous retry is resolved through the durable parent idempotency key.
        dup = c.execute("SELECT id,order_ids FROM cart_checkouts WHERE customer_id=? AND request_key=?",
                        (u["id"],request_key)).fetchone()
        if dup:
            ids=json.loads(dup["order_ids"] or "[]")
            return _send(h,200,{"checkout_id":dup["id"],"orders":[dict(r) for oid in ids if (r:=c.execute("SELECT id,status,region_id FROM delivery_orders WHERE id=? AND customer_id=?",(oid,u["id"])).fetchone())],"duplicate":True})
        return _send(h,409,{"error":"تعذر تأكيد الطلب بأمان، حدّث السلة وحاول مرة أخرى"})
    except Exception:
        if c.in_transaction: c.rollback()
        return _send(h,500,{"error":"تعذر إنشاء طلبات التوصيل، لم يتم إنشاء أي طلب"})
    # Dispatch only after the entire checkout is committed. Reuse the same push loop as normal orders.
    for order in created:
        try: _H["push"](order["id"])
        except Exception: pass
    return _send(h,201,{"checkout_id":checkout_id,"orders":created,"delivery_fee":"يحددها تدفق التوصيل الحالي لكل طلب"})

def handle(h, c, u, method, path, q):
    if not (path == "/api/cart" or path == "/api/cart/items" or re.fullmatch(r"/api/cart/items/\d+",path) or path == "/api/cart/checkout"):
        return False
    install(c)
    if not enabled(c):
        h.send(404, {"error":"السلة غير مفعّلة بعد"}); return True
    if not u:
        h.send(401, {"error":"سجّل الدخول أولًا"}); return True
    if u["role"] not in ("customer",):
        h.send(403, {"error":"السلة متاحة لحساب العميل فقط"}); return True
    if path == "/api/cart/checkout":
        if method != "POST": return _send(h,405,{"error":"طريقة غير مدعومة"})
        if not _H.get("push") or not _H.get("audit") or not _H.get("count_orders_sql") or not _H.get("max_open_orders"):
            return _send(h,503,{"error":"ربط الدليفري غير جاهز على الخادم"})
        cart = _cart(c,u["id"])
        return _checkout(h,c,u,cart,h.body())
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
        return _send(h, 200, {"id":cart["id"],"region_id":cart["region_id"],"items":items,"total":round(total,2)})
    if method == "POST" and path == "/api/cart/items":
        d=h.body()
        kind=d.get("item_type"); sid=d.get("source_id"); pid=d.get("provider_id"); qty=d.get("quantity",1)
        if kind not in ("product","rx_quote") or isinstance(sid,bool) or not isinstance(sid,int) or sid<=0 or isinstance(pid,bool) or not isinstance(pid,int) or pid<=0 or isinstance(qty,bool) or not isinstance(qty,int) or not 1<=qty<=99:
            return _send(h, 400,{"error":"بيانات الصنف غير صالحة"})
        if kind == "rx_quote" and qty != 1:
            return _send(h, 400,{"error":"كمية الروشتة يجب أن تكون 1"})
        if kind == "product":
            try: info=_item_info(c,kind,sid,pid,cart["region_id"])
            except ValueError as e: return _send(h, 409,{"error":str(e)})
        else:
            # Restrict prescription quote to the authenticated customer; use prescription id as source_id.
            r=c.execute("""SELECT rr.prescription_id,rr.provider_id,rr.price,rr.status,rr.review,rx.status rx_status,
                           p.status provider_status,p.region_id provider_region FROM prescription_responses rr
                           JOIN prescriptions rx ON rx.id=rr.prescription_id JOIN providers p ON p.user_id=rr.provider_id
                           WHERE rr.prescription_id=? AND rr.provider_id=? AND rx.customer_id=?""",(sid,pid,u["id"])).fetchone()
            if not r or r["provider_status"]!="approved" or r["rx_status"]=="closed" or r["status"] not in ("available","quoted","responded") or r["review"] not in (None,"approved") or not r["price"] or float(r["price"])<=0:
                return _send(h, 409,{"error":"رد الروشتة غير معتمد أو غير متاح"})
            if cart["region_id"] and r["provider_region"] not in gsearch._related(c, cart["region_id"]):
                return _send(h, 409,{"error":"الصيدلية خارج نطاق منطقة العميل"})
        now=int(time.time())
        try:
            c.execute("INSERT INTO cart_items(cart_id,item_type,source_id,provider_id,quantity,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(cart_id,item_type,source_id,provider_id) DO UPDATE SET quantity=excluded.quantity,updated_at=excluded.updated_at",
                      (cart["id"],kind,sid,pid,qty,now,now))
            c.execute("UPDATE carts SET updated_at=? WHERE id=?",(now,cart["id"])); c.commit()
        except sqlite3.Error:
            c.rollback(); return _send(h, 409,{"error":"تعذر تحديث السلة، حاول مرة أخرى"})
        return _send(h, 200,{"ok":True,"cart_id":cart["id"]})
    m=re.fullmatch(r"/api/cart/items/(\d+)",path)
    if method == "DELETE" and m:
        cur=c.execute("DELETE FROM cart_items WHERE id=? AND cart_id=?",(int(m[1]),cart["id"]))
        c.execute("UPDATE carts SET updated_at=? WHERE id=?",(int(time.time()),cart["id"])); c.commit()
        return _send(h, 200,{"ok":True,"removed":bool(cur.rowcount)})
    return _send(h, 405,{"error":"طريقة غير مدعومة"})
