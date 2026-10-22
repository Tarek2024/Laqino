# لاقينو — عروض المنتجات في القسم الطبي (المرحلة 2). وحدة مستقلة بنمط notif.py/gsearch.py: لا تستورد server.py.
# صيدلية معتمدة تنشر عروض منتجات غير دوائية (تجميل، أم وطفل، عناية شخصية، مستلزمات) → تُراجَع من الإدارة → تظهر للعميل.
# المسارات:
#   عام:      GET /api/medical/product-categories?region_id=   |   GET /api/medical/products?q=&category_id=&region_id=&limit=&offset=
#   صيدلية:   GET|POST /api/provider/products  |  POST /api/provider/products/<id>/(edit|confirm|delete)
#   إدارة:    GET /api/admin/products?status=  |  POST /api/admin/products/<id>/review
# لا تُرجع أي رقم هاتف أبدًا. إضافة فقط: جدول جديد + تصنيفات فرعية للقسم الطبي؛ لا تعديل على جداول قائمة.
import re, json, time, os
import market, gsearch, notif
UP = os.environ.get("LAQINO_UPLOADS", "uploads")  # نفس مجلد server.py

MAX_LIMIT, SCAN, MAX_PER_PHARMACY, MAX_PRICE, MAX_IMAGES = 50, 1000, 200, 1_000_000, 3
FRESH_DAYS_DEFAULT = 14  # العرض الأقدم من آخر تأكيد بهذه المدة لا يظهر للعملاء (يمكن تغييره من settings.product_fresh_days)
SEED = (("med-cosmetics", "مستحضرات تجميل", 1), ("med-mother-child", "الأم والطفل", 2),
        ("med-personal-care", "عناية شخصية", 3), ("med-supplies", "مستلزمات طبية", 4))
SCHEMA = """
CREATE TABLE IF NOT EXISTS product_offers(id INTEGER PRIMARY KEY,
 provider_id INTEGER NOT NULL REFERENCES providers(user_id), category_id INTEGER NOT NULL REFERENCES categories(id),
 title TEXT NOT NULL, brand TEXT, description TEXT, price REAL NOT NULL CHECK(price>0), old_price REAL,
 available INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','rejected','deleted')),
 reject_reason TEXT, reviewed_by INTEGER, reviewed_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, confirmed_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_product_offers ON product_offers(status,category_id);
CREATE INDEX IF NOT EXISTS ix_product_offers_prov ON product_offers(provider_id,status);
CREATE TABLE IF NOT EXISTS product_images(id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES product_offers(id) ON DELETE CASCADE,
 file_id INTEGER NOT NULL UNIQUE REFERENCES files(id), position INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_product_images ON product_images(offer_id,position);
"""


def enabled(c):
    """مفتاح إظهار المنتجات للعملاء (settings.products_enabled). الافتراضي مطفي: لا يظهر قسم المنتجات عند الإطلاق
    حتى تشغّله الإدارة. لا يمسح أي بيانات ولا يمنع الصيدليات من إضافة عروضها ومراجعة الإدارة لها."""
    r = c.execute("SELECT value FROM settings WHERE key='products_enabled'").fetchone()
    return bool(r) and str(r[0]) == "1"


def autoseed(c):
    """بذر تلقائي لتصنيفات المنتجات: بدونها تظهر قائمة التصنيف فارغة في لوحة الصيدلية فيفشل نشر أي منتج («تصنيف غير صالح»).
    يعمل فقط حين يكون القسم الطبي مفعّلًا (حتى لا تظهر تصنيفات قبل تفعيل الإدارة للقسم) وحين لا يوجد أي تصنيف فرعي له (فلا يعيد إنشاء ما حذفته الإدارة)."""
    root = c.execute("SELECT id FROM categories WHERE section='medical' AND parent_id IS NULL AND is_active=1 ORDER BY id LIMIT 1").fetchone()
    if root and not c.execute("SELECT 1 FROM categories WHERE section='medical' AND parent_id IS NOT NULL LIMIT 1").fetchone():
        for sl, nm, srt in SEED: c.execute("INSERT OR IGNORE INTO categories(parent_id,section,slug,name_ar,sort,is_active) VALUES(?,?,?,?,?,1)", (root[0], "medical", sl, nm, srt))
        c.commit()


def install(c):
    """جدول العروض فقط (إضافة؛ آمنة للتكرار). التصنيفات الفرعية تُنشأ بقرار الإدارة عبر POST /api/admin/products/seed-categories."""
    c.executescript(SCHEMA)
    autoseed(c)
    # إشعارات (triggers بنفس بادئة notif.py `ntf_` فتُحذف معها عند إزالة الإشعارات): للإدارة عند عرض جديد/معدَّل، وللصيدلية عند النشر/الرفض.
    for n, in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'ntf_prod_%'").fetchall(): c.execute("DROP TRIGGER IF EXISTS " + n)
    adm = lambda title: notif._ins("(users.id)", "admin.product", title, body="NEW.title", link="admin:products", ref_type="product", ref_id="NEW.id", frm="FROM users", where="WHERE users.role IN ('admin','staff')")
    T = {"adm_ins": ("AFTER INSERT ON product_offers", "WHEN NEW.status='pending'", adm("عرض منتج جديد بانتظار المراجعة")),
         "adm_upd": ("AFTER UPDATE OF status ON product_offers", "WHEN NEW.status='pending' AND OLD.status IS NOT 'pending'", adm("عرض منتج معدَّل بانتظار المراجعة")),
         "review": ("AFTER UPDATE OF status ON product_offers", "WHEN OLD.status IS NOT NEW.status AND NEW.status IN ('approved','rejected')",
                    notif._ins("NEW.provider_id", "product.review", "CASE NEW.status WHEN 'approved' THEN 'تم نشر عرض المنتج' ELSE 'تم رفض عرض المنتج' END", body="COALESCE(NEW.reject_reason, NEW.title)", link="pharmacy", ref_type="product", ref_id="NEW.id"))}
    for name, (when, cond, body) in T.items(): c.execute("CREATE TRIGGER ntf_prod_%s %s %s BEGIN %s END" % (name, when, cond, body))
    c.commit()


def _fresh_cut(c):
    try: d = float((c.execute("SELECT value FROM settings WHERE key='product_fresh_days'").fetchone() or {"value": FRESH_DAYS_DEFAULT})["value"])
    except (TypeError, ValueError): d = FRESH_DAYS_DEFAULT
    return int(time.time() - max(d, 1) * 86400)


def _med_category(c, cid):
    """تصنيف فرعي نشط تحت القسم الطبي (وكل أسلافه نشطة)."""
    r = c.execute("SELECT 1 FROM categories WHERE id=? AND section='medical' AND parent_id IS NOT NULL", (cid,)).fetchone()
    return bool(r) and market.is_visible_category(c, cid)


def _num(v, name, req=True):
    if v in (None, ""):
        if req: raise ValueError("أدخل " + name)
        return None
    if isinstance(v, bool): raise ValueError(name + " غير صالح")
    try: n = float(v)
    except (TypeError, ValueError): raise ValueError(name + " غير صالح")
    if not (0 < n <= MAX_PRICE) or n != n: raise ValueError(name + " غير صالح")
    return round(n, 2)


def _clean(c, d, cur=None):
    """يتحقق من الحقول ويرجع dict نظيفًا. يرفع ValueError برسالة عربية. cur = الصف الحالي عند التعديل."""
    out = {}
    def pick(k): return d[k] if k in d else (cur[k] if cur is not None else None)
    t = re.sub(r"\s+", " ", str(pick("title") or "")).strip()
    if not 3 <= len(t) <= 120: raise ValueError("اسم المنتج من 3 إلى 120 حرفًا")
    out["title"] = t
    out["brand"] = (str(pick("brand") or "").strip()[:60]) or None
    out["description"] = (str(pick("description") or "").strip()[:1000]) or None
    try: cid = int(pick("category_id"))
    except (TypeError, ValueError): raise ValueError("اختر التصنيف")
    if isinstance(pick("category_id"), bool) or not _med_category(c, cid): raise ValueError("تصنيف غير صالح")
    out["category_id"] = cid
    out["price"] = _num(pick("price"), "السعر")
    out["old_price"] = _num(pick("old_price"), "السعر القديم", False)
    if out["old_price"] is not None and out["old_price"] <= out["price"]: raise ValueError("السعر القديم يجب أن يكون أكبر من السعر الحالي")
    return out


def images_for(c, ids):
    out = {i: [] for i in ids}
    if ids:
        for r in c.execute("SELECT offer_id,file_id FROM product_images WHERE offer_id IN (%s) ORDER BY offer_id,position,id" % ",".join("?" * len(ids)), list(ids)): out[r[0]].append(r[1])
    return out


def _check_images(c, uid, raw, offer_id=None):
    if raw is None: return None
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES or len(set(map(repr, raw))) != len(raw) or not all(isinstance(i, int) and not isinstance(i, bool) for i in raw):
        raise ValueError("قائمة الصور غير صالحة (حتى %d صور بلا تكرار)" % MAX_IMAGES)
    for fid in raw:
        r = c.execute("SELECT f.owner_id,(SELECT 1 FROM listing_images WHERE file_id=f.id) li,(SELECT offer_id FROM product_images WHERE file_id=f.id) po FROM files f JOIN market_files mf ON mf.file_id=f.id WHERE f.id=?", (fid,)).fetchone()
        if not r or r["owner_id"] != uid or r["li"] or (r["po"] is not None and r["po"] != offer_id): raise ValueError("صورة غير صالحة")
    return raw


def _set_images(c, offer_id, uid, new, now):
    """يستبدل صور العرض؛ الصور المزالة تُحذف (سجل + ملف) ما لم تكن مستخدمة في مكان آخر. يرجع مسارات الملفات للحذف من القرص بعد الـcommit."""
    old = images_for(c, [offer_id])[offer_id]; drop = []
    c.execute("DELETE FROM product_images WHERE offer_id=?", (offer_id,))
    for i, fid in enumerate(new): c.execute("INSERT INTO product_images(offer_id,file_id,position,created_at) VALUES(?,?,?,?)", (offer_id, fid, i, now))
    for fid in old:
        if fid in new or market.file_used_elsewhere(c, fid): continue
        f = c.execute("SELECT path FROM files WHERE id=? AND owner_id=?", (fid, uid)).fetchone()
        if f: c.execute("DELETE FROM files WHERE id=?", (fid,)); drop.append(f["path"])
    return drop


def _rm(paths):
    for p in paths:
        try: os.remove(os.path.join(UP, p))
        except OSError: pass


def _pub(r):
    return {k: r[k] for k in ("id", "title", "brand", "description", "price", "old_price", "category", "category_id", "pharmacy_id", "pharmacy", "address", "region_name", "confirmed_at")}


def public_products(c, qtext, rid, cid, limit, offset=0, pharmacy_id=0):
    """عروض منشورة (معتمدة + متوفرة + حديثة + صيدلية معتمدة + تصنيف ظاهر) مرتبة بالأحدث تأكيدًا."""
    if not enabled(c): return [], 0  # المنتجات مخفية من العملاء (الإدارة تتحكم)
    w = ["o.status='approved'", "o.available=1", "o.confirmed_at>?", "p.status='approved'", "o.category_id IN " + market.VISIBLE_CATEGORIES]
    a = [_fresh_cut(c)]
    if rid:
        rel = gsearch._related(c, rid); w.append("p.region_id IN (%s)" % ",".join("?" * len(rel))); a += rel
    if pharmacy_id: w.append("o.provider_id=?"); a.append(pharmacy_id)
    if cid:
        sub = market.subtree_ids(c, cid); w.append("o.category_id IN (%s)" % ",".join("?" * len(sub))); a += sub
    rows = c.execute("SELECT o.id,o.title,o.brand,o.description,o.price,o.old_price,o.category_id,k.name_ar category,o.confirmed_at,p.user_id pharmacy_id,p.name_ar pharmacy,p.address,g.name_ar region_name "
                     "FROM product_offers o JOIN providers p ON p.user_id=o.provider_id JOIN categories k ON k.id=o.category_id JOIN regions g ON g.id=p.region_id "
                     "WHERE " + " AND ".join(w) + " ORDER BY o.confirmed_at DESC,o.id DESC LIMIT ?", (*a, SCAN)).fetchall()
    toks = gsearch.norm(qtext).split()
    hit = [_pub(r) for r in rows if not toks or gsearch._match(toks, r["title"], r["brand"], r["description"], r["category"])]
    page = hit[offset:offset + limit]; imgs = images_for(c, [r["id"] for r in page])
    for r in page: r["images"] = imgs[r["id"]]
    return page, len(hit)


def _int(v, d, lo, hi):
    try: return max(lo, min(int(v), hi))
    except (TypeError, ValueError): return d


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. h = معالج السيرفر (send/body). الأخطاء تُرجَع مباشرة عبر h.send."""
    if not path.startswith(("/api/medical/product", "/api/medical/pharmacies/", "/api/provider/products", "/api/admin/products")): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    if method == "GET" and path == "/api/medical/product-categories":
        if not enabled(c): h.send(200, []); return True
        autoseed(c)
        rid = _int(q.get("region_id", [0])[0], 0, 0, 2 ** 62)
        cats = c.execute("SELECT k.id,k.name_ar FROM categories k WHERE k.section='medical' AND k.parent_id IS NOT NULL AND k.is_active=1 AND k.id IN " + market.VISIBLE_CATEGORIES + " ORDER BY k.sort,k.id").fetchall()
        h.send(200, [{"id": k["id"], "name": k["name_ar"], "count": public_products(c, "", rid, k["id"], 1)[1]} for k in cats]); return True
    m = re.fullmatch(r"/api/medical/pharmacies/(\d+)", path)
    if method == "GET" and m:  # صفحة عامة للصيدلية: بيانات الصيدلية المعتمدة + عروضها المنشورة. لا هاتف.
        p = c.execute("SELECT p.user_id id,p.name_ar,p.address,g.name_ar region_name FROM providers p JOIN regions g ON g.id=p.region_id WHERE p.user_id=? AND p.status='approved'", (int(m[1]),)).fetchone()
        if not p: return err(404, "غير موجود")
        lim, off = _int(q.get("limit", [20])[0], 20, 1, MAX_LIMIT), _int(q.get("offset", [0])[0], 0, 0, 10 ** 6)
        items, total = public_products(c, "", 0, 0, lim, off, p["id"])
        h.send(200, {**dict(p), "items": items, "total": total}); return True
    m = re.fullmatch(r"/api/medical/products/(\d+)/images/(\d+)", path)
    if method == "GET" and m:  # عام للعرض المنشور؛ غير المنشور لصاحبه والإدارة فقط (404 لغيرهم)
        if not enabled(c) and not (u and u["role"] in ("admin", "staff")): return err(404, "غير موجود")
        r = c.execute("SELECT o.status,o.provider_id,o.category_id,p.status pst,f.path,f.mime FROM product_images i JOIN product_offers o ON o.id=i.offer_id JOIN providers p ON p.user_id=o.provider_id JOIN files f ON f.id=i.file_id WHERE i.offer_id=? AND i.file_id=?", (int(m[1]), int(m[2]))).fetchone()
        if not r or r["status"] == "deleted": return err(404, "غير موجود")
        public = r["status"] == "approved" and r["pst"] == "approved" and market.is_visible_category(c, r["category_id"])
        if not public and not (u and (u["id"] == r["provider_id"] or u["role"] in ("admin", "staff"))): return err(404, "غير موجود")
        try: raw = open(os.path.join(UP, r["path"]), "rb").read()
        except OSError: return err(404, "غير موجود")
        h.send(200, None, r["mime"], raw, {"Cache-Control": "public, max-age=3600" if public else "private, no-store"}); return True
    if method == "GET" and path == "/api/medical/products":
        qt = (q.get("q", [""])[0] or "").strip()[:80]
        rid, cid = _int(q.get("region_id", [0])[0], 0, 0, 2 ** 62), _int(q.get("category_id", [0])[0], 0, 0, 2 ** 62)
        lim, off = _int(q.get("limit", [20])[0], 20, 1, MAX_LIMIT), _int(q.get("offset", [0])[0], 0, 0, 10 ** 6)
        items, total = public_products(c, qt, rid, cid, lim, off)
        h.send(200, {"items": items, "total": total}); return True

    if path.startswith("/api/admin/products"):
        if not u: return err(401, "سجّل الدخول أولًا")
        if u["role"] not in ("admin", "staff"): return err(403, "ليس لديك صلاحية")
        if method == "GET" and path == "/api/admin/products":
            st = q.get("status", ["pending"])[0]
            if st not in ("pending", "approved", "rejected"): return err(400, "حالة غير صالحة")
            rows = [dict(r) for r in c.execute("SELECT o.id,o.title,o.brand,o.description,o.price,o.old_price,o.available,o.status,o.reject_reason,o.created_at,k.name_ar category,p.name_ar pharmacy,p.status pharmacy_status "
                                               "FROM product_offers o JOIN providers p ON p.user_id=o.provider_id JOIN categories k ON k.id=o.category_id WHERE o.status=? ORDER BY o.id LIMIT 200", (st,))]
            imgs = images_for(c, [r["id"] for r in rows])
            for r in rows: r["images"] = imgs[r["id"]]
            h.send(200, rows); return True
        if method == "POST" and path == "/api/admin/products/seed-categories":  # يُنشئ الناقص فقط (بالـ slug)؛ لا يعدّل ولا يعيد تفعيل ما عطّلته الإدارة
            root = c.execute("SELECT id FROM categories WHERE section='medical' AND parent_id IS NULL ORDER BY id LIMIT 1").fetchone()
            if not root: return err(409, "لا يوجد جذر للقسم الطبي")
            n = sum(c.execute("INSERT OR IGNORE INTO categories(parent_id,section,slug,name_ar,sort,is_active) VALUES(?,?,?,?,?,1)", (root["id"], "medical", sl, nm, srt)).rowcount for sl, nm, srt in SEED)
            c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "product.seed_categories", None, json.dumps({"created": n}), int(time.time())))
            c.commit(); h.send(200, {"ok": True, "created": n}); return True
        m = re.fullmatch(r"/api/admin/products/(\d+)/review", path)
        if method == "POST" and m:
            d = h.body(); st = d.get("status"); reason = str(d.get("reason") or "").strip()[:300]
            if st not in ("approved", "rejected"): return err(400, "حالة غير صالحة")
            if st == "rejected" and not reason: return err(400, "اكتب سبب الرفض")
            n = c.execute("UPDATE product_offers SET status=?,reject_reason=?,reviewed_by=?,reviewed_at=?,confirmed_at=CASE WHEN ?='approved' THEN ? ELSE confirmed_at END WHERE id=? AND status='pending'",
                          (st, reason or None, u["id"], int(time.time()), st, int(time.time()), int(m[1]))).rowcount
            if not n: return err(409, "الطلب غير موجود أو سبقت مراجعته")
            c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "product." + st, m[1], json.dumps(d, ensure_ascii=False), int(time.time())))
            c.commit(); h.send(200, {"ok": True}); return True
        return err(404, "غير موجود")

    if path.startswith("/api/provider/products"):
        if not u: return err(401, "سجّل الدخول أولًا")
        pv = c.execute("SELECT * FROM providers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone()
        if not pv: return err(403, "حساب الصيدلية غير معتمد")
        pid, now = u["id"], int(time.time())
        if method == "GET" and path == "/api/provider/products":
            autoseed(c)
            rows = [dict(r) for r in c.execute("SELECT o.id,o.title,o.brand,o.description,o.price,o.old_price,o.available,o.status,o.reject_reason,o.category_id,k.name_ar category,o.confirmed_at "
                                               "FROM product_offers o JOIN categories k ON k.id=o.category_id WHERE o.provider_id=? AND o.status!='deleted' ORDER BY o.id DESC LIMIT ?", (pid, MAX_PER_PHARMACY + 50))]
            imgs = images_for(c, [r["id"] for r in rows])
            for r in rows: r["images"] = imgs[r["id"]]
            h.send(200, rows); return True
        if method == "POST" and path == "/api/provider/products":
            if c.execute("SELECT COUNT(*) FROM product_offers WHERE provider_id=? AND status!='deleted'", (pid,)).fetchone()[0] >= MAX_PER_PHARMACY: return err(429, "وصلت للحد الأقصى من العروض (%d)" % MAX_PER_PHARMACY)
            d = h.body()
            try: f = _clean(c, d); imgs = _check_images(c, pid, d.get("image_file_ids"))
            except ValueError as e: return err(400, str(e))
            cur = c.execute("INSERT INTO product_offers(provider_id,category_id,title,brand,description,price,old_price,available,created_at,updated_at,confirmed_at) VALUES(?,?,?,?,?,?,?,1,?,?,?)",
                            (pid, f["category_id"], f["title"], f["brand"], f["description"], f["price"], f["old_price"], now, now, now))
            if imgs: _set_images(c, cur.lastrowid, pid, imgs, now)
            c.commit(); h.send(200, {"ok": True, "id": cur.lastrowid, "status": "pending"}); return True
        m = re.fullmatch(r"/api/provider/products/(\d+)/(edit|confirm|delete)", path)
        if method == "POST" and m:
            cur = c.execute("SELECT * FROM product_offers WHERE id=? AND provider_id=? AND status!='deleted'", (int(m[1]), pid)).fetchone()
            if not cur: return err(404, "غير موجود")
            act = m[2]
            if act == "delete":
                c.execute("UPDATE product_offers SET status='deleted',updated_at=? WHERE id=?", (now, cur["id"])); drop = _set_images(c, cur["id"], pid, [], now)
                c.commit(); _rm(drop); h.send(200, {"ok": True}); return True
            d = h.body()
            if act == "confirm":  # تأكيد حديث للسعر/التوفر؛ لا يعيد المراجعة ولا يغيّر المحتوى
                try:
                    price = _num(d["price"], "السعر") if "price" in d else cur["price"]
                    old = _num(d["old_price"], "السعر القديم", False) if "old_price" in d else cur["old_price"]
                    if old is not None and old <= price: raise ValueError("السعر القديم يجب أن يكون أكبر من السعر الحالي")
                except ValueError as e: return err(400, str(e))
                av = int(bool(d["available"])) if "available" in d else cur["available"]
                c.execute("UPDATE product_offers SET price=?,old_price=?,available=?,confirmed_at=?,updated_at=? WHERE id=?", (price, old, av, now, now, cur["id"]))
                c.commit(); h.send(200, {"ok": True}); return True
            try: f = _clean(c, d, cur); new_imgs = _check_images(c, pid, d.get("image_file_ids") if "image_file_ids" in d else None, cur["id"])
            except ValueError as e: return err(400, str(e))
            old_imgs = images_for(c, [cur["id"]])[cur["id"]]
            if (f["title"], f["brand"], f["description"], f["category_id"]) != (cur["title"], cur["brand"], cur["description"], cur["category_id"]) or (new_imgs is not None and new_imgs != old_imgs):
                c.execute("UPDATE product_offers SET title=?,brand=?,description=?,category_id=?,price=?,old_price=?,status='pending',reject_reason=NULL,reviewed_by=NULL,reviewed_at=NULL,confirmed_at=?,updated_at=? WHERE id=?",
                          (f["title"], f["brand"], f["description"], f["category_id"], f["price"], f["old_price"], now, now, cur["id"])); st = "pending"
            else:
                c.execute("UPDATE product_offers SET price=?,old_price=?,confirmed_at=?,updated_at=? WHERE id=?", (f["price"], f["old_price"], now, now, cur["id"])); st = cur["status"]
            drop = _set_images(c, cur["id"], pid, new_imgs, now) if new_imgs is not None and new_imgs != old_imgs else []
            c.commit(); _rm(drop); h.send(200, {"ok": True, "status": st}); return True
        return err(404, "غير موجود")
    return err(404, "غير موجود")
