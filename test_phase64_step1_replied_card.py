"""phase-64 خطوة 1: الطلب اللي الصيدلية ردّت عليه يتحول لكارت صغير «تم إرسال ردك» بدون فورم تسعير، والصورة محدودة الارتفاع وتتكبّر بالضغط، والرد المرفوض يفضل بفورمه."""
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
    pc = page_for(CU); pc.wait_for_timeout(600)
    for _ in range(2):
        pc.evaluate("mt='rx';rxm='home';go(4)"); pc.wait_for_selector("#rfp", state="attached", timeout=8000)
        pc.set_input_files("#rfp", [fp]); pc.tap("button.full:has-text('ابعت')"); pc.wait_for_timeout(1500)
    ids = [r[0] for r in sql("SELECT id FROM prescriptions ORDER BY id")]
    ok("طلبان اتسجلا", len(ids) == 2)
    uid0 = call("GET", "/me", None, PH[0])[1]["id"]
    for i in ids: ok("تحويل يدوي للصيدلية %d" % i, call("POST", "/admin/prescriptions/%d/forward" % i, {"provider_id": uid0}, at)[0] == 200)
    p0 = page_for(PH[0], "/pharmacy.html"); p0.wait_for_timeout(1500)
    R1, R2 = ids
    ok("قبل الرد: فورم التسعير ظاهر للطلبين", txt(p0).count("الروشتة كاملة ← إرسال") == 2)
    qr = "#qr%d" % R1
    p0.fill(qr + " .qn >> nth=0", "باراسيتامول"); p0.fill(qr + " .qp >> nth=0", "25"); p0.tap("#rxc%d button:has-text('الروشتة كاملة')" % R1); p0.wait_for_timeout(1500)
    ok("الرد اتسجّل", sql("SELECT status FROM prescription_responses WHERE prescription_id=?", (R1,)) == [("available",)])
    c1, c2 = txt_c1 = p0.inner_text("#rxc%d" % R1).replace("\n", " "), p0.inner_text("#rxc%d" % R2).replace("\n", " ")
    ok("الطلب المردود عليه: كارت «تم إرسال ردك»", "تم إرسال ردك" in c1)
    ok("الطلب المردود عليه: بدون فورم تسعير ظاهر", "الروشتة كاملة ← إرسال" not in c1 and "+ بند" not in c1)
    ok("الطلب المردود عليه: زر «تعديل ردك» موجود", "تعديل ردك" in c1)
    ok("الطلب التاني (لم يُرد عليه) فورمه كما هو", "الروشتة كاملة ← إرسال" in c2 and "تم إرسال ردك" not in c2)
    h1 = p0.evaluate("document.querySelector('#rxc%d img').getBoundingClientRect().height" % R1)
    ok("صورة الطلب المردود عليه مصغّرة (h=%d)" % h1, 0 < h1 <= 92)
    p0.tap("#rxc%d img" % R1); p0.wait_for_timeout(300)
    h2 = p0.evaluate("document.querySelector('#rxc%d img').getBoundingClientRect().height" % R1)
    ok("الضغط على الصورة يكبّرها (h=%d)" % h2, h2 > h1)
    h3 = p0.evaluate("document.querySelector('#rxc%d img').getBoundingClientRect().height" % R2)
    ok("صورة الطلب التاني محدودة بـ220px (h=%d)" % h3, 0 < h3 <= 222)
    p0.tap("#rxc%d summary" % R1); p0.wait_for_timeout(300)
    ok("فتح «تعديل ردك» يظهر الفورم", "الروشتة كاملة ← إرسال" in p0.inner_text("#rxc%d" % R1))
    sql("UPDATE prescription_responses SET review='rejected', review_reason='x' WHERE prescription_id=?", (R1,)); p0.reload(); p0.wait_for_timeout(1500)
    c1 = p0.inner_text("#rxc%d" % R1).replace("\n", " ")
    ok("الرد المرفوض يفضل بفورمه مفتوحًا لإعادة الإرسال", "الروشتة كاملة ← إرسال" in c1 and "رفضته الإدارة" in c1)
    br.close()
ok("لا أخطاء JS ولا 4xx/5xx في أي صفحة", not errs and not bad)
print("ALL OK")
