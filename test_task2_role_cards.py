# المهمة 2: كروت الدخول للوحات حسب الدور — متصفح Chromium حقيقي بحجم هاتف (390x844) لثلاث حالات رئيسية + حالات الطلب.
# يحتاج: المهمة 1 (مسار /api/my/applications). يُتخطى إن لم يتوفر playwright. البيانات في قاعدة مؤقتة فقط. LAQINO_SHOTS=<مجلد> لحفظ اللقطات.
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser test (playwright not installed)"); sys.exit(0)
_TMP = tempfile.mkdtemp(prefix="laqino-t2-"); os.environ["LAQINO_DB"] = os.path.join(_TMP, "t.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "up"); os.makedirs(os.environ["LAQINO_UPLOADS"])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN"
if not hasattr(__import__("notif"), "handle"): print("FAIL ZIP 1 (notif.py) is required"); sys.exit(1)
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]; SH = os.environ.get("LAQINO_SHOTS")
if SH: os.makedirs(SH, exist_ok=True)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
def courier(ph, nm, st, reason=None):
    t, i = user(ph, nm); assert apply_docs(call, t)[0] == 201
    if st != "pending": assert call("POST", "/admin/couriers/%d/review" % i, {"status": st, **({"reason": reason} if reason else {})}, at)[0] == 200
    return t, i
def pharmacy(ph, nm, st):
    t, i = user(ph, nm); assert call("POST", "/providers/apply", {"name_ar": "صيدلية " + nm, "region_id": 3, "address": "ش 1"}, t)[0] == 201
    if st != "pending": assert call("POST", "/admin/providers/%d/review" % i, {"status": st}, at)[0] == 200
    return t, i
cust, _ = user("01011110001", "عميل عادي")
pharm, _ = pharmacy("01011110002", "الشفاء", "approved")
cour, _ = courier("01011110003", "مندوب معتمد", "approved")
cour_pend, cp_id = courier("01011110004", "مندوب معلق", "pending")
cour_rej, _ = courier("01011110005", "مندوب مرفوض", "rejected", "صورة البطاقة غير واضحة")
cour_sus, _ = courier("01011110006", "مندوب موقوف", "suspended")
ph_pend, _ = pharmacy("01011110007", "الأمل", "pending")
ph_rej, _ = pharmacy("01011110008", "المرفوضة", "rejected")

with sync_playwright() as p:
    b = p.chromium.launch()
    def page_for(tok, name):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="ar-EG", service_workers="block")
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and "favicon" not in m.text and "ERR_TUNNEL_CONNECTION_FAILED" not in m.text and "ERR_NAME_NOT_RESOLVED" not in m.text and "status of 404" not in m.text and errs.append(m.text))
        pg.add_init_script("localStorage.setItem('rg','3');" + ("localStorage.setItem('t','%s');" % tok if tok else ""))
        pg.errs = errs; pg.name = name; return pg
    def home(pg):
        pg.goto(BASE + "/"); pg.wait_for_selector(".tiles", timeout=8000); pg.wait_for_function("window._sk===0", timeout=8000)
    def account(pg):
        pg.click("#t3"); pg.wait_for_selector("text=طلباتي", timeout=8000); pg.wait_for_function("window._sk===0", timeout=8000)
    def shot(pg, tag):
        if SH: pg.screenshot(path=os.path.join(SH, "%s-%s.png" % (pg.name, tag)), full_page=True)
    def fits(pg): return pg.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
    def card(pg, k): return pg.query_selector('[data-panel="%s"]' % k)
    def foot_link(pg): return pg.query_selector('.foot a[href="/pharmacy.html"]')
    def apply_form(pg): return pg.query_selector("details.cr")

    # ===== الحالة 1: عميل عادي =====
    pg = page_for(cust, "customer"); home(pg)
    ok("customer/home: no role cards", card(pg, "pharmacy") is None and card(pg, "courier") is None)
    ok("customer/home: pharmacy join link still offered", foot_link(pg) is not None); shot(pg, "home")
    account(pg)
    ok("customer/account: no role cards", card(pg, "pharmacy") is None and card(pg, "courier") is None)
    ok("customer/account: courier application form offered", apply_form(pg) is not None and apply_form(pg).is_visible()); shot(pg, "account")
    ok("customer: fits phone width, no JS errors", fits(pg) and not pg.errs)

    # ===== الحالة 2: صيدلية معتمدة =====
    pg = page_for(pharm, "pharmacy"); home(pg); c = card(pg, "pharmacy")
    ok("pharmacy/home: pharmacy card is a link to /pharmacy.html", c is not None and c.get_attribute("href") == "/pharmacy.html" and "لوحة الصيدلية" in c.inner_text() and "الشفاء" in c.inner_text() and "معتمد" in c.inner_text())
    ok("pharmacy/home: no courier card, join link hidden", card(pg, "courier") is None and foot_link(pg) is None)
    ok("pharmacy/home: card tap target >= 44px & visible without scrolling past tiles", c.bounding_box()["height"] >= 44 and c.is_visible()); shot(pg, "home")
    account(pg); c = card(pg, "pharmacy")
    ok("pharmacy/account: card present", c is not None and c.get_attribute("href") == "/pharmacy.html")
    ok("pharmacy/account: courier form still offered (courier is a separate role)", apply_form(pg) is not None); shot(pg, "account")
    ok("pharmacy: fits phone width, no JS errors", fits(pg) and not pg.errs)
    c.click(); pg.wait_for_url("**/pharmacy.html", timeout=8000); pg.wait_for_load_state("domcontentloaded")
    ok("pharmacy: tapping the card opens the pharmacy panel", pg.url.endswith("/pharmacy.html") and pg.query_selector("body") is not None)

    # ===== الحالة 3: مندوب معتمد =====
    pg = page_for(cour, "courier"); home(pg); c = card(pg, "courier")
    ok("courier/home: courier card is a link to /courier.html", c is not None and c.get_attribute("href") == "/courier.html" and "لوحة المندوب" in c.inner_text() and "معتمد" in c.inner_text())
    ok("courier/home: no pharmacy card", card(pg, "pharmacy") is None); shot(pg, "home")
    account(pg)
    ok("courier/account: card present, application form HIDDEN (already applied)", card(pg, "courier") is not None and apply_form(pg) is None); shot(pg, "account")
    ok("courier: fits phone width, no JS errors", fits(pg) and not pg.errs)
    card(pg, "courier").click(); pg.wait_for_url("**/courier.html", timeout=8000)
    ok("courier: tapping the card opens the courier panel", pg.url.endswith("/courier.html"))

    # ===== حالات الطلب =====
    pg = page_for(cour_pend, "courier-pending"); home(pg); c = card(pg, "courier")
    ok("pending courier: status card (not a link), 'قيد المراجعة'", c is not None and c.get_attribute("href") is None and "قيد المراجعة" in c.inner_text())
    account(pg); ok("pending courier: application form hidden", apply_form(pg) is None and card(pg, "courier") is not None); shot(pg, "account")
    # الإدارة تعتمده أثناء فتح التطبيق: تتحدث الحالة بدون تسجيل خروج
    call("POST", "/admin/couriers/%d/review" % cp_id, {"status": "approved"}, at); pg.click("#t0"); pg.wait_for_selector('a[data-panel="courier"]', timeout=8000)
    ok("pending -> approved: card turns into a link without re-login", card(pg, "courier").get_attribute("href") == "/courier.html")
    pg = page_for(cour_rej, "courier-rejected"); home(pg); account(pg)
    ok("rejected courier: reason shown on the card", "صورة البطاقة غير واضحة" in card(pg, "courier").inner_text() and "مرفوض" in card(pg, "courier").inner_text())
    ok("rejected courier: may re-apply (form visible)", apply_form(pg) is not None); shot(pg, "account")
    pg = page_for(cour_sus, "courier-suspended"); home(pg); account(pg)
    ok("suspended courier: 'موقوف', no link, no apply form", "موقوف" in card(pg, "courier").inner_text() and card(pg, "courier").get_attribute("href") is None and apply_form(pg) is None)
    pg = page_for(ph_pend, "pharmacy-pending"); home(pg)
    ok("pending pharmacy: status card, join link hidden", card(pg, "pharmacy").get_attribute("href") is None and "قيد المراجعة" in card(pg, "pharmacy").inner_text() and foot_link(pg) is None); shot(pg, "home")
    pg = page_for(ph_rej, "pharmacy-rejected"); home(pg)
    ok("rejected pharmacy: 'مرفوض' card, no dead link", "مرفوض" in card(pg, "pharmacy").inner_text() and card(pg, "pharmacy").get_attribute("href") is None)

    # ===== زائر + تراجع السيرفر =====
    pg = page_for("", "guest"); home(pg)
    ok("guest: no cards, join link offered, no JS errors", card(pg, "pharmacy") is None and card(pg, "courier") is None and foot_link(pg) is not None and not pg.errs)
    pg = page_for(cour, "old-server")
    pg.route("**/api/my/applications", lambda r: r.fulfill(status=404, content_type="application/json", body='{"error":"غير موجود"}')); home(pg)
    ok("old server (no /api/my/applications): app still loads, just no cards", card(pg, "courier") is None and not pg.errs); account(pg)
    ok("old server: account page still works with courier form", apply_form(pg) is not None)
    # شاشة صغيرة جدًا (320px)
    ctx = b.new_context(viewport={"width": 320, "height": 640}, is_mobile=True, has_touch=True, locale="ar-EG", service_workers="block"); pg = ctx.new_page()
    pg.add_init_script("localStorage.setItem('rg','3');localStorage.setItem('t','%s');" % cour); pg.goto(BASE + "/"); pg.wait_for_selector('[data-panel="courier"]', timeout=8000)
    ok("320px wide: no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1"))
    b.close()
print("ALL TASK-2 BROWSER CHECKS PASSED")
