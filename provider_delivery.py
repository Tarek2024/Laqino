# لاقينو — المرحلة 40: زر «اطلب دليفري» للصيدليات. مؤسسة معتمدة تضغط زرًا فيستلم أول مندوب متاح الأوردر منها، وينتهي الطلب لحظة الاستلام.
# وحدة مستقلة بنمط products.py/notif.py: لا تستورد server.py (ما تحتاجه من server يمرّره server.bind). إضافة فقط: عمود delivery_orders.origin_type.
# المسارات:  صيدلية: POST /api/provider/delivery-request  |  GET /api/provider/delivery-requests   —   إدارة: GET|POST /api/admin/provider-delivery
# المفتاح العام settings.provider_delivery_enabled (مطفي افتراضيًا) + عمولة ثابتة على المندوب settings.provider_delivery_commission (0 = مجانية).
import time, secrets, sqlite3

KIND = "provider_pickup"  # قيمة delivery_orders.origin_type؛ NULL = الطلب العادي
NEXT = {"assigned": "heading_pickup", "heading_pickup": "completed"}  # مراحل المندوب: ينتهي الطلب عند الاستلام من الصيدلية
MAX_OPEN = 10
ACTIVE = "('assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation')"
_H = {}


def bind(push, audit, region, count_sql):
    """يُستدعى من server.init: دوال server التي تحتاجها الوحدة (دفع الطلب للمناديب، سجل التدقيق، منطقة افتراضية، عدّ الطلبات المفتوحة)."""
    _H.update(push=push, audit=audit, region=region, count_sql=count_sql)


def install(c):
    """عمود واحد، آمن للتكرار، ولا يمسّ البيانات القديمة."""
    try: c.execute("ALTER TABLE delivery_orders ADD COLUMN origin_type TEXT")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower(): raise


def settings(c):
    g = lambda k: (c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone() or [None])[0]
    try: comm = max(0.0, float(g("provider_delivery_commission") or 0))
    except (TypeError, ValueError): comm = 0.0
    return str(g("provider_delivery_enabled") or "0") == "1", comm


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. h = معالج السيرفر (send/body). الأخطاء تُرجَع مباشرة عبر h.send."""
    if path not in ("/api/provider/delivery-request", "/api/provider/delivery-requests", "/api/admin/provider-delivery"): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    if path == "/api/admin/provider-delivery":
        if method not in ("GET", "POST"): return False
        if not u: return err(401, "سجّل الدخول أولًا")
        if u["role"] != "admin": return err(403, "ليس لديك صلاحية")
        if method == "GET":
            on, comm = settings(c); h.send(200, {"enabled": on, "commission": comm}); return True
        d = h.body(); en = d.get("enabled")
        if not isinstance(en, bool): return err(400, "قيمة التفعيل غير صالحة")
        try: comm = round(float(d.get("commission", 0) or 0), 2)
        except (TypeError, ValueError): return err(400, "قيمة العمولة غير صالحة")
        if not (0 <= comm <= 100000): return err(400, "قيمة العمولة غير صالحة")  # يرفض NaN/inf/سالب
        for k, x in (("provider_delivery_enabled", "1" if en else "0"), ("provider_delivery_commission", str(comm))):
            c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, x))
        _H["audit"](c, u["id"], "settings.provider_delivery", None, {"enabled": en, "commission": comm}); c.commit()
        h.send(200, {"enabled": en, "commission": comm}); return True
    if (method, path) not in (("POST", "/api/provider/delivery-request"), ("GET", "/api/provider/delivery-requests")): return False
    if not u: return err(401, "سجّل الدخول أولًا")
    pv = c.execute("SELECT * FROM providers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone()
    if not pv: return err(403, "حساب الصيدلية غير معتمد")
    on, comm = settings(c)
    if method == "GET":
        rows = [dict(r) for r in c.execute(
            "SELECT o.id,o.status,o.dropoff_text,o.created_at,o.updated_at,CASE WHEN o.status IN " + ACTIVE + " THEN cu.name END courier_name,"
            "CASE WHEN o.status IN " + ACTIVE + " THEN cu.phone END courier_phone,"
            "(SELECT MIN(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='assigned') accepted_at,"
            "(SELECT MAX(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='completed') picked_at "
            "FROM delivery_orders o LEFT JOIN users cu ON cu.id=o.courier_id WHERE o.customer_id=? AND o.origin_type=? ORDER BY o.id DESC LIMIT 20", (u["id"], KIND))]
        h.send(200, {"enabled": on, "items": rows}); return True
    # POST: ضغطة واحدة — بلا أجرة ولا تفاصيل؛ عنوان العميل اختياري
    if not on: return err(403, "طلب المندوب من الصيدلية غير مفعّل حاليًا")
    d = h.body(); rid = pv["region_id"]
    if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone(): rid = _H["region"](c)
    if not rid: return err(400, "الدليفري غير متاح حاليًا")
    rk = str(d.get("request_key", "")).strip()[:64] or None  # مفتاح من الواجهة لكل ضغطة: الضغط المزدوج أو إعادة المحاولة يرجعان نفس الطلب
    if rk:
        dup = c.execute("SELECT id,status FROM delivery_orders WHERE customer_id=? AND request_key=?", (u["id"], rk)).fetchone()
        if dup: h.send(200, {"id": dup["id"], "status": dup["status"], "duplicate": True}); return True
    if c.execute(_H["count_sql"], (u["id"],)).fetchone()[0] >= MAX_OPEN: return err(429, "لديك طلبات مندوب مفتوحة كثيرة، انتظر أو ألغِ بعضها أولًا")
    dr = str(d.get("dropoff_text", "")).strip()[:300]; now = int(time.time())
    pk = ("صيدلية " + pv["name_ar"] + (" — " + pv["address"] if pv["address"] else ""))[:300]
    cur = c.execute("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,details,fee,commission,created_at,updated_at,search_started_at,delivery_code,request_key,fare_status,origin_type,comm_type,comm_value) VALUES(?,?,?,?,?,0,?,?,?,?,?,?,'approved',?,'fixed',?)",
                    (u["id"], rid, pk, dr, "طلب استلام من صيدلية", comm, now, now, now, "%06d" % secrets.randbelow(10 ** 6), rk, KIND, comm))
    oid = cur.lastrowid
    c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, u["id"], None, "searching", now))
    _H["audit"](c, u["id"], "provider.delivery_request", str(oid)); c.commit(); _H["push"](oid)
    h.send(201, {"id": oid, "status": "searching"}); return True
