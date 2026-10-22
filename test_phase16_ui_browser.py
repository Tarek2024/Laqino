# المرحلة 16: اختبار متصفح حقيقي (Chromium بحجم هاتف) لنماذج الإدارة وبطاقات المستخدم. يُتخطى إن لم يتوفر playwright/Pillow/Chromium.
# يضبط LAQINO_SHOTS=<مجلد> لحفظ لقطات الشاشة. البيانات في قاعدة مؤقتة فقط.
import os, json, threading, urllib.request, urllib.error, tempfile, time, io, sys
try:
    from playwright.sync_api import sync_playwright
    from PIL import Image
except Exception:
    print("SKIP browser UI test (playwright or Pillow not installed)"); sys.exit(0)
_TMP = tempfile.mkdtemp(prefix="laqino-p16ui-")  # قاعدة ومجلد رفع مؤقتان معزولان
os.environ["LAQINO_DB"] = os.path.join(_TMP, "test.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "uploads"); os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)) and os.path.realpath(server.UP).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
_srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=_srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % _srv.server_address[1]; SH = os.environ.get("LAQINO_SHOTS"); T = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
sp = call("POST", "/admin/specialties", {"name_ar": "أسنان"}, at)[1]["id"]
# سجلات قديمة بلا صور (منشورة)
od = call("POST", "/admin/doctors", {"name_ar": "د. بدون صورة", "specialty_id": sp, "region_id": 3, "clinic_name": "عيادة قديمة", "address": "ش النيل", "phone": "0473111111"}, at)[1]["id"]; call("POST", f"/admin/doctors/{od}/publish", {"published": True}, at)
ol = call("POST", "/admin/labs", {"name_ar": "معمل بدون شعار", "region_id": 3, "address": "ش المحطة", "phone": "0473222222", "tests": "سكر"}, at)[1]["id"]; call("POST", f"/admin/labs/{ol}/publish", {"published": True}, at)
def img(name, w, h, color, fmt="JPEG"):
    p = os.path.join(T, name); Image.new("RGB", (w, h), color).save(p, fmt); return p
big = img("صورة الدكتور.jpg", 2400, 1800, (30, 90, 160)); logo = img("شعار المعمل.png", 600, 600, (20, 140, 120), "PNG"); big2 = img("صورة ثانية.jpg", 1200, 1600, (200, 80, 30))
bad = os.path.join(T, "ملف.txt"); open(bad, "w").write("not an image"); fake = os.path.join(T, "fake.jpg"); open(fake, "w").write("not really a jpeg")
def until(pg, expr, sec=15):  # polling via evaluate: page.wait_for_function would be blocked by the page's CSP (no unsafe-eval)
    for _ in range(int(sec * 10)):
        if pg.evaluate(expr): return True
        time.sleep(.1)
    raise AssertionError("timeout waiting for " + expr)
shot = lambda pg, n, full=False: SH and pg.screenshot(path=os.path.join(SH, n), full_page=full)
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception as e: print("SKIP browser tests (Chromium not installed: run `playwright install chromium`)"); sys.exit(0)
    errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True, locale="ar-EG"); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append("ADMIN " + str(e) + " | " + str(getattr(e, "stack", ""))[:300])); pg.on("dialog", lambda d: d.accept())
    # ---------------- الإدارة ----------------
    pg.goto(BASE + "/admin.html"); pg.fill("#p", "01000000000"); pg.fill("#w", "AdminPass123"); pg.click('button:has-text("دخول")'); pg.wait_for_selector("nav button")
    pg.click('nav button:has-text("الأطباء والتخصصات")'); pg.wait_for_selector("#dn")
    ok("doctor form shows an empty-photo placeholder and no remove button", pg.locator("#dpv .phe").count() == 1 and pg.locator("#dpx").is_hidden())
    pg.set_input_files("#dpf", bad); pg.wait_for_timeout(200)
    ok("text file rejected with a clear Arabic error", "غير مدعوم" in pg.inner_text("#err") and pg.locator("#dpv img").count() == 0)
    pg.set_input_files("#dpf", fake); pg.wait_for_timeout(500)
    ok("corrupt image named .jpg rejected", pg.locator("#dpv img").count() == 0 and len(pg.inner_text("#err")) > 3)
    pg.set_input_files("#dpf", big); pg.wait_for_selector("#dpv img"); ok("preview shown before saving (Arabic file name)", pg.locator("#dpv img").count() == 1 and "معاينة" in pg.inner_text("#dpm"))
    ok("remove button appears after picking", pg.locator("#dpx").is_visible()); shot(pg, "admin_doctor_form.png", True)
    ok("admin doctor form fits a 390px phone (no sideways scroll)", pg.evaluate("document.documentElement.scrollWidth<=innerWidth"))
    pg.fill("#dn", "د. منى عبد الله"); pg.select_option("#dsp", str(sp)); pg.fill("#dcl", "عيادة الأمل"); pg.fill("#dad", "شارع البحر"); pg.fill("#dph", "0473123456")
    pg.click('#v button:has-text("إضافة"):not(:has-text("تخصص"))'); pg.wait_for_selector("img.th")
    ok("success message shown in green", "بنجاح" in pg.inner_text("#err") and pg.get_attribute("#err", "class") == "good")
    rows = call("GET", "/admin/doctors", None, at)[1]; nd = [x for x in rows if x["name_ar"] == "د. منى عبد الله"][0]
    ok("doctor saved unpublished with a photo, thumbnail visible in list", nd["is_published"] == 0 and nd["photo_file_id"] and pg.locator("img.th").count() == 1)
    pg.click(f'button[onclick="go(\'/admin/doctors/{nd["id"]}/publish\',{{published:true}})"]'); pg.wait_for_timeout(500)
    pub = call("GET", f"/doctors/{nd['id']}")[1]; ok("published; photo_url present", pub["photo_url"] is not None)
    with urllib.request.urlopen(BASE + pub["photo_url"]) as r: d1 = Image.open(io.BytesIO(r.read())); size1 = d1.size
    ok("browser downscaled the 2400px photo to <=900px before upload", max(size1) == 900 and size1 == (900, 675))
    # تعديل: تغيير الصورة فقط
    pg.click(f'button[onclick="ed({nd["id"]})"]'); pg.wait_for_selector("#dpv img")
    ok("edit form loads the current photo and keeps the data", pg.input_value("#dn") == "د. منى عبد الله" and pg.locator("#dpv img").count() == 1)
    pg.set_input_files("#dpf", big2); until(pg, "document.querySelector('#dpm').textContent.includes('معاينة')"); pg.click('#v button:has-text("حفظ التعديل")'); until(pg, "document.querySelector('#err').className=='good'")
    pub2 = call("GET", f"/doctors/{nd['id']}")[1]; d2 = call("GET", f"/admin/doctors", None, at)[1]
    with urllib.request.urlopen(BASE + pub2["photo_url"]) as r: size2 = Image.open(io.BytesIO(r.read())).size
    ok("photo replaced (new URL, portrait 675x900) and published state kept", pub2["photo_url"] != pub["photo_url"] and size2 == (675, 900) and [x for x in d2 if x["id"] == nd["id"]][0]["is_published"] == 1 and pub2["clinic_name"] == "عيادة الأمل")
    # المعامل
    pg.click('nav button:has-text("المعامل")'); pg.wait_for_selector("#lbn"); pg.set_input_files("#lpf", logo); pg.wait_for_selector("#lpv img")
    pg.fill("#lbn", "معمل النور للتحاليل"); pg.fill("#lba", "شارع الجمهورية"); pg.fill("#lbp", "0473555555"); pg.fill("#lbt", "سكر، دهون، وظائف كبد")
    pg.click('#v button:has-text("إضافة")'); pg.wait_for_selector("img.th")
    nl = [x for x in call("GET", "/admin/labs", None, at)[1] if x["name_ar"] == "معمل النور للتحاليل"][0]; ok("lab saved with logo", nl["photo_file_id"] and "بنجاح" in pg.inner_text("#err"))
    call("POST", f"/admin/labs/{nl['id']}/publish", {"published": True}, at)
    pg.reload(); pg.wait_for_selector("nav button"); pg.click('nav button:has-text("المعامل")'); pg.wait_for_selector("img.th"); pg.click(f'button[onclick="el({nl["id"]})"]'); pg.wait_for_selector("#lpv img")
    pg.click("#lpx"); ok("remove button clears preview and explains", pg.locator("#lpv .phe").count() == 1 and "ستُزال" in pg.inner_text("#lpm"))
    pg.click('#v button:has-text("حفظ التعديل")'); until(pg, "document.querySelector('#err').className=='good'")
    ok("lab photo removed on save; data kept", call("GET", f"/labs/{nl['id']}")[1]["photo_url"] is None and call("GET", f"/labs/{nl['id']}")[1]["tests"] == "سكر، دهون، وظائف كبد")
    # أعد صورة للمعمل ليظهر في بطاقات المستخدم
    pg.wait_for_selector('button[onclick^="el("]'); pg.wait_for_timeout(500)  # let the post-save re-render settle
    pg.click(f'button[onclick="el({nl["id"]})"]'); pg.wait_for_selector("text=تعديل معمل #"); pg.set_input_files("#lpf", logo)
    try: pg.wait_for_selector("#lpv img", timeout=5000)
    except Exception: pg.screenshot(path=os.path.join(SH or T, "dbg.png"), full_page=True); print("DBG", repr(pg.inner_text("#err")), repr(pg.inner_text("#lpm")), pg.evaluate("[document.querySelectorAll('#lpf').length, document.getElementById('lpf').files.length, JSON.stringify(Object.keys(PH.l)), !!PH.l.blob]")); raise
    pg.click('#v button:has-text("حفظ التعديل")'); until(pg, "document.querySelector('#err').className=='good'")
    errs and print("JSERR", errs); ok("no JS errors in the admin panel", not errs)
    # ---------------- المستخدم (بدون تسجيل دخول) ----------------
    u = ctx.new_page(); u.on("pageerror", lambda e: errs.append("USER " + str(e) + " | " + str(getattr(e, "stack", ""))[:300])); u.goto(BASE + "/"); u.wait_for_timeout(600)
    u.evaluate("mt='dr';go(4)"); u.wait_for_selector("#dq"); u.fill("#dq", "د"); u.wait_for_timeout(450); u.evaluate("dsr()")  # 450ms: let the 300ms oninput debounce fire first, or its late re-render wipes the details card; u.wait_for_selector("#dres .pc")
    cards = u.locator("#dres .pc"); ok("doctor cards rendered (new photo card + old no-photo card)", cards.count() == 2)
    until(u, "[...document.querySelectorAll('#dres img.pic')].every(i=>i.complete&&i.naturalWidth>0)")
    ok("photo loads for the new doctor; old doctor gets the default avatar", u.locator("#dres img.pic").count() == 1 and u.locator("#dres .pic.ph").count() == 1)
    ok("no horizontal overflow on a 390px phone", u.evaluate("document.documentElement.scrollWidth<=innerWidth"))
    dims = u.evaluate("(()=>{const i=document.querySelector('#dres img.pic').getBoundingClientRect();return [i.width,i.height]})()"); ok("photo box is square and consistent (84x84)", abs(dims[0] - dims[1]) < 1 and round(dims[0]) == 84)
    shot(u, "user_doctors.png", True)
    u.click("#dres .pc:has(img.pic)"); u.wait_for_selector("#dres .dd"); ok("details card: big photo, name, specialty, only real fields", u.locator("#dres .dd img.big").count() == 1 and "عيادة الأمل" in u.inner_text("#dres .dd"))
    txt = u.inner_text("#dres .dd"); ok("details hide fields that are empty (no schedule/bio rows)", "المواعيد" not in txt and "0473123456" not in txt)
    shot(u, "user_doctor_detail.png", True)
    u.evaluate("mt='lab';go(4)"); u.wait_for_selector(".lc"); until(u, "[...document.querySelectorAll('.lc img.pic')].every(i=>i.complete&&i.naturalWidth>0)")
    ok("lab cards: logo for the new lab, default icon for the old lab", u.locator(".lc").count() == 2 and u.locator(".lc img.pic").count() == 1 and u.locator(".lc .pic.ph.lab").count() == 1)
    ok("lab cards fit the phone and keep the contact button", u.evaluate("document.documentElement.scrollWidth<=innerWidth") and u.locator(".lc button:has-text('عرض رقم التواصل')").count() == 2 and "0473555555" not in u.content())
    shot(u, "user_labs.png", True)
    errs and print("JSERR", errs); ok("no JS errors on user pages", not errs)
    b.close()
