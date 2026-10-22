"""المرحلة 27 — أجرة يقترحها العميل على الشاشات الفعلية (Chromium): حقل السعر الاختياري في فورم الطلب، ظهور أجرة العميل للمندوب،
القبول المباشر بسعر العميل، والقبول مع تعديل السعر ثم رفض العميل. (مسار الـAPI مغطّى في test_phase27_customer_offer.py)"""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error, sqlite3
ROOT = os.path.dirname(os.path.abspath(__file__))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP (playwright not installed)"); sys.exit(0)
_T = tempfile.mkdtemp(prefix="lq27b-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
sys.path.insert(0, ROOT)
import server, testutil
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}; Z2 = Z["المجد 55"]  # أجرتها الافتراضية 120
cust, cid = user("01037770001", "عميل تجريبي"); c1, u1 = user("01037770002", "المندوب أحمد"); c2, u2 = user("01037770003", "المندوب سيد")
for t, u in ((c1, u1), (c2, u2)):
    testutil.apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
def row(oid): return sql("SELECT status,fare_status,fee,offer_fee,courier_id FROM delivery_orders WHERE id=?", oid)[0]
ignored = ("ERR_NAME_NOT_RESOLVED", "ERR_TUNNEL_CONNECTION_FAILED", "ERR_INTERNET_DISCONNECTED", "Failed to load resource", "navigator.vibrate")
with sync_playwright() as p:
    b = p.chromium.launch(); pages = []
    def page(token, w=390, h=844):
        ctx = b.new_context(viewport={"width": w, "height": h}, locale="ar-EG", service_workers="block"); pg = ctx.new_page(); pg.errs = []; pg.dialogs = []; pages.append(pg)
        pg.on("pageerror", lambda e: pg.errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and not any(x in m.text for x in ignored) and pg.errs.append(m.text))
        pg.on("dialog", lambda d: (pg.dialogs.append(d.message), d.accept()))
        pg.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','%d');" % (token, Z2)); return pg
    def text(pg): return pg.inner_text("body")
    def wait_text(pg, s, n=80):
        for _ in range(n):
            if s in text(pg): return True
            pg.wait_for_timeout(100)
        return False
    def courier_page(tok): pg = page(tok); pg.goto(BASE + "/courier.html"); pg.wait_for_selector("text=طلبات متاحة"); return pg
    def customer_orders():
        pg = page(cust); pg.goto(BASE + "/"); pg.wait_for_selector("#t3"); pg.click("#t3"); pg.wait_for_selector("text=طلباتي"); return pg
    def place_order(offer):
        pg = page(cust); pg.goto(BASE + "/"); pg.wait_for_selector("#t0"); pg.evaluate("go(2)"); pg.wait_for_selector("#pk")
        pg.fill("#pk", "مخبز النور"); pg.fill("#dr", "شارع المدرسة")
        if offer is not None: pg.fill("#of", offer)
        pg.click("button:has-text('تأكيد الطلب')"); ok("order submitted via UI", wait_text(pg, "تم إنشاء الطلب"))
        pg.context.close(); return sql("SELECT MAX(id) FROM delivery_orders")[0][0]

    # ---- 1) فورم العميل: الحقل موجود واختياري
    pg = page(cust); pg.goto(BASE + "/"); pg.wait_for_selector("#t0"); pg.evaluate("go(2)"); pg.wait_for_selector("#pk")
    ok("form has optional offer input", pg.locator("#of").count() == 1 and "اختياري" in (pg.get_attribute("#of", "placeholder") or ""))
    ok("form explains courier accepts or edits", "يقبلها أو يعدّلها" in text(pg)); pg.context.close()

    # ---- 2) طلب بسعر العميل ← المندوب يقبل مباشرة
    oidA = place_order("15")
    ok("DB: fee=15 and offer_fee=15 (region default is 120)", row(oidA)[2:4] == (15.0, 15.0))
    cu = customer_orders(); ok("customer sees own proposed fare while searching", wait_text(cu, "أجرتك المقترحة: 15 ج")); cu.context.close()
    cp = courier_page(c1); ok("courier sees customer's fare on the card", wait_text(cp, f"طلب #{oidA}") and "أجرة العميل: 15 ج" in text(cp))
    ok("courier has accept-at-15 and edit buttons", cp.locator("button:has-text('قبول بـ15 ج')").count() == 1 and cp.locator("button:has-text('قبول وتعديل السعر')").count() == 1)
    ok("addresses still hidden before accept", "مخبز النور" not in text(cp))
    cp.click("button:has-text('قبول بـ15 ج')")
    ok("accept at 15 -> addresses and fee 15 shown, customer contact visible", wait_text(cp, "من: مخبز النور") and "الرسوم: 15 ج" in text(cp) and "العميل:" in text(cp))
    ok("accept at 15 -> start button available without another approval", wait_text(cp, "أنا في الطريق للاستلام"))
    ok("DB: assigned + approved + 15", row(oidA)[:3] == ("assigned", "approved", 15.0))
    cu = customer_orders(); ok("customer sees courier name and fare, no approval prompt", wait_text(cu, "المندوب أحمد") and "موافقة وبدء التوصيل" not in text(cu)); cu.context.close()

    # ---- 3) طلب بسعر العميل ← قبول مع تعديل ← رفض العميل
    oidB = place_order("15")
    cp2 = courier_page(c2); ok("courier2 sees order B with 15", wait_text(cp2, f"طلب #{oidB}") and "أجرة العميل: 15 ج" in text(cp2))
    cp2.click("button:has-text('قبول وتعديل السعر')")
    ok("counter -> draft labelled as customer's fare", wait_text(cp2, "أجرة العميل المقترحة: 15 ج") and "الأجرة الافتراضية للمنطقة" not in text(cp2))
    ok("DB: assigned + draft", row(oidB)[:2] == ("assigned", "draft"))
    cp2.fill(f"#fe{oidB}", "22"); cp2.click("button:has-text('إرسال الأجرة للعميل')")
    ok("courier2: proposed 22 waiting", wait_text(cp2, "الأجرة المقترحة: 22 ج"))
    cu = customer_orders(); ok("customer sees courier's 22 proposal", wait_text(cu, "يقترح أجرة 22 ج"))
    cu.click("button:has-text('رفض الأجرة')")
    ok("rejected -> back to searching", wait_text(cu, "أجرتك المقترحة: 15 ج") and row(oidB)[0] == "searching" and row(oidB)[3] == 15.0)
    cu.context.close()

    # ---- 4) بلا سعر: التدفق القديم
    oidC = place_order(None)
    ok("no offer -> offer_fee NULL in DB", row(oidC)[3] is None)
    cp3 = courier_page(c2)
    ok("no offer -> card shows plain accept, no customer fare", wait_text(cp3, f"طلب #{oidC}") and "أجرة العميل" not in text(cp3).split(f"طلب #{oidC}")[1].split("طلب #")[0])
    ok("no JS errors in any page", all(not pg.errs for pg in pages))
    b.close()
print("ALL PASSED")
