# المرحلة 16: توافق واجهة لوحة الإدارة الحالية ذات المجموعات والتنقل المتجاوب. قاعدة مؤقتة معزولة.
import os, re, json, tempfile, threading, time, sys
_TMP = tempfile.mkdtemp(prefix="laqino-p16compat-")
os.environ["LAQINO_DB"] = os.path.join(_TMP, "test.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "uploads"); os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
here = os.path.dirname(os.path.abspath(__file__)); rd = lambda f: open(os.path.join(here, "static", f), encoding="utf-8").read()
adm = rd("admin.html"); tabs = re.search(r"TABS=\{(.*?)\}", adm, re.S).group(1); keys = re.findall(r"(\w+):'", tabs)
ok("admin panel declares 25 unique sections including Firebase status", len(keys) == 25 and len(set(keys)) == 25)
ok("desktop sidebar and mobile grouped horizontal scroller are both defined", "flex-direction:column" in adm and "overflow:auto" in adm and bool(re.search(r"@media[(]max-width:760px[)][\\s\\S]*?nav[{][^}]*overflow-x:auto", adm)))
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
    ok("all 25 section buttons render on a 360px phone", pg.locator("nav button").count() == 25)
    ok("mobile nav uses grouped horizontal scrolling without page overflow", pg.evaluate("(()=>{const n=document.querySelector('nav');return n.querySelectorAll('.nav-group').length===8&&getComputedStyle(n).overflowX==='auto'&&n.scrollWidth>n.clientWidth&&document.documentElement.scrollWidth<=innerWidth})()"))
    pg.locator("nav button").last.scroll_into_view_if_needed()
    ok("last group is reachable within the navigation viewport", pg.evaluate("(()=>{const n=document.querySelector('nav'),b=n.querySelector('nav button:last-of-type'),r=b.getBoundingClientRect(),q=n.getBoundingClientRect();return r.left>=q.left-1&&r.right<=q.right+1})()"))
    bad = []
    for i in range(25):
        pg.locator("nav button").nth(i).click(); pg.wait_for_timeout(350)
        if pg.locator("nav button").nth(i).get_attribute("class") != "on" or not pg.evaluate("document.documentElement.scrollWidth<=innerWidth"): bad.append(i)
    ok("each of the 25 sections opens and is highlighted without page overflow (bad=%s)" % bad, not bad)
    ok("no JS errors while opening all sections", not errs); b.close()
