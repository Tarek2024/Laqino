# لاقينو — البحث الشامل (المرحلة 1). وحدة مستقلة بنمط notif.py: لا تستورد server.py.
# المسار: GET /api/search?q=&region_id=&limit=  (عام كباقي مسارات البحث؛ لا يرجع أي رقم تواصل).
# يغطي ما لم تغطّه واجهات الأطباء/المعامل/الخدمات الموجودة: الأدوية (بتطبيع عربي)، الصيدليات، الإعلانات (بتطبيع عربي)،
# التخصصات، وأنواع الخدمات. الأطباء والمعامل والخدمات ما زالت تُبحث عبر /api/doctors و/api/labs و/api/services.
import re, time
import market

_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي",
                     "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"})
MAX_LIMIT, SCAN_LISTINGS, SCAN_STOCK = 20, 500, 1000


def norm(t):
    """تطبيع عربي: حذف التشكيل والتطويل، توحيد الألف والهاء والياء، أرقام هندية → لاتينية، حروف صغيرة."""
    t = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", str(t or "")).translate(_AR).lower()
    return re.sub(r"\s+", " ", t).strip()


def _match(toks, *fields):
    hay = " ".join(norm(f) for f in fields)
    return all(t in hay for t in toks)


def _related(c, rid):
    """المنطقة + أسلافها + أحفادها (نفس منطق الصيدليات في server.py)."""
    ids, cur, n = {rid}, rid, 0
    while cur is not None and n < 10:
        r = c.execute("SELECT parent_id FROM regions WHERE id=?", (cur,)).fetchone()
        cur = r["parent_id"] if r else None
        if cur is not None: ids.add(cur)
        n += 1
    ids.update(r[0] for r in c.execute("WITH RECURSIVE r(id) AS (SELECT ? UNION SELECT g.id FROM regions g JOIN r ON g.parent_id=r.id) SELECT id FROM r", (rid,)))
    return sorted(ids)


def _subtree(c, rid):
    return [r[0] for r in c.execute("WITH RECURSIVE r(id) AS (SELECT ? UNION SELECT g.id FROM regions g JOIN r ON g.parent_id=r.id) SELECT id FROM r", (rid,))]


def search(c, qtext, rid, limit):
    toks = norm(qtext).split()
    out = {"q": qtext, "region_id": rid or None, "needs_region": not rid, "medicines": [], "pharmacies": [], "listings": [], "specialties": [], "service_types": [], "products": []}
    ph = lambda ids: ",".join("?" * len(ids))
    if rid:
        rel = _related(c, rid)
        try: hrs = float((c.execute("SELECT value FROM settings WHERE key='stock_fresh_hours'").fetchone() or {"value": 24})["value"])
        except (TypeError, ValueError): hrs = 24.0
        rows = c.execute("SELECT s.medicine_name,s.price,s.confirmed_at,p.name_ar pharmacy,p.address FROM provider_stock s JOIN providers p ON p.user_id=s.provider_id "
                         "WHERE s.available=1 AND p.status='approved' AND p.region_id IN (%s) AND s.confirmed_at>? ORDER BY s.price LIMIT ?" % ph(rel),
                         (*rel, int(time.time() - hrs * 3600), SCAN_STOCK)).fetchall()
        out["medicines"] = [dict(r) for r in rows if _match(toks, r["medicine_name"])][:limit]
    prow = c.execute("SELECT p.user_id id,p.name_ar,p.address,rg.name_ar region_name,p.region_id FROM providers p JOIN regions rg ON rg.id=p.region_id WHERE p.status='approved' AND p.kind='pharmacy'").fetchall()
    rel = set(_related(c, rid)) if rid else None
    out["pharmacies"] = [dict(r) for r in prow if (rel is None or r["region_id"] in rel) and _match(toks, r["name_ar"], r["address"])][:limit]
    w, a = ["l.status='approved'", "l.category_id IN " + market.VISIBLE_CATEGORIES], []
    if rid:
        sub = _subtree(c, rid); w.append("l.region_id IN (%s)" % ph(sub)); a += sub
    lrows = c.execute("SELECT l.id,l.title,l.description,l.price,l.created_at,u.name seller,k.name_ar category FROM listings l JOIN users u ON u.id=l.user_id "
                      "JOIN categories k ON k.id=l.category_id WHERE " + " AND ".join(w) + " ORDER BY l.created_at DESC,l.id DESC LIMIT ?", (*a, SCAN_LISTINGS)).fetchall()
    hit = [dict(r) for r in lrows if _match(toks, r["title"], r["description"], r["category"])][:limit]
    imgs = market.images_for(c, [r["id"] for r in hit]) if hit else {}
    for r in hit: r["images"] = imgs.get(r["id"], [])
    out["listings"] = hit
    try:
        import products
        out["products"] = products.public_products(c, qtext, rid, 0, limit)[0]
    except ImportError: pass
    out["specialties"] = [dict(r) for r in c.execute("SELECT s.id,s.name_ar,(SELECT COUNT(*) FROM doctors d JOIN regions g ON g.id=d.region_id WHERE d.specialty_id=s.id AND d.is_published=1 AND g.is_active=1) doctors FROM specialties s WHERE s.is_active=1")
                          if _match(toks, r["name_ar"])][:limit]
    out["service_types"] = [dict(r) for r in c.execute("SELECT t.id,t.name_ar,(SELECT COUNT(*) FROM service_providers p JOIN regions g ON g.id=p.region_id WHERE p.type_id=t.id AND p.is_published=1 AND g.is_active=1) providers FROM service_types t WHERE t.is_active=1")
                            if _match(toks, r["name_ar"])][:limit]
    return out


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. h = معالج السيرفر (send)."""
    if method != "GET" or path != "/api/search": return False
    qt = (q.get("q", [""])[0] or "").strip()[:80]
    if len(norm(qt)) < 2: h.send(400, {"error": "اكتب حرفين على الأقل"}); return True
    try: rid = int(q.get("region_id", [0])[0] or 0)
    except (TypeError, ValueError): h.send(400, {"error": "قيمة رقمية غير صحيحة"}); return True
    try: lim = max(1, min(int(q.get("limit", [10])[0]), MAX_LIMIT))
    except (TypeError, ValueError): lim = 10
    h.send(200, search(c, qt, rid, lim)); return True
