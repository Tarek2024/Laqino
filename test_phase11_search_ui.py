# المرحلة 11 / A-3: البحث العام من الرئيسية (أدوية + أطباء + سوق) بنتائج حقيقية فقط. fake-DOM في node، ليس متصفحًا.
# البيانات هنا بيانات اختبار داخل قاعدة مؤقتة فقط.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8784), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8784"; D = os.path.dirname(os.path.abspath(__file__)); HN = os.path.join(D, "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def page(tok, steps):
    o = subprocess.run(["node", HN, "index", BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); return json.loads(o.stdout)
def search(tok, q, pre=""):
    return page(tok, [{"js": f"{pre};window.gq={json.dumps(q, ensure_ascii=False)};go(5)", "snap": "v", "wait": 1200}])
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cust, ph1, sel = user("01012345678"), user("01011111111"), user("01022222222")
uid = call("GET", "/me", None, ph1)[1]["id"]
call("POST", "/providers/apply", {"name_ar": "صيدلية الأمل", "region_id": 3, "address": "شارع البحر"}, ph1); call("POST", f"/admin/providers/{uid}/review", {"status": "approved"}, at)
call("POST", "/provider/stock", {"medicine_name": "Panadol", "available": True, "price": 55}, ph1)
sp = call("POST", "/admin/specialties", {"name_ar": "أطفال"}, at)[1]["id"]
d1 = call("POST", "/admin/doctors", {"name_ar": "د. أحمد محمود", "specialty_id": sp, "region_id": 3, "clinic_name": "عيادة النور", "address": "شارع البحر", "phone": "0473123456", "schedule": "السبت 5-9"}, at)[1]["id"]
call("POST", f"/admin/doctors/{d1}/publish", {"published": True}, at)
d2 = call("POST", "/admin/doctors", {"name_ar": "خالد مخفي", "specialty_id": sp, "region_id": 3, "phone": "0473123456", "schedule": "", "whatsapp": ""}, at)[1]["id"]  # غير منشور
cid = call("POST", "/admin/categories", {"parent_id": 2, "section": "souq", "slug": "furn", "name_ar": "أثاث", "is_active": True}, at)[1]["id"]
call("POST", f"/admin/categories/{cid}/fields", {"key": "price", "label_ar": "السعر", "type": "price", "required": True}, at)
good = {"category_id": cid, "region_id": 3, "title": "كنبة ثلاثية", "description": "حالة ممتازة", "fields": {"price": 3500}}
l1 = call("POST", "/listings", good, sel)[1]["id"]; call("POST", f"/admin/listings/{l1}/review", {"status": "approved"}, at)
l2 = call("POST", "/listings", {**good, "title": "كنبة معلقة"}, sel)[1]["id"]  # قيد المراجعة، يجب ألا تظهر
r = page("", [{"js": "go(0)", "snap": "v", "wait": 900}])
ok("home shows the global search bar (guest too), no script errors", not r["errs"] and 'id="gq"' in r["v"])
r = search("", "ب")
ok("1-char query: asks for more, no API noise", not r["errs"] and "حرفين على الأقل" in r["v"])
r = search(cust, "كنبة")
ok("market hit: approved listing only (pending hidden), no medicine/doctor noise", not r["errs"] and "كنبة ثلاثية" in r["v"] and "كنبة معلقة" not in r["v"] and "الأدوية" not in r["v"] and "الأطباء" not in r["v"])
r = search(cust, "احمد")
ok("doctor hit (Arabic-normalised), unpublished doctor hidden", not r["errs"] and "أحمد محمود" in r["v"] and "خالد مخفي" not in r["v"] and "الأطباء" in r["v"])
r = search(cust, "panadol")
ok("medicine hit shows pharmacy, price and confirmation time", not r["errs"] and "Panadol" in r["v"] and "صيدلية الأمل" in r["v"] and "55" in r["v"] and "آخر تأكيد" in r["v"])
r = search(cust, "xyzzyq")
ok("no results: clear empty state with the typed word, no invented rows", not r["errs"] and "مفيش نتايج" in r["v"] and "xyzzyq" in r["v"] and "card ad" not in r["v"])
r = search(cust, "<img src=x onerror=alert(1)>")
ok("typed HTML is escaped in results", not r["errs"] and "<img src=x" not in r["v"] and "&lt;img" in r["v"])
r = search(cust, "احمد", "var _f=fetch;fetch=(u,o)=>String(u).includes('/doctors')?Promise.reject(new Error('x')):_f(u,o)")
ok("one section failing shows its own error, others still render", not r["errs"] and "تعذّر البحث في الأطباء" in r["v"])
r = search(cust, "كنبة", "var _f=fetch;fetch=(u,o)=>String(u).includes('/api/')?Promise.reject(new Error('x')):_f(u,o)")
ok("all sections failing: retry state, not a blank page", not r["errs"] and "تعذّر البحث" in r["v"] and "حاول تاني" in r["v"])
nr = subprocess.run(["node", HN, "index", BASE, cust, json.dumps([{"js": "localStorage.removeItem;window.gq='Panadol';R=0;go(5)", "snap": "v", "wait": 1200}])], capture_output=True, text=True); r = json.loads(nr.stdout)
ok("no region: medicines not searched, region hint shown", not r["errs"] and "اختار منطقتك" in r["v"])
for k in ("souq", "dr", "rx"):
    r = page(cust, [{"js": f"window.gq='احمد';go(5)", "wait": 900}, {"js": f"gsAll('{k}')", "snap": "v", "wait": 1500}]); ok(f"'show all' for {k} opens its section without errors", not r["errs"] and len(r["v"]) > 50)
r = page(cust, [{"js": "window.gq='احمد';go(5)", "wait": 900}, {"js": "gsAll('dr')", "snap": "v", "wait": 1500}, {"js": "0", "snap": "dres", "wait": 50}])
ok("doctors 'show all' pre-fills the box and runs the doctor search", 'value="احمد"' in r["v"] and "أحمد محمود" in r["dres"] and "خالد مخفي" not in r["dres"])
print("ALL PASSED")
