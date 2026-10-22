# phase-36: open the request page from a notification (bell click + #req deep link)
import os, sys, json, threading, time, tempfile, urllib.request, urllib.error, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
os.environ["LAQINO_AUTO_BACKUP"] = "0"
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8956; BASE = "http://127.0.0.1:%d" % PORT
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

rp = lambda p, i: call("POST", "/medical/prescriptions/%d/respond" % i, {"status": "available", "price": 10}, tk[p])
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
    ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3')" % tk[CU])
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/"); pg.wait_for_selector(".lqn-b", state="visible", timeout=10000)
    ok("customer starts on the home tab, not the request page", pg.locator("text=رجوع لطلباتك").count() == 0)
    cnt0 = call("GET", "/notifications/count", None, tk[CU])[1]
    pg.click(".lqn-b"); pg.wait_for_selector(".lqn-i", timeout=8000)
    items = pg.evaluate("[...document.querySelectorAll('.lqn-i')].map(e=>e.innerText.replace(/\\s+/g,' '))")
    ok("bell lists the pharmacy replies", len(items) >= 2)
    # newest first: the cheapest reply on request A (id A) arrived last
    pg.locator(".lqn-i", has_text="صيدلية الرخيصة").first.click()
    pg.wait_for_selector("text=رجوع لطلباتك", timeout=8000)
    ok("clicking a reply notification opens the request page", pg.locator("text=رجوع لطلباتك").count() == 1)
    ok("it is the right request (دواء أ)", "دواء أ" in pg.inner_text("#v"))
    ok("replies are listed on that page", names[0] in pg.inner_text("#v") and names[1] in pg.inner_text("#v"))
    cnt1 = call("GET", "/notifications/count", None, tk[CU])[1]
    n0 = cnt0 if isinstance(cnt0, int) else cnt0.get("unread", cnt0.get("count", 0)); n1 = cnt1 if isinstance(cnt1, int) else cnt1.get("unread", cnt1.get("count", 0))
    ok("the notification is marked read (unread count dropped %s->%s)" % (n0, n1), n1 == n0 - 1)
    # deep link on a fresh load
    pg2 = ctx.new_page(); pg2.on("pageerror", lambda e: errs.append(str(e)))
    pg2.goto(BASE + "/#req/inquiry/%d" % A); pg2.wait_for_selector("text=رجوع لطلباتك", timeout=10000)
    ok("deep link #req/inquiry/<id> opens the request page", "دواء أ" in pg2.inner_text("#v"))
    ok("hash is cleared after opening", pg2.evaluate("location.hash") == "")
    pg2.locator("text=رجوع لطلباتك").click(); pg2.wait_for_selector(".rqc")
    ok("back button still returns to the cards", pg2.locator(".rqc").count() >= 2)
    # someone else's / missing request falls back to the normal screen
    pg3 = ctx.new_page(); pg3.on("pageerror", lambda e: errs.append(str(e)))
    pg3.goto(BASE + "/#req/inquiry/99999"); pg3.wait_for_timeout(2500)
    ok("unknown id falls back to the medical tab without an error page", pg3.locator("text=رجوع لطلباتك").count() == 0 and pg3.locator("#v .ph h2", has_text="الخدمات الطبية").count() == 1)
    pg4 = ctx.new_page(); pg4.on("pageerror", lambda e: errs.append(str(e)))
    pg4.goto(BASE + "/#req/inquiry/abc"); pg4.wait_for_timeout(2500)
    ok("malformed hash is ignored (normal home)", pg4.locator("text=رجوع لطلباتك").count() == 0)
    # another customer cannot open this request through the link
    ctx2 = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
    ctx2.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3')" % tk[CR])
    pg5 = ctx2.new_page(); pg5.on("pageerror", lambda e: errs.append(str(e)))
    pg5.goto(BASE + "/#req/inquiry/%d" % A); pg5.wait_for_timeout(2500)
    ok("a different account gets nothing from the link (request A not shown)", "دواء أ" not in pg5.inner_text("#v") and pg5.locator("text=رجوع لطلباتك").count() == 0)
    ok("no page errors", not errs)
    b.close()
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "notif.js"), encoding="utf-8").read()
ok("notif.js routes inquiry/prescription notifications to laqOpenReq", "laqOpenReq" in src and "'inquiry'" in src and "'prescription'" in src)
print("DONE %d/%d" % (sum(res), len(res))); exit(0 if all(res) else 1)
