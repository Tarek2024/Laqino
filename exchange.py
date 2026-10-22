# لاقينو — سوق الصيدليات (تبادل بيع بخصم بين الصيدليات المعتمدة فقط). وحدة مستقلة بنمط products.py: لا تستورد server.py.
# صيدلية معتمدة تنشر دواءً فائضًا (صورة + صلاحية + خصم) → تراجعه الإدارة → تراه الصيدليات المعتمدة الأخرى فقط → تحجزه → يتبادل الطرفان الهاتف.
# لا يراه العميل العادي أبدًا، ولا تتعامل لاقينو مع أي مبالغ (ربط فقط). بيع بخصم فقط: لا مقايضة دواء بدواء.
# المسارات:
#   صيدلية: GET|POST /api/provider/exchange | GET /api/provider/exchange/(mine|reservations)
#           POST /api/provider/exchange/<id>/(edit|delete|reserve|release|sold|report) | GET /api/provider/exchange/<id>/images/<file_id>
#   إدارة:  GET /api/admin/exchange?status= | POST /api/admin/exchange/<id>/(review|takedown)
#           GET /api/admin/exchange/reports | POST /api/admin/exchange/reports/<id>/resolve | GET /api/admin/exchange/<id>/images/<file_id>
import re, json, time, os, datetime
import notif
UP = os.environ.get("LAQINO_UPLOADS", "uploads")  # نفس مجلد server.py

MAX_IMAGES, MAX_PER_PHARMACY, MAX_QTY, MAX_PRICE, MAX_LIMIT, SCAN = 3, 100, 9999, 1_000_000, 50, 1000
MIN_EXPIRY_CREATE = 60    # أقل مدة صلاحية متبقية (بالأيام) لقبول الإعلان
MIN_EXPIRY_VISIBLE = 30   # الإعلان يختفي من السوق تلقائيًا حين تقل الصلاحية المتبقية عن هذا
RESERVE_HOURS = 48        # الحجز غير المؤكَّد بيعه يُفك تلقائيًا بعد هذه المدة
MAX_OPEN_RESERVATIONS = 5  # أقصى حجوزات مفتوحة للصيدلية الواحدة
MIN_DISCOUNT_PCT = 5      # أقل خصم مقبول (٪) كي يكون الإعلان «بخصم» فعلًا
# كلمات تمنع النشر (مخدرات/مؤثرات عقلية/أدوية تحتاج تبريد). قائمة بداية فقط وتحت مراجعة الإدارة: عدّلها حسب توجيه النقابة/المستشار القانوني.
BLOCKED = ("انسولين", "إنسولين", "insulin", "مخدر", "ترامادول", "ترامدول", "tramadol", "مورفين", "morphine", "كودايين", "كوديين", "codeine",
           "مؤثر عقلي", "مؤثرات عقلية", "تطعيم", "لقاح", "vaccine", "سلسلة تبريد")
SCHEMA = """
CREATE TABLE IF NOT EXISTS exchange_deals(id INTEGER PRIMARY KEY,
 provider_id INTEGER NOT NULL REFERENCES providers(user_id), title TEXT NOT NULL, details TEXT,
 qty INTEGER NOT NULL CHECK(qty>0), expiry_date TEXT NOT NULL, orig_price REAL NOT NULL CHECK(orig_price>0), price REAL NOT NULL CHECK(price>0),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','rejected','reserved','sold','deleted')),
 reject_reason TEXT, reserved_by INTEGER REFERENCES providers(user_id), reserved_at INTEGER,
 reviewed_by INTEGER, reviewed_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_exchange_status ON exchange_deals(status,expiry_date);
CREATE INDEX IF NOT EXISTS ix_exchange_prov ON exchange_deals(provider_id,status);
CREATE TABLE IF NOT EXISTS exchange_images(id INTEGER PRIMARY KEY, deal_id INTEGER NOT NULL REFERENCES exchange_deals(id) ON DELETE CASCADE,
 file_id INTEGER NOT NULL UNIQUE REFERENCES files(id), position INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_exchange_images ON exchange_images(deal_id,position);
CREATE TABLE IF NOT EXISTS exchange_reports(id INTEGER PRIMARY KEY, deal_id INTEGER NOT NULL REFERENCES exchange_deals(id) ON DELETE CASCADE,
 reporter_id INTEGER NOT NULL REFERENCES providers(user_id), reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','closed')),
 created_at INTEGER NOT NULL, UNIQUE(deal_id,reporter_id));
"""


def install(c):
    """جداول جديدة فقط (إضافة؛ آمنة للتكرار) + إشعارات (triggers بادئة ntf_exch_ فتُحذف مع الإشعارات إن أُزيلت)."""
    c.executescript(SCHEMA)
    for n, in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'ntf_exch_%'").fetchall(): c.execute("DROP TRIGGER IF EXISTS " + n)
    adm = lambda title, ref="NEW.id", body="NEW.title": notif._ins("(users.id)", "admin.exchange", title, body=body, link="admin:exchange", ref_type="exchange", ref_id=ref, frm="FROM users", where="WHERE users.role IN ('admin','staff')")
    me = lambda uid, kind, title, body="NEW.title": notif._ins(uid, kind, title, body=body, link="pharmacy", ref_type="exchange", ref_id="NEW.id")
    T = {"adm_ins": ("AFTER INSERT ON exchange_deals", "WHEN NEW.status='pending'", adm("إعلان جديد في سوق الصيدليات بانتظار المراجعة")),
         "adm_upd": ("AFTER UPDATE OF status ON exchange_deals", "WHEN NEW.status='pending' AND OLD.status IS NOT 'pending'", adm("إعلان معدَّل في سوق الصيدليات بانتظار المراجعة")),
         "adm_rep": ("AFTER INSERT ON exchange_reports", "", adm("بلاغ على إعلان في سوق الصيدليات", ref="NEW.deal_id", body="NEW.reason")),
         "review": ("AFTER UPDATE OF status ON exchange_deals", "WHEN (NEW.status='approved' AND OLD.status='pending') OR (NEW.status='rejected' AND OLD.status IN ('pending','approved','reserved'))",
                    me("NEW.provider_id", "exchange.review", "CASE NEW.status WHEN 'approved' THEN 'تم نشر إعلانك في سوق الصيدليات' ELSE 'تم رفض/إيقاف إعلانك في سوق الصيدليات' END", "COALESCE(NEW.reject_reason, NEW.title)")),
         "reserve": ("AFTER UPDATE OF status ON exchange_deals", "WHEN OLD.status='approved' AND NEW.status='reserved'", me("NEW.provider_id", "exchange.reserved", "صيدلية حجزت إعلانك في سوق الصيدليات")),
         "release_b": ("AFTER UPDATE OF status ON exchange_deals", "WHEN OLD.status='reserved' AND NEW.status='approved' AND OLD.reserved_by IS NOT NULL", me("OLD.reserved_by", "exchange.released", "أُلغي حجزك في سوق الصيدليات")),
         "release_s": ("AFTER UPDATE OF status ON exchange_deals", "WHEN OLD.status='reserved' AND NEW.status='approved'", me("NEW.provider_id", "exchange.released", "عاد إعلانك متاحًا في سوق الصيدليات (أُلغي الحجز)")),
         "sold": ("AFTER UPDATE OF status ON exchange_deals", "WHEN NEW.status='sold' AND OLD.status IS NOT 'sold' AND OLD.reserved_by IS NOT NULL", me("OLD.reserved_by", "exchange.sold", "تم تأكيد البيع لك في سوق الصيدليات"))}
    for name, (when, cond, body) in T.items(): c.execute("CREATE TRIGGER ntf_exch_%s %s %s BEGIN %s END" % (name, when, cond, body))
    c.commit()


def _int(v, d, lo, hi):
    try: return max(lo, min(int(v), hi))
    except (TypeError, ValueError): return d


def _num(v, name):
    if v in (None, "") or isinstance(v, bool): raise ValueError("أدخل " + name)
    try: n = float(v)
    except (TypeError, ValueError): raise ValueError(name + " غير صالح")
    if not (0 < n <= MAX_PRICE) or n != n: raise ValueError(name + " غير صالح")
    return round(n, 2)


def _expiry(v):
    """تاريخ الصلاحية كما يُطبع على العبوة. يقبل: 2027-06 | 2027/06 | 06/2027 | 6-2027 | 06/27 | 2027-06-15 | 15/06/2027 (وأرقام عربية).
    الشهر وحده = آخر يوم في الشهر. يرجع (نص ISO، date)."""
    s = str(v or "").strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    s = re.sub(r"[\s./\\_,\u060c-]+", "-", s).strip("-")
    try:
        parts = s.split("-")
        if not all(x.isdigit() for x in parts) or len(parts) not in (2, 3): raise ValueError
        if len(parts) == 2:
            a, b = parts
            y, m = (int(a), int(b)) if len(a) == 4 else (int(b), int(a))
            if y < 100: y += 2000
            d = datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
            if not 1 <= m <= 12: raise ValueError
        else:
            a, b, c3 = parts
            y, m, dd = (int(a), int(b), int(c3)) if len(a) == 4 else (int(c3), int(b), int(a))
            if y < 100: y += 2000
            d = datetime.date(y, m, dd)
    except (ValueError, OverflowError): raise ValueError("تاريخ الصلاحية غير مفهوم — اكتبه هكذا: 06/2027 أو 2027-06")
    return d.isoformat(), d


def _today(): return datetime.date.fromtimestamp(time.time())


def _clean(d, cur=None):
    pick = lambda k: d[k] if k in d else (cur[k] if cur is not None else None)
    t = re.sub(r"\s+", " ", str(pick("title") or "")).strip()
    if not 3 <= len(t) <= 120: raise ValueError("اسم الدواء من 3 إلى 120 حرفًا")
    det = (str(pick("details") or "").strip()[:500]) or None
    low = (t + " " + (det or "")).lower()
    if any(w in low for w in BLOCKED): raise ValueError("هذا الصنف غير مسموح نشره في سوق الصيدليات (مخدرات/مؤثرات عقلية/أدوية تحتاج تبريد)")
    try: qty = int(pick("qty"))
    except (TypeError, ValueError): raise ValueError("الكمية غير صالحة")
    if isinstance(pick("qty"), bool) or not 1 <= qty <= MAX_QTY: raise ValueError("الكمية من 1 إلى %d" % MAX_QTY)
    iso, dt = _expiry(pick("expiry_date"))
    if (dt - _today()).days < MIN_EXPIRY_CREATE: raise ValueError("الصلاحية المتبقية %d يومًا فقط — المطلوب %d يومًا على الأقل (آخر صلاحية مسموحة قبل %s)" % (max((dt - _today()).days, 0), MIN_EXPIRY_CREATE, (_today() + datetime.timedelta(days=MIN_EXPIRY_CREATE)).strftime("%Y-%m")))
    orig, price = _num(pick("orig_price"), "السعر الأصلي"), _num(pick("price"), "سعر الخصم")
    if price > orig * (1 - MIN_DISCOUNT_PCT / 100.0): raise ValueError("يجب أن يكون الخصم %d٪ على الأقل من السعر الأصلي" % MIN_DISCOUNT_PCT)
    return {"title": t, "details": det, "qty": qty, "expiry_date": iso, "orig_price": orig, "price": price}


def _check_images(c, uid, raw, deal_id=None, required=True):
    if raw is None:
        if required: raise ValueError("أرفق صورة العبوة وتاريخ الصلاحية")
        return None
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES or len(set(map(repr, raw))) != len(raw) or not all(isinstance(i, int) and not isinstance(i, bool) for i in raw):
        raise ValueError("قائمة الصور غير صالحة (حتى %d صور بلا تكرار)" % MAX_IMAGES)
    if required and not raw: raise ValueError("أرفق صورة العبوة وتاريخ الصلاحية")
    for fid in raw:
        r = c.execute("SELECT f.owner_id,(SELECT 1 FROM listing_images WHERE file_id=f.id) li,(SELECT 1 FROM product_images WHERE file_id=f.id) pi,(SELECT deal_id FROM exchange_images WHERE file_id=f.id) ei "
                      "FROM files f JOIN market_files mf ON mf.file_id=f.id WHERE f.id=?", (fid,)).fetchone()
        if not r or r["owner_id"] != uid or r["li"] or r["pi"] or (r["ei"] is not None and r["ei"] != deal_id): raise ValueError("صورة غير صالحة")
    return raw


def images_for(c, ids):
    out = {i: [] for i in ids}
    if ids:
        for r in c.execute("SELECT deal_id,file_id FROM exchange_images WHERE deal_id IN (%s) ORDER BY deal_id,position,id" % ",".join("?" * len(ids)), list(ids)): out[r[0]].append(r[1])
    return out


def _set_images(c, deal_id, uid, new, now):
    old = images_for(c, [deal_id])[deal_id]; drop = []
    c.execute("DELETE FROM exchange_images WHERE deal_id=?", (deal_id,))
    for i, fid in enumerate(new): c.execute("INSERT INTO exchange_images(deal_id,file_id,position,created_at) VALUES(?,?,?,?)", (deal_id, fid, i, now))
    for fid in old:
        if fid in new: continue
        f = c.execute("SELECT path FROM files WHERE id=? AND owner_id=?", (fid, uid)).fetchone()
        if f: c.execute("DELETE FROM files WHERE id=?", (fid,)); drop.append(f["path"])
    return drop


def _rm(paths):
    for p in paths:
        try: os.remove(os.path.join(UP, p))
        except OSError: pass


def _visible_cut(): return (_today() + datetime.timedelta(days=MIN_EXPIRY_VISIBLE)).isoformat()


def _lapse(c):
    """حجز مضى عليه RESERVE_HOURS بلا تأكيد بيع يُفك تلقائيًا (يعود الإعلان متاحًا). الإشعار يصدر من trigger الإفراج."""
    c.execute("UPDATE exchange_deals SET status='approved',reserved_by=NULL,reserved_at=NULL WHERE status='reserved' AND reserved_at<?", (int(time.time()) - RESERVE_HOURS * 3600,)); c.commit()


def _row(r, me):
    d = {k: r[k] for k in ("id", "title", "details", "qty", "expiry_date", "orig_price", "price", "status", "pharmacy_id", "pharmacy", "address", "region_name", "created_at")}
    d["discount_pct"] = round((1 - r["price"] / r["orig_price"]) * 100); d["mine"] = r["pharmacy_id"] == me
    d["reserved_by_me"] = r["reserved_by"] == me and r["reserved_by"] is not None
    return d


SEL = ("SELECT d.id,d.title,d.details,d.qty,d.expiry_date,d.orig_price,d.price,d.status,d.reserved_by,d.created_at,p.user_id pharmacy_id,p.name_ar pharmacy,p.address,g.name_ar region_name "
       "FROM exchange_deals d JOIN providers p ON p.user_id=d.provider_id JOIN regions g ON g.id=p.region_id ")


def board(c, me, qtext, rid, limit, offset):
    """السوق: إعلانات معتمدة/محجوزة وصلاحيتها كافية وصيدلية صاحبها ما زالت معتمدة."""
    import gsearch
    w, a = ["d.status IN ('approved','reserved')", "d.expiry_date>=?", "p.status='approved'"], [_visible_cut()]
    if rid: w.append("p.region_id=?"); a.append(rid)
    rows = c.execute(SEL + "WHERE " + " AND ".join(w) + " ORDER BY d.expiry_date ASC,d.id DESC LIMIT ?", (*a, SCAN)).fetchall()
    toks = gsearch.norm(qtext).split()
    hit = [_row(r, me) for r in rows if not toks or gsearch._match(toks, r["title"], r["details"])]
    page = hit[offset:offset + limit]; imgs = images_for(c, [r["id"] for r in page])
    for r in page: r["images"] = imgs[r["id"]]
    return page, len(hit)


def _contact(c, uid):
    r = c.execute("SELECT u.phone,p.name_ar FROM users u JOIN providers p ON p.user_id=u.id WHERE u.id=?", (uid,)).fetchone()
    return {"pharmacy": r["name_ar"], "phone": r["phone"]} if r else None


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب."""
    if not path.startswith(("/api/provider/exchange", "/api/admin/exchange")): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    if not u: return err(401, "سجّل الدخول أولًا")
    now = int(time.time())

    def send_img(deal_id, fid, allowed):
        r = c.execute("SELECT d.provider_id,d.status,d.reserved_by,f.path,f.mime FROM exchange_images i JOIN exchange_deals d ON d.id=i.deal_id JOIN files f ON f.id=i.file_id WHERE i.deal_id=? AND i.file_id=?", (deal_id, fid)).fetchone()
        if not r or r["status"] == "deleted" or not allowed(r): return err(404, "غير موجود")
        try: raw = open(os.path.join(UP, r["path"]), "rb").read()
        except OSError: return err(404, "غير موجود")
        h.send(200, None, r["mime"], raw, {"Cache-Control": "private, no-store"}); return True

    if path.startswith("/api/admin/exchange"):
        if u["role"] not in ("admin", "staff"): return err(403, "ليس لديك صلاحية")
        m = re.fullmatch(r"/api/admin/exchange/(\d+)/images/(\d+)", path)
        if method == "GET" and m: return send_img(int(m[1]), int(m[2]), lambda r: True)
        if method == "GET" and path == "/api/admin/exchange":
            st = q.get("status", ["pending"])[0]
            if st not in ("pending", "approved", "rejected", "reserved", "sold"): return err(400, "حالة غير صالحة")
            rows = [dict(r) for r in c.execute("SELECT d.id,d.title,d.details,d.qty,d.expiry_date,d.orig_price,d.price,d.status,d.reject_reason,d.created_at,p.name_ar pharmacy,p.status pharmacy_status FROM exchange_deals d JOIN providers p ON p.user_id=d.provider_id WHERE d.status=? ORDER BY d.id LIMIT 200", (st,))]
            imgs = images_for(c, [r["id"] for r in rows])
            for r in rows: r["images"] = imgs[r["id"]]
            h.send(200, rows); return True
        if method == "GET" and path == "/api/admin/exchange/reports":
            h.send(200, [dict(r) for r in c.execute("SELECT x.id,x.deal_id,x.reason,x.status,x.created_at,d.title,d.status deal_status,pr.name_ar reporter,po.name_ar pharmacy FROM exchange_reports x JOIN exchange_deals d ON d.id=x.deal_id JOIN providers pr ON pr.user_id=x.reporter_id JOIN providers po ON po.user_id=d.provider_id WHERE x.status='open' ORDER BY x.id LIMIT 200")]); return True
        if method == "POST":
            d = h.body()
            m = re.fullmatch(r"/api/admin/exchange/(\d+)/review", path)
            if m:
                st, reason = d.get("status"), str(d.get("reason") or "").strip()[:300]
                if st not in ("approved", "rejected"): return err(400, "حالة غير صالحة")
                if st == "rejected" and not reason: return err(400, "اكتب سبب الرفض")
                n = c.execute("UPDATE exchange_deals SET status=?,reject_reason=?,reviewed_by=?,reviewed_at=?,updated_at=? WHERE id=? AND status='pending'", (st, reason or None, u["id"], now, now, int(m[1]))).rowcount
                if not n: return err(409, "الإعلان غير موجود أو سبقت مراجعته")
                c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "exchange." + st, m[1], json.dumps(d, ensure_ascii=False), now)); c.commit(); h.send(200, {"ok": True}); return True
            m = re.fullmatch(r"/api/admin/exchange/(\d+)/takedown", path)
            if m:  # إيقاف إعلان منشور/محجوز (يُرفض بسبب)
                reason = str(d.get("reason") or "").strip()[:300]
                if not reason: return err(400, "اكتب سبب الإيقاف")
                n = c.execute("UPDATE exchange_deals SET status='rejected',reject_reason=?,reserved_by=NULL,reserved_at=NULL,reviewed_by=?,reviewed_at=?,updated_at=? WHERE id=? AND status IN ('approved','reserved')", (reason, u["id"], now, now, int(m[1]))).rowcount
                if not n: return err(409, "الإعلان غير منشور")
                c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "exchange.takedown", m[1], json.dumps(d, ensure_ascii=False), now)); c.commit(); h.send(200, {"ok": True}); return True
            m = re.fullmatch(r"/api/admin/exchange/reports/(\d+)/resolve", path)
            if m:
                n = c.execute("UPDATE exchange_reports SET status='closed' WHERE id=? AND status='open'", (int(m[1]),)).rowcount
                if not n: return err(409, "البلاغ غير موجود أو أُغلق")
                c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "exchange.report_closed", m[1], None, now)); c.commit(); h.send(200, {"ok": True}); return True
        return err(404, "غير موجود")

    # ---- الصيدلية (معتمدة فقط؛ التحقق من الخادم) ----
    pv = c.execute("SELECT * FROM providers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone()
    if not pv: return err(403, "سوق الصيدليات متاح للصيدليات المعتمدة فقط")
    me = u["id"]; _lapse(c)
    m = re.fullmatch(r"/api/provider/exchange/(\d+)/images/(\d+)", path)
    if method == "GET" and m: return send_img(int(m[1]), int(m[2]), lambda r: r["provider_id"] == me or r["status"] in ("approved", "reserved"))
    if method == "GET" and path == "/api/provider/exchange":
        qt = (q.get("q", [""])[0] or "").strip()[:80]
        items, total = board(c, me, qt, _int(q.get("region_id", [0])[0], 0, 0, 2 ** 62), _int(q.get("limit", [20])[0], 20, 1, MAX_LIMIT), _int(q.get("offset", [0])[0], 0, 0, 10 ** 6))
        h.send(200, {"items": items, "total": total}); return True
    if method == "GET" and path == "/api/provider/exchange/mine":
        rows = c.execute(SEL + "WHERE d.provider_id=? AND d.status!='deleted' ORDER BY d.id DESC LIMIT ?", (me, MAX_PER_PHARMACY + 50)).fetchall()
        extra = {r["id"]: r for r in c.execute("SELECT id,reject_reason FROM exchange_deals WHERE provider_id=?", (me,))}
        imgs = images_for(c, [r["id"] for r in rows]); out = []
        for r in rows:
            d = _row(r, me); d["images"] = imgs[r["id"]]; d["reject_reason"] = extra[r["id"]]["reject_reason"]
            if r["reserved_by"] and r["status"] in ("reserved", "sold"): d["buyer"] = _contact(c, r["reserved_by"])  # هاتف المشتري يظهر لك فقط بعد حجزه
            out.append(d)
        h.send(200, out); return True
    if method == "GET" and path == "/api/provider/exchange/reservations":
        rows = c.execute(SEL + "WHERE d.reserved_by=? AND d.status IN ('reserved','sold') ORDER BY d.id DESC LIMIT 100", (me,)).fetchall(); imgs = images_for(c, [r["id"] for r in rows]); out = []
        for r in rows:
            d = _row(r, me); d["images"] = imgs[r["id"]]; d["seller"] = _contact(c, r["pharmacy_id"]); out.append(d)
        h.send(200, out); return True
    if method == "POST" and path == "/api/provider/exchange":
        if c.execute("SELECT COUNT(*) FROM exchange_deals WHERE provider_id=? AND status NOT IN ('deleted','sold')", (me,)).fetchone()[0] >= MAX_PER_PHARMACY: return err(429, "وصلت للحد الأقصى من الإعلانات (%d)" % MAX_PER_PHARMACY)
        d = h.body()
        try: f = _clean(d); imgs = _check_images(c, me, d.get("image_file_ids"))
        except ValueError as e: return err(400, str(e))
        cur = c.execute("INSERT INTO exchange_deals(provider_id,title,details,qty,expiry_date,orig_price,price,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (me, f["title"], f["details"], f["qty"], f["expiry_date"], f["orig_price"], f["price"], now, now))
        _set_images(c, cur.lastrowid, me, imgs, now); c.commit(); h.send(200, {"ok": True, "id": cur.lastrowid, "status": "pending"}); return True
    m = re.fullmatch(r"/api/provider/exchange/(\d+)/(edit|delete|reserve|release|sold|report)", path)
    if method == "POST" and m:
        cur = c.execute("SELECT * FROM exchange_deals WHERE id=? AND status!='deleted'", (int(m[1]),)).fetchone()
        if not cur: return err(404, "غير موجود")
        act, mine = m[2], cur["provider_id"] == me
        if act in ("edit", "delete", "sold") and not mine: return err(404, "غير موجود")
        if act == "delete":
            if cur["status"] in ("reserved",): return err(409, "الإعلان محجوز: افك الحجز أو أكّد البيع أولًا")
            c.execute("UPDATE exchange_deals SET status='deleted',updated_at=? WHERE id=?", (now, cur["id"])); drop = _set_images(c, cur["id"], me, [], now); c.commit(); _rm(drop); h.send(200, {"ok": True}); return True
        if act == "edit":
            if cur["status"] not in ("pending", "approved", "rejected"): return err(409, "لا يمكن تعديل إعلان محجوز أو مباع")
            d = h.body()
            try: f = _clean(d, cur); new = _check_images(c, me, d.get("image_file_ids") if "image_file_ids" in d else None, cur["id"], required=False)
            except ValueError as e: return err(400, str(e))
            c.execute("UPDATE exchange_deals SET title=?,details=?,qty=?,expiry_date=?,orig_price=?,price=?,status='pending',reject_reason=NULL,reviewed_by=NULL,reviewed_at=NULL,updated_at=? WHERE id=?", (f["title"], f["details"], f["qty"], f["expiry_date"], f["orig_price"], f["price"], now, cur["id"]))
            drop = _set_images(c, cur["id"], me, new, now) if new is not None else []
            c.commit(); _rm(drop); h.send(200, {"ok": True, "status": "pending"}); return True  # أي تعديل يعيد المراجعة (السعر/الصلاحية/الصور حساسة)
        if act == "reserve":
            if mine: return err(400, "لا يمكنك حجز إعلانك")
            if c.execute("SELECT COUNT(*) FROM exchange_deals WHERE reserved_by=? AND status='reserved'", (me,)).fetchone()[0] >= MAX_OPEN_RESERVATIONS: return err(429, "وصلت للحد الأقصى من الحجوزات المفتوحة (%d)" % MAX_OPEN_RESERVATIONS)
            n = c.execute("UPDATE exchange_deals SET status='reserved',reserved_by=?,reserved_at=?,updated_at=? WHERE id=? AND status='approved' AND expiry_date>=? AND provider_id!=? AND EXISTS(SELECT 1 FROM providers WHERE user_id=provider_id AND status='approved')", (me, now, now, cur["id"], _visible_cut(), me)).rowcount
            if not n: return err(409, "الإعلان غير متاح للحجز (حجزه غيرك أو انتهى)")
            c.commit(); h.send(200, {"ok": True, "seller": _contact(c, cur["provider_id"])}); return True  # أول من يحجز يفوز (UPDATE شرطي ذري)
        if act == "release":
            if cur["status"] != "reserved" or me not in (cur["provider_id"], cur["reserved_by"]): return err(409, "لا يوجد حجز يمكنك فكّه")
            c.execute("UPDATE exchange_deals SET status='approved',reserved_by=NULL,reserved_at=NULL,updated_at=? WHERE id=? AND status='reserved'", (now, cur["id"])); c.commit(); h.send(200, {"ok": True}); return True
        if act == "sold":
            if cur["status"] != "reserved": return err(409, "أكّد البيع بعد أن تحجزه صيدلية")
            c.execute("UPDATE exchange_deals SET status='sold',updated_at=? WHERE id=? AND status='reserved'", (now, cur["id"])); c.commit(); h.send(200, {"ok": True}); return True
        if act == "report":
            if mine: return err(400, "لا يمكنك الإبلاغ عن إعلانك")
            reason = str(h.body().get("reason") or "").strip()[:300]
            if len(reason) < 3: return err(400, "اكتب سبب البلاغ")
            if c.execute("INSERT OR IGNORE INTO exchange_reports(deal_id,reporter_id,reason,created_at) VALUES(?,?,?,?)", (cur["id"], me, reason, now)).rowcount == 0: return err(409, "سبق أن أبلغت عن هذا الإعلان")
            c.commit(); h.send(200, {"ok": True}); return True
    return err(404, "غير موجود")
