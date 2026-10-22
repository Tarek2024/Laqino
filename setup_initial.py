"""تهيئة أولية آمنة لـ Laqino (الخطوة 1). تُشغَّل مرة واحدة أو أكثر دون ضرر (idempotent).
لا تنشئ مستخدمين ولا بيانات وهمية؛ تُفعّل الأقسام وتضبط الرسوم والعمولة بقيم تحددها أنت صراحةً.

مثال:
  python3 setup_initial.py --region 3 --fee 15 --commission-type fixed --commission-value 2
  (القيم أعلاه مثال فقط، حدّد أرقامك الفعلية.)
لا يغيّر شيئًا موجودًا: الرسوم/العمولة تُكتب فقط إن لم تكن مضبوطة، إلا مع --overwrite.
"""
import argparse, sys
import server

SOUQ = [  # تصنيفات السوق الابتدائية وحقولها (قابلة للتعديل لاحقًا من لوحة الإدارة)
    ("souq-cars", "سيارات", [("price", "السعر", "price", 1), ("year", "سنة الصنع", "number", 0)]),
    ("souq-realestate", "عقارات", [("price", "السعر", "price", 1), ("area", "المساحة (م²)", "number", 0)]),
    ("souq-electronics", "أجهزة وإلكترونيات", [("price", "السعر", "price", 1)]),
    ("souq-furniture", "أثاث ومستعمل", [("price", "السعر", "price", 1)]),
]
def main():
    a = argparse.ArgumentParser(); a.add_argument("--region", type=int, required=True, help="رقم المنطقة (مركز الرياض = 3)")
    a.add_argument("--fee", type=float, required=True, help="رسوم التوصيل للعميل")
    a.add_argument("--commission-type", choices=("fixed", "percent"), required=True)
    a.add_argument("--commission-value", type=float, required=True, help="عمولة لاقينو")
    a.add_argument("--overwrite", action="store_true", help="اكتب الرسوم/العمولة حتى لو كانت مضبوطة")
    a.add_argument("--seed-market", action="store_true", help="ابذر 27 محافظة (غير مفعّلة) وتصنيفات السوق الإضافية (غير مفعّلة) عبر market_seed.py")
    a.add_argument("--activate-market-categories", action="store_true", help="مع --seed-market: فعّل التصنيفات المضافة حديثًا")
    o = a.parse_args()
    if o.fee < 0 or o.commission_value < 0 or (o.commission_type == "percent" and o.commission_value > 100): sys.exit("قيم غير صالحة")
    server.init(); c = server.db(); log = []
    if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (o.region,)).fetchone(): sys.exit("المنطقة غير موجودة أو غير مفعّلة")
    if o.overwrite or not c.execute("SELECT 1 FROM region_fees WHERE region_id=?", (o.region,)).fetchone():
        c.execute("INSERT INTO region_fees(region_id,fee) VALUES(?,?) ON CONFLICT(region_id) DO UPDATE SET fee=excluded.fee", (o.region, o.fee)); log.append("رسوم التوصيل: %s" % o.fee)
    if o.overwrite or not c.execute("SELECT 1 FROM settings WHERE key='commission_type'").fetchone():
        for k, v in (("commission_type", o.commission_type), ("commission_value", str(o.commission_value))):
            c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        log.append("العمولة: %s %s" % (o.commission_type, o.commission_value))
    for sec in ("souq", "delivery", "medical"):  # الخدمات تبقى مخفية حتى يوجد لها محتوى
        if c.execute("UPDATE categories SET is_active=1 WHERE section=? AND parent_id IS NULL AND is_active=0", (sec,)).rowcount: log.append("تفعيل قسم: " + sec)
    root = c.execute("SELECT id FROM categories WHERE section='souq' AND parent_id IS NULL").fetchone()["id"]
    for slug, nm, fields in SOUQ:
        if c.execute("SELECT 1 FROM categories WHERE slug=?", (slug,)).fetchone(): continue
        cid = c.execute("INSERT INTO categories(parent_id,section,slug,name_ar,is_active) VALUES(?,?,?,?,1)", (root, "souq", slug, nm)).lastrowid
        for i, (k, lb, t, req) in enumerate(fields): c.execute("INSERT INTO category_fields(category_id,key,label_ar,type,required,sort) VALUES(?,?,?,?,?,?)", (cid, k, lb, t, req, i))
        log.append("تصنيف سوق: " + nm)
    if o.activate_market_categories and not o.seed_market: sys.exit("--activate-market-categories يتطلب --seed-market")
    if o.seed_market:
        import market_seed
        r = market_seed.seed_all(c, o.activate_market_categories)
        if any(r.values()): log.append("بذر السوق: %(governorates_added)d محافظة، %(categories_added)d تصنيف، %(fields_added)d حقل" % r)
    server.audit(c, None, "setup.initial", str(o.region), {"log": log}); c.commit(); c.close()
    print("\n".join(log) or "لا تغييرات: التهيئة مطبّقة بالفعل")
if __name__ == "__main__": main()
