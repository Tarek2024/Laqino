# phase-33: pharmacy replies sorted cheapest-first (inquiries + prescription quotes) and delivery request lands on «طلباتي»
import os, sys, json, threading, time, tempfile, sqlite3, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
os.environ["LAQINO_AUTO_BACKUP"] = "0"
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8953; BASE = "http://127.0.0.1:%d" % PORT
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
res = []
def ok(n, c):
    print(("PASS " if c else "FAIL ") + n); res.append(bool(c))
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
PH = ["01022220001", "01022220002", "01022220003", "01022220004"]; CU, CR = "01022220010", "01022220011"
tk = {p: user(p) for p in PH + [CU, CR]}; uid = lambda p: call("GET", "/me", None, tk[p])[1]["id"]
names = ["صيدلية الغالية", "صيدلية الرخيصة", "صيدلية الناقصة", "صيدلية المتوسطة"]
for p, n in zip(PH, names):
    call("POST", "/providers/apply", {"name_ar": n, "region_id": 3, "address": "x"}, tk[p]); call("POST", "/admin/providers/%d/review" % uid(p), {"status": "approved"}, at)
apply_docs(call, tk[CR]); call("POST", "/admin/couriers/%d/review" % uid(CR), {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at)
inq = call("POST", "/medical/inquiries", {"medicine_name": "دواء اختبار", "region_id": 3}, tk[CU])[1]["id"]
rs = lambda p, st, pr=None: call("POST", "/provider/inquiries/%d/respond" % inq, {"status": st, **({"price": pr} if pr else {})}, tk[p])
rs(PH[0], "available", 90); rs(PH[1], "available", 60); rs(PH[2], "unavailable"); rs(PH[3], "available", 75)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
    ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3')" % tk[CU])
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/"); pg.wait_for_timeout(800)
    pg.evaluate("go(4)"); pg.wait_for_selector("text=استعلاماتي", timeout=8000)
    txt = pg.evaluate("[...document.querySelectorAll('#v .card p')].map(e=>e.innerText)")
    order = [next((n for n in names if n in t), None) for t in txt]; order = [o for o in order if o]
    ok("inquiry replies order: cheapest, middle, priciest, unavailable last", order == [names[1], names[3], names[0], names[2]])
    ok("exactly one reply tagged «الأرخص» and it is the 60 ج one", sum("الأرخص" in t for t in txt) == 1 and any(names[1] in t and "الأرخص" in t for t in txt))
    # delivery request lands on «طلباتي» (tab 3) with the success note
    pg.on("dialog", lambda d: d.accept("شارع الجمهورية 10") if d.type == "prompt" else d.dismiss())
    pg.locator("#v .card p", has_text=names[1]).locator("button", has_text="اطلب توصيل").click()
    pg.wait_for_selector("text=طلباتي", timeout=8000); pg.wait_for_timeout(600)
    ok("after ordering delivery the view is حسابي/طلباتي", pg.locator("#v .ph h2", has_text="حسابي").count() == 1)
    ok("success note with reference is shown there", pg.locator("#v .okb", has_text="تم إنشاء طلب التوصيل").count() == 1)
    ok("the new delivery order is listed", pg.locator("#v .card.od").count() >= 1)
    ok("no page errors", not errs)
    b.close()
# prescription quotes: pure sorting function from the shipped page
import subprocess, re
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"), encoding="utf-8").read()
m = re.search(r"const rk=.*?const qsrt=[^\n;]*;", src)
js = m.group(0) + """
const q=[{n:'partial',partial:true,price:10},{n:'unav',price:null},{n:'b',complete:true,price:80},{n:'a',complete:true,price:50}];
console.log(JSON.stringify(qsrt(q).map(x=>x.n)))"""
out = subprocess.run(["node", "-e", js], capture_output=True, text=True).stdout.strip()
ok("prescription quotes: complete cheapest-first, then partial, then unavailable", out == '["a","b","partial","unav"]')
print("DONE %d/%d" % (sum(res), len(res))); exit(0 if all(res) else 1)
