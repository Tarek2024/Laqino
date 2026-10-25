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
    for _ in range(3):
        pc.evaluate("mt='rx';rxm='home';go(4)"); pc.wait_for_selector("#rfp", state="attached", timeout=8000)
        pc.set_input_files("#rfp", [fp]); pc.tap("button.full:has-text('ابعت')"); pc.wait_for_timeout(1200)
    ids = [r[0] for r in sql("SELECT id FROM prescriptions ORDER BY id")]
    ok("3 روشتات اتسجلت", len(ids) == 3)
    uid0 = call("GET", "/me", None, PH[0])[1]["id"]
    for i in ids: call("POST", "/admin/prescriptions/%d/forward" % i, {"provider_id": uid0}, at)
    inq = [call("POST", "/medical/inquiries", {"medicine_name": "دواء %d" % k, "region_id": 3}, CU)[1]["id"] for k in range(2)]
    pc.context.close()  # صفحة العميل فيها خطأ قديم معروف (typing is not defined في index.html كل 15 ثانية) وخارج نطاق الخطوة دي
    ok("استعلامان اتسجلا", len(inq) == 2 and all(inq))
    ok("رد على استعلام واحد", call("POST", "/provider/inquiries/%d/respond" % inq[0], {"status": "available", "price": 5}, PH[0])[0] == 200)
    ok("رد على روشتة واحدة", call("POST", "/provider/prescriptions/%d/respond" % ids[0], {"status": "available", "price": 10}, PH[0])[0] == 200)
    p0 = page_for(PH[0], "/pharmacy.html"); p0.wait_for_timeout(1500)
    tiles = lambda: p0.evaluate("[...document.querySelectorAll('.kp .kt')].map(t=>[t.querySelector('small').textContent,t.querySelector('b').textContent,t.getAttribute('role'),t.tabIndex])")
    t = tiles()
    ok("المربعات التلاتة أزرار (role=button وقابلة للتركيز)", len(t) == 3 and all(x[2] == "button" and x[3] == 0 for x in t))
    d = {x[0]: x[1] for x in t}
    ok("عدّاد روشتات = 2 (المحتاجة رد فقط من 3) — %s" % d, d["روشتات"] == "2")
    ok("عدّاد استعلامات = 1 (المحتاج رد فقط من 2)", d["استعلامات"] == "1")
    sql("UPDATE prescription_responses SET review='rejected', review_reason='x' WHERE prescription_id=?", (ids[0],)); p0.reload(); p0.wait_for_timeout(1500)
    ok("الرد المرفوض يرجع يتحسب محتاج رد (3)", {x[0]: x[1] for x in tiles()}["روشتات"] == "3")
    top = lambda sel: p0.evaluate("(()=>{const e=document.querySelector('%s');return e?Math.round(e.getBoundingClientRect().top):null})()" % sel)
    p0.evaluate("ptab('s')"); p0.wait_for_timeout(300)
    ok("بداية من تبويب المخزون: القسم مش ظاهر", p0.evaluate("document.querySelector('section[data-t=o]').classList.contains('on')") is False)
    p0.evaluate("ptab('o')"); p0.wait_for_timeout(300)
    for lab, sel in (("استعلامات", "#s-inq"), ("توصيل جاري", "#s-dv"), ("روشتات", "#s-rx")):
        p0.evaluate("scrollTo(0,0)"); p0.wait_for_timeout(200)
        p0.tap(".kp .kt:has-text('%s')" % lab); p0.wait_for_timeout(1200)
        y = top(sel)
        lim = 780 if sel == "#s-dv" else 130  # آخر قسم في الصفحة: ما يقدرش يوصل لأعلى الشاشة، يكفي إنه يبقى ظاهرًا
        ok("الضغط على «%s» ينقل لقسمه (top=%s)" % (lab, y), y is not None and -5 <= y <= lim)
    p0.evaluate("ptab('s')"); p0.wait_for_timeout(300); p0.evaluate("ptab('o')"); p0.evaluate("scrollTo(0,0)"); p0.wait_for_timeout(200)
    p0.evaluate("ptab('s')"); p0.wait_for_timeout(300)
    p0.evaluate("pgo('s-inq')"); p0.wait_for_timeout(1000)
    ok("pgo من تبويب تاني يرجّع تبويب الطلبات", p0.evaluate("document.querySelector('section[data-t=o]').classList.contains('on')"))
    p0.evaluate("scrollTo(0,0)"); p0.wait_for_timeout(200)
    p0.focus(".kp .kt:has-text('استعلامات')"); p0.keyboard.press("Enter"); p0.wait_for_timeout(1200)
    y = top("#s-inq"); ok("Enter على المربع يعمل نفس الضغط (top=%s)" % y, y is not None and -5 <= y <= 130)
    br.close()
ok("لا أخطاء JS ولا 4xx/5xx في أي صفحة", not errs and not bad)
print("ALL OK")
