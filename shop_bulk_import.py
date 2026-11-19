# استيراد أصناف المحلات جماعيًا من Excel — إضافة فقط، على نفس جدول وصلاحيات أصناف المحل.
import base64, io, re, time, zipfile
import bulk_import
import shops

MAX_FILE = 5_000_000
MAX_ROWS = 1000
SHOW_ROWS = 300
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
AR = str.maketrans({"أ":"ا","إ":"ا","آ":"ا","ٱ":"ا","ة":"ه","ى":"ي","ؤ":"و","ئ":"ي"})
SYN = {
    "name": {"الاسم", "اسم الصنف", "الصنف", "اسم المنتج", "المنتج", "name", "item", "product"},
    "price": {"السعر", "سعر", "السعر بالجنيه", "السعر الأساسي", "سعر المنتج", "base price", "price"},
    "description": {"الوصف", "التفاصيل", "وصف الصنف", "description", "details"},
    "available": {"متاح", "متوفر", "حالة التوفر", "التوفر", "available", "availability", "in stock"},
    "category": {"القسم", "القسم (اختياري)", "القسم الاختياري", "التصنيف", "قسم الصنف", "category", "section"},
    "group_name": {"اسم المجموعة", "اسم الخاصية / المجموعة", "اسم الخاصية", "الخاصية", "مجموعة الاختيارات", "مجموعة", "option group", "group", "attribute", "attribute name"},
    "group_kind": {"نوع المجموعة", "نوع الاختيارات", "نوع الخيار", "نوع الاختيار", "نوع الاختيار (اختياري)", "طريقة الاختيار", "selection mode", "group type", "kind"},
    "option_name": {"الاختيار", "اسم الاختيار", "القيمة", "القيمة / الاختيار", "قيمة الخاصية", "option", "option name", "value", "attribute value"},
    "price_delta": {"فرق السعر", "فرق السعر بالجنيه", "زيادة السعر", "price delta", "delta"},
    "required": {"إلزامي", "إلزامي؟", "مطلوب", "اختيار إجباري", "required"},
}
YES = {"نعم", "ايوه", "ايوا", "متاح", "متوفر", "موجود", "yes", "y", "true", "1"}
NO = {"لا", "غير متاح", "غير متوفر", "نفد", "نفذ", "no", "n", "false", "0"}


CATEGORY_RULES = {
    "restaurants": [
        ("فول وطعمية", ("فول", "طعمية", "فلافل")),
        ("ساندوتشات", ("ساندوتش", "سندوتش", "شاورما", "كبدة", "سجق")),
        ("برجر", ("برجر", "burger")),
        ("بيتزا", ("بيتزا", "pizza")),
        ("مشويات", ("مشوي", "كباب", "كفتة", "ريش")),
        ("فراخ", ("فراخ", "دجاج", "بانيه", "شاورما فراخ")),
        ("كشري ومكرونة", ("كشري", "مكرونة", "اسباجتي", "لازانيا")),
        ("مقبلات", ("بطاطس", "سمبوسة", "سلطة", "مقبلات")),
        ("مشروبات", ("عصير", "مشروب", "مياه", "قهوة", "شاي", "نسكافيه", "كانز")),
        ("حلويات", ("حلويات", "كيك", "جاتوه", "بسبوسة", "كنافة", "مهلبية")),
    ],
    "sweets": [
        ("تورت وكيك", ("تورت", "كيك", "جاتوه")),
        ("حلويات شرقية", ("كنافة", "بسبوسة", "بقلاوة", "هريسة", "بلح الشام")),
        ("حلويات غربية", ("تشيز كيك", "دونات", "كوكيز", "براونيز")),
        ("آيس كريم", ("ايس كريم", "آيس كريم", "جيلاتي")),
        ("مشروبات", ("عصير", "مشروب", "قهوة", "شاي")),
    ],
    "supermarket": [
        ("مشروبات", ("مياه", "عصير", "مشروب", "كانز", "قهوة", "شاي")),
        ("ألبان وأجبان", ("لبن", "زبادي", "جبنة", "جبن", "قشطة", "زبدة")),
        ("زيوت وسمن", ("زيت", "سمن")),
        ("منظفات", ("مسحوق", "منظف", "صابون", "كلور", "مطهر", "سائل أطباق")),
        ("خضروات وفاكهة", ("طماطم", "بطاطس", "بصل", "تفاح", "موز", "برتقال")),
        ("مخبوزات", ("عيش", "خبز", "توست", "فينو", "كرواسون")),
        ("تسالي وسناكس", ("شيبسي", "شوكولاتة", "بسكويت", "لب", "مكسرات")),
        ("معلبات", ("تونة", "فول معلب", "صلصة", "معلب")),
    ],
    "clothing": [
        ("رجالي", ("رجالي", "رجاليه", "للرجال")),
        ("حريمي", ("حريمي", "نسائي", "للسيدات")),
        ("أطفال", ("أطفال", "اطفال", "ولادي", "بناتي")),
        ("أحذية", ("حذاء", "حذاء", "كوتشي", "شبشب", "جزمة")),
        ("إكسسوارات", ("إكسسوار", "اكسسوار", "حزام", "شنطة", "محفظة")),
    ],
}


def _has_category_term(text, word):
    term = shops._norm(word)
    if " " in term:
        return term in text
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.UNICODE) is not None


def _infer_category(slug, name):
    text = shops._norm(name)
    matches = []
    for category, words in CATEGORY_RULES.get(slug, []):
        if any(_has_category_term(text, word) for word in words):
            matches.append(category)
    return matches[0] if len(matches) == 1 else None


def _existing_category(c, shop_id, suggested):
    if not suggested:
        return None
    rows = c.execute("SELECT id,name_ar FROM shop_categories WHERE shop_id=? AND is_active=1", (shop_id,)).fetchall()
    if not rows:
        return suggested
    norm = shops._norm(suggested)
    for row in rows:
        if shops._norm(row["name_ar"]) == norm:
            return row["name_ar"]
    return None


def _ensure_category(c, shop_id, name, now):
    if not name:
        return None
    row = c.execute("SELECT id FROM shop_categories WHERE shop_id=? AND name_ar=? COLLATE NOCASE AND is_active=1", (shop_id, name)).fetchone()
    if row:
        return row["id"]
    count = c.execute("SELECT COUNT(*) FROM shop_categories WHERE shop_id=? AND is_active=1", (shop_id,)).fetchone()[0]
    if count >= 60:
        return None
    sort = c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM shop_categories WHERE shop_id=?", (shop_id,)).fetchone()[0]
    return c.execute("INSERT INTO shop_categories(shop_id,name_ar,sort,created_at,updated_at) VALUES(?,?,?,?,?)", (shop_id, name, sort, now, now)).lastrowid


class ImportError_(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def _header(rows):
    best = (None, {}, 0)
    for ri, row in enumerate(rows[:10]):
        cols = {}
        for ci, value in enumerate(row):
            key = re.sub(r"\s+", " ", str(value or "").strip()).translate(AR).casefold()
            for field, names in SYN.items():
                norm_names = {re.sub(r"\s+", " ", x).translate(AR).casefold() for x in names}
                if field not in cols and key in norm_names:
                    cols[field] = ci
                    break
        if len(cols) > best[2]:
            best = (ri, cols, len(cols))
    return (best[0], best[1]) if "name" in best[1] and "price" in best[1] else (None, {})


def _price(raw):
    s = str(raw or "").translate(DIGITS).strip().replace("٫", ".").replace("٬", "")
    if s.endswith("جنيه"):
        s = s[:-4].strip()
    try:
        return shops._price(s)
    except (ValueError, TypeError):
        raise ValueError("السعر غير صالح؛ اكتب رقمًا أكبر من صفر وحتى 1,000,000")


def _available(raw):
    s = re.sub(r"\s+", " ", str(raw or "").strip()).translate(AR).casefold()
    if not s:
        return True
    if s in YES:
        return True
    if s in NO:
        return False
    raise ValueError("حالة التوفر اكتبها نعم أو لا")


def _infer_group_kind(group_name):
    """Infer the interaction mode from a free-form attribute label; never infer from the option value."""
    label = shops._norm(group_name)
    multi_terms = (
        "اضافات", "اضافة", "التوبينج", "توبينج", " toppings", "topping", "extras",
        "extra", "add on", "addon", "اختيارات متعددة", "متعدد", "المكونات الاضافية",
        "الصوصات", "الصوص", "الصلصات", "الجبن الاضافي", "الاضافات"
    )
    single_terms = (
        "الحجم", "حجم", "المقاس", "مقاس", "اللون", "لون", "النوع", "نوع",
        "الخامة", "خامه", "السعة", "سعة", "النكهة", "نكهة", "الوزن", "وزن",
        "عدد القطع", "المادة", "الموديل", "الشكل", "الرائحة", "التركيز",
        "size", "color", "colour", "material", "capacity", "flavor", "flavour",
        "weight", "model", "type"
    )
    if any(shops._norm(term) in label for term in multi_terms):
        return "addon"
    if any(shops._norm(term) in label for term in single_terms):
        return "variant"
    # Conservative fallback: a named attribute is treated as a single-choice group.
    # The preview keeps this inference visible so an admin can correct it explicitly.
    return "variant"


def _group_kind(group_name, explicit):
    raw = shops._norm(explicit)
    aliases = {
        "variant": "variant", "single": "variant", "single select": "variant",
        "one": "variant", "اختيار واحد": "variant", "واحد": "variant",
        "مفرد": "variant", "حجم": "variant", "مقاس": "variant", "نوع": "variant",
        "addon": "addon", "add-on": "addon", "multi": "addon", "multiple": "addon",
        "multi select": "addon", "اختيارات متعددة": "addon", "اختيار متعدد": "addon",
        "متعدد": "addon", "إضافة": "addon", "اضافة": "addon", "إضافات": "addon",
        "اضافات": "addon"
    }
    aliases = {shops._norm(key): value for key, value in aliases.items()}
    if not raw:
        return _infer_group_kind(group_name)
    kind = aliases.get(raw)
    if kind not in ("variant", "addon"):
        raise ValueError("نوع الاختيار غير مفهوم؛ اتركه فارغًا ليحدده النظام أو اكتب اختيار واحد / اختيارات متعددة")
    return kind


def plan(c, shop_id, raw):
    shop = c.execute("SELECT s.id,s.status,s.type_id,t.slug,t.require_image FROM shops s JOIN shop_types t ON t.id=s.type_id WHERE s.id=?", (shop_id,)).fetchone()
    if not shop:
        raise ImportError_(404, "المحل غير موجود")
    if shop["status"] != "approved":
        raise ImportError_(409, "لا يمكن إضافة أصناف إلا لمحل معتمد")
    if len(raw) > MAX_FILE:
        raise ImportError_(413, "الملف كبير (الحد 5 ميجابايت)")
    try:
        sheets = bulk_import.read_xlsx(raw)
    except bulk_import.Bad as e:
        raise ImportError_(e.code, e.msg)
    selected = None
    for sheet_name, rows in sheets:
        hi, cols = _header(rows)
        if hi is not None:
            selected = (sheet_name, rows, hi, cols)
            break
    if selected is None:
        raise ImportError_(400, "لم أجد صف عناوين يحتوي على اسم الصنف والسعر الأساسي. حمّل النموذج واستخدمه.")
    sheet_name, rows, hi, cols = selected
    if len(rows) - hi - 1 > MAX_ROWS:
        raise ImportError_(413, "عدد الصفوف كبير (الحد 1000 صف لكل ملف)")
    current = c.execute("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active'", (shop_id,)).fetchone()[0]
    existing = {shops._norm(r["name_ar"]) for r in c.execute("SELECT name_ar FROM shop_items WHERE shop_id=? AND status='active'", (shop_id,))}
    products, row_errors = {}, []
    for ri in range(hi + 1, len(rows)):
        row = rows[ri]
        if not any(str(x or "").strip() for x in row):
            continue
        get = lambda field: str(row[cols[field]] if field in cols and cols[field] < len(row) else "").strip()
        item = {"row": ri + 1, "name": get("name"), "status": "error", "message": ""}
        norm = None
        try:
            name = shops._text(item["name"], "اسم الصنف", 2, 80)
            norm = shops._norm(name)
            price = _price(get("price"))
            desc_raw = get("description")
            desc = None if not desc_raw else shops._text(desc_raw, "الوصف", 1, 500)
            available = _available(get("available"))
            explicit_category = get("category")
            if explicit_category:
                category_name = shops._text(explicit_category, "اسم القسم", 2, 50)
            else:
                category_name = _existing_category(c, shop_id, _infer_category(shop["slug"], name))
            group_name, option_name = get("group_name"), get("option_name")
            if bool(group_name) != bool(option_name):
                raise ValueError("لازم تكتب اسم المجموعة والاختيار معًا")
            group = None
            if group_name:
                group = shops._text(group_name, "اسم مجموعة الاختيارات", 2, 50)
                option_name = shops._text(option_name, "اسم الاختيار", 1, 50)
                kind = _group_kind(group, get("group_kind"))
                req_raw = get("required").strip()
                if req_raw:
                    required = _available(req_raw)
                else:
                    required = kind == "variant"
                if kind == "addon" and required:
                    raise ValueError("مجموعة الإضافات المتعددة لا يمكن جعلها إجبارية")
                delta_raw = get("price_delta")
                try:
                    delta = 0.0 if not delta_raw else float(str(delta_raw).translate(DIGITS).replace("٫", ".").replace("٬", ""))
                except (TypeError, ValueError, OverflowError):
                    raise ValueError("فرق السعر غير صالح")
                if delta != delta or abs(delta) > 100000:
                    raise ValueError("فرق السعر غير صالح")
                delta = round(delta, 2)
            else:
                kind, required, delta = None, False, 0.0
            if norm not in products:
                products[norm] = {"row": item["row"], "rows": [item["row"]], "name": name, "price": price,
                    "description": desc, "is_available": available, "category_name": category_name,
                    "groups": [], "row_mode": "grouped" if group else "plain", "status": "new", "message": "جاهز للإضافة"}
            product = products[norm]
            if product["row_mode"] != ("grouped" if group else "plain"):
                raise ValueError("لا تخلط صفوف المنتج العادي مع صفوف خياراته؛ استخدم صفوف الخيارات كلها أو صفًا عاديًا واحدًا")
            if product["row"] != item["row"] and not group and not product["groups"]:
                row_errors.append({"row": item["row"], "name": name, "product_norm": norm, "status": "duplicate", "message": "اسم المنتج مكرر داخل الملف بدون مجموعة اختيارات"})
                continue
            if product["row"] != item["row"] and item["row"] not in product["rows"]:
                product["rows"].append(item["row"])
            if product["price"] != price or product["description"] != desc or product["is_available"] != available or product["category_name"] != category_name:
                raise ValueError("بيانات المنتج الأساسية مختلفة بين صفوف المنتج الواحد")
            if group:
                norm_group = shops._norm(group)
                target = next((g for g in product["groups"] if shops._norm(g["name_ar"]) == norm_group), None)
                if target is None:
                    target = {"name_ar": group, "kind": kind, "required": required, "values": []}
                    product["groups"].append(target)
                elif target["kind"] != kind or target["required"] != required:
                    raise ValueError("نوع المجموعة أو إلزاميتها غير متطابق بين صفوفها")
                if any(shops._norm(v["name_ar"]) == shops._norm(option_name) for v in target["values"]):
                    raise ValueError("اختيار مكرر داخل المجموعة")
                target["values"].append({"name_ar": option_name, "price_delta": delta})
                if len(target["values"]) > 20:
                    raise ValueError("كل مجموعة تسمح بحد أقصى 20 اختيارًا")
                if sum(len(g["values"]) for g in product["groups"]) > 40:
                    raise ValueError("الحد الأقصى 40 اختيارًا للمنتج")
                if len(product["groups"]) > 10:
                    raise ValueError("الحد الأقصى 10 مجموعات للمنتج")
            elif product["groups"]:
                raise ValueError("لا تخلط صفوف المنتج العادي مع صفوف خياراته")
        except (ValueError, TypeError, OverflowError) as e:
            row_errors.append({"row": item["row"], "name": item["name"], "product_norm": norm, "status": "error", "message": str(e)})
    items = []
    for norm, product in products.items():
        if norm in existing:
            product.update(status="duplicate", message="المنتج موجود بالفعل في المحل؛ تم تخطيه")
        elif shop["require_image"]:
            product.update(status="error", message="هذا النوع من المحلات يشترط صورة لكل صنف؛ أضف الصورة من لوحة صاحب المحل")
        elif any(x.get("product_norm") == norm for x in row_errors if x["status"] == "error"):
            details = [x for x in row_errors if x.get("product_norm") == norm and x["status"] == "error"]
            product.update(status="error", message="خطأ في صف %s: %s؛ لم يتم استيراد المنتج" % (details[0]["row"], details[0]["message"]))
        items.append(product)
        existing.add(norm)
    # Keep row-level diagnostics only when no product summary row represents that name.
    items.extend(x for x in row_errors if x["status"] == "duplicate" or x.get("product_norm") not in products)
    remaining = max(0, shops.MAX_ITEMS - current)
    accepted = 0
    for item in items:
        if item["status"] != "new":
            continue
        if accepted >= remaining:
            item["status"], item["message"] = "error", "تم الوصول للحد الأقصى (300 صنف نشط للمحل)"
        else:
            accepted += 1
    return {"shop_id": shop_id, "items": items, "current": current, "remaining": remaining,
            "require_image": bool(shop["require_image"]), "sheet": sheet_name}


def summary(p):
    counts = {k: 0 for k in ("new", "duplicate", "error")}
    option_groups = option_values = 0
    for item in p["items"]:
        if item["status"] in counts:
            counts[item["status"]] += 1
        if item["status"] == "new":
            option_groups += len(item.get("groups", []))
            option_values += sum(len(g["values"]) for g in item.get("groups", []))
    shown = p["items"][:SHOW_ROWS]
    return {"shop_id": p["shop_id"], "sheet": p["sheet"], "current_items": p["current"],
            "remaining_slots": p["remaining"], "require_image": p["require_image"],
            "summary": counts, "option_groups": option_groups, "option_values": option_values,
            "truncated": len(p["items"]) > SHOW_ROWS,
            "items": [{"row": x["row"], "rows": x.get("rows", [x["row"]]), "name": x["name"],
                       "price": x.get("price", ""), "status": x["status"], "message": x["message"],
                       "category_name": x.get("category_name"), "option_groups": len(x.get("groups", [])),
                       "option_values": sum(len(g["values"]) for g in x.get("groups", []))} for x in shown]}


def template_xlsx():
    rows = [
        ["اسم الصنف", "السعر الأساسي", "الوصف", "متاح", "القسم (اختياري)", "اسم الخاصية / المجموعة", "نوع الاختيار (اختياري)", "القيمة / الاختيار", "فرق السعر", "إلزامي؟"],
        ["بيتزا", "100", "السعر الأساسي قبل الاختيارات", "نعم", "بيتزا", "الحجم", "", "صغير", "0", "نعم"],
        ["بيتزا", "100", "السعر الأساسي قبل الاختيارات", "نعم", "بيتزا", "الحجم", "", "وسط", "20", "نعم"],
        ["بيتزا", "100", "السعر الأساسي قبل الاختيارات", "نعم", "بيتزا", "الحجم", "", "كبير", "40", "نعم"],
        ["بيتزا", "100", "السعر الأساسي قبل الاختيارات", "نعم", "بيتزا", "إضافات", "", "جبنة إضافية", "15", "لا"],
        ["بيتزا", "100", "السعر الأساسي قبل الاختيارات", "نعم", "بيتزا", "إضافات", "", "زيتون", "8", "لا"],
        ["قميص", "250", "السعر الأساسي قبل الاختيارات", "نعم", "ملابس", "اللون", "", "أسود", "0", "نعم"],
        ["قميص", "250", "السعر الأساسي قبل الاختيارات", "نعم", "ملابس", "اللون", "", "أبيض", "0", "نعم"],
        ["قميص", "250", "السعر الأساسي قبل الاختيارات", "نعم", "ملابس", "المقاس", "", "XL", "20", "نعم"],
        ["قميص", "250", "السعر الأساسي قبل الاختيارات", "نعم", "ملابس", "المقاس", "", "XXL", "35", "نعم"],
        ["قميص", "250", "السعر الأساسي قبل الاختيارات", "نعم", "ملابس", "إضافات", "", "تغليف هدية", "10", "لا"],
        ["برجر", "65", "منتج عادي بدون خيارات", "نعم", "برجر", "", "", "", "", ""],
    ]
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
    root = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="الأصناف" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", root)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/worksheets/sheet1.xml", bulk_import._sheet_xml(rows, [24, 14, 30, 12, 22, 24, 22, 18, 14, 12]))
    return b.getvalue()


def handle(h, c, u, method, path, q):
    prefix = "/api/admin/shops/items-import"
    if not path.startswith(prefix):
        return False
    if not u:
        h.send(401, {"error": "سجّل الدخول أولًا"})
        return True
    if u["role"] not in ("admin", "staff"):
        h.send(403, {"error": "ليس لديك صلاحية"})
        return True
    if method == "GET" and path == prefix + "/template":
        h.send(200, {"name": "laqino-shop-items-template.xlsx",
                     "data": base64.b64encode(template_xlsx()).decode()})
        return True
    if method != "POST" or path not in (prefix + "/preview", prefix + "/commit"):
        h.send(404, {"error": "غير موجود"})
        return True
    try:
        d = h.body(8_000_000)
        try:
            shop_id = int(d.get("shop_id"))
            if isinstance(d.get("shop_id"), bool) or shop_id < 1:
                raise ValueError
        except (TypeError, ValueError):
            raise ImportError_(400, "اختر محلًا صحيحًا")
        try:
            raw = base64.b64decode(str(d.get("data", "")), validate=True)
        except Exception:
            raise ImportError_(400, "ملف Excel غير صالح")
        if path.endswith("/preview"):
            p = plan(c, shop_id, raw)
            h.send(200, summary(p))
            return True
        c.execute("BEGIN IMMEDIATE")
        p = plan(c, shop_id, raw)
        ready = [x for x in p["items"] if x["status"] == "new"]
        if not ready:
            raise ImportError_(409, "لا توجد أصناف صالحة للإضافة؛ راجع الأخطاء والتكرارات")
        now = int(time.time())
        inserted = inserted_groups = inserted_options = 0
        for item in ready:
            category_id = _ensure_category(c, shop_id, item.get("category_name"), now)
            sort = c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM shop_items WHERE shop_id=?", (shop_id,)).fetchone()[0]
            cur = c.execute("INSERT INTO shop_items(shop_id,name_ar,description,price,is_available,sort,status,category_id,created_at,updated_at) VALUES(?,?,?,?,?,?, 'active',?,?,?)",
                            (shop_id, item["name"], item["description"], item["price"], int(item["is_available"]),
                             sort, category_id, now, now))
            item_id = cur.lastrowid
            for gi, group in enumerate(item.get("groups", []), 1):
                inserted_groups += 1
                for vi, value in enumerate(group["values"], 1):
                    c.execute("INSERT INTO shop_item_options(shop_id,item_id,group_name,group_kind,option_name,price_delta,is_required,group_sort,sort,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                              (shop_id, item_id, group["name_ar"], group["kind"], value["name_ar"], value["price_delta"],
                               int(group["required"]), gi, vi, now, now))
                    inserted_options += 1
            inserted += 1
        audit = shops._H.get("audit")
        if audit:
            audit(c, u["id"], "shopitem.bulk_import", shop_id, {"count": inserted, "source": "xlsx"})
        c.commit()
        out = summary(p)
        out["done"] = {"inserted": inserted, "option_groups": inserted_groups, "option_values": inserted_options}
        h.send(200, out)
        return True
    except ImportError_ as e:
        c.rollback()
        h.send(e.code, {"error": e.message})
        return True
    except Exception:
        c.rollback()
        h.send(500, {"error": "تعذّر استيراد الأصناف؛ لم يتم حفظ أي تغييرات"})
        return True
