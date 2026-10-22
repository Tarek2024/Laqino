# المرحلة 4 في Chromium حقيقي (playwright) بمقاس موبايل: محادثة مشترٍ/بائع، منع حقن HTML، اختيار طريقة التواصل من السوق ومن «إعلاناتي»، وتبويب بلاغات الإدارة.
# يُتخطى بأمان إن لم يتوفر playwright/Chromium. لا يغطي Web Push الحقيقي (يحتاج خدمة دفع حقيقية).
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser part (playwright not installed)"); sys.exit(0)
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
SELLER, BUYER = "01077770001", "01077770002"; ts, tb = user(SELLER), user(BUYER)
root = sql("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "أجهزة", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [x for x in call("GET", "/categories?section=souq")[1] if x["parent_id"]][0]["id"]
L = call("POST", "/listings", {"category_id": cat, "region_id": 3, "title": "غسالة للبيع", "contact_mode": "both"}, ts)[1]["id"]; call("POST", f"/admin/listings/{L}/review", {"status": "approved"}, at)
INJ = "<img src=x onerror=window.__x=1> مرحبا"
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception: print("SKIP browser tests (Chromium not installed)"); sys.exit(0)
    errs = []
    def page(tok, path, w=390, h=780):
        ctx = b.new_context(viewport={"width": w, "height": h}, is_mobile=True, has_touch=True, locale="ar-EG")
        if tok: ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3')" % tok)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(BASE + path); return pg
    noscroll = lambda pg: pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    # ---- مشترٍ يراسل البائع
    bp = page(tb, f"/market.html#/l/{L}"); bp.wait_for_selector("text=راسل البائع")
    ok("buyer sees both contact buttons on a 'both' listing (real browser, 390px)", bp.locator("button:has-text('إظهار رقم البائع')").count() == 1 and noscroll(bp))
    bp.click("button:has-text('راسل البائع')"); bp.wait_for_selector("textarea")
    ok("clicking 'message seller' opens the chat screen", "#/chat/" in bp.url and noscroll(bp))
    bp.fill("textarea", INJ); bp.click("button:has-text('إرسال')"); bp.wait_for_selector(".msg.mine")
    ok("message appears as literal text; injected HTML did not run", INJ in bp.inner_text(".msg.mine") and bp.evaluate("window.__x === undefined") and bp.locator(".msgs img").count() == 0)
    # ---- بائع يرى ويرد
    sp = page(ts, "/market.html#/chats"); sp.wait_for_selector("text=غسالة للبيع")
    ok("seller chats list: listing, buyer name, unread badge", "u02" in sp.inner_text("#app") and "1 جديدة" in sp.inner_text("#app") and noscroll(sp))
    sp.click(".card:has-text('غسالة للبيع')"); sp.wait_for_selector(".msg")
    ok("seller opens the thread and sees the buyer's message as text", INJ in sp.inner_text(".msgs"))
    sp.fill("textarea", "نعم متاحة"); sp.click("button:has-text('إرسال')"); sp.wait_for_selector(".msg.mine:has-text('نعم متاحة')")
    bp.wait_for_selector(".msg:not(.mine):has-text('نعم متاحة')", timeout=12000)
    ok("buyer receives the seller's reply by polling (no reload)", True)
    # ---- حظر + بلاغ من البائع
    sp.click("button:has-text('حظر')"); sp.wait_for_selector("text=المحادثة موقوفة")
    ok("block from the UI shows the stopped notice", sql("select blocked_by from chat_threads")[0][0] is not None)
    sp.once("dialog", lambda d: d.accept("ألفاظ مسيئة")); sp.click("button:has-text('إبلاغ')"); sp.wait_for_selector("text=تم إرسال البلاغ للإدارة")
    ok("report from the UI reaches the server", sql("select count(*) from chat_reports")[0][0] == 1)
    sp.click("button:has-text('رفع الحظر')"); sp.wait_for_function("!document.body.innerText.includes('المحادثة موقوفة')")
    # ---- البائع يغيّر الطريقة من صفحة إعلانه
    op = page(ts, f"/market.html#/l/{L}"); op.wait_for_selector("select[aria-label='طريقة تواصل المشترين']")
    op.select_option("select[aria-label='طريقة تواصل المشترين']", "chat"); op.click("button:has-text('حفظ')"); op.wait_for_selector("text=تم الحفظ")
    ok("owner saves 'chat only' from the listing page; buyer then loses the phone button", call("GET", f"/listings/{L}")[1]["contact_mode"] == "chat" and page(tb, f"/market.html#/l/{L}").locator("button:has-text('إظهار رقم البائع')").count() == 0)
    # ---- «إعلاناتي» في التطبيق الرئيسي
    ip = page(ts, "/"); ip.wait_for_selector("nav, .tabs, #app", timeout=8000); ip.evaluate("go(3)"); ip.wait_for_selector("select[aria-label='طريقة التواصل']", timeout=8000)
    ip.select_option("select[aria-label='طريقة التواصل']", "phone"); ip.click("button:has-text('حفظ طريقة التواصل')"); ip.wait_for_selector("text=تم حفظ طريقة التواصل", timeout=8000)
    ok("index 'my listings': contact mode saved from the account page", call("GET", f"/listings/{L}")[1]["contact_mode"] == "phone" and noscroll(ip))
    # ---- نموذج الإنشاء يحمل الخيار
    ip.evaluate("go(1)"); time.sleep(.8)
    ok("index creation flow loads without JS errors", not errs)
    # ---- إدارة: تبويب بلاغات المحادثات
    ap = page(None, "/admin.html", 360, 740); ap.fill("#p", "01000000000"); ap.fill("#w", "AdminPass123"); ap.click("button:has-text('دخول')"); ap.wait_for_selector("nav button")
    ap.click("nav button:has-text('بلاغات المحادثات')"); ap.wait_for_selector("text=ألفاظ مسيئة")
    ok("admin tab lists the open chat report", "غسالة للبيع" in ap.inner_text("#v") and noscroll(ap))
    ap.click("button:has-text('عرض المحادثة')"); ap.wait_for_selector("text=نعم متاحة")
    ok("admin can read the reported thread (messages escaped, shown as text)", INJ in ap.inner_text("#v") and ap.evaluate("window.__x === undefined"))
    ap.click("button:has-text('تمت المعالجة')"); ap.wait_for_selector("text=لا توجد بلاغات محادثات مفتوحة")
    ok("resolving removes it from the open list", sql("select status from chat_reports")[0][0] == "resolved")
    ok("no JS errors in any page", not errs)
    b.close()
print("ALL PASSED")
