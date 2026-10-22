# الخطوة 2 في Chromium حقيقي (playwright) بمقاس موبايل: نموذج طلب الخدمة (عنوان/موعد/ميزانية/صور)، عرض الطلب للعميل،
# شغل المقدم (لا عنوان قبل القبول، أزرار التقدّم بعده)، وتبويب الإدارة. يُتخطى بأمان إن لم يتوفر playwright/Chromium/Pillow.
import os, sys, io, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
try:
    from playwright.sync_api import sync_playwright
    from PIL import Image
except Exception:
    print("SKIP browser part (playwright/Pillow not installed)"); sys.exit(0)
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(os.environ["LAQINO_DB"]); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
CU, PV = user("01099990001"), user("01099990002")
tid = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
p1 = call("POST", "/admin/services", {"name_ar": "المعلم سمير", "type_id": tid, "region_id": 3, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
call("POST", f"/admin/services/{p1}/publish", {"published": True}, at); call("POST", "/admin/service-owners", {"provider_id": p1, "phone": "01099990002"}, at)
buf = io.BytesIO(); Image.new("RGB", (2400, 1800), (30, 120, 200)).save(buf, "JPEG", quality=90)
d = tempfile.mkdtemp(); imgs = []
for i in range(4):
    pth = os.path.join(d, "p%d.jpg" % i); open(pth, "wb").write(buf.getvalue()); imgs.append(pth)
errs, bad = [], []
ADDR = "شارع النصر عمارة 5 شقة 3"
with sync_playwright() as pw:
    br = pw.chromium.launch()
    def page_for(token, url="", region=True):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("response", lambda r: bad.append((r.status, r.url.replace(BASE, ""))) if r.status >= 400 else None)
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "ERR_TUNNEL" not in m.text and "ERR_NAME_NOT_RESOLVED" not in m.text and "fonts" not in m.text and "status of 4" not in m.text else None)
        pg.add_init_script("try{localStorage.setItem('t','%s');%s}catch(e){}" % (token, "localStorage.setItem('rg','3');localStorage.setItem('rgn','المنطقة')" if region else "")); pg.goto(BASE + url); return pg
    # ---------- العميل: ملء النموذج
    pg = page_for(CU); pg.wait_for_timeout(600); pg.evaluate("go(6)"); pg.wait_for_selector("text=اطلب خدمة", timeout=8000)
    pg.click("text=اطلب خدمة"); pg.wait_for_selector("#srd", timeout=5000)
    ok("form shows address, time, budget and image fields", all(pg.locator(s).count() == 1 for s in ("#sra", "#srw", "#srb1", "#srb2", "#sri")) and not pg.locator("#srp").is_visible())
    pg.select_option("#srw", "t"); ok("choosing a fixed time reveals the date field", pg.locator("#srp").is_visible())
    pg.fill("#srd", "محتاج سباك لإصلاح تسريب في الحمام"); pg.fill("#sra", ADDR)
    pg.fill("#srp", time.strftime("%Y-%m-%dT%H:%M", time.localtime(time.time() + 2 * 86400))); pg.fill("#srb1", "100"); pg.fill("#srb2", "300")
    pg.set_input_files("#sri", imgs)  # 4 صور: الواجهة ترفع أول 3 فقط
    pg.click("text=إرسال الطلب"); pg.wait_for_selector("text=تم إرسال طلبك", timeout=15000)
    rows = sql("select id,address,budget_min,budget_max,preferred_at,status from service_requests")
    ok("request saved with all fields", len(rows) == 1 and rows[0][1] == ADDR and rows[0][2:4] == (100, 300) and rows[0][4] and rows[0][5] == "open")
    R1 = rows[0][0]
    ok("exactly 3 images uploaded (4th ignored), large photos were shrunk", sql("select count(*) from service_request_images where request_id=?", (R1,))[0][0] == 3
       and all(os.path.getsize(os.path.join(os.environ["LAQINO_UPLOADS"], p[0])) < 600_000 for p in sql("select f.path from files f join service_request_images i on i.file_id=f.id")))
    txt = pg.inner_text("body")
    ok("my requests card shows status label, address, budget and image buttons", "جديد" in txt and ADDR in txt and "100" in txt and "300" in txt and pg.locator("button:has-text('صورة 1')").count() == 1)
    pg.click("button:has-text('صورة 1')"); pg.wait_for_selector("img[alt='صورة الطلب']", timeout=8000)
    ok("clicking an image button loads it through the authenticated route", pg.eval_on_selector("img[alt='صورة الطلب']", "i=>new Promise(r=>{if(i.complete)r(i.naturalWidth);else i.onload=()=>r(i.naturalWidth)})") > 0)
    # ---------- المقدم: لا عنوان قبل القبول
    pp = page_for(PV, region=False); pp.wait_for_timeout(600); pp.evaluate("go(3)"); pp.wait_for_selector("text=اقبل الطلب", timeout=8000)
    ptxt = pp.inner_text("body")
    ok("provider sees time/budget/image count but NOT the address before accepting", "100" in ptxt and "300" in ptxt and "3 صورة" in ptxt and ADDR not in ptxt and "01099990001" not in ptxt)
    pp.click("text=اقبل الطلب"); pp.wait_for_selector("text=في الطريق", timeout=8000); ptxt = pp.inner_text("body")
    ok("after accepting: address, customer phone, progress buttons", ADDR in ptxt and "01099990001" in ptxt and "قبله المقدم" in ptxt and pp.locator("button:has-text('بدأت التنفيذ')").count() == 1)
    ok("provider can open the images after accepting", pp.locator("button:has-text('صورة 1')").count() == 1)
    pp.click("button:has-text('في الطريق')"); pp.wait_for_selector("text=المقدم في الطريق", timeout=8000)
    ok("on_the_way persisted; 'في الطريق' button is gone", sql("select status from service_requests where id=?", (R1,))[0][0] == "on_the_way" and pp.locator("button:has-text('في الطريق')").count() == 0)
    pp.click("button:has-text('بدأت التنفيذ')"); pp.wait_for_selector("text=قيد التنفيذ", timeout=8000)
    ok("in_progress persisted; only finish/return remain", sql("select status from service_requests where id=?", (R1,))[0][0] == "in_progress" and pp.locator("button:has-text('بدأت التنفيذ')").count() == 0 and pp.locator("button:has-text('تم الإنجاز')").count() == 1)
    # العميل يرى الحالة الجديدة ويقدر يلغي
    pg.evaluate("go(6)"); pg.wait_for_selector("text=قيد التنفيذ", timeout=8000)
    ok("customer sees the live status and can still cancel", pg.locator("button:has-text('إلغاء الطلب')").count() == 1 and "01099990002" not in pg.inner_text("body"))
    # ---------- الإدارة
    pa = page_for("", "/admin.html", region=False); pa.fill("input >> nth=0", "01000000000"); pa.fill("input[type=password]", "AdminPass123"); pa.click("button >> text=دخول"); pa.wait_for_selector("nav", timeout=8000)
    pa.click("nav button[data-k='svcreq']")
    pa.wait_for_selector("text=قيد التنفيذ", timeout=8000); atxt = pa.inner_text("body")
    ok("admin sees status label, address, budget, image buttons", ADDR in atxt and "100" in atxt and pa.locator("button:has-text('صورة 1')").count() == 1)
    pa.click("button:has-text('صورة 1')"); pa.wait_for_selector("img[alt='صورة الطلب']", timeout=8000); ok("admin opens a request image", True)
    ok("no page errors and no unexpected 4xx/5xx", not errs and not [b for b in bad if b[0] >= 500], )
    br.close()
if errs: print("ERRORS:", errs[:5])
print("ALL OK")
