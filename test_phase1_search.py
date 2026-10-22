# المرحلة 1: /api/search (وحدة gsearch.py) + نتائج الواجهة الجديدة. بيانات اختبار داخل قاعدة مؤقتة فقط. fake-DOM في node، ليس متصفحًا.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8791), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8791"; D = os.path.dirname(os.path.abspath(__file__)); HN = os.path.join(D, "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def page(tok, steps):
    o = subprocess.run(["node", HN, "index", BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); return json.loads(o.stdout)
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cust, ph1, ph2, sel = user("01012345678"), user("01011111111"), user("01033333333"), user("01022222222")
PHONES = ["01011111111", "01033333333", "01022222222", "01012345678"]
u1, u2 = call("GET", "/me", None, ph1)[1]["id"], call("GET", "/me", None, ph2)[1]["id"]
call("POST", "/providers/apply", {"name_ar": "صيدلية الأمل", "region_id": 3, "address": "شارع البحر"}, ph1); call("POST", f"/admin/providers/{u1}/review", {"status": "approved"}, at)
call("POST", "/providers/apply", {"name_ar": "صيدلية مخفية", "region_id": 3, "address": "x"}, ph2)  # لم تُعتمد
call("POST", "/provider/stock", {"medicine_name": "أوجمنتين", "available": True, "price": 120}, ph1)
call("POST", "/provider/stock", {"medicine_name": "Panadol Extra", "available": False}, ph1)
sp = call("POST", "/admin/specialties", {"name_ar": "أطفال"}, at)[1]["id"]
d1 = call("POST", "/admin/doctors", {"name_ar": "د. أحمد محمود", "specialty_id": sp, "region_id": 3, "clinic_name": "عيادة النور", "address": "شارع البحر", "phone": "0473123456", "schedule": "السبت 5-9"}, at)[1]["id"]; call("POST", f"/admin/doctors/{d1}/publish", {"published": True}, at)
call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)
cid = call("POST", "/admin/categories", {"parent_id": 2, "section": "souq", "slug": "ap", "name_ar": "شقق", "is_active": True}, at)[1]["id"]
call("POST", f"/admin/categories/{cid}/fields", {"key": "price", "label_ar": "السعر", "type": "price", "required": True}, at)
good = {"category_id": cid, "region_id": 3, "title": "شقة للإيجار", "description": "إطلالة جميلة", "fields": {"price": 2500}}
l1 = call("POST", "/listings", good, sel)[1]["id"]; call("POST", f"/admin/listings/{l1}/review", {"status": "approved"}, at)
call("POST", "/listings", {**good, "title": "شقة معلقة"}, sel)  # قيد المراجعة
S = lambda q, t=None: call("GET", "/search?q=" + urllib.request.quote(q) + "&region_id=3", None, t)
s, r = S("اوجمنتين"); ok("Arabic-normalised medicine hit (أ≈ا, م≈م) with pharmacy and price, public (no login)", s == 200 and r["medicines"] and r["medicines"][0]["price"] == 120 and r["medicines"][0]["pharmacy"] == "صيدلية الأمل")
s, r = S("panadol"); ok("unavailable stock is not returned", s == 200 and not r["medicines"])
s, r = S("الامل"); ok("pharmacy by name; unapproved pharmacy hidden", [p["name_ar"] for p in r["pharmacies"]] == ["صيدلية الأمل"])
s, r = S("شقه"); ok("listing hit via ة≈ه normalisation, pending listing hidden", [x["title"] for x in r["listings"]] == ["شقة للإيجار"])
s, r = S("شقق"); ok("listing found by its category name", len(r["listings"]) == 1 and r["listings"][0]["category"] == "شقق")
s, r = S("اطفال"); ok("specialty hit with published-doctor count", r["specialties"] and r["specialties"][0]["doctors"] == 1)
s, r = S("سباكه"); ok("service type hit (ة≈ه), zero providers reported honestly", r["service_types"] and r["service_types"][0]["providers"] == 0)
s, r = call("GET", "/search?q=" + urllib.request.quote("اوجمنتين") + "&region_id=99999"); ok("region with no coverage: no pharmacy stock leaks", s == 200 and not r["medicines"] and not r["pharmacies"])
s, r = call("GET", "/search?q=" + urllib.request.quote("اوجمنتين")); ok("no region: medicines not searched, needs_region flag", s == 200 and r["needs_region"] and not r["medicines"])
for q in ("ا", "%", "  "): ok(f"short/blank query {q!r} -> 400", call("GET", "/search?q=" + urllib.request.quote(q))[0] == 400)
ok("non-numeric region -> 400", call("GET", "/search?q=" + urllib.request.quote("شقه") + "&region_id=abc")[0] == 400)
s, r = call("GET", "/search?q=" + urllib.request.quote("%_") + "&region_id=3"); ok("LIKE wildcards are plain text (no rows, no error)", s == 200 and not r["listings"])
s, r = call("GET", "/search?q=" + urllib.request.quote("' OR 1=1 --") + "&region_id=3"); ok("SQL-ish input is inert", s == 200 and not r["listings"] and not r["medicines"])
blob = json.dumps([S(q)[1] for q in ("اوجمنتين", "الامل", "شقه", "اطفال")], ensure_ascii=False)
ok("no phone number (seller/pharmacy/doctor) appears in any search payload", not any(p in blob for p in PHONES + ["0473123456"]) and '"phone"' not in blob and "whatsapp" not in blob)
ok("limit is capped", len(call("GET", "/search?q=" + urllib.request.quote("شقه") + "&limit=999")[1]["listings"]) <= 20)
cl = lambda q, pre="": page(cust, [{"js": f"{pre};window.gq={json.dumps(q, ensure_ascii=False)};go(5)", "snap": "v", "wait": 1500}])
r = cl("الامل"); ok("UI: pharmacies section renders", not r["errs"] and "الصيدليات" in r["v"] and "صيدلية الأمل" in r["v"] and "صيدلية مخفية" not in r["v"])
r = cl("اطفال"); ok("UI: specialty card shown with doctor count", not r["errs"] and "التخصصات" in r["v"] and "طبيب منشور" in r["v"])
r = cl("اوجمنتين", "R=3"); ok("UI: Arabic-variant medicine query shows price and pharmacy", not r["errs"] and "أوجمنتين" in r["v"] and "120" in r["v"])
r = cl("اطفال", "var _f=fetch;fetch=(u,o)=>String(u).includes('/search')?Promise.reject(new Error('x')):_f(u,o)"); ok("UI: /search failing shows one error section; other sections still render", not r["errs"] and "تعذّر البحث في الأدوية" in r["v"] and r["v"].count("تعذّر البحث في") == 1 and "أحمد محمود" in r["v"])
sw = open(os.path.join(D, "static", "sw.js"), encoding="utf8").read(); ok("sw.js cache version >=v28 and caches market.html", (lambda m: bool(m) and int(m.group(1)) >= 28)(__import__("re").search(r"laqino-v(\d+)", sw)) and '"/market.html"' in sw)
print("ALL PASSED")
