# phase-63: medical home = ONE big prescription button (opens the device camera/gallery chooser) + 2x2 services grid
import os, sys, json, threading, time, tempfile, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
os.environ["LAQINO_AUTO_BACKUP"] = "0"
import server
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
CU = "01044440010"; tk = user(CU)
call("POST", "/medical/inquiries", {"medicine_name": "دواء س", "region_id": 3}, tk)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    for w in (360, 390):
        ctx = b.new_context(viewport={"width": w, "height": 844}, service_workers="block")
        ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3')" % tk)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/"); pg.wait_for_timeout(800); pg.evaluate("go(4)"); pg.wait_for_selector(".rxhero", timeout=8000)
        ok("[%d] exactly one big prescription button, no inner camera/gallery buttons" % w, pg.locator(".rxhero").count() == 1 and pg.locator(".rxhero button").count() == 0 and "ابعت روشتتك" in pg.inner_text(".rxhero"))
        ok("[%d] hero input has no capture attr, so the phone shows its own camera/gallery chooser" % w, pg.get_attribute("#rfp", "capture") is None and pg.get_attribute("#rfp", "accept") == "image/*" and pg.get_attribute("#rfp", "multiple") is not None)
        ok("[%d] service cards (3D icons), each once" % w, pg.locator(".msgrid .mscard").count() >= 2 and pg.locator(".msgrid .mscard svg.i3").count() == pg.locator(".msgrid .mscard").count() and pg.locator("text=اسأل عن دواء").count() == 1)
        ok("[%d] no tabs row on the home, no «خدمات تانية»" % w, pg.locator(".mtabs").count() == 0 and pg.locator("text=خدمات تانية").count() == 0)
        ok("[%d] labs card hidden while no lab is published (admin controls it); products card follows its flag" % w, pg.locator(".mscard", has_text="المعامل").count() == 0 and pg.locator(".mscard", has_text="المنتجات").count() == 0)
        ok("[%d] hero above services; no horizontal overflow" % w, pg.evaluate("document.querySelector('.rxhero').getBoundingClientRect().top<document.querySelector('.msgrid').getBoundingClientRect().top&&document.documentElement.scrollWidth<=innerWidth+1"))
        pg.locator(".mscard", has_text="الأطباء").click(); pg.wait_for_selector(".mtabs", timeout=6000)
        ok("[%d] a service opens with the tabs on top, «الأطباء» selected" % w, pg.locator(".mtabs .mt").count() >= 2 and "on" in pg.get_attribute(".mt:has-text('الأطباء')", "class").split())
        pg.locator(".mtabs .mt", has_text="الأدوية").click(); pg.wait_for_selector(".rxhero", timeout=6000)
        ok("[%d] «الأدوية» tab returns to the home" % w, pg.locator(".rxhero").count() == 1)
        pg.locator(".mscard", has_text="اسأل عن دواء").click(); pg.wait_for_selector("#ms", timeout=6000)
        ok("[%d] «اسأل عن دواء» opens the medicine search" % w, pg.locator("#ms").count() == 1)
        ok("[%d] no page errors" % w, not errs)
        ctx.close()
    b.close()
print("DONE %d/%d" % (sum(res), len(res))); exit(0 if all(res) else 1)
