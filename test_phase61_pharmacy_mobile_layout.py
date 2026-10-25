"""شاشة الصيدلية على الموبايل (Chromium بمقاس تليفون): الروشتة أول الصفحة، بانر حجز بعدّ تنازلي، لا 404 لنموذج التسعير، وحالة «تم إرسال ردك». يُتخطى بأمان بدون playwright."""
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, base64
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP (playwright not installed)"); sys.exit(0)
import server
from imgutil import png
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(os.environ["LAQINO_DB"]); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
CU = user("01077770001"); PH = [user("01077770002"), user("01077770003")]
for i, t in enumerate(PH):
    pid = call("GET", "/me", None, t)[1]["id"]
    print("apply", call("POST", "/providers/apply", {"name_ar": "صيدلية %d" % i, "region_id": 3, "address": "x"}, t)[0], call("POST", "/admin/providers/%d/review" % pid, {"status": "approved"}, at)[0])
sql("UPDATE providers SET distribution_enabled=1")
print("mode", call("POST", "/admin/rx/distribution-mode", {"mode": "auto"}, at))
tmp = tempfile.mkdtemp(); fp = os.path.join(tmp, "rx.png"); open(fp, "wb").write(base64.b64decode(png()))

errs, bad = [], []
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
txt = lambda pg: pg.inner_text("body").replace("\n", " ")
with sync_playwright() as pw:
    br = pw.chromium.launch(args=["--no-sandbox"])
    def page_for(token, url=""):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, service_workers="block")
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept(""))
        pg.on("response", lambda r: bad.append((r.status, r.url.replace(BASE, ""))) if r.status >= 400 else None)
        pg.add_init_script("try{localStorage.setItem('t','%s');localStorage.setItem('rg','3');localStorage.setItem('rgn','المنطقة')}catch(e){}" % token)
        try: pg.goto(BASE + url)
        except Exception as e:
            if "ERR_BLOCKED_BY_ADMINISTRATOR" in str(e): print("SKIP (browser policy blocks localhost)"); sys.exit(0)
            raise
        return pg
    pc = page_for(CU); pc.wait_for_timeout(600); pc.evaluate("mt='rx';rxm='home';go(4)"); pc.wait_for_selector("#rfp", state="attached", timeout=8000)
    pc.set_input_files("#rfp", [fp]); pc.tap("button.full:has-text('ابعت')"); pc.wait_for_timeout(1500)
    R = sql("SELECT id FROM prescriptions")[0][0]
    p0 = page_for(PH[0], "/pharmacy.html"); p1 = page_for(PH[1], "/pharmacy.html"); p0.wait_for_timeout(1500)
    y = p0.evaluate("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('قبول الطلب'));return b?Math.round(b.getBoundingClientRect().top+scrollY):-1})()")
    ok("زر القبول داخل أول شاشة تقريبًا (y=%s)" % y, 0 < y < 600)
    ok("قسم الروشتات أول قسم في الصفحة", p0.evaluate("document.querySelector('h2.sec').textContent.includes('طلبات الروشتات')"))
    p0.tap("button:has-text('قبول الطلب والحجز')"); p0.wait_for_selector(".cd", timeout=8000)
    ok("بانر الحجز بعد قبول الطلب مع عدّ تنازلي", "متبقي" in txt(p0) and ("دقيقة" in p0.inner_text(".cd")))
    ok("الصيدلية الثانية لا ترى نموذج تسعير بعد الحجز", p1.reload() is None or "الروشتة كاملة ← إرسال" not in (p1.wait_for_timeout(1200) or txt(p1)))
    qr = "#qr%d" % R
    p0.fill(qr + " .qn >> nth=0", "باراسيتامول"); p0.fill(qr + " .qp >> nth=0", "25"); p0.tap("button:has-text('الروشتة كاملة')"); p0.wait_for_timeout(1500)
    ok("الرد اتسجّل ومعتمد", sql("SELECT status,review FROM prescription_responses") == [("available", "approved")])
    ok("بعد الرد: لا نموذج ميت، وتظهر رسالة «تم إرسال ردك»", "تم إرسال ردك" in txt(p0) and p0.locator(qr).count() == 0)
    br.close()
ok("لا أخطاء JS ولا 4xx/5xx في أي صفحة", not errs and not bad)
print("ALL OK")
