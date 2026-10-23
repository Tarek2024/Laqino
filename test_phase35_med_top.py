# phase-35: medical tab top = two big actions, other services compact below
import os, sys, json, threading, time, tempfile, urllib.request, urllib.error, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
os.environ["LAQINO_AUTO_BACKUP"] = "0"
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8955; BASE = "http://127.0.0.1:%d" % PORT
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
CU = "01044440010"
tk = {CU: user(CU)}
inq = call("POST", "/medical/inquiries", {"medicine_name": "دواء س", "region_id": 3}, tk[CU])[1]["id"]
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    for w in (360, 390):
        ctx = b.new_context(viewport={"width": w, "height": 844}, service_workers="block")
        ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3')" % tk[CU])
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/"); pg.wait_for_timeout(800); pg.evaluate("go(4)"); pg.wait_for_selector(".rxbig", timeout=8000)
        bt = pg.evaluate("[...document.querySelectorAll('.rxbig button')].map(b=>[b.innerText.replace(/\\s+/g,' '),b.className,getComputedStyle(b).backgroundColor,Math.round(b.getBoundingClientRect().top)])")
        ok("[%d] two big actions, «ابعت روشتتك» first" % w, len(bt) == 2 and "ابعت روشتتك" in bt[0][0] and "اسأل عن دواء" in bt[1][0])
        ok("[%d] «ابعت روشتتك» is the orange primary" % w, "pri" in bt[0][1].split() and bt[0][2] == "rgb(242, 140, 27)" and bt[1][2] != "rgb(242, 140, 27)")
        ok("[%d] big actions are above the compact services row" % w, pg.evaluate("document.querySelector('.rxbig').getBoundingClientRect().top<document.querySelector('.mtabs.sm').getBoundingClientRect().top"))
        ok("[%d] no full-size tabs row above the actions" % w, pg.locator(".mtabs:not(.sm)").count() == 0 and pg.locator(".mtabs.sm .mt").count() >= 1)
        ok("[%d] «طلباتك» sits between the actions and the compact row" % w, pg.evaluate("(()=>{const y=s=>document.querySelector(s).getBoundingClientRect().top;return y('.rxbig')<y('.rqc')&&y('.rqc')<y('.mtabs.sm')})()"))
        ok("[%d] no horizontal overflow" % w, pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
        pg.locator(".rxbig button.pri").click(); pg.wait_for_selector("#rf", state="attached", timeout=6000)
        ok("[%d] «ابعت روشتتك» opens the prescription upload" % w, pg.locator("#rf").count() == 1 and "on" in pg.get_attribute(".rxbig button.pri", "class").split())
        pg.locator(".rxbig button:not(.pri)").click(); pg.wait_for_selector("#ms", timeout=6000)
        ok("[%d] «اسأل عن دواء» opens the medicine search box" % w, pg.locator("#ms").count() == 1)
        pg.locator(".mtabs.sm .mt", has_text="الأطباء").click(); pg.wait_for_selector("#dq", timeout=6000)
        ok("[%d] compact «الأطباء» opens doctors with the full tabs on top" % w, pg.locator(".mtabs:not(.sm) .mt").count() >= 2 and pg.locator(".rxbig").count() == 0)
        pg.locator(".mtabs .mt", has_text="الأدوية").click(); pg.wait_for_selector(".rxbig", timeout=6000)
        ok("[%d] «الأدوية» tab returns to the drugs view" % w, pg.locator(".rxbig").count() == 1)
        if w == 390: pg.screenshot(path=os.environ.get("SHOT", os.devnull) if os.environ.get("SHOT") else "/tmp/s35.png")
        ok("[%d] no page errors" % w, not errs)
        ctx.close()
    b.close()
print("DONE %d/%d" % (sum(res), len(res))); exit(0 if all(res) else 1)
