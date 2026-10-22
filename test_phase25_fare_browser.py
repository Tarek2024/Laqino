"""المرحلة 25 — دورة الدليفري بالأجرة على الشاشات الفعلية (Chromium): المندوب يقبل فيظهر له المكان والأجرة الافتراضية ويعدّلها،
ثم العميل يرى اسم المندوب وسعر التوصيل ويوافق/يرفض، ثم يبدأ المندوب التوصيل ويُغلق الطلب. (مسار الـAPI مغطّى في test_phase25_fare.py)"""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error, sqlite3
ROOT = os.path.dirname(os.path.abspath(__file__))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP (playwright not installed)"); sys.exit(0)
_T = tempfile.mkdtemp(prefix="lq25b-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
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
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}; Z1 = Z["فرج الكبرى / الكوم"]  # أجرتها الافتراضية 15
cust, cid = user("01033330001", "عميل تجريبي"); c1, u1 = user("01033330002", "المندوب أحمد"); c2, u2 = user("01033330003", "المندوب سيد")
for t, u in ((c1, u1), (c2, u2)):
    testutil.apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
def new_order(): return call("POST", "/delivery/orders", {"region_id": Z1, "pickup_text": "مخبز النور", "dropoff_text": "شارع المدرسة"}, cust)[1]["id"]
def status(oid): return sql("SELECT status,fare_status,fee,courier_id FROM delivery_orders WHERE id=?", oid)[0]
ignored = ("ERR_NAME_NOT_RESOLVED", "ERR_TUNNEL_CONNECTION_FAILED", "ERR_INTERNET_DISCONNECTED", "Failed to load resource", "navigator.vibrate")
with sync_playwright() as p:
    b = p.chromium.launch()
    def page(token, w=390, h=844):
        ctx = b.new_context(viewport={"width": w, "height": h}, locale="ar-EG", service_workers="block"); pg = ctx.new_page(); pg.errs = []; pg.dialogs = []
        pg.on("pageerror", lambda e: pg.errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and not any(x in m.text for x in ignored) and pg.errs.append(m.text))
        pg.on("dialog", lambda d: (pg.dialogs.append(d.message), d.accept()))
        pg.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3');" % token); return pg
    def courier_page(tok): pg = page(tok); pg.goto(BASE + "/courier.html"); pg.wait_for_selector("text=طلبات متاحة"); return pg
    def customer_orders():
        pg = page(cust); pg.goto(BASE + "/"); pg.wait_for_selector("#t3"); pg.click("#t3"); pg.wait_for_selector("text=طلباتي"); return pg
    def text(pg): return pg.inner_text("body")
    def wait_text(pg, s, n=60):
        for _ in range(n):
            if s in text(pg): return True
            pg.wait_for_timeout(100)
        return False

    # ---- 1) المندوب: يرى الطلب في المتاحة (بلا عنوان وبلا سعر) ثم يقبل
    oid = new_order(); cp = courier_page(c1)
    ok("courier sees the new order in available list", wait_text(cp, f"طلب #{oid}"))
    ok("available card hides addresses", "مخبز النور" not in text(cp) and "شارع المدرسة" not in text(cp))
    cp.click("button:has-text('قبول')")
    ok("accept -> pickup place and dropoff place shown", wait_text(cp, "من: مخبز النور") and "إلى: شارع المدرسة" in text(cp))
    ok("accept -> default fare 15 shown as draft", "الأجرة الافتراضية للمنطقة: 15 ج" in text(cp))
    ok("customer phone hidden from courier before approval", "العميل:" not in text(cp))
    ok("no start-delivery button before approval", "أنا في الطريق للاستلام" not in text(cp))
    ok("DB: assigned + draft + 15", status(oid)[:3] == ("assigned", "draft", 15.0))

    # ---- 2) العميل أثناء مسودة المندوب: لا يرى سعرًا ولا اسم مندوب
    cu = customer_orders()
    ok("customer in draft: sees 'courier is setting the fare', no price/name", wait_text(cu, "المندوب يحدد الأجرة الآن") and "المندوب أحمد" not in text(cu) and "موافقة وبدء التوصيل" not in text(cu))
    cu.context.close()

    # ---- 3) المندوب يعدّل الأجرة إلى 18 ويرسلها
    cp.fill(f"#fe{oid}", "18"); cp.click("button:has-text('إرسال الأجرة للعميل')")
    ok("courier: fare now 'proposed' and waiting for customer", wait_text(cp, "الأجرة المقترحة: 18 ج") and "بانتظار موافقة العميل" in text(cp))
    ok("courier: button becomes 'edit proposed fare'", cp.locator("button:has-text('تعديل الأجرة المقترحة')").count() == 1)
    ok("DB: proposed + 18", status(oid)[:3] == ("assigned", "proposed", 18.0))

    # ---- 4) العميل يرى اسم المندوب وسعر التوصيل
    cu = customer_orders()
    ok("customer sees courier name and 18 fare", wait_text(cu, "المندوب المندوب أحمد يقترح أجرة 18 ج"))
    ok("customer sees approve + reject buttons", cu.locator("button:has-text('موافقة وبدء التوصيل')").count() == 1 and cu.locator("button:has-text('رفض الأجرة')").count() == 1)

    # ---- 5) المندوب يعدّل مرة ثانية (20) والعميل يرى السعر الجديد بعد تحديث الصفحة ولا تعمل موافقة قديمة
    cp.fill(f"#fe{oid}", "20"); cp.click("button:has-text('تعديل الأجرة المقترحة')"); wait_text(cp, "الأجرة المقترحة: 20 ج")
    ok("DB: re-proposed 20", status(oid)[:3] == ("assigned", "proposed", 20.0))
    ok("stale approval (fee 18) is refused by the server, order stays proposed", call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 18}, cust)[0] == 409 and status(oid)[1] == "proposed")
    cu.context.close()
    cu = customer_orders(); ok("after reload customer sees 20", wait_text(cu, "يقترح أجرة 20 ج"))

    # ---- 6) العميل يوافق -> المندوب يرى بيانات العميل ويبدأ التوصيل
    cu.click("button:has-text('موافقة وبدء التوصيل')")
    ok("customer approval message", wait_text(cu, "تمت الموافقة على الأجرة"))
    ok("DB: approved at 20", status(oid)[:3] == ("assigned", "approved", 20.0))
    cp.reload(); cp.wait_for_selector("text=طلباتي الحالية")
    ok("courier sees customer contact + 'الرسوم: 20 ج' after approval", wait_text(cp, "العميل: عميل تجريبي") and "الرسوم: 20 ج" in text(cp) and cp.locator(f"#fe{oid}").count() == 0)
    for label in ("أنا في الطريق للاستلام", "تم استلام الطلب", "في الطريق للعميل", "وصلت للعميل", "تم التسليم"):
        cp.click(f"button:has-text('{label}')"); cp.wait_for_timeout(500)
    ok("courier walked to awaiting_confirmation", status(oid)[0] == "awaiting_confirmation")
    cu.context.close(); cu = customer_orders(); cu.wait_for_selector("button:has-text('تأكيد الاستلام')"); cu.click("button:has-text('تأكيد الاستلام')"); cu.wait_for_timeout(800)
    ok("customer confirms -> completed, one commission of -4", status(oid)[0] == "completed" and sql("SELECT COUNT(*),SUM(amount) FROM wallet_entries WHERE kind='commission' AND ref_id=?", oid)[0] == (1, -4.0))

    # ---- 7) رفض العميل للأجرة: يرجع للبحث والمندوب الأول لا يراه والثاني يراه
    oid2 = new_order(); cp.reload(); cp.wait_for_selector(f"text=طلب #{oid2}"); cp.click("button:has-text('قبول')"); wait_text(cp, "الأجرة الافتراضية للمنطقة")
    cp.click("button:has-text('إرسال الأجرة للعميل')"); wait_text(cp, "بانتظار موافقة العميل")
    cu = customer_orders(); cu.click("button:has-text('رفض الأجرة')")
    ok("customer rejection message", wait_text(cu, "تم رفض الأجرة"))
    ok("DB: back to searching, unassigned", status(oid2)[:2] == ("searching", "none") and status(oid2)[3] is None)
    cp.reload(); cp.wait_for_selector("text=طلبات متاحة"); cp.wait_for_timeout(500)
    ok("first courier no longer sees the rejected order", f"طلب #{oid2}" not in text(cp))
    c2p = courier_page(c2)
    ok("second courier sees it", wait_text(c2p, f"طلب #{oid2}"))

    for pg in [cp, c2p, cu]: ok("no JS errors on page: " + pg.url.split("/")[-1], not pg.errs or print(pg.errs))
    b.close()
print("ALL PASSED")
