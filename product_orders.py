# لاقينو — المرحلة 87: «اطلب من الصيدلية مباشرة» لقسم المنتجات. وحدة مستقلة بنمط shop_delivery.py: لا تستورد server.py (ما تحتاجه يمرّره server.bind).
# الدورة: العميل يختار منتجات صيدلية واحدة (عروض منشورة ومتوفرة) + كمية + عنوان ← طلب «جديد» عند الصيدلية (لا مندوب بعد)
#   ← الصيدلية «تقبل» فيتحوّل الطلب تلقائيًا لطلب توصيل عادي (origin_type='product_order') يبحث له النظام عن مندوب ← «جاهز للاستلام» ← المندوب يستلم ويسلّم بدورة الطلب العادي كاملة
#   (أجرة المندوب تُقترح وتُوافق عليها، رمز التسليم، التأكيد، التقييم). أو «تعتذر» (قبل أو بعد القبول وقبل استلام المندوب) فيُلغى الطلب ويُشعَر العميل.
# لماذا الصيدلية أولًا (بخلاف المحلات): منتج قد يكون نفد من الرف، فلا نُرسل مندوبًا قبل تأكيد الصيدلية. ثمن المنتجات لا يمر على النظام (لا مدفوعات في المشروع): يُحاسَب بين العميل والصيدلية.
# الأسعار لقطة وقت الطلب. الصيدلية لا ترى عنوان العميل ولا هاتفه (المندوب فقط بعد القبول، كباقي الطلبات).
# جدول واحد product_orders (إضافة فقط؛ لا تعديل على جداول قائمة). يعمل فقط حين تكون المنتجات مفعّلة (settings.products_enabled) كما تقرّر الإدارة.
# المسارات:
#   عميل:     POST /api/medical/pharmacies/<id>/order | GET /api/my/product-orders | POST /api/my/product-orders/<id>/cancel
#   صيدلية:   GET /api/provider/product-orders | POST /api/provider/product-orders/<id>/(accept|ready|reject)
import re, json, time, secrets, sqlite3
import notif, products, shops

ORIGIN = "product_order"  # قيمة delivery_orders.origin_type
MAX_LINES, MAX_QTY, MAX_PER_HOUR, MAX_NEW = 20, 20, 10, 5
PRE_PICKUP = ("searching", "assigned", "heading_pickup")  # المراحل اللي ينفع فيها للصيدلية تقبل/تجهّز/تعتذر (قبل ما المندوب يستلم)
PRE_PICKUP_SQL = "('searching','assigned','heading_pickup')"
push_hook = None  # server.py يضبطها: توقظ الصيدلية عند طلب منتجات جديد
customer_push_hook = None  # server.py يضبطها: توقظ العميل عند قبول/تجهيز/رفض طلبه
_H = {}
SCHEMA = """
CREATE TABLE IF NOT EXISTS product_orders(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES users(id), provider_id INTEGER NOT NULL REFERENCES providers(user_id),
 items_json TEXT NOT NULL, items_total REAL NOT NULL, note TEXT, dropoff_text TEXT NOT NULL, dropoff_lat REAL, dropoff_lng REAL, request_key TEXT,
 status TEXT NOT NULL DEFAULT 'new' CHECK(status IN('new','accepted','ready','rejected','cancelled')), reject_reason TEXT,
 order_id INTEGER REFERENCES delivery_orders(id), created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, accepted_at INTEGER, ready_at INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS ux_po_key ON product_orders(customer_id,request_key) WHERE request_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_po_prov ON product_orders(provider_id,status,id);
CREATE INDEX IF NOT EXISTS ix_po_cust ON product_orders(customer_id,id);
CREATE INDEX IF NOT EXISTS ix_po_order ON product_orders(order_id);
"""


def _push_customer(uid):
    if callable(customer_push_hook):
        try: customer_push_hook(int(uid))
        except Exception: pass  # الإيقاظ best-effort ولا يُفشل تحديث الطلب


def bind(push, push_stop, audit, region_fee, commission_for, count_sql, cust_limit):
    """يُستدعى من server.init: دفع الطلب للمناديب، إيقاف تكرار الدفع، سجل التدقيق، أجرة المنطقة، حساب العمولة، عدّ طلبات العميل المفتوحة، سقفها."""
    _H.update(push=push, push_stop=push_stop, audit=audit, region_fee=region_fee, commission_for=commission_for, count_sql=count_sql, cust_limit=cust_limit)


def install(c):
    """الجدول + إشعارات (triggers بادئة ntf_po_ فتُحذف مع الإشعارات إن أُزيلت): للصيدلية عند طلب جديد، وللعميل عند القبول/الجاهزية/الاعتذار. آمن للتكرار."""
    c.executescript(SCHEMA)
    for (n,) in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'ntf_po_%'").fetchall(): c.execute("DROP TRIGGER IF EXISTS " + n)
    new = notif._ins("NEW.provider_id", "provider.product_order", "طلب منتجات جديد من عميل", body="'طلب رقم ' || NEW.id", link="pharmacy", ref_type="product_order", ref_id="NEW.id")
    stage = notif._ins("NEW.customer_id", "product_order.stage", "CASE NEW.status WHEN 'accepted' THEN 'الصيدلية قبلت طلبك' WHEN 'ready' THEN 'طلبك جاهز للاستلام من الصيدلية' ELSE 'الصيدلية اعتذرت عن طلبك' END",
                       body="COALESCE(NEW.reject_reason, 'طلب رقم ' || NEW.id)", link="orders", ref_type="product_order", ref_id="NEW.id")
    c.execute("CREATE TRIGGER ntf_po_new AFTER INSERT ON product_orders BEGIN %s END" % new)
    c.execute("CREATE TRIGGER ntf_po_stage AFTER UPDATE OF status ON product_orders WHEN OLD.status IS NOT NEW.status AND NEW.status IN ('accepted','ready','rejected') BEGIN %s END" % stage)
    c.commit()


def _int(v):
    return None if isinstance(v, bool) or not isinstance(v, int) else v


def _view(r):
    try: its = json.loads(r["items_json"] or "[]")
    except ValueError: its = []
    return [{"offer_id": i.get("id"), "name": i.get("name"), "price": i.get("price"), "qty": i.get("qty"), "line_total": round(float(i.get("price") or 0) * int(i.get("qty") or 0), 2)} for i in its if isinstance(i, dict)]


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. h = معالج السيرفر (send/body). الأخطاء تُرجَع مباشرة عبر h.send."""
    mc = re.fullmatch(r"/api/medical/pharmacies/(\d{1,9})/order", path)
    mm = re.fullmatch(r"/api/my/product-orders(?:/(\d{1,9})/cancel)?", path)
    mp = re.fullmatch(r"/api/provider/product-orders(?:/(\d{1,9})/(accept|ready|reject))?", path)
    if not (mc or mm or mp): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    ok = lambda obj, code=200: (h.send(code, obj), True)[1]
    if not u: return err(401, "سجّل الدخول أولًا")
    audit = lambda act, tgt, det=None: _H["audit"](c, u["id"], act, tgt, det)
    now = int(time.time())

    # ---- العميل: طلب من صيدلية
    if mc:
        if method != "POST": return False
        pid = int(mc[1])
        if not products.enabled(c): return err(403, "الطلب من الصيدليات غير مفعّل حاليًا")
        pv = c.execute("SELECT user_id,name_ar,address,region_id FROM providers WHERE user_id=? AND status='approved'", (pid,)).fetchone()
        if not pv or not shops.region_ok(c, pv["region_id"]): return err(404, "الصيدلية غير موجودة")
        if pid == u["id"]: return err(403, "لا يمكنك الطلب من صيدليتك")
        d = h.body(); raw = d.get("items")
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_LINES: return err(400, "اختر من 1 إلى %d منتجات" % MAX_LINES)
        want = {}
        for x in raw:
            iid, qty = (_int(x.get("offer_id")), _int(x.get("qty"))) if isinstance(x, dict) else (None, None)
            if iid is None or qty is None or not 1 <= iid <= 10 ** 12 or not 1 <= qty <= MAX_QTY or iid in want: return err(400, "قائمة المنتجات غير صالحة (الكمية من 1 إلى %d بلا تكرار منتج)" % MAX_QTY)
            want[iid] = qty
        rows = {r["id"]: r for r in c.execute("SELECT id,title,price,available,confirmed_at,category_id FROM product_offers WHERE provider_id=? AND status='approved' AND id IN (%s)" % ",".join("?" * len(want)), (pid, *want))}
        if len(rows) != len(want): return err(400, "منتج غير موجود عند هذه الصيدلية")
        cut = products._fresh_cut(c)
        for iid in want:  # نفس شروط ظهور العرض للعملاء: متوفر + حديث التأكيد + تصنيف ظاهر
            r = rows[iid]
            if not r["available"] or r["confirmed_at"] <= cut or not products.market.is_visible_category(c, r["category_id"]): return err(409, "المنتج «%s» غير متاح حاليًا" % r["title"])
        lines = [{"id": i, "name": rows[i]["title"], "price": rows[i]["price"], "qty": want[i]} for i in want]
        total = round(sum(x["price"] * x["qty"] for x in lines), 2)
        dr = re.sub(r"\s+", " ", str(d.get("dropoff_text") or "")).strip()
        if len(dr) < 3: return err(400, "عنوان التسليم مطلوب")
        try: dla, dln = shops._geo({"lat": d.get("dropoff_lat"), "lng": d.get("dropoff_lng")})
        except ValueError as e: return err(400, str(e))
        note = re.sub(r"\s+", " ", str(d.get("note") or "")).strip()[:300]
        if not _H["region_fee"](c, pv["region_id"]): return err(400, "الدليفري غير متاح في منطقة الصيدلية")
        rk = str(d.get("request_key", "")).strip()[:64] or None
        if rk:
            dup = c.execute("SELECT id,status FROM product_orders WHERE customer_id=? AND request_key=?", (u["id"], rk)).fetchone()
            if dup: return ok({"id": dup["id"], "status": dup["status"], "duplicate": True})
        if c.execute("SELECT COUNT(*) FROM product_orders WHERE customer_id=? AND created_at>?", (u["id"], now - 3600)).fetchone()[0] >= MAX_PER_HOUR: return err(429, "طلبات كثيرة من الصيدليات في ساعة، حاول لاحقًا")
        if c.execute("SELECT COUNT(*) FROM product_orders WHERE customer_id=? AND status='new'", (u["id"],)).fetchone()[0] >= MAX_NEW: return err(429, "لديك طلبات كثيرة بانتظار رد الصيدليات، انتظر الرد أو ألغِ بعضها أولًا")
        if c.execute(_H["count_sql"], (u["id"],)).fetchone()[0] >= _H["cust_limit"]: return err(429, "لديك طلبات توصيل مفتوحة كثيرة، أكمل أو ألغِ بعضها أولًا")
        try:
            cur = c.execute("INSERT INTO product_orders(customer_id,provider_id,items_json,items_total,note,dropoff_text,dropoff_lat,dropoff_lng,request_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (u["id"], pid, json.dumps(lines, ensure_ascii=False), total, note or None, dr[:300], dla, dln, rk, now, now))
        except sqlite3.IntegrityError:  # سباق مفتاح الطلب المكرر ← نُرجع الأول
            c.rollback(); dup = c.execute("SELECT id,status FROM product_orders WHERE customer_id=? AND request_key=?", (u["id"], rk)).fetchone()
            if dup: return ok({"id": dup["id"], "status": dup["status"], "duplicate": True})
            raise
        audit("product_order.create", str(cur.lastrowid), {"pharmacy": pid, "total": total}); c.commit()
        if push_hook:
            try: push_hook(pid)
            except Exception: pass  # الإيقاظ لا يُفشل الطلب أبدًا
        return ok({"id": cur.lastrowid, "status": "new", "items_total": total}, 201)

    # ---- العميل: طلباتي من الصيدليات (قبل التحويل لدليفري) + الإلغاء
    if mm:
        if mm[1]:
            if method != "POST": return False
            if not c.execute("UPDATE product_orders SET status='cancelled',updated_at=? WHERE id=? AND customer_id=? AND status='new'", (now, int(mm[1]), u["id"])).rowcount:
                return err(404, "الطلب غير موجود") if not c.execute("SELECT 1 FROM product_orders WHERE id=? AND customer_id=?", (int(mm[1]), u["id"])).fetchone() else err(409, "لا يمكن إلغاء الطلب بعد رد الصيدلية عليه")
            audit("product_order.cancel", mm[1]); c.commit(); return ok({"id": int(mm[1]), "status": "cancelled"})
        if method != "GET": return False
        # المقبولة صارت طلب توصيل يظهر في «طلباتي» بمراحله؛ هنا الجديدة والمعتذَر عنها والملغاة (آخر 3 أيام) فقط
        rows = [{"id": r["id"], "status": r["status"], "pharmacy": r["pharmacy"], "items": _view(r), "items_total": r["items_total"], "note": r["note"] or "", "reject_reason": r["reject_reason"] or "", "created_at": r["created_at"]}
                for r in c.execute("SELECT o.*,p.name_ar pharmacy FROM product_orders o JOIN providers p ON p.user_id=o.provider_id WHERE o.customer_id=? AND (o.status='new' OR (o.status IN ('rejected','cancelled') AND o.updated_at>?)) ORDER BY o.id DESC LIMIT 20", (u["id"], now - 3 * 86400))]
        return ok(rows)

    # ---- الصيدلية (معتمدة فقط)
    pv = c.execute("SELECT * FROM providers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone()
    if not pv: return err(403, "حساب الصيدلية غير معتمد")
    if not mp[1]:
        if method != "GET": return False
        rows = []
        for r in c.execute("SELECT o.*,d.status dstatus,CASE WHEN d.status IN ('assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation') THEN cu.name END courier_name,"
                           "CASE WHEN d.status IN ('assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation') THEN cu.phone END courier_phone "
                           "FROM product_orders o LEFT JOIN delivery_orders d ON d.id=o.order_id LEFT JOIN users cu ON cu.id=d.courier_id WHERE o.provider_id=? ORDER BY o.id DESC LIMIT 50", (u["id"],)):
            live = r["status"] in ("accepted", "ready") and r["dstatus"] in PRE_PICKUP
            rows.append({"id": r["id"], "status": r["status"], "created_at": r["created_at"], "items": _view(r), "items_total": r["items_total"], "note": r["note"] or "", "reject_reason": r["reject_reason"] or "",
                         "delivery_status": r["dstatus"], "courier_name": r["courier_name"], "courier_phone": r["courier_phone"],
                         "can_accept": r["status"] == "new", "can_ready": r["status"] == "accepted" and live, "can_reject": r["status"] == "new" or live})
        return ok(rows)
    if method != "POST": return False
    oid, act = int(mp[1]), mp[2]
    po = c.execute("SELECT * FROM product_orders WHERE id=? AND provider_id=?", (oid, u["id"])).fetchone()
    if not po: return err(404, "الطلب غير موجود")
    if act == "accept":  # الطلب يتحوّل هنا لطلب توصيل: أجرة المنطقة ثابتة من region_fees لمنطقة الصيدلية، والمندوب يقترح الأجرة ويوافق العميل عليها كباقي الطلبات
        if po["status"] != "new": return err(409, "تم الرد على هذا الطلب بالفعل")
        f = _H["region_fee"](c, pv["region_id"])
        if not f: return err(409, "الدليفري غير متاح في منطقة الصيدلية حاليًا")
        cm = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; ct, cv = cm.get("commission_type", "fixed"), float(cm.get("commission_value", 0))
        comm = _H["commission_for"](c, f["fee"], ct, cv); code = "%06d" % secrets.randbelow(10 ** 6)
        pk = ("صيدلية " + pv["name_ar"] + (" — " + pv["address"] if pv["address"] else ""))[:300]
        lines = json.loads(po["items_json"]); det = "\n".join("%d× %s" % (x["qty"], x["name"]) for x in lines) + ("\nملاحظة: " + po["note"] if po["note"] else "")
        if not c.execute("UPDATE product_orders SET status='accepted',accepted_at=?,updated_at=? WHERE id=? AND status='new'", (now, now, oid)).rowcount: return err(409, "تغيّرت حالة الطلب، حدّث الصفحة")  # القفل قبل إنشاء الطلب فلا يتكرر مع نقرتين
        cur = c.execute("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,details,fee,commission,created_at,updated_at,search_started_at,delivery_code,dropoff_lat,dropoff_lng,fare_status,origin_type,comm_type,comm_value) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'none',?,?,?)",
                        (po["customer_id"], pv["region_id"], pk, po["dropoff_text"], "", f["fee"], round(comm, 2), now, now, now, code, po["dropoff_lat"], po["dropoff_lng"], ORIGIN, ct, cv))
        did = cur.lastrowid
        c.execute("UPDATE delivery_orders SET details=? WHERE id=?", ("طلب منتجات من صيدلية %s — رقم الطلب %d\n%s" % (pv["name_ar"], did, det[:900]), did))
        c.execute("UPDATE product_orders SET order_id=? WHERE id=?", (did, oid))
        c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (did, po["customer_id"], None, "searching", now))
        audit("product_order.accept", str(oid), {"delivery_order": did}); c.commit(); _H["push"](did); _push_customer(po["customer_id"])
        return ok({"id": oid, "status": "accepted", "order_id": did})
    if act == "ready":
        if po["status"] == "new": return err(409, "اقبل الطلب أولًا")
        if po["status"] == "ready": return err(409, "الطلب مُعلَّم جاهزًا بالفعل")
        if po["status"] != "accepted": return err(409, "لا يمكن تغيير حالة الطلب الآن")
        if not c.execute("UPDATE product_orders SET status='ready',ready_at=?,updated_at=? WHERE id=? AND status='accepted' AND EXISTS(SELECT 1 FROM delivery_orders WHERE id=? AND status IN %s)" % PRE_PICKUP_SQL, (now, now, oid, po["order_id"])).rowcount:
            return err(409, "لا يمكن تغيير حالة الطلب بعد استلام المندوب له أو إغلاقه")
        audit("product_order.ready", str(oid)); c.commit(); _push_customer(po["customer_id"]); return ok({"id": oid, "status": "ready"})
    # reject: «جديد» ← يُرفض بلا دليفري؛ «مقبول/جاهز» ← يُلغى طلب التوصيل ما دام المندوب لم يستلم
    reason = re.sub(r"\s+", " ", str((h.body() or {}).get("reason") or "")).strip()[:200] or None
    if po["status"] == "new":
        if not c.execute("UPDATE product_orders SET status='rejected',reject_reason=?,updated_at=? WHERE id=? AND status='new'", (reason, now, oid)).rowcount: return err(409, "تغيّرت حالة الطلب، حدّث الصفحة")
        audit("product_order.reject", str(oid)); c.commit(); _push_customer(po["customer_id"]); return ok({"id": oid, "status": "rejected"})
    if po["status"] not in ("accepted", "ready"): return err(409, "لا يمكن رفض الطلب في حالته الحالية")
    d = c.execute("SELECT status FROM delivery_orders WHERE id=?", (po["order_id"],)).fetchone()
    if not d or not c.execute("UPDATE delivery_orders SET status='cancelled',updated_at=? WHERE id=? AND status IN %s" % PRE_PICKUP_SQL, (now, po["order_id"])).rowcount: return err(409, "لا يمكن رفض الطلب بعد استلام المندوب له أو إغلاقه")
    c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (po["order_id"], u["id"], d["status"], "cancelled", now))
    c.execute("UPDATE product_orders SET status='rejected',reject_reason=?,updated_at=? WHERE id=?", (reason, now, oid))
    audit("product_order.reject", str(oid), {"delivery_order": po["order_id"]}); c.commit(); _H["push_stop"](po["order_id"]); _push_customer(po["customer_id"])
    return ok({"id": oid, "status": "rejected"})
