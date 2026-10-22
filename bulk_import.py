# لاقينو — استيراد الأطباء والمعامل من ملف Excel (المرحلة 23).
# وحدة مستقلة بنمط notif.py/chat.py/svc.py: لا تستورد server.py، وتُربط بسطرين (handle + حقن norm_ar/audit). بلا مكتبات خارجية (zipfile + xml من المكتبة القياسية).
# إضافة فقط: لا جداول جديدة، لا تغيير في أي مسار قائم. تكتب في جداول doctors/labs/specialties نفسها بنفس قواعد النموذج اليدوي.
#   إدارة (admin فقط):
#     GET  /api/admin/import/template                     -> {name, data(base64 xlsx)}  نموذج جاهز بصفحتين «الأطباء» و«المعامل»
#     POST /api/admin/import/preview {data, default_region_id?, update_existing?}   معاينة بلا أي كتابة
#     POST /api/admin/import/commit  {data, default_region_id?, update_existing?, publish?}   تنفيذ في معاملة واحدة (كله أو لا شيء)
# القواعد:
#   - كل صف جديد يُحفظ «غير منشور» (كالإضافة اليدوية) إلا إن طلبت publish، وعندها يُنشر المكتمل فقط (نفس شروط النشر اليدوي).
#   - التخصصات الناقصة تُنشأ تلقائيًا؛ المنطقة تُطابَق بالاسم على المناطق المفعّلة فقط (والمكرر يحتاج عمود «المركز/المحافظة» أو منطقة افتراضية).
#   - المكرر (طبيب: الاسم+التخصص+المنطقة، معمل: الاسم+المنطقة) يُتخطّى، أو يُحدَّث بالخلايا غير الفارغة فقط إن اخترت update_existing. لا حذف أبدًا.
import base64, io, re, time, zipfile
import xml.etree.ElementTree as ET

norm_ar = None   # server.py يحقنها (نفس تطبيع الاسم المستخدم في الإضافة اليدوية)
audit = None     # server.py يحقنها (سجل التدقيق)

MAX_FILE, MAX_UNZIPPED, MAX_ROWS, SHOW_ROWS = 5_000_000, 40_000_000, 1000, 400
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})
_DIG = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


class Bad(Exception):
    def __init__(self, code, msg): self.code, self.msg = code, msg


def hn(s):
    """تطبيع للعناوين وأسماء المناطق (بلا إسقاط «د» من أول الاسم)."""
    s = re.sub(r"[ً-ٰٟـ]", "", str(s or "")).translate(_AR).lower()
    return re.sub(r"[^\w]+", " ", s).strip()


def _syn(*xs): return {hn(x) for x in xs}


COLS_DOC = {
    "name": _syn("الاسم", "اسم الطبيب", "الطبيب", "اسم الدكتور", "الدكتور", "name"),
    "specialty": _syn("التخصص", "القسم", "الاختصاص", "التخصص الطبي", "تخصص", "specialty", "department"),
    "region": _syn("المنطقة", "البلد", "البلدة", "القرية", "المدينة", "region", "city"),
    "parent": _syn("المركز", "المحافظة", "التابع لـ", "تابع ل", "تابعة ل", "parent"),
    "clinic": _syn("العيادة", "اسم العيادة", "المكان", "clinic"),
    "address": _syn("العنوان", "address"),
    "schedule": _syn("المواعيد", "التواجد", "مواعيد التواجد", "أيام التواجد", "مواعيد الحضور", "أوقات التواجد", "أيام وساعات التواجد", "مواعيد العمل", "schedule", "hours"),
    "phone": _syn("الهاتف", "رقم الهاتف", "التليفون", "رقم التليفون", "تليفون", "هاتف", "الموبايل", "رقم الموبايل", "المحمول", "phone", "mobile"),
    "whatsapp": _syn("واتساب", "واتس اب", "الواتساب", "رقم الواتساب", "رقم واتساب", "whatsapp"),
    "bio": _syn("نبذة", "معلومات", "ملاحظات", "bio", "notes"),
}
COLS_LAB = {
    "name": _syn("اسم المعمل", "المعمل", "الاسم", "name"),
    "region": COLS_DOC["region"], "parent": COLS_DOC["parent"], "address": COLS_DOC["address"],
    "schedule": COLS_DOC["schedule"], "phone": COLS_DOC["phone"], "whatsapp": COLS_DOC["whatsapp"],
    "tests": _syn("التحاليل", "التحاليل المتاحة", "الفحوصات", "الخدمات", "tests"),
    "home": _syn("سحب منزلي", "سحب عينات منزلي", "سحب عينات", "زيارة منزلية", "خدمة منزلية", "home"),
}
LABELS = {"name": "الاسم", "specialty": "التخصص", "region": "المنطقة", "parent": "المركز", "clinic": "العيادة", "address": "العنوان", "schedule": "المواعيد",
          "phone": "الهاتف", "whatsapp": "واتساب", "bio": "نبذة", "tests": "التحاليل", "home": "سحب منزلي"}


# ---------------------------------------------------------------- قراءة xlsx (مكتبة قياسية فقط)
def _xml(z, name):
    b = z.read(name)
    if b"<!DOCTYPE" in b[:2048].upper() or b"<!ENTITY" in b.upper(): raise Bad(400, "الملف غير صالح")
    return ET.fromstring(b)


def _num(v):
    v = v.strip()
    try:
        f = float(v)
        if f == int(f) and abs(f) < 1e15: return str(int(f))
    except (ValueError, OverflowError): pass
    return v


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Za-z]+", ref).group(0).upper(): n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(raw):
    """-> [(sheet_name, [[cell str, ...], ...])] بالترتيب."""
    if len(raw) > MAX_FILE: raise Bad(413, "الملف كبير (الحد 5 ميجابايت)")
    try: z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile: raise Bad(400, "الملف ليس Excel بصيغة xlsx (احفظه من Excel كـ «مصنف Excel .xlsx»)")
    if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED: raise Bad(413, "الملف كبير بعد فك الضغط")
    names = set(z.namelist())
    if "xl/workbook.xml" not in names: raise Bad(400, "الملف ليس مصنف Excel صالحًا")
    try:
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in _xml(z, "xl/sharedStrings.xml").iter(NS + "si"): shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for r in _xml(z, "xl/_rels/workbook.xml.rels"):
                t = r.get("Target", ""); rels[r.get("Id")] = t.lstrip("/") if t.startswith("/") else "xl/" + t
        out = []
        for s in _xml(z, "xl/workbook.xml").iter(NS + "sheet"):
            path = rels.get(s.get(RNS + "id"))
            if not path or path not in names: continue
            rows = []
            for row in _xml(z, path).iter(NS + "row"):
                cells = {}
                for cel in row.findall(NS + "c"):
                    t = cel.get("t"); v = cel.find(NS + "v"); val = ""
                    if t == "s" and v is not None and v.text is not None: val = shared[int(v.text)] if int(v.text) < len(shared) else ""
                    elif t == "inlineStr": val = "".join(x.text or "" for x in cel.iter(NS + "t"))
                    elif t == "str" and v is not None: val = v.text or ""
                    elif t == "b" and v is not None: val = "1" if (v.text or "") == "1" else "0"
                    elif t == "e": val = ""
                    elif v is not None and v.text is not None: val = _num(v.text)
                    if val != "": cells[_col(cel.get("r", "A1"))] = val.strip()
                try: rn = int(row.get("r") or 0)
                except ValueError: rn = 0
                while rn and len(rows) < rn - 1: rows.append([])   # Excel لا يكتب الصفوف الفارغة: نحافظ على رقم الصف الحقيقي
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
                if len(rows) > MAX_ROWS + 60: raise Bad(413, "عدد الصفوف كبير (الحد %d صف لكل صفحة)" % MAX_ROWS)
            out.append((s.get("name", ""), rows))
        return out
    except Bad: raise
    except (ET.ParseError, KeyError, ValueError, IndexError, AttributeError): raise Bad(400, "تعذّرت قراءة الملف، تأكد أنه xlsx سليم")


def _header(rows, spec):
    """أفضل صف عناوين في أول 10 صفوف -> (index, {field: col}) أو (None, {})."""
    best = (None, {}, 0)
    for i, r in enumerate(rows[:10]):
        m = {}
        for ci, h in enumerate(r):
            k = hn(h)
            for f, syn in spec.items():
                if f not in m and k in syn: m[f] = ci; break
        if len(m) > best[2]: best = (i, m, len(m))
    return (best[0], best[1]) if best[2] >= 2 and "name" in best[1] else (None, {})


def _kind(name, rows):
    n = hn(name)
    if re.search(r"طبيب|اطباء|دكتور|دكاتر|doctor", n): return "doctors"
    if re.search(r"معمل|معامل|تحليل|lab", n): return "labs"
    hd, hl = _header(rows, COLS_DOC), _header(rows, COLS_LAB)
    if hd[0] is not None and "specialty" in hd[1]: return "doctors"
    if hl[0] is not None and ("tests" in hl[1] or "home" in hl[1]): return "labs"
    return None


# ---------------------------------------------------------------- تنظيف الحقول
def _phone(raw):
    """-> (رقم أو "", تحذير أو "", خطأ أو "")"""
    raw = str(raw or "").translate(_DIG).strip()
    if not raw: return "", "", ""
    parts = [p for p in re.split(r"[/,،;؛\n|]+", raw) if p.strip()]
    s = re.sub(r"[\s\-().]", "", parts[0])
    if s.startswith("0020"): s = "+" + s[2:]
    elif re.fullmatch(r"20\d{10}", s): s = "+" + s
    elif re.fullmatch(r"1[0125]\d{8}", s): s = "0" + s        # Excel يحذف الصفر الأول من الأرقام
    if not re.fullmatch(r"\+?\d{7,15}", s): return "", "", "رقم غير صالح: " + parts[0][:25]
    return s, ("أكثر من رقم في الخلية: اعتُمد الأول فقط" if len(parts) > 1 else ""), ""


def _yes(v): return hn(v) in {"نعم", "yes", "y", "1", "true", "ايوه", "ايوا", "يوجد", "متاح", "متوفر", "موجود"}


def _cut(s, n): return re.sub(r"[ \t]+", " ", str(s or "")).strip()[:n]


def _strip_pre(k): return re.sub(r"^(قريه|مركز|مدينه|محافظه|حي|عزبه|نجع|كفر)\s+", "", k)


class Regions:
    def __init__(self, c):
        rows = {r["id"]: r for r in c.execute("SELECT id,parent_id,name_ar,is_active FROM regions")}
        self.idx = {}
        for r in rows.values():
            anc, p, guard = set(), r["parent_id"], 0
            while p and p in rows and guard < 8: anc.add(hn(rows[p]["name_ar"])); p = rows[p]["parent_id"]; guard += 1
            e = {"id": r["id"], "active": bool(r["is_active"]), "anc": anc}
            k = hn(r["name_ar"])
            for key in {k, _strip_pre(k)}: self.idx.setdefault(key, []).append(e)

    def find(self, name, parent=""):
        k = hn(name)
        cands = self.idx.get(k) or self.idx.get(_strip_pre(k)) or []
        if not cands: return None, "المنطقة غير موجودة: " + _cut(name, 40)
        if parent:
            pk = hn(parent); f = [x for x in cands if pk in x["anc"] or _strip_pre(pk) in {_strip_pre(a) for a in x["anc"]}]
            if f: cands = f
        act = [x for x in cands if x["active"]]
        if not act: return None, "المنطقة غير مفعّلة: " + _cut(name, 40)
        if len(act) > 1: return None, "اسم المنطقة مكرر (%d)؛ أضف عمود «المركز» أو «المحافظة» أو اختر منطقة افتراضية" % len(act)
        return act[0]["id"], ""


# ---------------------------------------------------------------- الخطة (نفسها للمعاينة والتنفيذ)
def plan(c, raw, default_region=None, update_existing=False):
    sheets = read_xlsx(raw)
    regions = Regions(c)
    if default_region is not None and not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (default_region,)).fetchone():
        raise Bad(400, "المنطقة الافتراضية غير مفعّلة")
    specs = {}   # name_norm -> (id|None, name, active)
    for r in c.execute("SELECT id,name_ar,name_norm,is_active FROM specialties"): specs[r["name_norm"]] = [r["id"], r["name_ar"], r["is_active"]]
    new_specs, items, notes = {}, [], []
    used = {"doctors": False, "labs": False}
    ex_doc = {(r["name_norm"], r["specialty_id"], r["region_id"]): r for r in c.execute("SELECT * FROM doctors")}
    ex_lab = {(r["name_norm"], r["region_id"]): r for r in c.execute("SELECT * FROM labs")}
    seen = set()
    for sname, rows in sheets:
        kind = _kind(sname, rows)
        if not kind: notes.append("تم تجاهل الصفحة «%s» (لم أتعرف عليها كأطباء أو معامل)" % sname); continue
        spec = COLS_DOC if kind == "doctors" else COLS_LAB
        hi, cm = _header(rows, spec)
        if hi is None: notes.append("الصفحة «%s»: لم أجد صف العناوين (يلزم عمود الاسم وعمود آخر على الأقل)" % sname); continue
        used[kind] = True
        known = {x for f, i in cm.items() for x in [i]}
        unk = [h for i, h in enumerate(rows[hi]) if h and i not in known]
        if unk: notes.append("الصفحة «%s»: أعمدة لم تُستخدم: %s" % (sname, "، ".join(_cut(x, 25) for x in unk[:6])))
        if kind == "doctors" and "specialty" not in cm: notes.append("الصفحة «%s»: لا يوجد عمود «التخصص»، سيُرفض كل الصفوف" % sname)
        if "region" not in cm and default_region is None: notes.append("الصفحة «%s»: لا يوجد عمود «المنطقة»، اختر منطقة افتراضية" % sname)
        g = lambda r, f: (r[cm[f]] if f in cm and cm[f] < len(r) else "").strip()
        for ri in range(hi + 1, len(rows)):
            r = rows[ri]
            if not any(x for x in r): continue
            it = {"kind": kind, "sheet": sname, "row": ri + 1, "name": _cut(g(r, "name"), 120), "status": "error", "msg": "", "warn": []}
            items.append(it)
            if len(it["name"]) < 3: it["msg"] = "الاسم مطلوب (3 أحرف على الأقل)"; continue
            region_txt = g(r, "region")
            if region_txt: rid, why = regions.find(region_txt, g(r, "parent"))
            elif default_region is not None: rid, why = default_region, ""
            else: rid, why = None, "المنطقة مطلوبة"
            if rid is None: it["msg"] = why; continue
            it["region"] = region_txt or "(افتراضية)"
            ph, w1, e1 = _phone(g(r, "phone")); wa, w2, e2 = _phone(g(r, "whatsapp"))
            if e1 or e2: it["msg"] = e1 or ("واتساب: " + e2); continue
            it["warn"] += [w for w in (w1, ("واتساب: " + w2) if w2 else "") if w]
            sch = _cut(g(r, "schedule"), 500)
            if re.fullmatch(r"0\.\d+", sch): it["warn"].append("المواعيد تبدو وقتًا بتنسيق Excel؛ اكتبها كنص")
            if kind == "doctors":
                sp = _cut(g(r, "specialty"), 60)
                if len(sp) < 2: it["msg"] = "التخصص مطلوب"; continue
                it["specialty"] = sp; sk = norm_ar(sp)
                vals = {"clinic_name": _cut(g(r, "clinic"), 120), "address": _cut(g(r, "address"), 300), "schedule": sch, "phone": ph, "whatsapp": wa, "bio": _cut(g(r, "bio"), 1000)}
                sid = specs[sk][0] if sk in specs else None
                if sk in specs and not specs[sk][2]: it["warn"].append("التخصص «%s» مخفي حاليًا، فلن يظهر الطبيب حتى تفعّله" % specs[sk][1])
                key = (norm_ar(it["name"]), sid if sid is not None else "new:" + sk, rid)
                ex = ex_doc.get(key)
            else:
                vals = {"address": _cut(g(r, "address"), 300), "hours": sch, "tests": _cut(g(r, "tests"), 1000), "phone": ph, "whatsapp": wa}
                hv = g(r, "home"); vals["home_visit"] = (1 if _yes(hv) else 0) if hv else None
                key = (norm_ar(it["name"]), rid); ex = ex_lab.get(key)
            it.update(key=key, vals=vals, rid=rid)
            if key in seen: it["status"], it["msg"] = "duplicate", "مكرر داخل الملف"; continue
            seen.add(key)
            if ex is not None:
                ch = {k: v for k, v in vals.items() if v not in ("", None) and v != ex[k]}
                if update_existing and ch: it["status"], it["id"], it["changes"] = "update", ex["id"], ch; it["msg"] = "تحديث: " + "، ".join(LABELS.get({"clinic_name": "clinic", "hours": "schedule", "home_visit": "home"}.get(k, k), k) for k in ch)
                else: it["status"], it["msg"] = "duplicate", ("موجود مسبقًا ولا جديد فيه" if update_existing else "موجود مسبقًا (يُتخطّى)")
                continue
            if kind == "doctors" and sk not in specs and sk not in new_specs: new_specs[sk] = sp
            it["status"] = "new"
    if not any(used.values()): raise Bad(400, "لم أجد صفحة «الأطباء» أو «المعامل» في الملف. حمّل النموذج واستخدمه." + ((" " + notes[0]) if notes else ""))
    return {"items": items, "new_specialties": list(new_specs.values()), "_new_specs": new_specs, "notes": notes}


def _complete(kind, v):
    if kind == "doctors": return bool((v["address"] or v["clinic_name"]) and (v["phone"] or v["whatsapp"] or v["schedule"]))
    return bool(v["address"])


def summarize(p):
    s = {k: {"new": 0, "update": 0, "duplicate": 0, "error": 0} for k in ("doctors", "labs")}
    for it in p["items"]: s[it["kind"]][it["status"]] += 1
    shown = sorted(p["items"], key=lambda i: 0 if i["status"] == "error" else 1)[:SHOW_ROWS]
    shown.sort(key=lambda i: (i["kind"], i["row"]))
    return {"summary": s, "new_specialties": p["new_specialties"], "notes": p["notes"], "truncated": len(p["items"]) > SHOW_ROWS,
            "items": [{k: it.get(k, "") for k in ("kind", "sheet", "row", "name", "specialty", "region", "status", "msg")} | {"warn": it["warn"]} for it in shown]}


def apply(c, p, uid, publish=False):
    now = int(time.time()); ids = {}
    for sk, nm in p["_new_specs"].items():
        row = c.execute("SELECT id FROM specialties WHERE name_norm=? OR name_ar=?", (sk, nm)).fetchone()
        ids[sk] = row["id"] if row else c.execute("INSERT INTO specialties(name_ar,name_norm) VALUES(?,?)", (nm, sk)).lastrowid
    done = {"doctors": 0, "labs": 0, "updated": 0, "published": 0}
    for it in p["items"]:
        v = it.get("vals"); k = it["kind"]
        if it["status"] == "update":
            ch = it["changes"]
            c.execute("UPDATE %s SET %s,updated_at=? WHERE id=?" % (k, ",".join("%s=?" % f for f in ch)), (*ch.values(), now, it["id"])); done["updated"] += 1
        elif it["status"] == "new":
            pub = 1 if publish and _complete(k, v) else 0
            if k == "doctors":
                sk = norm_ar(it["specialty"]); sid = c.execute("SELECT id FROM specialties WHERE name_norm=?", (sk,)).fetchone()
                sid = sid["id"] if sid else ids[sk]
                c.execute("INSERT INTO doctors(name_ar,name_norm,specialty_id,region_id,clinic_name,address,schedule,phone,whatsapp,bio,is_published,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (it["name"], norm_ar(it["name"]), sid, it["rid"], v["clinic_name"], v["address"], v["schedule"], v["phone"], v["whatsapp"], v["bio"], pub, now, now))
            else:
                c.execute("INSERT INTO labs(name_ar,name_norm,region_id,address,hours,tests,home_visit,phone,whatsapp,is_published,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                          (it["name"], norm_ar(it["name"]), it["rid"], v["address"], v["hours"], v["tests"], v["home_visit"] or 0, v["phone"], v["whatsapp"], pub, now, now))
            done[k] += 1; done["published"] += pub
    done["specialties"] = len(p["_new_specs"])
    audit(c, uid, "import.excel", None, done)
    return done


# ---------------------------------------------------------------- نموذج Excel جاهز
def _esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _sheet_xml(rows, widths):
    def cell(r, ci, v): return '<c r="%s%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (chr(65 + ci), r, _esc(v))
    body = "".join('<row r="%d">%s</row>' % (ri, "".join(cell(ri, ci, v) for ci, v in enumerate(row))) for ri, row in enumerate(rows, 1))
    cols = "".join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, w) for i, w in enumerate(widths))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews><cols>%s</cols><sheetData>%s</sheetData></worksheet>' % (cols, body))


def template_xlsx():
    docs = [["الاسم", "التخصص", "المنطقة", "المركز", "العيادة", "العنوان", "المواعيد", "الهاتف", "واتساب", "نبذة"],
            ["د. أحمد محمود", "باطنة", "اكتب اسم القرية أو المدينة", "اسم المركز (اختياري)", "عيادة النور", "شارع المحطة", "السبت والثلاثاء 5م-9م", "01012345678", "01012345678", ""]]
    labs = [["الاسم", "المنطقة", "المركز", "العنوان", "المواعيد", "التحاليل", "سحب منزلي", "الهاتف", "واتساب"],
            ["معمل الأمل", "اكتب اسم القرية أو المدينة", "اسم المركز (اختياري)", "بجوار الوحدة الصحية", "يوميًا 8ص-10م", "سكر، وظائف كبد، صورة دم", "نعم", "01012345678", ""]]
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
          '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="الأطباء" sheetId="1" r:id="rId1"/><sheet name="المعامل" sheetId="2" r:id="rId2"/></sheets></workbook>')
    wr = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
          '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
          '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct); z.writestr("_rels/.rels", rels); z.writestr("xl/workbook.xml", wb); z.writestr("xl/_rels/workbook.xml.rels", wr)
        z.writestr("xl/worksheets/sheet1.xml", _sheet_xml(docs, [20, 14, 22, 20, 18, 24, 26, 15, 15, 24]))
        z.writestr("xl/worksheets/sheet2.xml", _sheet_xml(labs, [20, 22, 20, 24, 20, 30, 12, 15, 15]))
    return b.getvalue()


# ---------------------------------------------------------------- المسارات
def handle(h, c, u, method, path, q):
    if not path.startswith("/api/admin/import/"): return False
    h.need(u, "admin")
    if method == "GET" and path == "/api/admin/import/template":
        h.send(200, {"name": "laqino-doctors-labs-template.xlsx", "data": base64.b64encode(template_xlsx()).decode()}); return True
    if method == "POST" and path in ("/api/admin/import/preview", "/api/admin/import/commit"):
        d = h.body(8_000_000)
        try:
            try: raw = base64.b64decode(str(d.get("data", "")), validate=True)
            except Exception: raise Bad(400, "الملف غير صالح")
            dr = d.get("default_region_id")
            try: dr = int(dr) if dr not in (None, "", 0) else None
            except (TypeError, ValueError): raise Bad(400, "المنطقة الافتراضية غير صالحة")
            p = plan(c, raw, dr, d.get("update_existing") in (1, True))
            if path.endswith("/preview"): h.send(200, summarize(p)); return True
            if not any(i["status"] in ("new", "update") for i in p["items"]): raise Bad(409, "لا يوجد ما يُستورد: كل الصفوف مكررة أو بها أخطاء")
            try: done = apply(c, p, u["id"], d.get("publish") in (1, True)); c.commit()
            except Exception: c.rollback(); raise
            out = summarize(p); out["done"] = done; h.send(200, out); return True
        except Bad as e:
            h.send(e.code, {"error": e.msg}); return True
    h.send(404, {"error": "غير موجود"}); return True
