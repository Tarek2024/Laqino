# phase-34: «طلباتك» cards + request detail page in the medical tab
import os, sys, json, threading, time, tempfile, urllib.request, urllib.error, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
os.environ["LAQINO_AUTO_BACKUP"] = "0"
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8954; BASE = "http://127.0.0.1:%d" % PORT
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
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
PH = ["01033330001", "01033330002"]; CU, CR = "01033330010", "01033330011"
tk = {p: user(p) for p in PH + [CU, CR]}; uid = lambda p: call("GET", "/me", None, tk[p])[1]["id"]
names = ["صيدلية الغالية", "صيدلية الرخيصة"]
for p, n in zip(PH, names):
    call("POST", "/providers/apply", {"name_ar": n, "region_id": 3, "address": "x"}, tk[p]); call("POST", "/admin/providers/%d/review" % uid(p), {"status": "approved"}, at)
apply_docs(call, tk[CR]); call("POST", "/admin/couriers/%d/review" % uid(CR), {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at)
mk = lambda n: call("POST", "/medical/inquiries", {"medicine_name": n, "region_id": 3}, tk[CU])[1]["id"]
A, B, C = mk("دواء أ"), mk("دواء ب"), mk("دواء ج")
call("POST", "/medical/inquiries/%d/cancel" % C, {}, tk[CU])
rs = lambda p, i, pr: call("POST", "/provider/inquiries/%d/respond" % i, {"status": "available", "price": pr}, tk[p])
rs(PH[0], A, 90); rs(PH[1], A, 60)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
    ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3')" % tk[CU])
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/"); pg.wait_for_timeout(800)
    pg.evaluate("go(4)"); pg.wait_for_selector(".rqc", timeout=8000)
    cards = pg.evaluate("[...document.querySelectorAll('.rqc')].map(e=>[e.className,e.innerText.replace(/\\s+/g,' ')])")
    ok("two active cards: replies-arrived first, waiting second", len(cards) == 2 and "o" in cards[0][0].split() and "دواء أ" in cards[0][1] and "b" not in cards[1][0].split() and "w" in cards[1][0].split())
    ok("orange card says «وصلك 2 رد» (arabic digits ok)", "وصلك" in cards[0][1] and "رد" in cards[0][1] and ("2" in cards[0][1] or "٢" in cards[0][1]))
    ok("waiting card says بانتظار الصيدليات", "بانتظار الصيدليات" in cards[1][1])
    ok("cancelled request hidden under «السابقة»", pg.locator("button", has_text="السابقة").count() == 1 and "دواء ج" not in pg.inner_text("#v .rqc >> nth=1") and pg.locator(".rqc.g").count() == 0)
    pg.locator("button", has_text="السابقة").click(); pg.wait_for_selector(".rqc.g")
    ok("tapping «السابقة» shows the cancelled card", pg.locator(".rqc.g", has_text="دواء ج").count() == 1)
    # open the request page
    pg.locator(".rqc.o").click(); pg.wait_for_selector("text=رجوع لطلباتك", timeout=6000)
    txt = pg.inner_text("#v")
    ok("detail page lists replies cheapest first", txt.index(names[1]) < txt.index(names[0]))
    ok("detail page has the delivery button", pg.locator("#v button", has_text="اطلب توصيل").count() == 2)
    ok("detail replaces the cards list", pg.locator(".rqc").count() == 0)
    # order delivery from the detail page -> account orders
    pg.on("dialog", lambda d: d.accept("شارع الجمهورية 10") if d.type == "prompt" else d.dismiss())
    pg.locator("#v p", has_text=names[1]).locator("button", has_text="اطلب توصيل").click()
    pg.wait_for_selector("#v .okb", timeout=8000)
    ok("delivery from detail lands on «طلباتي»", pg.locator("#v .ph h2", has_text="حسابي").count() == 1)
    # back in the medical tab: that request is now blue
    pg.evaluate("mview=null;go(4)"); pg.wait_for_selector(".rqc", timeout=8000)
    ok("request shows blue «التوصيل جاي» after ordering", pg.locator(".rqc.b", has_text="التوصيل جاي").count() == 1)
    pg.locator(".rqc.b").click(); pg.wait_for_selector("text=رجوع لطلباتك"); pg.locator("text=رجوع لطلباتك").click(); pg.wait_for_selector(".rqc")
    ok("back button returns to the cards", pg.locator(".rqc").count() >= 2)
    # switching the medical sub-tab leaves any open request
    pg.locator(".rqc.b").click(); pg.wait_for_selector("text=رجوع لطلباتك"); pg.evaluate("document.querySelector('.mt:nth-child(2)').click()"); pg.wait_for_timeout(700)
    ok("switching medical tab leaves the request page", pg.locator("text=رجوع لطلباتك").count() == 0)
    ok("no page errors", not errs)
    b.close()
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"), encoding="utf-8").read()
m = re.search(r"const rqInfo=.*?\n(?=async function myreq)", src, re.S)
js = m.group(0) + """
const f=(k,x)=>JSON.stringify(rqInfo(k,x));
const o=[f('r',{status:'forwarded',stage:'quoted',responses:[]}),f('r',{status:'forwarded',stage:'at_pharmacies',responses:[]}),f('r',{status:'pending',stage:'review',responses:[]}),f('r',{status:'closed',stage:'closed',responses:[]}),f('r',{status:'forwarded',stage:'quoted',responses:[{delivery_order_id:5}]})];
console.log(o.map(x=>JSON.parse(x).c+(JSON.parse(x).old?'*':'')).join(','))"""
out = subprocess.run(["node", "-e", js], capture_output=True, text=True).stdout.strip()
ok("prescription states: quoted=o, at pharmacies=w, review=w, closed=g(old), delivery=b", out == "o,w,w,g*,b")
print("DONE %d/%d" % (sum(res), len(res))); exit(0 if all(res) else 1)
