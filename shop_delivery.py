# لاقينو — المرحلة 69 (م4 من خطة «محلات في منطقتك»): الدليفري للمحلات في اتجاهين. وحدة مستقلة بنمط provider_delivery.py: لا تستورد server.py (ما تحتاجه يمرّره server.bind).
# 1) المحل يطلب مندوب (origin_type='shop_pickup'): نفس زر الصيدلية بالظبط — أول مندوب متاح يستلم الأوردر من المحل وينتهي الطلب لحظة الاستلام، بلا أجرة داخل التطبيق.
#    المراحل والقبول المباشر وتحصيل العمولة عند الاستلام يعالجها server.py عبر PICKUP_KINDS (تضم provider_pickup وshop_pickup) فلا تكرار لمنطق المندوب.
# 2) العميل يطلب من المحل (origin_type='shop_order'): أصناف المحل (id + كمية) تتحوّل لطلب توصيل عادي من المحل إلى عنوان العميل، والمندوب يوصله مباشرة بدورة الطلب العادي كاملة
#    (أجرة المندوب تُقترح وتُوافق عليها، رمز التسليم، التأكيد، التقييم). أجرة المنطقة ثابتة من region_fees لمنطقة المحل مثل توصيل الصيدلية. بلا سلة: محل واحد في الطلب.
#    المحل يُشعَر بالطلب (trigger ntf_shop_) ويراه في قائمته ويقدر يرفضه قبل الاستلام. ثمن الأصناف لا يمر على النظام (لا مدفوعات في المشروع)؛ يُعرض للعميل والمحل فقط.
# جدول إضافي واحد shop_delivery_links يربط الطلب بالمحل. عمود delivery_orders.origin_type يضيفه provider_delivery.install.
# المسارات:
#   مالك المحل: POST /api/owner/shops/<id>/delivery-request | GET /api/owner/shops/<id>/delivery-requests | GET /api/owner/shops/<id>/orders | POST /api/owner/shops/<id>/orders/<oid>/reject
#   عميل:       GET /api/shops/<id>/menu (نص فقط؛ الصور في م5) | POST /api/shops/<id>/order
#   إدارة:      GET (admin/staff) | POST (admin فقط) /api/admin/shop-delivery
# م79 (phase-79): المحل يطلب مندوب صار مطابقًا للصيدلية بعد م2: 4 مراحل حتى التسليم للعميل، تفاصيل اختيارية، تأكيد التسليم يدويًا، وإحصائيات في shop_delivery_stats.py.
# المفتاح settings.shop_delivery_enabled (مطفي افتراضيًا ويشترط أيضًا shops_enabled) + settings.shop_delivery_commission (عمولة ثابتة على المندوب لطلب «المحل يطلب مندوب» فقط؛ 0 = مجانية).
import re, json, time, secrets, sqlite3
import notif, shops, provider_delivery as pd

PICKUP, ORDER = "shop_pickup", "shop_order"  # قيم delivery_orders.origin_type
MAX_LINES, MAX_QTY, MAX_PER_HOUR = 20, 50, 10
_H = {}
SCHEMA = """
CREATE TABLE IF NOT EXISTS shop_delivery_links(order_id INTEGER PRIMARY KEY REFERENCES delivery_orders(id), shop_id INTEGER NOT NULL REFERENCES shops(id),
 kind TEXT NOT NULL CHECK(kind IN('shop_pickup','shop_order')), items_json TEXT, items_total REAL, note TEXT, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_sdl_shop ON shop_delivery_links(shop_id,kind,order_id);
"""


def bind(push, push_stop, audit, region, count_sql, region_fee, commission_for, cust_limit):
    """يُستدعى من server.init: دفع الطلب للمناديب، إيقاف تكرار الدفع، سجل التدقيق، منطقة افتراضية، عدّ الطلبات المفتوحة، أجرة المنطقة، حساب العمولة، سقف طلبات العميل."""
    _H.update(push=push, push_stop=push_stop, audit=audit, region=region, count_sql=count_sql, region_fee=region_fee, commission_for=commission_for, cust_limit=cust_limit)


def install(c):
    """جدول الربط + إشعار المحل بطلب العميل. آمن للتكرار؛ يُستدعى بعد shops.install (الذي يعيد كتابة triggers ntf_shop_)."""
    c.executescript(SCHEMA)
    c.execute("DROP TRIGGER IF EXISTS ntf_shop_dl_new")
    body = notif._ins("(shops.owner_id)", "shop.order", "طلب جديد من عميل", body="'طلب رقم ' || NEW.order_id", link="shoporders", ref_type="order", ref_id="NEW.order_id", frm="FROM shops", where="WHERE shops.id=NEW.shop_id")
    c.execute("CREATE TRIGGER ntf_shop_dl_new AFTER INSERT ON shop_delivery_links WHEN NEW.kind='shop_order' BEGIN %s END" % body)
    c.commit()


def settings(c):
    g = lambda k: (c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone() or [None])[0]
    try: comm = max(0.0, float(g("shop_delivery_commission") or 0))
    except (TypeError, ValueError): comm = 0.0
    return str(g("shop_delivery_enabled") or "0") == "1" and shops.enabled(c), str(g("shop_delivery_enabled") or "0") == "1", comm


def late_minutes(c):
    """حد تأخير مرحلة التوصيل (من الاستلام حتى التسليم للعميل) بالدقائق لطلبات المحلات؛ 0 = بلا إنذار. مفتاح مستقل عن الصيدلية، وافتراضيه نفس افتراضيها."""
    r = c.execute("SELECT value FROM settings WHERE key='shop_delivery_late_minutes'").fetchone()
    try: return max(0, int(float(r[0]))) if r else pd.DEFAULT_LATE_MIN
    except (TypeError, ValueError): return pd.DEFAULT_LATE_MIN


def _int(v):
    return None if isinstance(v, bool) or not isinstance(v, int) else v


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. h = معالج السيرفر (send/body). الأخطاء تُرجَع مباشرة عبر h.send."""
    mo = re.fullmatch(r"/api/owner/shops/(\d{1,9})/(delivery-request|delivery-requests|orders)(?:/(\d{1,9})/(reject))?", path)
    mc = re.fullmatch(r"/api/shops/(\d{1,9})/(menu|order)", path)
    md = re.fullmatch(r"/api/owner/shops/(\d{1,9})/delivery-requests/(\d{1,9})/delivered", path)  # م79: «تم التسليم» يدويًا من المحل (مثل الصيدلية)
    if path != "/api/admin/shop-delivery" and not mo and not mc and not md: return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    ok = lambda obj, code=200: (h.send(code, obj), True)[1]
    audit = lambda act, tgt, det=None: _H["audit"](c, u["id"], act, tgt, det)

    # ---- الإدارة: المفتاح + العمولة
    if path == "/api/admin/shop-delivery":
        if method not in ("GET", "POST"): return False
        if not u: return err(401, "سجّل الدخول أولًا")
        if u["role"] not in ("admin", "staff") or (method == "POST" and u["role"] != "admin"): return err(403, "ليس لديك صلاحية")  # القراءة للموظف أيضًا (تبويب المحلات في الإدارة يفتح له)؛ الكتابة للمدير فقط
        if method == "GET":
            _, en, comm = settings(c); return ok({"enabled": en, "commission": comm, "late_minutes": late_minutes(c)})
        d = h.body(); en = d.get("enabled")
        if not isinstance(en, bool): return err(400, "قيمة التفعيل غير صالحة")
        try: comm = round(float(d.get("commission", 0) or 0), 2)
        except (TypeError, ValueError): return err(400, "قيمة العمولة غير صالحة")
        if not (0 <= comm <= 100000): return err(400, "قيمة العمولة غير صالحة")  # يرفض NaN/inf/سالب
        kv = [("shop_delivery_enabled", "1" if en else "0"), ("shop_delivery_commission", str(comm))]
        if d.get("late_minutes") is not None:  # اختياري: غيابه يُبقي القيمة الحالية
            try: lm = int(float(str(d["late_minutes"]).translate(pd._AR)))
            except (TypeError, ValueError, OverflowError): return err(400, "حد التأخير غير صالح")
            if not (0 <= lm <= 1440): return err(400, "حد التأخير غير صالح")
            kv.append(("shop_delivery_late_minutes", str(lm)))
        for k, x in kv:
            c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, x))
        audit("settings.shop_delivery", None, {"enabled": en, "commission": comm, "late_minutes": late_minutes(c)}); c.commit()
        return ok({"enabled": en, "commission": comm, "late_minutes": late_minutes(c)})

    # ---- العميل: قائمة أصناف المحل (نص فقط) وطلب من المحل
    if mc:
        sid, what = int(mc[1]), mc[2]
        if (method, what) not in (("GET", "menu"), ("POST", "order")): return False
        if what == "menu":
            if not shops.enabled(c): return ok({"enabled": False, "shop": None, "items": []})
            s = c.execute("SELECT s.id,s.name_ar,s.region_id,s.is_open,t.name_ar type_name FROM shops s JOIN shop_types t ON t.id=s.type_id WHERE s.id=? AND s.status='approved'", (sid,)).fetchone()
            if not s or not shops.region_ok(c, s["region_id"]): return err(404, "المحل غير موجود")
            imgs = {}
            for r in c.execute("SELECT i.item_id,i.file_id FROM shop_item_images i JOIN shop_items x ON x.id=i.item_id WHERE x.shop_id=? ORDER BY i.rowid", (sid,)): imgs.setdefault(r["item_id"], []).append(r["file_id"])
            its = [{"id": r["id"], "name_ar": r["name_ar"], "description": r["description"] or "", "price": r["price"], "image_ids": imgs.get(r["id"], [])} for r in c.execute("SELECT id,name_ar,description,price FROM shop_items WHERE shop_id=? AND status='active' AND is_available=1 ORDER BY sort,id", (sid,))]
            return ok({"enabled": True, "order_enabled": settings(c)[0], "shop": {"id": s["id"], "name_ar": s["name_ar"], "type_name": s["type_name"], "region_id": s["region_id"], "is_open": bool(s["is_open"])}, "items": its})
        if not u: return err(401, "سجّل الدخول أولًا")
        on, _, _ = settings(c)
        if not on: return err(403, "الطلب من المحلات غير مفعّل حاليًا")
        d = h.body()
        s = c.execute("SELECT * FROM shops WHERE id=? AND status='approved'", (sid,)).fetchone()
        if not s: return err(404, "المحل غير موجود")
        if not shops.region_ok(c, s["region_id"]): return err(404, "المحل غير موجود")
        if s["owner_id"] == u["id"]: return err(403, "لا يمكنك الطلب من محلك")
        if not s["is_open"]: return err(409, "المحل مغلق حاليًا")
        raw = d.get("items")
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_LINES: return err(400, "اختر من 1 إلى %d أصناف" % MAX_LINES)
        want = {}
        for x in raw:
            # سقف المعرّف (1..10^12) يمنع OverflowError في SQLite
            iid, qty = (_int(x.get("item_id")), _int(x.get("qty"))) if isinstance(x, dict) else (None, None)
            if iid is None or qty is None or not 1 <= iid <= 10 ** 12 or not 1 <= qty <= MAX_QTY or iid in want: return err(400, "قائمة الأصناف غير صالحة (الكمية من 1 إلى %d بلا تكرار صنف)" % MAX_QTY)
            want[iid] = qty
        rows = {r["id"]: r for r in c.execute("SELECT id,name_ar,price,is_available FROM shop_items WHERE shop_id=? AND status='active' AND id IN (%s)" % ",".join("?" * len(want)), (sid, *want))}
        if len(rows) != len(want): return err(400, "صنف غير موجود في هذا المحل")
        for iid in want:
            if not rows[iid]["is_available"]: return err(409, "الصنف «%s» غير متاح حاليًا" % rows[iid]["name_ar"])
        lines = [{"id": i, "name": rows[i]["name_ar"], "price": rows[i]["price"], "qty": want[i]} for i in want]
        total = round(sum(x["price"] * x["qty"] for x in lines), 2)
        note = re.sub(r"\s+", " ", str(d.get("note") or "")).strip()[:300]
        dr = str(d.get("dropoff_text", "")).strip()
        if len(dr) < 3: return err(400, "عنوان التسليم مطلوب")
        try: dla, dln = shops._geo({"lat": d.get("dropoff_lat"), "lng": d.get("dropoff_lng")})
        except ValueError as e: return err(400, str(e))
        f = _H["region_fee"](c, s["region_id"])
        if not f: return err(400, "الدليفري غير متاح في منطقة المحل")
        rk = str(d.get("request_key", "")).strip()[:64] or None
        if rk:
            dup = c.execute("SELECT id,status,delivery_code FROM delivery_orders WHERE customer_id=? AND request_key=?", (u["id"], rk)).fetchone()
            if dup: return ok({"id": dup["id"], "status": dup["status"], "delivery_code": dup["delivery_code"], "duplicate": True})
        if c.execute("SELECT COUNT(*) FROM shop_delivery_links l JOIN delivery_orders o ON o.id=l.order_id WHERE o.customer_id=? AND l.kind=? AND l.created_at>?", (u["id"], ORDER, int(time.time()) - 3600)).fetchone()[0] >= MAX_PER_HOUR: return err(429, "طلبات كثيرة من المحلات في ساعة، حاول لاحقًا")  # م6: سقف إساءة الاستخدام
        if c.execute(_H["count_sql"], (u["id"],)).fetchone()[0] >= _H["cust_limit"]: return err(429, "لديك طلبات توصيل مفتوحة كثيرة، أكمل أو ألغِ بعضها أولًا")
        cm = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; ct, cv = cm.get("commission_type", "fixed"), float(cm.get("commission_value", 0))
        comm = _H["commission_for"](c, f["fee"], ct, cv); now = int(time.time()); code = "%06d" % secrets.randbelow(10 ** 6)
        pk = ("محل " + s["name_ar"] + (" — " + s["address"] if s["address"] else ""))[:300]
        det = "\n".join("%d× %s" % (x["qty"], x["name"]) for x in lines) + ("\nملاحظة: " + note if note else "")
        try:
            cur = c.execute("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,details,fee,commission,created_at,updated_at,search_started_at,delivery_code,request_key,dropoff_lat,dropoff_lng,fare_status,origin_type,comm_type,comm_value) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'none',?,?,?)",
                            (u["id"], s["region_id"], pk, dr[:300], "", f["fee"], round(comm, 2), now, now, now, code, rk, dla, dln, ORDER, ct, cv))
        except sqlite3.IntegrityError:  # م6: سباق مفتاح الطلب المكرر (طلبان متزامنان) ← نُرجع الأول
            c.rollback(); dup = c.execute("SELECT id,status,delivery_code FROM delivery_orders WHERE customer_id=? AND request_key=?", (u["id"], rk)).fetchone()
            if dup: return ok({"id": dup["id"], "status": dup["status"], "delivery_code": dup["delivery_code"], "duplicate": True})
            raise
        oid = cur.lastrowid
        c.execute("UPDATE delivery_orders SET details=? WHERE id=?", ("طلب من محل %s — رقم الطلب %d\n%s" % (s["name_ar"], oid, det[:900]), oid))
        c.execute("INSERT INTO shop_delivery_links(order_id,shop_id,kind,items_json,items_total,note,created_at) VALUES(?,?,?,?,?,?,?)", (oid, sid, ORDER, json.dumps(lines, ensure_ascii=False), total, note or None, now))
        c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, u["id"], None, "searching", now))
        audit("shop.order", str(oid), {"shop": sid, "total": total}); c.commit(); _H["push"](oid)
        return ok({"id": oid, "status": "searching", "delivery_code": code, "items_total": total}, 201)

    # ---- م79: تأكيد التسليم يدويًا من المحل (لو المندوب لم يضغطها) — صاحب الطلب فقط، بعد الاستلام فقط؛ لا يتطلب المفتاح العام كي لا يعلق أوردر شغّال
    if md:
        if method != "POST": return False
        if not u: return err(401, "سجّل الدخول أولًا")
        sid, oid = int(md[1]), int(md[2])
        s, e = shops.need_shop_owner(c, u, sid)
        if e: return err(*e)
        o = c.execute("SELECT o.status FROM shop_delivery_links l JOIN delivery_orders o ON o.id=l.order_id WHERE l.order_id=? AND l.shop_id=? AND l.kind=?", (oid, sid, PICKUP)).fetchone()
        if not o: return err(404, "غير موجود")
        now = int(time.time())
        if not c.execute("UPDATE delivery_orders SET status='completed',updated_at=? WHERE id=? AND status IN ('picked_up','heading_customer')", (now, oid)).rowcount: return err(409, "لا يمكن تأكيد التسليم في الحالة الحالية")
        c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, u["id"], o["status"], "completed", now))
        audit("shop.delivery_confirm", str(oid), {"shop": sid}); c.commit()
        return ok({"id": oid, "status": "completed"})

    # ---- مالك المحل (محله المعتمد فقط)
    sid, what = int(mo[1]), mo[2]
    if (method, what, bool(mo[4])) not in (("POST", "delivery-request", False), ("GET", "delivery-requests", False), ("GET", "orders", False), ("POST", "orders", True)): return False
    if not u: return err(401, "سجّل الدخول أولًا")
    s, e = shops.need_shop_owner(c, u, sid)
    if e: return err(*e)
    on, _, comm = settings(c)
    if what == "delivery-requests":
        now = int(time.time()); lm = late_minutes(c); rows = []
        for r in c.execute(
                "SELECT o.id,o.status,o.dropoff_text,o.pd_cust_phone,o.pd_price,o.pd_note,o.created_at,o.updated_at,CASE WHEN o.status IN " + pd.ACTIVE + " THEN cu.name END courier_name,"
                "CASE WHEN o.status IN " + pd.ACTIVE + " THEN cu.phone END courier_phone," + pd.EVSQL +
                " FROM shop_delivery_links l JOIN delivery_orders o ON o.id=l.order_id LEFT JOIN users cu ON cu.id=o.courier_id WHERE l.shop_id=? AND l.kind=? ORDER BY o.id DESC LIMIT 20", (sid, PICKUP)):
            r = pd.timing(dict(r), now, lm, s["owner_id"])
            if r.get("delivered_by") == "pharmacy": r["delivered_by"] = "shop"
            rows.append(r)
        return ok({"enabled": on, "late_minutes": lm, "items": rows})
    if what == "orders" and not mo[4]:
        rows = []
        for r in c.execute(
                "SELECT o.id,o.status,o.fare_status,o.created_at,l.items_json,l.items_total,l.note,CASE WHEN o.status IN " + pd.ACTIVE + " AND o.fare_status='approved' THEN cu.name END courier_name,"
                "CASE WHEN o.status IN " + pd.ACTIVE + " AND o.fare_status='approved' THEN cu.phone END courier_phone "
                "FROM shop_delivery_links l JOIN delivery_orders o ON o.id=l.order_id LEFT JOIN users cu ON cu.id=o.courier_id WHERE l.shop_id=? AND l.kind=? ORDER BY o.id DESC LIMIT 50", (sid, ORDER)):
            rows.append({"id": r["id"], "status": r["status"], "created_at": r["created_at"], "items": json.loads(r["items_json"] or "[]"), "items_total": r["items_total"], "note": r["note"] or "",
                         "courier_name": r["courier_name"], "courier_phone": r["courier_phone"], "can_reject": r["status"] in ("searching", "assigned", "heading_pickup")})
        return ok({"enabled": on, "items": rows})
    if what == "orders":  # رفض المحل لطلب عميل قبل أن يستلمه المندوب
        oid = int(mo[3])
        l = c.execute("SELECT 1 FROM shop_delivery_links WHERE order_id=? AND shop_id=? AND kind=?", (oid, sid, ORDER)).fetchone()
        if not l: return err(404, "الطلب غير موجود")
        o = c.execute("SELECT status FROM delivery_orders WHERE id=?", (oid,)).fetchone(); now = int(time.time())
        if not c.execute("UPDATE delivery_orders SET status='cancelled',updated_at=? WHERE id=? AND status IN ('searching','assigned','heading_pickup')", (now, oid)).rowcount: return err(409, "لا يمكن رفض الطلب في حالته الحالية")
        c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, u["id"], o["status"], "cancelled", now))
        audit("shop.order_reject", str(oid), {"shop": sid}); c.commit(); _H["push_stop"](oid)
        return ok({"status": "cancelled"})
    # POST delivery-request: ضغطة واحدة — بلا أجرة ولا تفاصيل؛ عنوان العميل اختياري (نفس منطق الصيدلية)
    if not on: return err(403, "طلب المندوب من المحل غير مفعّل حاليًا")
    d = h.body(); rid = s["region_id"]
    if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone(): rid = _H["region"](c)
    if not rid: return err(400, "الدليفري غير متاح حاليًا")
    rk = str(d.get("request_key", "")).strip()[:64] or None
    if rk:
        dup = c.execute("SELECT id,status FROM delivery_orders WHERE customer_id=? AND request_key=?", (u["id"], rk)).fetchone()
        if dup: return ok({"id": dup["id"], "status": dup["status"], "duplicate": True})
    if c.execute(_H["count_sql"], (u["id"],)).fetchone()[0] >= pd.MAX_OPEN: return err(429, "لديك طلبات مندوب مفتوحة كثيرة، انتظر أو ألغِ بعضها أولًا")
    dr = str(d.get("dropoff_text", "")).strip()[:300]; now = int(time.time())
    cph = str(d.get("customer_phone", "") or "").strip(); cn = None  # م79: تفاصيل اختيارية مثل الصيدلية (رقم العميل/السعر/ملاحظة)
    if cph:
        cn = pd.norm_phone(cph)
        if not cn: return err(400, "رقم العميل غير صالح")
    pr = d.get("price"); pnote = str(d.get("note", "") or "").strip()[:500]
    if pr is not None and str(pr).strip() != "":
        try: pr = round(float(str(pr).translate(pd._AR)), 2)
        except (TypeError, ValueError): return err(400, "السعر غير صالح")
        if not (0 <= pr <= 1000000): return err(400, "السعر غير صالح")  # يرفض NaN/inf/سالب
    else: pr = None
    pk = ("محل " + s["name_ar"] + (" — " + s["address"] if s["address"] else ""))[:300]
    cur = c.execute("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,details,fee,commission,created_at,updated_at,search_started_at,delivery_code,request_key,fare_status,origin_type,comm_type,comm_value) VALUES(?,?,?,?,?,0,?,?,?,?,?,?,'approved',?,'fixed',?)",
                    (u["id"], rid, pk, dr, "طلب استلام من محل", comm, now, now, now, "%06d" % secrets.randbelow(10 ** 6), rk, PICKUP, comm))
    oid = cur.lastrowid
    if cn or pr is not None or pnote: c.execute("UPDATE delivery_orders SET pd_cust_phone=?,pd_cust_norm=?,pd_price=?,pd_note=? WHERE id=?", (cn, cn, pr, pnote or None, oid))
    c.execute("INSERT INTO shop_delivery_links(order_id,shop_id,kind,created_at) VALUES(?,?,?,?)", (oid, sid, PICKUP, now))
    c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, u["id"], None, "searching", now))
    audit("shop.delivery_request", str(oid), {"shop": sid}); c.commit(); _H["push"](oid)
    return ok({"id": oid, "status": "searching"}, 201)
