"""سوق لاقينو — بذر التصنيفات والحقول والمحافظات (المرحلة 3).
الـslugs والأسماء الأربعة الأولى (cars/realestate/electronics/furniture) هي نفسها التي يبذرها setup_initial.py، فلا تتكرر؛ وما كان موجودًا لا تُمس حقوله.

متكرر بأمان: يتخطى أي شيء موجود بالـslug (لا يعدّل ولا يعطّل ما غيّرته الإدارة).
المحافظات تُضاف غير مفعّلة (تفعّلها الإدارة)، والتصنيفات غير مفعّلة افتراضيًا (active=True لتفعيلها).
الاستخدام: python3 market_seed.py [--db PATH] [--activate-categories]
أو من setup_initial.py:  import market_seed; market_seed.seed_all(c)  (قبل خطوة تفعيل تصنيفات السوق إن أردتها مفعّلة)
"""
import os, sys, json, sqlite3

GOVERNORATES = (
    ("eg-cai", "القاهرة"), ("eg-giz", "الجيزة"), ("eg-alx", "الإسكندرية"), ("eg-kal", "القليوبية"), ("eg-pts", "بورسعيد"),
    ("eg-suz", "السويس"), ("eg-dak", "الدقهلية"), ("eg-shr", "الشرقية"), ("eg-gha", "الغربية"), ("eg-mnf", "المنوفية"),
    ("eg-beh", "البحيرة"), ("eg-kfs", "كفر الشيخ"), ("eg-dam", "دمياط"), ("eg-ism", "الإسماعيلية"), ("eg-fay", "الفيوم"),
    ("eg-bns", "بني سويف"), ("eg-min", "المنيا"), ("eg-asy", "أسيوط"), ("eg-soh", "سوهاج"), ("eg-qen", "قنا"),
    ("eg-lux", "الأقصر"), ("eg-asw", "أسوان"), ("eg-bah", "البحر الأحمر"), ("eg-wad", "الوادي الجديد"), ("eg-mat", "مطروح"),
    ("eg-nsi", "شمال سيناء"), ("eg-ssi", "جنوب سيناء"),
)

# (slug, الاسم، [(key, label, type, required, options)])
_P = ("price", "السعر", "price", 1, None)
CATEGORIES = (
    ("souq-electronics", "أجهزة وإلكترونيات", [_P,
        ("item_type", "النوع", "select", 1, ["موبايل", "تابلت", "لابتوب", "تلفزيون وشاشات", "كاميرات", "إكسسوارات", "أخرى"]),
        ("brand", "الماركة", "text", 0, None)]),
    ("souq-cars", "سيارات", [_P,
        ("brand", "الماركة والموديل", "text", 1, None), ("year", "سنة الصنع", "number", 1, None), ("km", "المسافة المقطوعة (كم)", "number", 0, None),
        ("fuel", "الوقود", "select", 0, ["بنزين", "سولار", "غاز طبيعي", "كهرباء"]), ("transmission", "ناقل الحركة", "select", 0, ["أوتوماتيك", "مانوال"])]),
    ("souq-realestate", "عقارات", [_P,
        ("offer", "نوع العرض", "select", 1, ["بيع", "إيجار"]),
        ("property_type", "نوع العقار", "select", 1, ["شقة", "فيلا", "أرض", "محل", "مكتب", "أخرى"]),
        ("area", "المساحة (م²)", "number", 1, None), ("rooms", "عدد الغرف", "number", 0, None)]),
    ("souq-furniture", "أثاث ومستعمل", [_P,
        ("item_type", "النوع", "select", 0, ["أثاث", "أجهزة كهربائية", "مفروشات", "ديكور", "أخرى"])]),
    ("souq-clothing", "ملابس", [_P,
        ("gender", "الفئة", "select", 0, ["رجالي", "حريمي", "أطفال"]), ("size", "المقاس", "text", 0, None)]),
    ("souq-jobs", "وظائف", [
        ("salary", "المرتب", "number", 0, None),
        ("job_type", "نوع الدوام", "select", 0, ["دوام كامل", "دوام جزئي", "عمل حر", "تدريب"]), ("company", "الجهة", "text", 0, None)]),
    ("souq-services-trades", "خدمات ومهن", [
        ("price", "السعر (اختياري)", "price", 0, None), ("experience", "سنوات الخبرة", "number", 0, None)]),
    ("souq-personal-home", "مستلزمات شخصية ومنزلية", [_P]),
    ("souq-kids", "مستلزمات أطفال", [_P, ("age_range", "الفئة العمرية", "text", 0, None)]),
)


def seed_regions(c):
    """يضيف المحافظات تحت جذر مصر (slug=eg) غير مفعّلة. يعيد عدد المضاف."""
    root = c.execute("SELECT id FROM regions WHERE slug='eg'").fetchone()
    if not root: raise RuntimeError("جذر مصر (slug=eg) غير موجود؛ شغّل الخادم مرة لإنشاء المخطط أولًا")
    n = 0
    for i, (slug, name) in enumerate(GOVERNORATES, 1):
        if c.execute("SELECT 1 FROM regions WHERE slug=?", (slug,)).fetchone(): continue
        c.execute("INSERT INTO regions(parent_id,level,slug,name_ar,is_active,sort) VALUES(?,?,?,?,0,?)", (root[0], "governorate", slug, name, i)); n += 1
    return n


def seed_categories(c, active=False):
    """يضيف تصنيفات السوق الفرعية وحقولها تحت جذر souq. يعيد (تصنيفات مضافة، حقول مضافة)."""
    root = c.execute("SELECT id FROM categories WHERE section='souq' AND parent_id IS NULL").fetchone()
    if not root:
        cur = c.execute("INSERT INTO categories(section,slug,name_ar,is_active) VALUES('souq','souq','سوق لاقينو',0)"); root = (cur.lastrowid,)
    nc = nf = 0
    for i, (slug, name, fields) in enumerate(CATEGORIES, 1):
        row = c.execute("SELECT id FROM categories WHERE slug=?", (slug,)).fetchone()
        if row: cid = row[0]
        else:
            cid = c.execute("INSERT INTO categories(parent_id,section,slug,name_ar,sort,is_active) VALUES(?,?,?,?,?,?)", (root[0], "souq", slug, name, i * 10, int(bool(active)))).lastrowid; nc += 1
            for j, (key, label, typ, req, opts) in enumerate(fields, 1):  # حقول التصنيف الجديد فقط؛ لا نعيد حقولًا حذفتها الإدارة من تصنيف موجود
                c.execute("INSERT INTO category_fields(category_id,key,label_ar,type,required,searchable,options,sort) VALUES(?,?,?,?,?,?,?,?)",
                          (cid, key, label, typ, req, 1 if typ == "select" else 0, json.dumps(opts, ensure_ascii=False) if opts else None, j * 10)); nf += 1
    return nc, nf


def seed_all(c, active_categories=False):
    r = seed_regions(c); k, f = seed_categories(c, active_categories); c.commit()
    return {"governorates_added": r, "categories_added": k, "fields_added": f}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--db", default=os.environ.get("LAQINO_DB", "laqino.db")); ap.add_argument("--activate-categories", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.db): sys.exit("قاعدة البيانات غير موجودة: " + a.db + " (شغّل الخادم مرة أولًا)")
    c = sqlite3.connect(a.db); c.execute("PRAGMA foreign_keys=ON")
    print(seed_all(c, a.activate_categories)); c.close()
