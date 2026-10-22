# الخطوة 4 في Chromium حقيقي (مقاس موبايل): العميل يرفع 3 صور، الإدارة تحوّل، الصيدلية ترى الصور وتسعّر،
# الإدارة تعتمد الرد من تبويب الروشتات، ثم يظهر للعميل. يُتخطى بأمان إن لم يتوفر playwright/Chromium.
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
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
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(os.environ["LAQINO_DB"]); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
CU, PH = user("01077770001"), user("01077770002")
pid = call("GET", "/me", None, PH)[1]["id"]
call("POST", "/providers/apply", {"name_ar": "صيدلية الشفاء", "region_id": 3, "address": "x"}, PH); call("POST", f"/admin/providers/{pid}/review", {"status": "approved"}, at)
tmp = tempfile.mkdtemp(); files = []
for i in range(3):
    fp = os.path.join(tmp, "rx%d.png" % i); open(fp, "wb").write(__import__("base64").b64decode(png())); files.append(fp)
errs, bad = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    def page_for(token, url="", region=True, prompt_text=""):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: d.accept(prompt_text))
        pg.on("response", lambda r: bad.append((r.status, r.url.replace(BASE, ""))) if r.status >= 400 else None)
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "ERR_TUNNEL" not in m.text and "ERR_NAME_NOT_RESOLVED" not in m.text and "fonts" not in m.text and "status of 4" not in m.text else None)
        pg.add_init_script("try{localStorage.setItem('t','%s');%s}catch(e){}" % (token, "localStorage.setItem('rg','3');localStorage.setItem('rgn','المنطقة')" if region else "")); pg.goto(BASE + url); return pg
    # ---- العميل يرفع 3 صور
    pc = page_for(CU); pc.wait_for_timeout(600); pc.evaluate("mt='rx';rxm='quote';go(4)"); pc.wait_for_selector("#rf", timeout=8000)
    pc.set_input_files("#rf", files); pc.click("button:has-text('إرسال للمراجعة')"); pc.wait_for_selector("text=قيد مراجعة الإدارة", timeout=8000)
    R = sql("SELECT id FROM prescriptions")[0][0]
    ok("3 images uploaded from the UI in one prescription", sql("SELECT COUNT(*) FROM rx_images WHERE prescription_id=?", (R,))[0][0] == 3)
    ok("customer card shows stage + image count + a delete button per image", "(3 صور)" in pc.inner_text("body") and pc.locator("button:has-text('حذف الصورة')").count() == 3)
    call("POST", f"/admin/prescriptions/{R}/forward-many", {"provider_ids": [pid]}, at)
    # ---- الصيدلية
    pp = page_for(PH, "/pharmacy.html"); pp.wait_for_selector("img[data-im]", timeout=8000); pp.wait_for_timeout(800)
    ok("pharmacy page shows all 3 images", pp.locator("img[data-im]").count() == 3)
    ok("pharmacy opening the images marked it as seen", sql("SELECT COUNT(*) FROM rx_seen WHERE prescription_id=?", (R,))[0][0] == 1)
    pp.fill(f"#qr{R} .qn >> nth=0", "باراسيتامول"); pp.fill(f"#qr{R} .qp >> nth=0", "25"); pp.click("button:has-text('إرسال التسعيرة')"); pp.wait_for_selector("text=بانتظار اعتماد الإدارة", timeout=8000)
    ok("pharmacy sees its quote is waiting for approval", sql("SELECT review FROM prescription_responses")[0][0] == "pending")
    pc.evaluate("go(4)"); pc.wait_for_timeout(900)
    ok("customer sees no quote yet but a review notice", "تُراجعها الإدارة" in pc.inner_text("body") and "باراسيتامول" not in pc.inner_text("body"))
    # ---- الإدارة
    pa = page_for("", "/admin.html", region=False); pa.fill("input >> nth=0", "01000000000"); pa.fill("input[type=password]", "AdminPass123"); pa.click("button >> text=دخول"); pa.wait_for_selector("nav", timeout=8000)
    pa.click("nav button[data-k='rx']"); pa.wait_for_selector("text=ردود الصيدليات بانتظار الاعتماد (1)", timeout=8000); pa.wait_for_timeout(600)
    ok("admin tab: pending response + all 3 images + tracking line", pa.locator("img[data-f]").count() >= 3 and "صيدلية الشفاء: استلمت ← اطّلعت" in pa.inner_text("body").replace("\n", " ") and "ردّت" in pa.inner_text("body"))
    pa.click("button:has-text('اعتماد وإظهار للعميل')"); pa.wait_for_selector("text=ردود الصيدليات بانتظار الاعتماد (0)", timeout=8000)
    ok("approval from the UI", sql("SELECT review FROM prescription_responses")[0][0] == "approved")
    pc.evaluate("go(4)"); pc.wait_for_selector("text=باراسيتامول", timeout=8000)
    ok("customer now sees the quote and stage 'وصلت ردود'", "وصلت ردود" in pc.inner_text("body") and "صيدلية الشفاء" in pc.inner_text("body"))
    br.close()
ok("no JS errors / no unexpected 4xx-5xx in any page", not errs and not [b for b in bad if b[0] >= 500])
print("ALL OK", bad[:3])
