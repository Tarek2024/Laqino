# إضافة سوق الصيدليات في Chromium حقيقي (مقاس موبايل): الصيدلية أ تنشر إعلانًا بصورة، الإدارة تعتمده، الصيدلية ب تحجزه، أ ترى هاتف ب وتؤكد البيع.
# يُتخطى بأمان إن لم يتوفر playwright/Chromium.
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, base64, datetime
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser part (playwright not installed)"); sys.exit(0)
import server
from imgutil import png
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def until(pg, expr, sec=40):  # polling via evaluate: wait_for_function is blocked by the page's CSP (no unsafe-eval)
    for _ in range(int(sec * 10)):
        if pg.evaluate(expr): return True
        time.sleep(.1)
    raise AssertionError("timeout waiting for " + expr)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
PA, PB, CU = user("01088880001"), user("01088880002"), user("01088880003")
for t in (PA, PB):
    pid = call("GET", "/me", None, t)[1]["id"]; call("POST", "/providers/apply", {"name_ar": "صيدلية %d" % pid, "region_id": 3, "address": "x"}, t); call("POST", "/admin/providers/%d/review" % pid, {"status": "approved"}, at)
fp = os.path.join(tempfile.mkdtemp(), "box.png"); open(fp, "wb").write(base64.b64decode(png()))
exp = (datetime.date.today() + datetime.timedelta(days=300)).strftime("%Y-%m")
errs, bad = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    def page_for(token, url, admin=False):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept("سبب تجريبي"))
        pg.on("response", lambda r: bad.append((r.status, r.url.replace(BASE, ""))) if r.status >= 400 else None)
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "ERR_TUNNEL" not in m.text and "ERR_NAME_NOT_RESOLVED" not in m.text and "fonts" not in m.text and "status of 4" not in m.text else None)
        pg.add_init_script("try{%s}catch(e){}" % (("sessionStorage.setItem('at','%s')" % token) if admin else "localStorage.setItem('t','%s');localStorage.setItem('rg','3');localStorage.setItem('rgn','x')" % token)); pg.goto(BASE + url); return pg
    # ---- أ تنشر
    a = page_for(PA, "/pharmacy.html#x"); a.wait_for_selector("#dxa summary"); a.click("#dxa summary"); a.wait_for_selector("#xt")
    ok("pharmacy panel shows the exchange section", "سوق الصيدليات" in a.inner_text("#m"))
    a.fill("#xt", "أوجمنتين 1 جم"); a.fill("#xd", "علبة ١٤ قرص"); a.fill("#xq", "4"); a.fill("#xe", exp); a.fill("#xo", "100"); a.fill("#xp", "65"); a.set_input_files("#xf", fp)
    a.click("button:has-text('نشر في سوق الصيدليات')"); a.wait_for_selector("text=تم إرسال الإعلان للمراجعة")
    until(a, "document.querySelector('#exw').innerText.includes('أوجمنتين')")
    ok("A sees own deal as pending review", "قيد المراجعة" in a.inner_text("#exw") and "أوجمنتين" in a.inner_text("#exw"))
    until(a, "document.querySelector('#exw img[data-xi]') && document.querySelector('#exw img[data-xi]').naturalWidth>0")
    ok("owner's image renders from the protected endpoint", True)
    b = page_for(PB, "/pharmacy.html#x"); b.wait_for_selector("#exw .card")
    ok("B does NOT see the pending deal", "أوجمنتين" not in b.inner_text("#exw"))
    # ---- الإدارة تعتمد من التبويب
    ad = page_for(at, "/admin.html", admin=True); ad.wait_for_selector("nav button"); ad.click("nav button:has-text('سوق الصيدليات')"); ad.wait_for_selector("#v >> text=أوجمنتين")
    until(ad, "document.querySelector('#v img[data-xi]') && document.querySelector('#v img[data-xi]').naturalWidth>0"); ok("admin tab lists the deal with its image", True)
    ad.click("#v button:has-text('نشر')"); ad.wait_for_selector("#v >> text=لا توجد إعلانات قيد المراجعة"); ok("admin approved from the tab", True)
    # ---- ب تحجز
    b.reload(); b.wait_for_selector("#exw button:has-text('حجز')", timeout=30000); ok("B now sees the approved deal with discount 35%", "35" in b.inner_text("#exw") and "أوجمنتين" in b.inner_text("#exw"))
    until(b, "[...document.querySelectorAll('#exw img[data-xi]')].some(i=>i.naturalWidth>0)")
    b.click("#exw button:has-text('حجز')"); b.wait_for_selector("text=تم الحجز")
    until(b, "document.querySelector('#exw').innerText.includes('01088880001')")
    ok("B sees seller's phone after reserving", "01088880001" in b.inner_text("#exw"))
    a.reload(); a.wait_for_selector("#exw >> text=المشتري", timeout=60000); ok("A sees buyer's phone after reservation", "01088880002" in a.inner_text("#exw"))
    a.click("#exw button:has-text('تم البيع')"); a.wait_for_selector("#exw >> text=تم البيع"); ok("A confirmed the sale", True)
    br.close()
ok("no JS page errors", not errs)
ok("no unexpected HTTP 4xx/5xx", not bad)
if errs: print(errs)
if bad: print(bad)
print("ALL PASSED")
