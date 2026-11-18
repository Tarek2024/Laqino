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
    "price": {"السعر", "سعر", "السعر بالجنيه", "price"},
    "description": {"الوصف", "التفاصيل", "وصف الصنف", "description", "details"},
    "available": {"متاح", "متوفر", "حالة التوفر", "التوفر", "available", "availability", "in stock"},
}
YES = {"نعم", "ايوه", "ايوا", "متاح", "متوفر", "موجود", "yes", "y", "true", "1"}
NO = {"لا", "غير متاح", "غير متوفر", "نفد", "نفذ", "no", "n", "false", "0"}


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


def plan(c, shop_id, raw):
    shop = c.execute("SELECT s.id,s.status,s.type_id,t.require_image FROM shops s JOIN shop_types t ON t.id=s.type_id WHERE s.id=?", (shop_id,)).fetchone()
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
        raise ImportError_(400, "لم أجد صف عناوين يحتوي على «اسم الصنف» و«السعر». حمّل النموذج واستخدمه.")
    sheet_name, rows, hi, cols = selected
    if len(rows) - hi - 1 > MAX_ROWS:
        raise ImportError_(413, "عدد الصفوف كبير (الحد 1000 صف لكل ملف)")
    current = c.execute("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active'", (shop_id,)).fetchone()[0]
    existing = {shops._norm(r["name_ar"]) for r in c.execute("SELECT name_ar FROM shop_items WHERE shop_id=? AND status='active'", (shop_id,))}
    seen, items = set(), []
    for ri in range(hi + 1, len(rows)):
        row = rows[ri]
        if not any(str(x or "").strip() for x in row):
            continue
        get = lambda field: str(row[cols[field]] if field in cols and cols[field] < len(row) else "").strip()
        item = {"row": ri + 1, "name": get("name"), "status": "error", "message": ""}
        items.append(item)
        try:
            name = shops._text(item["name"], "اسم الصنف", 2, 80)
            price = _price(get("price"))
            desc_raw = get("description")
            desc = None if not desc_raw else shops._text(desc_raw, "الوصف", 1, 500)
            available = _available(get("available"))
            norm = shops._norm(name)
            if norm in seen:
                item.update(status="duplicate", message="مكرر داخل الملف")
                continue
            seen.add(norm)
            if norm in existing:
                item.update(status="duplicate", message="الصنف موجود بالفعل في المحل؛ تم تخطيه")
                continue
            if shop["require_image"]:
                item["message"] = "هذا النوع من المحلات يشترط صورة لكل صنف؛ أضف الصورة من لوحة صاحب المحل"
                continue
            item.update(status="new", message="جاهز للإضافة", name=name, price=price, description=desc, is_available=available)
            existing.add(norm)
        except ValueError as e:
            item["message"] = str(e)
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
    for item in p["items"]:
        counts[item["status"]] += 1
    shown = p["items"][:SHOW_ROWS]
    return {"shop_id": p["shop_id"], "sheet": p["sheet"], "current_items": p["current"],
            "remaining_slots": p["remaining"], "require_image": p["require_image"],
            "summary": counts, "truncated": len(p["items"]) > SHOW_ROWS,
            "items": [{"row": x["row"], "name": x["name"], "price": x.get("price", ""),
                       "status": x["status"], "message": x["message"]} for x in shown]}


def template_xlsx():
    rows = [["اسم الصنف", "السعر", "الوصف", "متاح"],
            ["كشري كبير", "45.50", "طبق كبير", "نعم"],
            ["عصير مانجو", "25", "حجم 300 مل", "نعم"],
            ["مياه معدنية", "10", "", "لا"]]
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
        z.writestr("xl/worksheets/sheet1.xml", bulk_import._sheet_xml(rows, [24, 14, 30, 12]))
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
        inserted = 0
        for item in ready:
            cur = c.execute("INSERT INTO shop_items(shop_id,name_ar,description,price,is_available,sort,status,created_at,updated_at) VALUES(?,?,?,?,?,?, 'active',?,?)",
                            (shop_id, item["name"], item["description"], item["price"], int(item["is_available"]),
                             c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM shop_items WHERE shop_id=?", (shop_id,)).fetchone()[0],
                             now, now))
            inserted += 1
        audit = shops._H.get("audit")
        if audit:
            audit(c, u["id"], "shopitem.bulk_import", shop_id, {"count": inserted, "source": "xlsx"})
        c.commit()
        out = summary(p)
        out["done"] = {"inserted": inserted}
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
