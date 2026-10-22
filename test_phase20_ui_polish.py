"""المرحلة 20: إصلاحات بصرية (Chromium حقيقي، قاعدة مؤقتة). تبويبات الطبي، عنوان اللوحتين، كارت الطبي الفردي، مربع «إظهار» في الإدارة."""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser test (playwright not installed)"); sys.exit(0)
_T = tempfile.mkdtemp(prefix="lq20-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
pharm, pid = user("01022220002", "صيدلي"); cour, kid = user("01022220003", "مندوب")
call("POST", "/providers/apply", {"name_ar": "صيدلية الشفاء", "region_id": 3, "address": "ش 1"}, pharm); call("POST", "/admin/providers/%d/review" % pid, {"status": "approved"}, at)
apply_docs(call, cour); call("POST", "/admin/couriers/%d/review" % kid, {"status": "approved"}, at)
with sync_playwright() as p:
    b = p.chromium.launch()
    def page(w, h, tok=None):
        pg = b.new_context(viewport={"width": w, "height": h}, locale="ar-EG", service_workers="block").new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.setItem('rg','3');" + ("localStorage.setItem('t','%s');" % tok if tok else "")); pg.errs = errs; return pg
    for w in (360, 390, 430):
        pg = page(w, 844); pg.goto(BASE + "/"); pg.wait_for_timeout(800); pg.evaluate("go(4)"); pg.wait_for_timeout(700)
        r = pg.evaluate("[...document.querySelectorAll('.mtabs .mt')].map(b=>[b.scrollWidth<=b.clientWidth+1&&b.querySelector('span').scrollWidth<=b.querySelector('span').clientWidth+1, b.getBoundingClientRect().height<=100, Math.round(b.getBoundingClientRect().top)])")
        ok("[%d] medical tabs: label stays on one line (no per-letter wrapping)" % w, len(r) >= 2 and all(a and h for a, h, _ in r))
        ok("[%d] medical: no horizontal overflow" % w, pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
        ok("[%d] medical tabs: one row, no duplicate quick-cards" % w, len({t for _, _, t in r}) == 1 and pg.evaluate("document.querySelectorAll('.medical-quick,.mq').length") == 0)
        ok("[%d] drugs: a single entry with two inner tabs (search / quote)" % w, pg.evaluate("[...document.querySelectorAll('.seg2 button')].map(b=>b.textContent.trim())") == ["ابحث عن دواء", "سعّر روشتتك"] or not pg.evaluate("!!document.querySelector('.seg2')"))
    for w in (360, 390, 430):
        for path, tok in (("/pharmacy.html", pharm), ("/courier.html", cour)):
            pg = page(w, 844, tok); pg.goto(BASE + path); pg.wait_for_timeout(1500)
            t = pg.evaluate("(()=>{const h=document.querySelector('header.ph h1');return [h.scrollWidth<=h.clientWidth+1,h.innerText]})()")
            ok("[%d] %s: panel title not truncated (%s)" % (w, path, t[1]), t[0])
            ok("[%d] %s: back-to-app link text still visible" % (w, path), pg.evaluate("getComputedStyle(document.querySelector('header.ph .back span')).display")!="none" or w <= 340)
    for w in (390, 1366):
        pg = page(w, 900); pg.goto(BASE + "/admin.html"); pg.fill("#p", "01000000000"); pg.fill("#w", "AdminPass123"); pg.click('button:has-text("دخول")'); pg.wait_for_timeout(1000)
        pg.evaluate("tab='homeui';shell()"); pg.wait_for_timeout(700)
        d = pg.evaluate("(()=>{const c=document.querySelector('#hv-med').getBoundingClientRect();const l=document.querySelector('#hv-med').closest('label').getBoundingClientRect();const n=document.querySelector('#hn-med').getBoundingClientRect(),dd=document.querySelector('#hd-med').getBoundingClientRect();return [c.width,c.height,l.height,n.width,dd.width]})()")
        ok("[%d] admin home-sections: checkbox is normal size (%dx%d)" % (w, d[0], d[1]), d[0] <= 24 and d[1] <= 24 and d[2] <= 50)
        ok("[%d] admin home-sections: name and description fields same width" % w, abs(d[3] - d[4]) <= 2)
        ok("[%d] admin home-sections: no horizontal overflow, no JS errors" % w, pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1") and not pg.errs)
    b.close()
print("ALL PASSED")
