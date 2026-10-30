# لاقينو — المرحلة 66 (م1 من خطة «محلات في منطقتك»): أنواع المحلات + تقديم المحل + اعتماد الإدارة. وحدة مستقلة بنمط provider_delivery.py: لا تستورد server.py.
# بدون سلة عمدًا: السلة ستُضاف لاحقًا للبرنامج كله. المحل جدول مستقل عن providers (الصيدلية لا تتغير).
# المسارات (GET وPOST فقط):
#   عام:    GET /api/shop-types                               (مغلق بالمفتاح العام)
#   تقديم:  POST /api/shops/apply                             (مغلق بالمفتاح العام)
#   مالك:   GET /api/owner/shops  |  POST /api/owner/shops/<id>/(open|close)
#   إدارة:  GET /api/admin/shops?status=&region_id=&type_id=&q=  |  POST /api/admin/shops/<id>/(review|edit)
#           GET|POST /api/admin/shop-types  |  POST /api/admin/shop-types/<id>/edit  |  GET|POST /api/admin/shops-settings
#   م3:     GET /api/owner/shops/<id>/items  |  POST /api/owner/shops/<id>/items  |  POST /api/owner/shops/<id>/items/<iid>/(edit|delete)   (الصور عبر /api/files ثم تُربط بـ image_ids)
# المفتاح العام settings.shops_enabled (مطفي افتراضيًا). الصلاحية = وجود محل معتمد للمالك (shops.owner_id + status='approved') وليس دور users.role.
# الأسعار في المشروع بالجنيه (REAL) فلا أعمدة سعر هنا؛ جداول الأصناف في م3.
import re, time, sqlite3, json
import notif

MAX_PENDING, MAX_ACTIVE, MAX_TYPES = 3, 5, 50
MAX_ITEMS, MAX_IMAGES, MAX_PRICE = 300, 5, 1_000_000  # م3: أصناف المحل
SEED = (("restaurants", "مطاعم", "🍽️", 1), ("supermarket", "سوبر ماركت", "🛒", 2), ("sweets", "محلات حلويات", "🍰", 3), ("clothing", "محلات ملابس", "👕", 4))
STATUSES = ("pending", "approved", "rejected", "suspended")
SCHEMA = """
CREATE TABLE IF NOT EXISTS shop_types(id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name_ar TEXT NOT NULL, icon TEXT NOT NULL DEFAULT '',
 sort INTEGER NOT NULL DEFAULT 0, is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN(0,1)), require_image INTEGER NOT NULL DEFAULT 0 CHECK(require_image IN(0,1)), created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS shops(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), type_id INTEGER NOT NULL REFERENCES shop_types(id),
 name_ar TEXT NOT NULL, name_norm TEXT NOT NULL, address TEXT NOT NULL, phone TEXT NOT NULL, region_id INTEGER NOT NULL REFERENCES regions(id), lat REAL, lng REAL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','rejected','suspended')), review_reason TEXT,
 is_open INTEGER NOT NULL DEFAULT 0 CHECK(is_open IN(0,1)), reviewed_by INTEGER, reviewed_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_shops_owner ON shops(owner_id,status);
CREATE INDEX IF NOT EXISTS ix_shops_browse ON shops(status,region_id,type_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_shops_owner_name ON shops(owner_id,name_norm) WHERE status!='rejected';
CREATE TABLE IF NOT EXISTS shop_items(id INTEGER PRIMARY KEY, shop_id INTEGER NOT NULL REFERENCES shops(id), name_ar TEXT NOT NULL, description TEXT,
 price REAL NOT NULL CHECK(price>0), is_available INTEGER NOT NULL DEFAULT 1 CHECK(is_available IN(0,1)), sort INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','deleted')), created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_shop_items ON shop_items(shop_id,status,sort,id);
CREATE TABLE IF NOT EXISTS shop_item_images(id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES shop_items(id) ON DELETE CASCADE,
 file_id INTEGER NOT NULL UNIQUE REFERENCES files(id), position INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_shop_item_images ON shop_item_images(item_id,position);
"""
_H = {}


def bind(audit):
    """يُستدعى من server.init: سجل التدقيق (الوحدة لا تستورد server)."""
    _H["audit"] = audit


def enabled(c):
    r = c.execute("SELECT value FROM settings WHERE key='shops_enabled'").fetchone()
    return bool(r) and str(r[0]) == "1"


def regions_allowed(c):
    """م6: تفعيل تدريجي. settings.shops_regions = JSON list لمعرّفات مناطق؛ فارغ/غير موجود = كل المناطق."""
    r = c.execute("SELECT value FROM settings WHERE key='shops_regions'").fetchone()
    try: v = json.loads(r[0]) if r else []
    except (ValueError, TypeError): v = []
    return [x for x in v if isinstance(x, int) and not isinstance(x, bool)] if isinstance(v, list) else []


def region_ok(c, region_id):
    a = regions_allowed(c)
    return not a or region_id in a


def public_image(c, file_id):
    """م5: صورة صنف نشط في محل معتمد تُعرض لأي مستخدم مسجَّل (والمفتاح العام مفعّل). غير ذلك يبقى الملف خاصًا بصاحبه."""
    if not enabled(c): return False
    r = c.execute("SELECT s.region_id FROM shop_item_images i JOIN shop_items x ON x.id=i.item_id AND x.status='active' JOIN shops s ON s.id=x.shop_id AND s.status='approved' WHERE i.file_id=?", (file_id,)).fetchone()
    return bool(r) and region_ok(c, r[0])


def install(c):
    """الجداول وبذر الأنواع الأولية (مرة واحدة فقط، فلا يعيد إنشاء ما حذفته/عطّلته الإدارة) وإشعارات triggers بنفس بادئة ntf_ (تُزال مع notif)."""
    c.executescript(SCHEMA)
    if not c.execute("SELECT 1 FROM shop_types LIMIT 1").fetchone() and not c.execute("SELECT 1 FROM settings WHERE key='shop_types_seeded'").fetchone():
        now = int(time.time())
        for sl, nm, ic, srt in SEED: c.execute("INSERT OR IGNORE INTO shop_types(slug,name_ar,icon,sort,is_active,require_image,created_at) VALUES(?,?,?,?,1,0,?)", (sl, nm, ic, srt, now))
        c.execute("INSERT OR IGNORE INTO settings VALUES('shop_types_seeded','1')")
    for n, in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'ntf_shop_%'").fetchall(): c.execute("DROP TRIGGER IF EXISTS " + n)
    adm = notif._ins("(users.id)", "admin.shop", "طلب انضمام محل جديد بانتظار المراجعة", body="NEW.name_ar", link="admin:shops", ref_type="shop", ref_id="NEW.id", frm="FROM users", where="WHERE users.role IN ('admin','staff')")
    own = notif._ins("NEW.owner_id", "shop.review", "CASE NEW.status WHEN 'approved' THEN 'تم اعتماد محلك' WHEN 'rejected' THEN 'تم رفض طلب محلك' ELSE 'تم إيقاف محلك' END",
                     body="COALESCE(NEW.review_reason, NEW.name_ar)", link="shop", ref_type="shop", ref_id="NEW.id")
    T = {"adm_ins": ("AFTER INSERT ON shops", "WHEN NEW.status='pending'", adm),
         "review": ("AFTER UPDATE OF status ON shops", "WHEN OLD.status IS NOT NEW.status AND NEW.status IN ('approved','rejected','suspended')", own)}
    for name, (when, cond, body) in T.items(): c.execute("CREATE TRIGGER ntf_shop_%s %s %s BEGIN %s END" % (name, when, cond, body))
    c.commit()


def _norm(s): return re.sub(r"\s+", " ", str(s or "")).strip().casefold()


def _text(v, name, lo, hi):
    t = re.sub(r"\s+", " ", v if isinstance(v, str) else "").strip()
    if not lo <= len(t) <= hi: raise ValueError("%s من %d إلى %d حرفًا" % (name, lo, hi))
    return t


def _phone(v):
    p = re.sub(r"[\s\-]", "", v if isinstance(v, str) else "")
    if not re.fullmatch(r"\+?\d{8,15}", p): raise ValueError("رقم الهاتف غير صالح")
    return p


def _geo(d):
    la, ln = d.get("lat"), d.get("lng")
    if la in (None, "") and ln in (None, ""): return None, None
    try:
        if isinstance(la, bool) or isinstance(ln, bool): raise ValueError
        la, ln = float(la), float(ln)
    except (TypeError, ValueError): raise ValueError("الموقع على الخريطة غير صالح")
    if not (-90 <= la <= 90 and -180 <= ln <= 180) or la != la or ln != ln: raise ValueError("الموقع على الخريطة غير صالح")
    return round(la, 6), round(ln, 6)


def _int(v):
    if isinstance(v, bool) or not isinstance(v, (int, str)): return None
    try: return int(v)
    except ValueError: return None


def _shop_row(r):
    return {"id": r["id"], "name_ar": r["name_ar"], "type_id": r["type_id"], "type_name": r["type_name"], "address": r["address"], "phone": r["phone"],
            "region_id": r["region_id"], "region_name": r["region_name"], "lat": r["lat"], "lng": r["lng"], "status": r["status"],
            "review_reason": r["review_reason"], "is_open": bool(r["is_open"]), "created_at": r["created_at"]}


SHOP_SEL = ("SELECT s.*,t.name_ar type_name,rg.name_ar region_name FROM shops s JOIN shop_types t ON t.id=s.type_id JOIN regions rg ON rg.id=s.region_id ")


def need_shop_owner(c, u, shop_id):
    """يرجع (صف المحل, None) أو (None, (code,msg)). المحل غير الموجود أو لغير صاحبه = 404 (لا نكشف وجوده)؛ محل صاحبه لكنه غير معتمد = 403."""
    r = c.execute("SELECT * FROM shops WHERE id=? AND owner_id=?", (shop_id, u["id"])).fetchone()
    if not r: return None, (404, "المحل غير موجود")
    if r["status"] != "approved": return None, (403, "المحل غير معتمد")
    return r, None


def _price(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)): raise ValueError("السعر غير صالح")
    try: p = float(v)
    except ValueError: raise ValueError("السعر غير صالح")
    if p != p or not 0 < p <= MAX_PRICE: raise ValueError("السعر يكون أكبر من صفر وحتى %d جنيه" % MAX_PRICE)
    return round(p, 2)


# الملف يُقبل فقط لو رفعه صاحب المحل عبر /api/files العام ولم يُربط بأي شيء آخر (لا يُستعمل ملف روشتة أو إعلان أو مستند كصورة صنف)
_LINKED = ("SELECT file_id FROM listing_images UNION SELECT file_id FROM product_images UNION SELECT file_id FROM exchange_images UNION SELECT file_id FROM service_request_images UNION SELECT file_id FROM rx_images "
           "UNION SELECT file_id FROM courier_documents UNION SELECT file_id FROM market_files UNION SELECT file_id FROM chat_messages WHERE file_id IS NOT NULL UNION SELECT file_id FROM prescriptions WHERE file_id IS NOT NULL "
           "UNION SELECT avatar_file_id FROM couriers WHERE avatar_file_id IS NOT NULL UNION SELECT photo_file_id FROM doctors WHERE photo_file_id IS NOT NULL UNION SELECT photo_file_id FROM labs WHERE photo_file_id IS NOT NULL")


def _image_ids(c, uid, raw, item_id=None):
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES or len(set(map(repr, raw))) != len(raw) or not all(isinstance(i, int) and not isinstance(i, bool) for i in raw):
        raise ValueError("قائمة الصور غير صالحة (حتى %d صور بلا تكرار)" % MAX_IMAGES)
    for fid in raw:
        r = c.execute("SELECT f.owner_id,(SELECT item_id FROM shop_item_images WHERE file_id=f.id) it,(SELECT 1 WHERE f.id IN (%s)) lk FROM files f WHERE f.id=?" % _LINKED, (fid,)).fetchone()
        if not r or r["owner_id"] != uid or r["lk"] or (r["it"] is not None and r["it"] != item_id): raise ValueError("صورة غير صالحة")
    return raw


def _items(c, shop_id, item_id=None):
    q = "SELECT * FROM shop_items WHERE shop_id=? AND status='active'" + (" AND id=?" if item_id else "") + " ORDER BY sort,id"
    rows = c.execute(q, (shop_id, item_id) if item_id else (shop_id,)).fetchall(); imgs = {}
    if rows:
        for r in c.execute("SELECT item_id,file_id FROM shop_item_images WHERE item_id IN (%s) ORDER BY item_id,position,id" % ",".join("?" * len(rows)), [x["id"] for x in rows]): imgs.setdefault(r[0], []).append(r[1])
    return [{"id": r["id"], "name_ar": r["name_ar"], "description": r["description"] or "", "price": r["price"], "is_available": bool(r["is_available"]), "sort": r["sort"], "image_ids": imgs.get(r["id"], []), "created_at": r["created_at"]} for r in rows]


def _set_images(c, item_id, ids, now):
    c.execute("DELETE FROM shop_item_images WHERE item_id=?", (item_id,))
    for i, fid in enumerate(ids): c.execute("INSERT INTO shop_item_images(item_id,file_id,position,created_at) VALUES(?,?,?,?)", (item_id, fid, i, now))


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. الأخطاء تُرجَع مباشرة عبر h.send."""
    if not path.startswith(("/api/shops", "/api/shop-types", "/api/owner/shops", "/api/admin/shops", "/api/admin/shop-types")): return False
    if method not in ("GET", "POST"): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    ok = lambda obj, code=200: (h.send(code, obj), True)[1]
    audit = lambda act, tgt, det=None: _H["audit"](c, u["id"], act, tgt, det) if _H.get("audit") else None
    m = None

    # ---- عام
    if (method, path) == ("GET", "/api/shop-types"):
        if not enabled(c): return ok({"enabled": False, "items": []})
        return ok({"enabled": True, "items": [dict(r) for r in c.execute("SELECT id,slug,name_ar,icon,require_image FROM shop_types WHERE is_active=1 ORDER BY sort,id")]})

    # ---- م5: تصفح المحلات المعتمدة (عام، قراءة فقط). المفتوحة أولًا، حد 60، بحث بالاسم، فلتر منطقة/نوع.
    if (method, path) == ("GET", "/api/shops"):
        if not enabled(c): return ok({"enabled": False, "items": []})
        g = lambda k: (q.get(k) or [""])[0]
        w, a = ["s.status='approved'"], []
        ra = regions_allowed(c)
        if ra: w.append("s.region_id IN (%s)" % ",".join("?" * len(ra))); a += ra
        for k, col in (("region_id", "s.region_id"), ("type_id", "s.type_id")):
            if g(k):
                v = _int(int(g(k))) if g(k).isdigit() and len(g(k)) <= 9 else None
                if v is None: return err(400, "قيمة الفلتر غير صالحة")
                w.append(col + "=?"); a.append(v)
        if g("q"):
            w.append("s.name_ar LIKE ? ESCAPE '\\'"); a.append("%" + g("q").strip()[:40].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        rows = c.execute("SELECT s.id,s.name_ar,s.type_id,s.region_id,s.address,s.is_open,t.name_ar type_name,r.name_ar region_name,"
                         "(SELECT COUNT(*) FROM shop_items x WHERE x.shop_id=s.id AND x.status='active' AND x.is_available=1) n,"
                         "(SELECT i.file_id FROM shop_item_images i JOIN shop_items x ON x.id=i.item_id WHERE x.shop_id=s.id AND x.status='active' AND x.is_available=1 ORDER BY x.sort,x.id,i.rowid LIMIT 1) cover "
                         "FROM shops s JOIN shop_types t ON t.id=s.type_id JOIN regions r ON r.id=s.region_id WHERE " + " AND ".join(w) + " ORDER BY s.is_open DESC,s.name_ar LIMIT 60", a).fetchall()
        return ok({"enabled": True, "items": [{"id": r["id"], "name_ar": r["name_ar"], "type_id": r["type_id"], "type_name": r["type_name"], "region_id": r["region_id"], "region_name": r["region_name"],
                                                "address": r["address"], "is_open": bool(r["is_open"]), "item_count": r["n"], "cover_file_id": r["cover"]} for r in rows]})

    # ---- التقديم
    if (method, path) == ("POST", "/api/shops/apply"):
        if not u: return err(401, "سجّل الدخول أولًا")
        if not enabled(c): return err(403, "تسجيل المحلات غير مفعّل حاليًا")
        d = h.body()
        try:
            tid = _int(d.get("type_id")); rid = _int(d.get("region_id"))
            if tid is None or not c.execute("SELECT 1 FROM shop_types WHERE id=? AND is_active=1", (tid,)).fetchone(): raise ValueError("اختر نوع المحل")
            nm = _text(d.get("name_ar"), "اسم المحل", 3, 80); ad = _text(d.get("address"), "العنوان", 3, 200); ph = _phone(d.get("phone")); la, ln = _geo(d)
            if rid is None or not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone(): raise ValueError("اختر منطقة مفعّلة")
        except ValueError as e: return err(400, str(e))
        now = int(time.time())
        try: cur = c.execute("INSERT INTO shops(owner_id,type_id,name_ar,name_norm,address,phone,region_id,lat,lng,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (u["id"], tid, nm, _norm(nm), ad, ph, rid, la, ln, now, now))
        except sqlite3.IntegrityError: c.rollback(); return err(409, "لديك محل بنفس الاسم بالفعل")
        # الحد يُفحص بعد الإدراج داخل نفس المعاملة (قفل الكتابة في SQLite يمنع تجاوزه بطلبين متزامنين)
        pend, act = c.execute("SELECT SUM(status='pending'),SUM(status!='rejected') FROM shops WHERE owner_id=?", (u["id"],)).fetchone()
        if (pend or 0) > MAX_PENDING: c.rollback(); return err(429, "لديك طلبات انضمام معلقة كثيرة، انتظر مراجعتها أولًا")
        if (act or 0) > MAX_ACTIVE: c.rollback(); return err(429, "وصلت للحد الأقصى لعدد المحلات")
        c.commit(); return ok({"id": cur.lastrowid, "status": "pending"}, 201)

    # ---- المالك
    if (method, path) == ("GET", "/api/owner/shops"):
        if not u: return err(401, "سجّل الدخول أولًا")
        return ok({"enabled": enabled(c), "items": [_shop_row(r) for r in c.execute(SHOP_SEL + "WHERE s.owner_id=? ORDER BY s.id", (u["id"],))]})
    m = re.fullmatch(r"/api/owner/shops/(\d{1,9})/(open|close)", path)
    if m and method == "POST":
        if not u: return err(401, "سجّل الدخول أولًا")
        s, e = need_shop_owner(c, u, int(m[1]))
        if e: return err(*e)
        v = 1 if m[2] == "open" else 0
        c.execute("UPDATE shops SET is_open=?,updated_at=? WHERE id=?", (v, int(time.time()), s["id"])); c.commit()
        return ok({"id": s["id"], "is_open": bool(v)})

    # ---- الإدارة
    if path.startswith(("/api/admin/shops", "/api/admin/shop-types")):
        if not u: return err(401, "سجّل الدخول أولًا")
        if u["role"] not in ("admin", "staff"): return err(403, "ليس لديك صلاحية")
        if (method, path) == ("GET", "/api/admin/shops"):
            st = q.get("status", ["pending"])[0]
            if st != "all" and st not in STATUSES: return err(400, "حالة غير صالحة")
            w, a = ["(?='all' OR s.status=?)"], [st, st]
            for k, col in (("region_id", "s.region_id"), ("type_id", "s.type_id")):
                if k in q:
                    n = _int(q[k][0])
                    if n is None: return err(400, "قيمة غير صالحة")
                    w.append(col + "=?"); a.append(n)
            if q.get("q", [""])[0].strip():
                like = "%" + q["q"][0].strip()[:60].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                w.append("(s.name_ar LIKE ? ESCAPE '\\' OR ow.name LIKE ? ESCAPE '\\' OR ow.phone LIKE ? ESCAPE '\\')"); a += [like, like, like]
            rows = c.execute(SHOP_SEL.replace("FROM shops s", "FROM shops s JOIN users ow ON ow.id=s.owner_id", 1).replace("SELECT s.*,", "SELECT s.*,ow.name owner_name,ow.phone owner_phone,", 1)
                             + "WHERE " + " AND ".join(w) + " ORDER BY s.id DESC LIMIT 200", a).fetchall()
            return ok([{**_shop_row(r), "owner_id": r["owner_id"], "owner_name": r["owner_name"], "owner_phone": r["owner_phone"]} for r in rows])
        m = re.fullmatch(r"/api/admin/shops/(\d{1,9})/(review|edit)", path)
        if m and method == "POST":
            s = c.execute("SELECT * FROM shops WHERE id=?", (int(m[1]),)).fetchone()
            if not s: return err(404, "المحل غير موجود")
            d = h.body(); now = int(time.time())
            if m[2] == "edit":
                tid = _int(d.get("type_id"))
                if tid is None or not c.execute("SELECT 1 FROM shop_types WHERE id=? AND is_active=1", (tid,)).fetchone(): return err(400, "نوع غير صالح")
                c.execute("UPDATE shops SET type_id=?,updated_at=? WHERE id=?", (tid, now, s["id"])); audit("shop.edit", s["id"], {"type_id": tid}); c.commit()
                return ok({"id": s["id"], "type_id": tid})
            st = d.get("status")
            if st not in ("approved", "rejected", "suspended"): return err(400, "حالة غير صالحة")
            reason = None
            if st != "approved":
                try: reason = _text(d.get("reason"), "السبب", 3, 200)
                except ValueError as e: return err(400, str(e))
            c.execute("UPDATE shops SET status=?,review_reason=?,is_open=CASE WHEN ?='approved' THEN is_open ELSE 0 END,reviewed_by=?,reviewed_at=?,updated_at=? WHERE id=?", (st, reason, st, u["id"], now, now, s["id"]))
            audit("shop.review", s["id"], {"status": st, "reason": reason}); c.commit()
            return ok({"id": s["id"], "status": st})
        # أنواع المحلات
        if (method, path) == ("GET", "/api/admin/shop-types"):
            return ok([dict(r) for r in c.execute("SELECT t.*,(SELECT COUNT(*) FROM shops s WHERE s.type_id=t.id AND s.status='approved') approved_shops FROM shop_types t ORDER BY t.sort,t.id")])
        m = re.fullmatch(r"/api/admin/shop-types/(\d{1,9})/edit", path)
        if (method, path) == ("POST", "/api/admin/shop-types") or (m and method == "POST"):
            if u["role"] != "admin": return err(403, "ليس لديك صلاحية")
            d = h.body(); cur = c.execute("SELECT * FROM shop_types WHERE id=?", (int(m[1]),)).fetchone() if m else None
            if m and not cur: return err(404, "النوع غير موجود")
            g = lambda k: d[k] if k in d else (cur[k] if cur else None)
            try:
                nm = _text(g("name_ar"), "اسم النوع", 2, 40); ic = _text(g("icon") or "", "الأيقونة", 0, 8)
                srt = g("sort"); srt = 0 if srt in (None, "") else _int(srt)
                if srt is None or not -1000 <= srt <= 1000: raise ValueError("الترتيب غير صالح")
                fl = {}
                for k, dflt in (("is_active", 1), ("require_image", 0)):
                    v = g(k); v = dflt if v is None else v
                    if isinstance(v, bool): v = int(v)
                    if v not in (0, 1) or isinstance(v, bool): raise ValueError("قيمة غير صالحة")
                    fl[k] = v
            except ValueError as e: return err(400, str(e))
            now = int(time.time())
            if m:
                c.execute("UPDATE shop_types SET name_ar=?,icon=?,sort=?,is_active=?,require_image=? WHERE id=?", (nm, ic, srt, fl["is_active"], fl["require_image"], cur["id"])); audit("shoptype.edit", cur["id"]); c.commit()
                return ok({"id": cur["id"]})
            if c.execute("SELECT COUNT(*) FROM shop_types").fetchone()[0] >= MAX_TYPES: return err(429, "وصلت للحد الأقصى لأنواع المحلات")
            sl = d.get("slug")
            if sl in (None, ""): sl = "type-%d" % (c.execute("SELECT COALESCE(MAX(id),0)+1 FROM shop_types").fetchone()[0])
            if not isinstance(sl, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}", sl): return err(400, "المعرّف يكون حروفًا إنجليزية صغيرة وأرقامًا وشرطة")
            try: cu = c.execute("INSERT INTO shop_types(slug,name_ar,icon,sort,is_active,require_image,created_at) VALUES(?,?,?,?,?,?,?)", (sl, nm, ic, srt, fl["is_active"], fl["require_image"], now))
            except sqlite3.IntegrityError: c.rollback(); return err(409, "المعرّف مستخدم من قبل")
            audit("shoptype.create", cu.lastrowid); c.commit(); return ok({"id": cu.lastrowid, "slug": sl}, 201)
        if path == "/api/admin/shops-settings":
            if method == "GET": return ok({"enabled": enabled(c), "regions": regions_allowed(c)})
            if u["role"] != "admin": return err(403, "ليس لديك صلاحية")
            d = h.body(); en, rg = d.get("enabled"), d.get("regions")
            if en is None and rg is None or (en is not None and not isinstance(en, bool)): return err(400, "قيمة التفعيل غير صالحة")
            if rg is not None:  # م6: قائمة مناطق التفعيل التدريجي ([] = كل المناطق)
                if not isinstance(rg, list) or len(rg) > 200 or any(isinstance(x, bool) or not isinstance(x, int) or not 1 <= x <= 10 ** 9 for x in rg): return err(400, "قائمة المناطق غير صالحة")
                rg = sorted(set(rg))
                if rg and c.execute("SELECT COUNT(*) FROM regions WHERE is_active=1 AND id IN (%s)" % ",".join("?" * len(rg)), rg).fetchone()[0] != len(rg): return err(400, "منطقة غير موجودة أو غير مفعّلة")
                c.execute("INSERT INTO settings VALUES('shops_regions',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(rg),))
            if en is not None: c.execute("INSERT INTO settings VALUES('shops_enabled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("1" if en else "0",))
            audit("settings.shops", None, {"enabled": en, "regions": rg}); c.commit(); return ok({"enabled": enabled(c), "regions": regions_allowed(c)})
    # ---- م3: أصناف المحل (المالك فقط، محله المعتمد)
    m = re.fullmatch(r"/api/owner/shops/(\d+)/items(?:/(\d+)/(edit|delete))?", path)
    if m:
        if not u: return err(401, "سجّل الدخول أولًا")
        shop, e = need_shop_owner(c, u, int(m[1]))
        if e: return err(*e)
        iid, act = (int(m[2]), m[3]) if m[2] else (None, None)
        if method == "GET" and not iid: return ok({"items": _items(c, shop["id"]), "max_items": MAX_ITEMS, "max_images": MAX_IMAGES,
                                                   "require_image": bool(c.execute("SELECT require_image FROM shop_types WHERE id=?", (shop["type_id"],)).fetchone()[0])})
        if method != "POST": return err(405, "غير مسموح")
        d = h.body(); now = int(time.time())
        req_img = bool(c.execute("SELECT require_image FROM shop_types WHERE id=?", (shop["type_id"],)).fetchone()[0])
        if not iid:  # إنشاء
            try:
                nm = _text(d.get("name_ar"), "اسم الصنف", 2, 80); pr = _price(d.get("price"))
                ds = d.get("description"); ds = "" if ds in (None, "") else _text(ds, "الوصف", 1, 500)
                av = d.get("is_available", True)
                if not isinstance(av, bool): raise ValueError("حالة التوفر: true أو false")
                imgs = _image_ids(c, u["id"], d.get("image_ids", []))
                if req_img and not imgs: raise ValueError("صورة الصنف مطلوبة لهذا النوع من المحلات")
            except ValueError as e: return err(400, str(e))
            cur = c.execute("INSERT INTO shop_items(shop_id,name_ar,description,price,is_available,sort,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                            (shop["id"], nm, ds or None, pr, int(av), c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM shop_items WHERE shop_id=?", (shop["id"],)).fetchone()[0], now, now))
            if c.execute("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active'", (shop["id"],)).fetchone()[0] > MAX_ITEMS: c.rollback(); return err(429, "وصلت للحد الأقصى من الأصناف (%d)" % MAX_ITEMS)
            try: _set_images(c, cur.lastrowid, imgs, now)
            except sqlite3.IntegrityError: c.rollback(); return err(400, "صورة غير صالحة")
            audit("shopitem.create", cur.lastrowid, {"shop": shop["id"]}); c.commit(); return ok({"id": cur.lastrowid}, 201)
        it = c.execute("SELECT * FROM shop_items WHERE id=? AND shop_id=? AND status='active'", (iid, shop["id"])).fetchone()
        if not it: return err(404, "الصنف غير موجود")
        if act == "delete":
            c.execute("UPDATE shop_items SET status='deleted',updated_at=? WHERE id=?", (now, iid))
            fids = [r[0] for r in c.execute("SELECT file_id FROM shop_item_images WHERE item_id=?", (iid,))]
            c.execute("DELETE FROM shop_item_images WHERE item_id=?", (iid,))  # الصور تعود ملفات عادية للمالك (يحذفها من /api/files)
            audit("shopitem.delete", iid, {"shop": shop["id"]}); c.commit(); return ok({"ok": True, "freed_image_ids": fids})
        try:
            nm = _text(d["name_ar"], "اسم الصنف", 2, 80) if "name_ar" in d else it["name_ar"]
            pr = _price(d["price"]) if "price" in d else it["price"]
            ds = it["description"]
            if "description" in d: ds = None if d["description"] in (None, "") else _text(d["description"], "الوصف", 1, 500)
            av = bool(it["is_available"])
            if "is_available" in d:
                if not isinstance(d["is_available"], bool): raise ValueError("حالة التوفر: true أو false")
                av = d["is_available"]
            imgs = _image_ids(c, u["id"], d["image_ids"], iid) if "image_ids" in d else None
            if req_img and not (imgs if imgs is not None else _items(c, shop["id"], iid)[0]["image_ids"]): raise ValueError("صورة الصنف مطلوبة لهذا النوع من المحلات")
        except ValueError as e: return err(400, str(e))
        c.execute("UPDATE shop_items SET name_ar=?,description=?,price=?,is_available=?,updated_at=? WHERE id=?", (nm, ds, pr, int(av), now, iid))
        if imgs is not None:
            try: _set_images(c, iid, imgs, now)
            except sqlite3.IntegrityError: c.rollback(); return err(400, "صورة غير صالحة")
        audit("shopitem.edit", iid, {"shop": shop["id"]}); c.commit(); return ok({"id": iid})
    return False
