# لاقينو — سعّر روشتتك (المرحلة 3). وحدة مستقلة بنمط notif.py/products.py: لا تستورد server.py.
# تبني فوق التدفق القائم (prescriptions / prescription_access / prescription_responses / medical_delivery_links) دون تغيير جداوله.
# الجديد:
#   صيدلية:   GET|POST /api/provider/prescriptions/<id>/quote   (تسعيرة ببنود: اسم + كمية + سعر الوحدة + متوفر؟)
#   عميل:     GET /api/medical/prescriptions/<id>/quotes          (مقارنة الأسعار، الأرخص أولًا)
#             POST /api/medical/prescriptions/<id>/close          (إغلاق الروشتة وسحب صلاحية الصيدليات غير المرتبطة بطلب توصيل)
#   إدارة:    POST /api/admin/prescriptions/<id>/forward-many     {provider_ids:[..]} أو {auto:true} (صيدليات المنطقة المعتمدة)
#             GET|POST /api/admin/rx/auto-forward                 {enabled} — تحويل تلقائي عند رفع الروشتة (افتراضيًا مغلق: قرار الإدارة)
# السعر الإجمالي يُكتب في prescription_responses.price كما كان، فيبقى طلب التوصيل والإشعارات القائمة تعمل بلا تعديل.
# لا تُرجع أي رقم هاتف أبدًا. إضافة فقط: جدول rx_quote_items.
# الخطوة 4 (الروشتات):
#   • صور متعددة (حتى MAX_IMAGES): جدول rx_images؛ prescriptions.file_id يبقى الصورة الأولى (غلاف) فلا ينكسر أي كود قديم.
#   • اعتماد الإدارة للردود: عمود prescription_responses.review (pending|approved|rejected). الردود القديمة تُعتمد مرة واحدة عند الترحيل،
#     وأي إدخال/تعديل جديد يجعلها pending بـtrigger (فيغطي مسار الرد القديم /respond ومسار التسعيرة). العميل لا يرى ولا يطلب توصيلًا من رد غير معتمد.
#   • من استلم ومن فتح ومن رد: جدول rx_seen + GET /api/admin/rx/tracking (إدارة) وحقل pharmacies في /quotes (عميل، أسماء بلا هواتف).
#   • مرحلة الطلب stage: review → at_pharmacies → quoted → closed (تُحسب ولا تُخزَّن، فلا تعارض مع CHECK على prescriptions.status).
#   إدارة: GET /api/admin/rx/responses?review=pending|rejected|approved ، POST /api/admin/rx/responses/<rx>/<provider>/review {decision:approve|reject, reason}
import re, json, time
import gsearch

MAX_ITEMS, MAX_QTY, MAX_UNIT, MAX_TOTAL, MAX_AUTO, MAX_MANY = 30, 99, 100_000, 1_000_000, 8, 10
MAX_IMAGES = 3  # صور الروشتة الواحدة
EXPIRE_DAYS_DEFAULT = 14  # روشتة أقدم من ذلك لا تقبل تسعيرات جديدة (settings.rx_expire_days اختياري)
STOCK_FRESH_HOURS_DEFAULT = 24  # نفس مفتاح server.py: stock_fresh_hours
SCHEMA = """
CREATE TABLE IF NOT EXISTS rx_quote_items(prescription_id INTEGER NOT NULL REFERENCES prescriptions(id), provider_id INTEGER NOT NULL REFERENCES providers(user_id),
 line_no INTEGER NOT NULL, name TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 1, unit_price REAL, available INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(prescription_id,provider_id,line_no));
CREATE TABLE IF NOT EXISTS rx_images(prescription_id INTEGER NOT NULL REFERENCES prescriptions(id), file_id INTEGER NOT NULL UNIQUE REFERENCES files(id), pos INTEGER NOT NULL, PRIMARY KEY(prescription_id,pos));
CREATE TABLE IF NOT EXISTS rx_seen(prescription_id INTEGER NOT NULL REFERENCES prescriptions(id), provider_id INTEGER NOT NULL REFERENCES providers(user_id), seen_at INTEGER NOT NULL, PRIMARY KEY(prescription_id,provider_id));
"""


# أي إدخال أو تعديل على رد الصيدلية يعيده «بانتظار الاعتماد» ويُشعِر الإدارة. تحديث review نفسه لا يطلق الـtrigger (يخص أعمدة الرد فقط).
# البادئة ntf_ مقصودة: notif.uninstall() يحذف كل ntf_* مع جدول notifications فلا يبقى trigger يشير لجدول غير موجود.
# والعمود DEFAULT 'pending' (مغلق افتراضيًا): لو غاب الـtrigger لأي سبب يبقى الرد الجديد غير ظاهر للعميل حتى تعتمده الإدارة.
_TRIGGERS = (
    "DROP TRIGGER IF EXISTS ntf_rxresp_ins", "DROP TRIGGER IF EXISTS ntf_rxresp_upd",
    """CREATE TRIGGER ntf_rxresp_ins AFTER INSERT ON prescription_responses BEGIN
 UPDATE prescription_responses SET review='pending',review_reason=NULL,reviewed_at=NULL,reviewed_by=NULL WHERE prescription_id=NEW.prescription_id AND provider_id=NEW.provider_id;
 INSERT INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) SELECT id,'admin.rx_response','رد صيدلية على روشتة بانتظار الاعتماد','روشتة #'||NEW.prescription_id,'admin:rx','prescription',NEW.prescription_id,strftime('%s','now') FROM users WHERE role IN('admin','staff');
END""",
    """CREATE TRIGGER ntf_rxresp_upd AFTER UPDATE OF status,price,note,updated_at ON prescription_responses BEGIN
 UPDATE prescription_responses SET review='pending',review_reason=NULL,reviewed_at=NULL,reviewed_by=NULL WHERE prescription_id=NEW.prescription_id AND provider_id=NEW.provider_id;
 INSERT INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) SELECT id,'admin.rx_response','رد صيدلية على روشتة بانتظار الاعتماد (تعديل)','روشتة #'||NEW.prescription_id,'admin:rx','prescription',NEW.prescription_id,strftime('%s','now') FROM users WHERE role IN('admin','staff');
END""")


def install(c):
    c.executescript(SCHEMA)
    have = [r[1] for r in c.execute("PRAGMA table_info(prescription_responses)")]
    # الردود الموجودة قبل الخطوة 4 تبقى ظاهرة للعميل (تُعتمد عند الترحيل): لا نحجب بيانات قائمة بأثر رجعي.
    first = "review" not in have
    for col, ddl in (("review", "TEXT NOT NULL DEFAULT 'pending'"), ("review_reason", "TEXT"), ("reviewed_at", "INTEGER"), ("reviewed_by", "INTEGER")):
        if col not in have: c.execute("ALTER TABLE prescription_responses ADD COLUMN %s %s" % (col, ddl))
    if first: c.execute("UPDATE prescription_responses SET review='approved'")  # مرة واحدة عند الترحيل
    for t in _TRIGGERS: c.execute(t)
    c.commit()


def _notify(c, user_id, kind, title, body, link, rx_id):
    """أي خطأ هنا لا يُفشل العملية الأساسية."""
    try:
        c.execute("INSERT INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?,?,?)", (user_id, kind, title, body, link, "prescription", rx_id, int(time.time())))
    except Exception as e:
        import sys; sys.stderr.write("rx notify failed: %r\n" % (e,))


def _phone_in(text):
    """8 أرقام متتالية فأكثر (بعد توحيد الأرقام العربية وإزالة الفواصل) تُعدّ رقم هاتف: التواصل يتم عبر المنصة فقط."""
    t = str(text or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    return bool(re.search(r"\d{8,}", re.sub(r"(?<=\d)[\s.\-_/]+(?=\d)", "", t)))


def images_of(c, rx_id):
    """معرّفات صور الروشتة بالترتيب. روشتة قديمة بلا rx_images = صورتها الوحيدة file_id."""
    ids = [r[0] for r in c.execute("SELECT file_id FROM rx_images WHERE prescription_id=? ORDER BY pos", (rx_id,))]
    if ids: return ids
    r = c.execute("SELECT file_id FROM prescriptions WHERE id=?", (rx_id,)).fetchone()
    return [r[0]] if r and r[0] else []


def set_images(c, rx_id, file_ids):
    """يكتب الصور (الأولى = الغلاف prescriptions.file_id). لا commit."""
    c.execute("DELETE FROM rx_images WHERE prescription_id=?", (rx_id,))
    c.executemany("INSERT INTO rx_images VALUES(?,?,?)", [(rx_id, f, i) for i, f in enumerate(file_ids, 1)])
    c.execute("UPDATE prescriptions SET file_id=? WHERE id=?", (file_ids[0] if file_ids else None, rx_id))


def remove_image(c, file_id):
    """يُستدعى قبل حذف ملف: يرجع True إن عولج (الصورة من روشتة فيها صور أخرى فلا تُغلق)، False إن لم تكن في rx_images أو كانت الوحيدة."""
    r = c.execute("SELECT prescription_id FROM rx_images WHERE file_id=?", (file_id,)).fetchone()
    if not r: return False
    rid = r[0]; rest = [f for f in images_of(c, rid) if f != file_id]
    c.execute("DELETE FROM rx_images WHERE file_id=?", (file_id,))
    if not rest: return False
    c.execute("DELETE FROM rx_images WHERE prescription_id=?", (rid,))
    c.executemany("INSERT INTO rx_images VALUES(?,?,?)", [(rid, f, i) for i, f in enumerate(rest, 1)])
    c.execute("UPDATE prescriptions SET file_id=? WHERE id=?", (rest[0], rid))
    return True


def mark_seen_by_file(c, user_id, file_id):
    """صيدلية فتحت صورة روشتة مخوَّلة بها = «اطّلعت». لا يفشل أبدًا."""
    try:
        c.execute("INSERT OR IGNORE INTO rx_seen SELECT p.id,a.provider_id,? FROM prescription_access a JOIN prescriptions p ON p.id=a.prescription_id "
                  "WHERE a.provider_id=? AND (p.file_id=? OR ? IN (SELECT file_id FROM rx_images WHERE prescription_id=p.id))", (int(time.time()), user_id, file_id, file_id))
    except Exception: pass


def stage_of(c, rx_id, status):
    if status == "closed": return "closed"
    if status == "pending": return "review"
    n = c.execute("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=? AND review='approved'", (rx_id,)).fetchone()[0]
    return "quoted" if n else "at_pharmacies"


def tracking(c, rx_id):
    """لكل صيدلية خوّلتها الإدارة: استلمت (دائمًا) ← اطّلعت (seen_at) ← ردّت (status/review). بلا هواتف."""
    out = []
    for r in c.execute("SELECT a.provider_id,p.name_ar pharmacy,s.seen_at,x.status resp_status,x.price,x.review,x.review_reason,x.updated_at FROM prescription_access a JOIN providers p ON p.user_id=a.provider_id "
                       "LEFT JOIN rx_seen s ON s.prescription_id=a.prescription_id AND s.provider_id=a.provider_id LEFT JOIN prescription_responses x ON x.prescription_id=a.prescription_id AND x.provider_id=a.provider_id "
                       "WHERE a.prescription_id=? ORDER BY p.name_ar", (rx_id,)):
        out.append(dict(r))
    return out


def _setting(c, key, default):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    try: return float(r["value"]) if r else float(default)
    except (TypeError, ValueError): return float(default)


def _clean_items(raw):
    """يتحقق من بنود التسعيرة ويحسب الإجمالي. يرفع ValueError برسالة عربية."""
    if not isinstance(raw, list) or not raw: raise ValueError("أضف بندًا واحدًا على الأقل")
    if len(raw) > MAX_ITEMS: raise ValueError("الحد الأقصى %d بندًا" % MAX_ITEMS)
    out, total = [], 0.0
    for i, it in enumerate(raw, 1):
        if not isinstance(it, dict): raise ValueError("بند غير صالح")
        name = str(it.get("name") or "").strip()
        if not 2 <= len(name) <= 80: raise ValueError("اسم البند %d مطلوب (2-80 حرفًا)" % i)
        av = it.get("available", True)
        if isinstance(av, str): av = av.strip().lower() not in ("0", "false", "no", "")
        av = bool(av)
        q = it.get("qty", 1)
        if isinstance(q, bool): raise ValueError("كمية البند %d غير صالحة" % i)
        try: q = int(q)
        except (TypeError, ValueError): raise ValueError("كمية البند %d غير صالحة" % i)
        if not 1 <= q <= MAX_QTY: raise ValueError("كمية البند %d بين 1 و%d" % (i, MAX_QTY))
        up = None
        if av:
            v = it.get("unit_price")
            if isinstance(v, bool): raise ValueError("سعر البند %d غير صالح" % i)
            try: up = float(v)
            except (TypeError, ValueError): raise ValueError("أدخل سعر البند %d" % i)
            if not (0 < up <= MAX_UNIT) or up != up: raise ValueError("سعر البند %d غير صالح" % i)
            up = round(up, 2); total += up * q
        out.append({"line_no": i, "name": name, "qty": q, "unit_price": up, "available": 1 if av else 0})
    return out, round(total, 2)


def _status_for(items):
    n_av = sum(1 for i in items if i["available"])
    if n_av == len(items): return "available"
    return "needs_confirmation" if n_av else "unavailable"  # جزئي → لا يُفتح له طلب توصيل (يشترط server.py حالة available)


def forward(c, rx_id, provider_ids):
    """يمنح الصيدليات المعتمدة صلاحية رؤية الروشتة. يرجع عدد من أُضيف فعلًا (الجدد فقط)."""
    n = 0
    for pid in provider_ids:
        if not c.execute("SELECT 1 FROM providers WHERE user_id=? AND status='approved'", (pid,)).fetchone(): continue
        n += c.execute("INSERT OR IGNORE INTO prescription_access VALUES(?,?)", (rx_id, pid)).rowcount
    if provider_ids: c.execute("UPDATE prescriptions SET status='forwarded' WHERE id=? AND status='pending'", (rx_id,))
    return n


def _region_pharmacies(c, region_id, limit=MAX_AUTO):
    rel = gsearch._related(c, region_id)
    return [r[0] for r in c.execute("SELECT user_id FROM providers WHERE status='approved' AND region_id IN (%s) ORDER BY user_id LIMIT ?" % ",".join("?" * len(rel)), (*rel, limit))]


def auto_forward(c, rx_id):
    """تُستدعى من server.py بعد إنشاء الروشتة. لا تفعل شيئًا إلا إن فعّلت الإدارة rx_auto_forward=1. لا تُفشل إنشاء الروشتة أبدًا."""
    try:
        if _setting(c, "rx_auto_forward", 0) != 1: return 0
        r = c.execute("SELECT region_id FROM prescriptions WHERE id=? AND file_id IS NOT NULL AND status='pending'", (rx_id,)).fetchone()
        if not r: return 0
        n = forward(c, rx_id, _region_pharmacies(c, r["region_id"])); c.commit(); return n
    except Exception: return 0


def quotes_for(c, rx_id, approved_only=True):
    """تسعيرات الروشتة المعتمدة من الإدارة فقط (ما لم يُطلب غير ذلك) مرتبة: كاملة متوفرة (الأرخص أولًا) ← جزئية ← غير متوفر/يحتاج تأكيد. بلا هواتف."""
    fresh_cut = time.time() - _setting(c, "stock_fresh_hours", STOCK_FRESH_HOURS_DEFAULT) * 3600
    rows = c.execute("SELECT x.provider_id,p.name_ar pharmacy,p.address,g.name_ar region_name,x.status,x.price,x.note,x.updated_at,"
                     "(SELECT d.order_id FROM medical_delivery_links d JOIN delivery_orders o ON o.id=d.order_id WHERE d.source_type='prescription' AND d.source_id=x.prescription_id AND d.provider_id=x.provider_id AND o.status!='cancelled' ORDER BY d.order_id DESC LIMIT 1) delivery_order_id "
                     "FROM prescription_responses x JOIN providers p ON p.user_id=x.provider_id JOIN regions g ON g.id=p.region_id WHERE x.prescription_id=? AND p.status='approved'" + (" AND x.review='approved'" if approved_only else ""), (rx_id,)).fetchall()
    items = {}
    for i in c.execute("SELECT provider_id,line_no,name,qty,unit_price,available FROM rx_quote_items WHERE prescription_id=? ORDER BY provider_id,line_no", (rx_id,)):
        items.setdefault(i["provider_id"], []).append({"name": i["name"], "qty": i["qty"], "unit_price": i["unit_price"], "available": bool(i["available"])})
    out = []
    for r in rows:
        d = dict(r); d["items"] = items.get(r["provider_id"], []); d["fresh"] = r["updated_at"] > fresh_cut
        d["complete"] = r["status"] == "available"
        d["partial"] = r["status"] == "needs_confirmation" and any(i["available"] for i in d["items"])
        d["missing"] = [i["name"] for i in d["items"] if not i["available"]]
        out.append(d)
    rank = lambda d: (0 if d["complete"] and d["fresh"] else 1 if d["complete"] else 2 if d["partial"] else 3, d["price"] if d["price"] is not None else 0, -d["updated_at"])
    out.sort(key=rank)
    best = next((d for d in out if d["complete"] and d["fresh"] and d["price"]), None)
    for d in out: d["cheapest"] = d is best
    return out


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. الأخطاء تُرجَع مباشرة عبر h.send."""
    if not path.startswith(("/api/provider/prescriptions/", "/api/medical/prescriptions/", "/api/admin/prescriptions/", "/api/admin/rx/")): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    now = int(time.time())

    # ---------- صيدلية ----------
    m = re.fullmatch(r"/api/provider/prescriptions/(\d+)/quote", path)
    if m:
        if not u: return err(401, "سجّل الدخول أولًا")
        if not c.execute("SELECT 1 FROM providers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone(): return err(403, "حساب الصيدلية غير معتمد")
        rid = int(m[1])
        rx = c.execute("SELECT p.id,p.status,p.created_at,p.file_id FROM prescription_access a JOIN prescriptions p ON p.id=a.prescription_id WHERE a.prescription_id=? AND a.provider_id=?", (rid, u["id"])).fetchone()
        if not rx or rx["status"] == "closed" or rx["file_id"] is None: return err(404, "غير موجود")
        if method == "GET":
            its = [dict(i) for i in c.execute("SELECT name,qty,unit_price,available FROM rx_quote_items WHERE prescription_id=? AND provider_id=? ORDER BY line_no", (rid, u["id"]))]
            r = c.execute("SELECT status,price,note,updated_at,review,review_reason FROM prescription_responses WHERE prescription_id=? AND provider_id=?", (rid, u["id"])).fetchone()
            c.execute("INSERT OR IGNORE INTO rx_seen VALUES(?,?,?)", (rid, u["id"], now)); c.commit()
            h.send(200, {"items": its, "response": dict(r) if r else None, "images": images_of(c, rid)}); return True
        if method == "POST":
            if rx["created_at"] < now - _setting(c, "rx_expire_days", EXPIRE_DAYS_DEFAULT) * 86400: return err(409, "انتهت صلاحية هذه الروشتة")
            d = h.body()
            try: items, total = _clean_items(d.get("items"))
            except ValueError as e: return err(400, str(e))
            if total > MAX_TOTAL: return err(400, "الإجمالي كبير جدًا")
            st = _status_for(items); note = str(d.get("note") or "")[:300]
            if _phone_in(note) or any(_phone_in(i["name"]) for i in items): return err(400, "ممنوع كتابة أرقام هاتف في التسعيرة، التواصل يتم عبر لاقينو")
            c.execute("INSERT INTO prescription_responses(prescription_id,provider_id,status,price,note,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(prescription_id,provider_id) DO UPDATE SET status=excluded.status,price=excluded.price,note=excluded.note,updated_at=excluded.updated_at",
                      (rid, u["id"], st, total if st != "unavailable" else None, note, now))
            c.execute("DELETE FROM rx_quote_items WHERE prescription_id=? AND provider_id=?", (rid, u["id"]))
            c.executemany("INSERT INTO rx_quote_items VALUES(?,?,?,?,?,?,?)", [(rid, u["id"], i["line_no"], i["name"], i["qty"], i["unit_price"], i["available"]) for i in items])
            c.execute("INSERT OR IGNORE INTO rx_seen VALUES(?,?,?)", (rid, u["id"], now))
            c.commit(); h.send(200, {"ok": True, "status": st, "total": total, "review": "pending"}); return True
        return err(404, "غير موجود")

    # ---------- عميل ----------
    m = re.fullmatch(r"/api/medical/prescriptions/(\d+)/(quotes|close)", path)
    if m:
        if not u: return err(401, "سجّل الدخول أولًا")
        rid = int(m[1])
        rx = c.execute("SELECT id,status,created_at FROM prescriptions WHERE id=? AND customer_id=?", (rid, u["id"])).fetchone()
        if not rx: return err(404, "غير موجود")
        if m[2] == "quotes" and method == "GET":
            pend = c.execute("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=? AND review='pending'", (rid,)).fetchone()[0]
            ph = [{"pharmacy": t["pharmacy"], "seen": t["seen_at"] is not None, "quoted": t["review"] == "approved"} for t in tracking(c, rid)]
            h.send(200, {"id": rid, "status": rx["status"], "stage": stage_of(c, rid, rx["status"]), "images": images_of(c, rid), "quotes": quotes_for(c, rid), "pending_review": pend, "pharmacies": ph}); return True
        if m[2] == "close" and method == "POST":
            if rx["status"] == "closed": return err(409, "الروشتة مغلقة بالفعل")
            c.execute("UPDATE prescriptions SET status='closed' WHERE id=?", (rid,))
            # تبقى الصلاحية فقط للصيدلية التي لها طلب توصيل غير ملغي (تحتاج الروشتة لتجهيز الطلب)
            c.execute("DELETE FROM prescription_access WHERE prescription_id=? AND provider_id NOT IN (SELECT d.provider_id FROM medical_delivery_links d JOIN delivery_orders o ON o.id=d.order_id WHERE d.source_type='prescription' AND d.source_id=? AND o.status!='cancelled')", (rid, rid))
            c.commit(); h.send(200, {"ok": True}); return True
        return err(404, "غير موجود")

    # ---------- إدارة ----------
    if path.startswith(("/api/admin/prescriptions/", "/api/admin/rx/")):
        if not u: return err(401, "سجّل الدخول أولًا")
        if u["role"] not in ("admin", "staff"): return err(403, "ليس لديك صلاحية")
        if path == "/api/admin/rx/auto-forward":
            if method == "GET": h.send(200, {"enabled": _setting(c, "rx_auto_forward", 0) == 1}); return True
            if method == "POST":
                if u["role"] != "admin": return err(403, "ليس لديك صلاحية")
                on = "1" if h.body().get("enabled") in (True, 1, "1", "true") else "0"
                c.execute("INSERT INTO settings(key,value) VALUES('rx_auto_forward',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (on,))
                c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "rx.auto_forward", on, None, now))
                c.commit(); h.send(200, {"ok": True, "enabled": on == "1"}); return True
        if path == "/api/admin/rx/responses" and method == "GET":
            rv = (q.get("review") or ["pending"])[0]
            if rv not in ("pending", "approved", "rejected"): return err(400, "حالة غير صالحة")
            rows = c.execute("SELECT x.prescription_id,x.provider_id,p.name_ar pharmacy,x.status,x.price,x.note,x.updated_at,x.review,x.review_reason FROM prescription_responses x JOIN providers p ON p.user_id=x.provider_id "
                             "JOIN prescriptions r ON r.id=x.prescription_id WHERE x.review=? AND r.status!='closed' ORDER BY x.updated_at LIMIT 100", (rv,)).fetchall()
            out = []
            for r in rows:
                d = dict(r); d["images"] = images_of(c, r["prescription_id"])
                d["items"] = [dict(i) for i in c.execute("SELECT name,qty,unit_price,available FROM rx_quote_items WHERE prescription_id=? AND provider_id=? ORDER BY line_no", (r["prescription_id"], r["provider_id"]))]
                out.append(d)
            h.send(200, out); return True
        m = re.fullmatch(r"/api/admin/rx/responses/(\d+)/(\d+)/review", path)
        if m and method == "POST":
            rid, pid = int(m[1]), int(m[2]); d = h.body(); dec = d.get("decision"); reason = str(d.get("reason") or "").strip()
            if dec not in ("approve", "reject"): return err(400, "القرار: approve أو reject")
            if dec == "reject" and not 5 <= len(reason) <= 300: return err(400, "سبب الرفض مطلوب (5 إلى 300 حرف) ويظهر للصيدلية")
            rr = c.execute("SELECT x.review,r.customer_id,r.status FROM prescription_responses x JOIN prescriptions r ON r.id=x.prescription_id WHERE x.prescription_id=? AND x.provider_id=?", (rid, pid)).fetchone()
            if not rr: return err(404, "غير موجود")
            if rr["status"] == "closed": return err(409, "الروشتة مغلقة")
            new = "approved" if dec == "approve" else "rejected"
            if rr["review"] == new: return err(409, "القرار نفسه مسجَّل بالفعل")
            c.execute("UPDATE prescription_responses SET review=?,review_reason=?,reviewed_at=?,reviewed_by=? WHERE prescription_id=? AND provider_id=?", (new, reason if new == "rejected" else None, now, u["id"], rid, pid))
            c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "rx.response." + new, "%d/%d" % (rid, pid), json.dumps({"reason": reason or None}, ensure_ascii=False), now))
            if new == "approved":
                _notify(c, rr["customer_id"], "rx.quote", "وصلك رد على روشتتك", "روشتة #%d — راجع التسعيرات" % rid, "medical", rid)
                _notify(c, pid, "rx.approved", "اعتمدت الإدارة تسعيرتك", "روشتة #%d" % rid, "pharmacy", rid)
            else:
                _notify(c, pid, "rx.rejected", "رفضت الإدارة تسعيرتك", ("روشتة #%d — %s" % (rid, reason))[:200], "pharmacy", rid)
            c.commit(); h.send(200, {"ok": True, "review": new}); return True
        if path == "/api/admin/rx/tracking" and method == "GET":
            out = []
            for r in c.execute("SELECT p.id,p.status,p.created_at,p.note,g.name_ar region_name,us.name customer FROM prescriptions p JOIN regions g ON g.id=p.region_id JOIN users us ON us.id=p.customer_id WHERE p.status='forwarded' ORDER BY p.id DESC LIMIT 50"):
                d = dict(r); d["stage"] = stage_of(c, r["id"], r["status"]); d["images"] = images_of(c, r["id"]); d["pharmacies"] = tracking(c, r["id"]); out.append(d)
            h.send(200, out); return True
        m = re.fullmatch(r"/api/admin/prescriptions/(\d+)/forward-many", path)
        if method == "POST" and m:
            rid = int(m[1]); d = h.body()
            rx = c.execute("SELECT region_id FROM prescriptions WHERE id=? AND file_id IS NOT NULL AND status!='closed'", (rid,)).fetchone()
            if not rx: return err(400, "روشتة متاحة مطلوبة")
            if d.get("auto") in (True, 1, "1", "true"): ids = _region_pharmacies(c, rx["region_id"])
            else:
                raw = d.get("provider_ids")
                if not isinstance(raw, list) or not raw or len(raw) > MAX_MANY: return err(400, "اختر صيدلية واحدة إلى %d صيدليات" % MAX_MANY)
                try: ids = sorted({int(x) for x in raw if not isinstance(x, bool)})
                except (TypeError, ValueError): return err(400, "صيدليات غير صالحة")
            if not ids: return err(409, "لا توجد صيدليات معتمدة في منطقة الروشتة")
            n = forward(c, rid, ids)
            c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "prescription.forward", str(rid), json.dumps({"providers": ids, "added": n}), now))
            c.commit(); h.send(200, {"ok": True, "added": n, "providers": len(ids)}); return True
    return False
