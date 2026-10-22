# الخطوة 1 في Chromium حقيقي (playwright) بمقاس موبايل: زر الصورة في الشات يرفع صورة حقيقية، تظهر عند الطرفين، وتظهر للإدارة بزر «عرض الصورة».
# يُتخطى بأمان إن لم يتوفر playwright/Chromium/Pillow. لا يغطي هاتفًا حقيقيًا (كاميرا/معرض).
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
SELLER, BUYER = "01088880001", "01088880002"; ts, tb = user(SELLER), user(BUYER)
root = sql("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "أجهزة", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [x for x in call("GET", "/categories?section=souq")[1] if x["parent_id"]][0]["id"]
L = call("POST", "/listings", {"category_id": cat, "region_id": 3, "title": "ثلاجة"}, ts)[1]["id"]; call("POST", f"/admin/listings/{L}/review", {"status": "approved"}, at)
tid = call("POST", f"/listings/{L}/chat", None, tb)[1]["thread_id"]
buf = io.BytesIO(); Image.new("RGB", (2400, 1800), (200, 60, 30)).save(buf, "JPEG", quality=90); big = buf.getvalue()
img_path = os.path.join(tempfile.mkdtemp(), "photo.jpg"); open(img_path, "wb").write(big)
errs, bad = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    def page_for(token, key="t", store="localStorage", url=""):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("response", lambda r: bad.append((r.status, r.url.replace(BASE, ""))) if r.status >= 400 else None)
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "ERR_TUNNEL" not in m.text and "ERR_NAME_NOT_RESOLVED" not in m.text and "fonts" not in m.text else None)
        pg.add_init_script("try{%s.setItem('%s','%s')}catch(e){}" % (store, key, token)); pg.goto(BASE + url); return pg
    pb = page_for(tb, url="/market.html#/chat/%d" % tid)
    pb.wait_for_selector("textarea")
    ok("the chat page has a photo button and a hidden image file input", pb.locator("button", has_text="صورة").count() == 1 and pb.locator("input[type=file]").count() == 1)
    pb.fill("textarea", "دي الصورة")
    pb.set_input_files("input[type=file]", img_path)
    pb.wait_for_selector(".msg img.ci", timeout=8000)
    ok("buyer sees the sent image inside the chat bubble (blob url)", pb.locator(".msg.mine img.ci").count() == 1 and pb.locator(".msg img.ci").first.get_attribute("src").startswith("blob:"))
    ok("the caption is shown with the image", "دي الصورة" in pb.locator(".msg.mine").first.inner_text())
    ok("the image really loaded (non-zero size)", pb.evaluate("document.querySelector('.msg img.ci').naturalWidth") > 0)
    sz = sql("select size from files order by id desc limit 1")[0][0]
    ok("the browser shrank the photo before upload (2400px -> 1280px, smaller bytes)", sz < len(big) and pb.evaluate("document.querySelector('.msg img.ci').naturalWidth") == 1280)
    ok("the textarea was cleared after sending", pb.input_value("textarea") == "")
    ps = page_for(ts, url="/market.html#/chat/%d" % tid); ps.wait_for_selector(".msg img.ci", timeout=8000)
    ok("seller sees the buyer's image on his side", ps.locator(".msg img.ci").count() == 1 and ps.locator(".msg.mine").count() == 0)
    po = page_for(call("POST", "/login", {"phone": user("01088880009") and "01088880009", "password": "password1"})[1]["token"], url="/market.html#/chat/%d" % tid)
    po.wait_for_timeout(1500)
    ok("a third user sees no image and no messages of this thread", po.locator(".msg").count() == 0 and po.locator(".msg img.ci").count() == 0)
    ok("a bad file type shows a readable error and sends nothing", (lambda: (open(os.path.join(os.path.dirname(img_path), "x.txt"), "w").write("hi"), pb.set_input_files("input[type=file]", os.path.join(os.path.dirname(img_path), "x.txt")), pb.wait_for_timeout(800), pb.locator(".m").last.inner_text() != "" and sql("select count(*) from chat_messages where file_id is not null")[0][0] == 1)[-1])())
    call("POST", f"/chats/{tid}/report", {"reason": "اختبار بلاغ"}, tb)
    pa = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block").new_page()
    pa.on("pageerror", lambda e: errs.append(str(e)))
    pa.goto(BASE + "/admin.html"); pa.fill("input >> nth=0", "01000000000"); pa.fill("input[type=password]", "AdminPass123"); pa.click("button >> text=دخول"); pa.wait_for_selector("nav", timeout=8000)
    pa.click("nav >> text=بلاغات المحادثات"); pa.wait_for_selector("text=عرض المحادثة", timeout=8000); pa.click("text=عرض المحادثة")
    pa.wait_for_selector("button:has-text('عرض الصورة')", timeout=8000)
    ok("admin sees a 'show image' button for the image message, not the image itself", pa.locator("button", has_text="عرض الصورة").count() == 1 and pa.locator("img[alt='صورة']").count() == 0)
    pa.click("button:has-text('عرض الصورة')"); pa.wait_for_selector("img[alt='صورة']", timeout=8000)
    ok("admin image loads after the click", pa.evaluate("document.querySelector(\"img[alt='صورة']\").naturalWidth") > 0)
    ok("both admin actions were written to audit_log", sql("select count(*) from audit_log where action='chat.admin_view'")[0][0] >= 1 and sql("select count(*) from audit_log where action='chat.admin_view_image'")[0][0] == 1)
    br.close()
# المتوقع الوحيد: طرف ثالث يطلب محادثة ليست له فيحصل على 404 (المتصفح يسجّله كخطأ تحميل مورد)
ok("the only failed requests are the third user being refused the thread (404)", bool(bad) and all(b[0] == 404 and b[1].startswith("/api/chats/%d" % tid) and "/images" not in b[1] for b in bad))
errs = [e for e in errs if "status of 404" not in e]
ok("no JS errors in any of the pages", not errs)
print("ALL PASSED")
