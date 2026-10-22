"""المرحلة 21: هيكل التطبيق (App Shell). فحوص ثابتة + Chromium حقيقي على قاعدة مؤقتة."""
import os, sys, re, json, time, tempfile, threading, subprocess, urllib.request
ROOT = os.path.dirname(os.path.abspath(__file__)); S = ROOT + "/static/"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
rd = lambda f: open(S + f, encoding="utf-8").read()

# ---- فحوص ثابتة ----
html, sw, css, js = rd("index.html"), rd("sw.js"), rd("shell.css"), rd("shell.js")
ok("index.html links shell.css and shell.js", '/shell.css' in html and '/shell.js' in html)
ok("service worker caches the new shell files", all(x in sw for x in ('"/shell.css"', '"/shell.js"', '"/assets/mascot-cut.webp"')))
syms = set(re.findall(r'<symbol id="(i3-[a-z]+)"', html)); uses = set(re.findall(r'href="#(i3-[a-z]+)"', html)) | set(re.findall(r"i3-\$\{k\}", html) and ["i3-med", "i3-souq", "i3-svc", "i3-moto"])
ok("every 3D icon used has a symbol in the sprite (%s)" % sorted(uses), uses <= syms and {"i3-home", "i3-med", "i3-souq", "i3-svc", "i3-me", "i3-moto"} <= syms)
ok("every gradient referenced by the sprite is defined", set(re.findall(r'url\(#(g3[a-z]|m3w)\)', html)) <= set(re.findall(r'id="(g3[a-z]|m3w)"', html)))
m = json.load(open(S + "manifest.webmanifest", encoding="utf-8"))
ok("manifest still valid, shortcuts point to existing pages", len(m["shortcuts"]) == 2 and all(os.path.exists(S + s["url"].split("#")[0].lstrip("/")) for s in m["shortcuts"]) and m["display"] == "standalone")
for f in ("shell.js", ):
    ok("node --check " + f, subprocess.run(["node", "--check", S + f]).returncode == 0)
ok("shell.js is inert outside body.app (guard present)", "classList.contains('app')" in js)
ok("panels (courier/pharmacy/admin) do not load the shell", all('shell.' not in rd(f) for f in ("courier.html", "pharmacy.html", "admin.html", "market.html")))

# ---- Chromium ----
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser checks (playwright not installed)"); print("ALL PASSED (static only)"); sys.exit(0)
_T = tempfile.mkdtemp(prefix="lq21-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
sys.path.insert(0, ROOT)
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
r = urllib.request.urlopen(BASE + "/assets/mascot-cut.webp")
ok("mascot cut-out served as image/webp", r.status == 200 and r.headers["Content-Type"] == "image/webp")

with sync_playwright() as p:
    b = p.chromium.launch()
    def page(w, h=844):
        ctx = b.new_context(viewport={"width": w, "height": h}, locale="ar-EG", service_workers="block"); pg = ctx.new_page(); pg.errs = []; pg.ctx = ctx
        pg.on("pageerror", lambda e: pg.errs.append(str(e))); pg.add_init_script("localStorage.setItem('rg','3');"); return pg
    for w in (320, 360, 390, 430):
        pg = page(w); pg.goto(BASE + "/"); pg.wait_for_timeout(1200)
        ok("[%d] home: no horizontal overflow, no JS errors" % w, pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1") and not pg.errs)
        ok("[%d] nav: 5 tabs with 3D icons, tap targets >=44px" % w, pg.evaluate("(()=>{const b=[...document.querySelectorAll('body.app>nav button')];return b.length==5&&b.every(x=>x.querySelector('svg.i3 use')&&x.getBoundingClientRect().height>=44)})()"))
        ok("[%d] home cards use 3D icons" % w, pg.evaluate("document.querySelectorAll('.tiles .sc svg.i3').length>=3"))
        ok("[%d] mascot visible in hero and not covering the search box" % w, pg.evaluate("(()=>{const m=document.querySelector('.find .mk'),s=document.querySelector('.find .sbar');if(!m||!m.complete||!m.naturalWidth)return false;const a=m.getBoundingClientRect(),c=s.getBoundingClientRect();return a.bottom<=c.top+10})()"))
        pg.evaluate("go(4)"); pg.wait_for_timeout(800)
        ok("[%d] sub page: compact header with back button, logo hidden" % w, pg.evaluate("(()=>{const b=document.querySelector('header.bar .bk');return document.body.classList.contains('sub')&&getComputedStyle(b).display!='none'&&getComputedStyle(document.querySelector('header.bar .lg')).display=='none'&&document.querySelector('header.bar .wm b').textContent=='الخدمات الطبية'})()"))
        ok("[%d] sub page: no horizontal overflow, no JS errors" % w, pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1") and not pg.errs)
        pg.ctx.close()

    pg = page(390); pg.goto(BASE + "/"); pg.wait_for_timeout(1200)
    n0 = pg.evaluate("history.length")
    pg.evaluate("go(4)"); pg.wait_for_timeout(600)
    ok("sub page pushes exactly one history entry", pg.evaluate("history.length") == n0 + 1)
    pg.evaluate("go(1)"); pg.wait_for_timeout(600)
    ok("tab to tab does not add history entries", pg.evaluate("history.length") == n0 + 1)
    pg.go_back(); pg.wait_for_timeout(800)
    ok("device back from a sub page returns to home (stays in the app)", pg.url.rstrip("/") == BASE and pg.evaluate("tab") == 0 and not pg.evaluate("document.body.classList.contains('sub')"))
    pg.evaluate("go(4)"); pg.wait_for_timeout(500); pg.click("header.bar .bk"); pg.wait_for_timeout(800)
    ok("header back button returns to home and drops the history entry", pg.evaluate("tab") == 0 and pg.evaluate("history.length") == n0 + 1 and pg.url.rstrip("/") == BASE)
    pg.evaluate("openRg()"); pg.wait_for_timeout(300)
    ok("region sheet open shows the second mascot", pg.evaluate("!document.getElementById('sh').hidden&&document.querySelector('#sh .mk2').naturalWidth>0"))
    pg.go_back(); pg.wait_for_timeout(600)
    ok("device back closes the region sheet first", pg.evaluate("document.getElementById('sh').hidden") and pg.evaluate("tab") == 0 and pg.url.rstrip("/") == BASE)
    pg.evaluate("go(4);openRg()"); pg.wait_for_timeout(500); pg.go_back(); pg.wait_for_timeout(500)
    ok("back with sheet over a sub page: closes the sheet only", pg.evaluate("document.getElementById('sh').hidden") and pg.evaluate("tab") == 4)
    pg.go_back(); pg.wait_for_timeout(600)
    ok("second back returns home", pg.evaluate("tab") == 0)

    pg.evaluate("go(1)"); pg.wait_for_timeout(800); pg.evaluate("document.body.style.minHeight='3000px';window.scrollTo(0,420)"); pg.wait_for_timeout(200)
    pg.evaluate("go(0)"); pg.wait_for_timeout(600); pg.evaluate("go(1)"); pg.wait_for_timeout(900)
    ok("scroll position is restored when returning to a tab", abs(pg.evaluate("window.pageYOffset") - 420) <= 5)

    pg.ctx.set_offline(True); pg.wait_for_timeout(400)
    ok("offline: banner shown", pg.evaluate("document.body.classList.contains('off')&&getComputedStyle(document.querySelector('.offbar')).display!='none'"))
    pg.ctx.set_offline(False); pg.wait_for_timeout(400)
    ok("online again: banner hidden", pg.evaluate("!document.body.classList.contains('off')"))
    pg.evaluate("laqToast('تجربة')"); pg.wait_for_timeout(300)
    ok("toast shows text above the nav", pg.evaluate("(()=>{const t=document.querySelector('.lq-toast');return t.classList.contains('on')&&t.textContent=='تجربة'&&t.getBoundingClientRect().bottom<=document.querySelector('body.app>nav').getBoundingClientRect().top+2})()"))
    ok("active tab is highlighted and others are not", pg.evaluate("document.querySelectorAll('body.app>nav button.on').length==1"))
    ok("no JS errors through the whole flow", not pg.errs)
    pg.ctx.close()

    # الشارات: مستخدم لديه إشعارات غير مقروءة
    import urllib.error
    def call(m, pth, d=None, t=None):
        rq = urllib.request.Request(BASE + "/api" + pth, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
        try: x = urllib.request.urlopen(rq); return x.status, json.loads(x.read() or b"{}")
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    call("POST", "/register", {"phone": "01011112222", "name": "عميل", "password": "password1"}); tk = call("POST", "/login", {"phone": "01011112222", "password": "password1"})[1]["token"]
    uid = call("GET", "/me", None, tk)[1]["id"]
    import sqlite3
    con = sqlite3.connect(os.environ["LAQINO_DB"])
    for k in ("chat", "orders", "medical", "orders"):
        con.execute("INSERT INTO notifications(user_id,kind,title,created_at) VALUES(?,?,?,strftime('%s','now'))", (uid, k, "اختبار"))
    con.commit(); con.close()
    pg = page(390); pg.add_init_script("localStorage.setItem('t','%s');" % tk); pg.goto(BASE + "/"); pg.wait_for_timeout(2500)
    ok("badges: counter on account tab (3 order/medical) and dot on market tab (chat)", pg.evaluate("(()=>{const m=document.querySelector('#t3 .nb'),s=document.querySelector('#t1 .nb');return m&&!m.hidden&&m.textContent=='3'&&s&&!s.hidden&&s.classList.contains('dot')})()"))
    pg.evaluate("go(1)"); pg.wait_for_timeout(600)
    ok("market dot hides while on the market tab", pg.evaluate("document.querySelector('#t1 .nb').hidden"))
    ok("badges: no JS errors", not pg.errs)
    b.close()
print("ALL PASSED")
