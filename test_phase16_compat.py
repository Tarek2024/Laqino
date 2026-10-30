# المرحلة 16: توافق مع Phase 15 — أقسام لوحة الإدارة الـ17 وإصلاح التفاف التبويبات على الموبايل. قاعدة مؤقتة معزولة.
import os, re, json, tempfile, threading, time, sys
_TMP = tempfile.mkdtemp(prefix="laqino-p16compat-")
os.environ["LAQINO_DB"] = os.path.join(_TMP, "test.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "uploads"); os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
here = os.path.dirname(os.path.abspath(__file__)); rd = lambda f: open(os.path.join(here, "static", f), encoding="utf-8").read()
adm = rd("admin.html"); tabs = re.search(r"TABS=\{(.*?)\}", adm, re.S).group(1); keys = re.findall(r"(\w+):'", tabs)
ok("admin panel declares exactly 24 sections", len(keys) == 24 and len(set(keys)) == 24)
ok("mobile tab-wrap fix kept (nav flex-wrap:wrap, buttons shrink-wrap)", re.search(r"nav\{[^}]*flex-wrap:wrap", adm) and re.search(r"nav button\{[^}]*flex:1 0 auto", adm))
ok("service worker cache version is current (laqino-vNN, >= v19)", (lambda m: bool(m) and int(m.group(1)) >= 19)(re.search(r"laqino-v(\d+)", rd("sw.js"))))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser part (playwright not installed)"); sys.exit(0)
server.init("01000000000", "AdminPass123")
_srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=_srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % _srv.server_address[1]
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception as e: print("SKIP browser tests (Chromium not installed: run `playwright install chromium`)"); sys.exit(0)
    errs = []
    pg = b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True, locale="ar-EG").new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/admin.html"); pg.fill("#p", "01000000000"); pg.fill("#w", "AdminPass123"); pg.click('button:has-text("دخول")'); pg.wait_for_selector("nav button")
    ok("all 24 section buttons render on a 360px phone", pg.locator("nav button").count() == 24)
    ok("tabs wrap onto several rows instead of scrolling sideways", pg.evaluate("(()=>{const n=document.querySelector('nav');const ys=new Set([...n.querySelectorAll('button')].map(b=>Math.round(b.getBoundingClientRect().top)));return ys.size>1&&n.scrollWidth<=n.clientWidth&&document.documentElement.scrollWidth<=innerWidth})()"))
    ok("every button is fully inside the screen (none cut off)", pg.evaluate("[...document.querySelectorAll('nav button')].every(b=>{const r=b.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1})"))
    bad = []
    for i in range(23):
        pg.locator("nav button").nth(i).click(); pg.wait_for_timeout(350)
        if pg.locator("nav button").nth(i).get_attribute("class") != "on" or not pg.evaluate("document.documentElement.scrollWidth<=innerWidth"): bad.append(i)
    ok("each of the 23 sections opens, is highlighted and fits without sideways scroll (bad=%s)" % bad, not bad)
    ok("no JS errors while opening all sections", not errs); b.close()
