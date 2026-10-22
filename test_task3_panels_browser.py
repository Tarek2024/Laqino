# المهمة 3: إعادة تصميم لوحتي الصيدلية والمندوب — Chromium حقيقي: هاتف 390x844 وكمبيوتر 1280x800.
# يتحقق من: الهيدر ورجوع للتطبيق، هوية التطبيق، عمود واحد/عمودان، عدم التمرير الأفقي، وأن الوظائف ما زالت تعمل بالنقر الفعلي.
# يُتخطى إن لم يتوفر playwright. قاعدة مؤقتة فقط. LAQINO_SHOTS=<مجلد> لحفظ اللقطات.
import os, sys, json, time, tempfile, threading, sqlite3, urllib.request, urllib.error
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser test (playwright not installed)"); sys.exit(0)
_TMP = tempfile.mkdtemp(prefix="laqino-t3-"); os.environ["LAQINO_DB"] = os.path.join(_TMP, "t.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "up"); os.makedirs(os.environ["LAQINO_UPLOADS"])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN"
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
db = lambda q, a=(): sqlite3.connect(os.environ["LAQINO_DB"]).execute(q, a).fetchall()
# --- بيانات: صيدلية معتمدة باستفسارين، مندوب معتمد برصيد وطلبين، عميل ---
cust, cid = user("01022220001", "عميل"); pharm, pid = user("01022220002", "صيدلي"); cour, kid = user("01022220003", "مندوب"); cour_p, kp = user("01022220004", "مندوب معلق")
assert call("POST", "/providers/apply", {"name_ar": "صيدلية الشفاء", "region_id": 3, "address": "ش 1"}, pharm)[0] == 201
assert call("POST", "/admin/providers/%d/review" % pid, {"status": "approved"}, at)[0] == 200
for nm in ("بنادول إكسترا", "أنسولين"): assert call("POST", "/medical/inquiries", {"medicine_name": nm, "region_id": 3, "note": "علبة واحدة"}, cust)[0] in (200, 201)
assert apply_docs(call, cour)[0] == 201 and call("POST", "/admin/couriers/%d/review" % kid, {"status": "approved"}, at)[0] == 200
assert apply_docs(call, cour_p)[0] == 201
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
assert call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "REF0001"}, cour)[0] in (200, 201)
tid = call("GET", "/admin/topups", None, at)[1][0]["id"]; assert call("POST", "/admin/topups/%d/review" % tid, {"status": "approved"}, at)[0] == 200
call("POST", "/courier/online", {"online": True}, cour)
o1 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "الصيدلية المركزية", "dropoff_text": "شارع النصر ٥", "details": "x"}, cust)[1]["id"]
assert call("POST", "/courier/orders/%d/accept" % o1, {}, cour)[0] == 200   # طلب جارٍ
import testutil; testutil.fare_ok(o1)
o2 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "محل الورد", "dropoff_text": "شارع السلام ٩", "details": "y"}, cust)[1]["id"]   # طلب متاح

with sync_playwright() as p:
    b = p.chromium.launch()
    def mk(kind, tok, name):
        vp = {"width": 390, "height": 844} if kind == "phone" else {"width": 1280, "height": 800}
        ctx = b.new_context(viewport=vp, device_scale_factor=2 if kind == "phone" else 1, is_mobile=kind == "phone", has_touch=kind == "phone", locale="ar-EG", service_workers="block")
        pg = ctx.new_page(); pg.errs = []; pg.alerts = []; pg.kind = kind; pg.name = name
        pg.on("pageerror", lambda e: pg.errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and "ERR_NAME_NOT_RESOLVED" not in m.text and "ERR_TUNNEL_CONNECTION_FAILED" not in m.text and "Blocked call to navigator.vibrate" not in m.text and "ERR_INTERNET_DISCONNECTED" not in m.text and "favicon" not in m.text and "the server responded with a status of 4" not in m.text and pg.errs.append(m.text))   # ردود 4xx من الـAPI سلوك طبيعي (مثلًا مندوب معلّق) وليست أخطاء صفحة
        pg.on("dialog", lambda d: (pg.alerts.append(d.message), d.accept()))
        pg.add_init_script("localStorage.setItem('rg','3');" + ("localStorage.setItem('t','%s');" % tok if tok else "")); return pg
    def open_(pg, path, sel):
        pg.goto(BASE + path); pg.wait_for_selector(sel, timeout=9000); pg.wait_for_timeout(400)
    def shot(pg): SH and pg.screenshot(path=os.path.join(SH, "%s-%s.png" % (pg.name, pg.kind)), full_page=True)
    fits = lambda pg: pg.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
    def lefts(pg): return pg.evaluate("[...document.querySelectorAll('main > .card')].map(e=>Math.round(e.getBoundingClientRect().left))")
    css = lambda pg, sel, prop: pg.evaluate("(a)=>getComputedStyle(document.querySelector(a[0]))[a[1]]", [sel, prop])

    for kind in ("phone", "desktop"):
        # ---------- الصيدلية ----------
        pg = mk(kind, pharm, "pharmacy"); open_(pg, "/pharmacy.html", "h2.sec")
        ok("[%s] pharmacy: header has back-to-app link to /" % kind, pg.get_attribute("header.ph a.back", "href") == "/" and "رجوع للتطبيق" in pg.inner_text("header.ph") and "لوحة الصيدلية" in pg.inner_text("header.ph h1"))
        ok("[%s] pharmacy: header title and back link are white on navy (readable)" % kind, css(pg, "header.ph h1", "color") == "rgb(255, 255, 255)" and css(pg, "header.ph a.back", "color") == "rgb(255, 255, 255)")
        ok("[%s] pharmacy: back link tap target >= 40px" % kind, pg.query_selector("header.ph a.back").bounding_box()["height"] >= 40)
        ok("[%s] pharmacy: app identity (navy header, orange buttons, 20px cards, 16px fields)" % kind,
           css(pg, "header.ph", "backgroundImage").count("15, 42, 92") == 1 and css(pg, "main button", "backgroundColor") == "rgb(242, 140, 27)" and css(pg, "main .card", "borderTopLeftRadius") == "20px" and css(pg, "main input", "fontSize") == "16px")
        ok("[%s] pharmacy: both inquiries and the section headings rendered" % kind, "بنادول إكسترا" in pg.inner_text("main") and "أنسولين" in pg.inner_text("main") and pg.locator("h2.sec").count() == 3)  # +1: «سوق الصيدليات»
        ok("[%s] pharmacy: no horizontal overflow, no JS errors" % kind, fits(pg) and not pg.errs)
        L = lefts(pg)
        if kind == "phone": ok("[phone] pharmacy: single column", len(set(L)) == 1)
        else: ok("[desktop] pharmacy: two columns, content centred and <= 1080px", len(set(L)) == 2 and pg.evaluate("document.querySelector('main').getBoundingClientRect().width") <= 1081)
        shot(pg)
        # وظائف بالنقر الفعلي (لا تغيّر): ردّ على استفسار + تأكيد توافر دواء
        iid = db("SELECT id FROM medicine_inquiries WHERE medicine_name='بنادول إكسترا'")[0][0]
        pg.select_option("#si%d" % iid, "available"); pg.fill("#pi%d" % iid, "33"); pg.click("button[onclick=\"rs('i',%d)\"]" % iid); pg.wait_for_timeout(900)
        r = db("SELECT status,price FROM inquiry_responses WHERE inquiry_id=? AND provider_id=?", (iid, pid))
        ok("[%s] pharmacy: replying to an inquiry still works (saved in DB)" % kind, r == [("available", 33.0)] or r == [("available", 33)])
        pg.fill("#sn", "كونجستال"); pg.fill("#sp", "20"); pg.click("button[onclick='st()']"); pg.wait_for_timeout(900)
        ok("[%s] pharmacy: stock confirmation still works" % kind, bool(db("SELECT 1 FROM provider_stock WHERE medicine_name='كونجستال' AND provider_id=?", (pid,))))
        pg.context.close()
        pg = mk(kind, "", "pharmacy-guest"); open_(pg, "/pharmacy.html", "main .card")
        ok("[%s] pharmacy (no login): message card, back link present, no overflow" % kind, "سجّل الدخول" in pg.inner_text("main") and pg.query_selector("header.ph a.back") is not None and fits(pg) and not pg.errs); pg.context.close()

        # ---------- المندوب ----------
        call("POST", "/courier/online", {"online": True}, cour)
        if kind == "desktop":   # بيانات جديدة للجولة الثانية: طلب متاح + طلب جارٍ
            o3 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "الصيدلية الجديدة", "dropoff_text": "شارع الجمهورية ٣", "details": "z"}, cust)[1]["id"]
        pg = mk(kind, cour, "courier"); open_(pg, "/courier.html", ".k")
        ok("[%s] courier: header has back-to-app link to /" % kind, pg.get_attribute("header.ph a.back", "href") == "/" and "لوحة المندوب" in pg.inner_text("header.ph h1"))
        ok("[%s] courier: header title is white on navy (readable)" % kind, css(pg, "header.ph h1", "color") == "rgb(255, 255, 255)")
        ok("[%s] courier: app identity" % kind, css(pg, "main button", "backgroundColor") == "rgb(242, 140, 27)" and css(pg, "main .card", "borderTopLeftRadius") == "20px")
        txt = pg.inner_text("main")
        ok("[%s] courier: all sections present (status, balance 95?, current, available, performance, topup, wallet)" % kind, all(x in txt for x in ("الحالة", "الرصيد", "طلباتي الحالية", "طلبات متاحة", "أدائي", "شحن الرصيد", "حركة المحفظة")) and "100 ج" in txt)
        ok("[%s] courier: no horizontal overflow, no JS errors" % kind, fits(pg) and not pg.errs)
        L = lefts(pg)
        if kind == "phone": ok("[phone] courier: single column", len(set(L)) == 1)
        else: ok("[desktop] courier: status spans full width, rest in two columns", len(set(L)) == 2 and pg.evaluate("(()=>{const c=document.querySelector('main > .card').getBoundingClientRect(),m=document.querySelector('main').getBoundingClientRect();return c.width>m.width*.9})()"))
        shot(pg)
        pg.click("button:has-text('قبول')"); pg.wait_for_timeout(1200); testutil.fare_ok(o2); pg.wait_for_timeout(6000)
        ok("[%s] courier: accepting an order by tapping still works (2 active orders, 90 net of 5 commission)" % kind, db("SELECT COUNT(*) FROM delivery_orders WHERE courier_id=? AND status='assigned'", (kid,))[0][0] == 2 and not pg.alerts)
        hp = lambda: db("SELECT COUNT(*) FROM delivery_orders WHERE courier_id=? AND status='heading_pickup'", (kid,))[0][0]; h0 = hp()
        pg.click("button:has-text('أنا في الطريق للاستلام') >> nth=0"); pg.wait_for_timeout(1000)
        ok("[%s] courier: advancing order status by tapping still works" % kind, hp() == h0 + 1)
        pg.click("button:has-text('قطع الاتصال')"); pg.wait_for_timeout(900)
        ok("[%s] courier: going offline still works" % kind, call("GET", "/courier/status", None, cour)[1]["online"] is False)
        pg.context.close()
        pg = mk(kind, "", "courier-login"); open_(pg, "/courier.html", "#x_ph")
        ok("[%s] courier login view: single centred card, fields >= 16px, back link, no overflow" % kind, "تسجيل دخول المندوب" in pg.inner_text("main") and pg.locator("main > .card").count() == 1 and css(pg, "#x_ph", "fontSize") == "16px" and fits(pg) and pg.query_selector("header.ph a.back") is not None and not pg.errs)
        ok("[%s] courier login view: card width <= 520px and centred" % kind, pg.evaluate("(()=>{const c=document.querySelector('main > .card').getBoundingClientRect();return c.width<=522&&Math.abs((c.left+c.right)/2-innerWidth/2)<2})()")); shot(pg); pg.context.close()
        pg = mk(kind, cour_p, "courier-pending"); open_(pg, "/courier.html", "main .card")
        ok("[%s] courier pending: status card shown, no overflow" % kind, ("قيد مراجعة" in pg.inner_text("main") or "قيد المراجعة" in pg.inner_text("main") or "مراجعة" in pg.inner_text("main")) and fits(pg) and not pg.errs); pg.context.close()
        pg = mk(kind, cour_p, "courier-apply"); open_(pg, "/courier.html", "main .card"); pg.evaluate("applyView()"); pg.wait_for_selector("#x_f1", timeout=5000); pg.wait_for_timeout(500)
        ok("[%s] courier apply form (file fields + region select) fits and is usable" % kind, fits(pg) and pg.locator("#x_rg select").count() >= 1 and pg.query_selector("#x_f1").bounding_box()["width"] > 200); pg.context.close()
    # لا يزال التطبيق الأساسي يفتح من رابط الرجوع
    pg = mk("phone", pharm, "back"); open_(pg, "/pharmacy.html", "header.ph a.back"); pg.click("header.ph a.back"); pg.wait_for_url(BASE + "/", timeout=8000); pg.wait_for_selector(".tiles", timeout=8000)
    ok("tapping 'رجوع للتطبيق' lands on the customer app home", pg.url.rstrip("/") == BASE)
    # شاشة صغيرة جدًا
    ctx = b.new_context(viewport={"width": 320, "height": 640}, is_mobile=True, has_touch=True, service_workers="block"); q = ctx.new_page()
    q.add_init_script("localStorage.setItem('rg','3');localStorage.setItem('t','%s');" % cour); q.goto(BASE + "/courier.html"); q.wait_for_selector(".k", timeout=9000)
    ok("320px: courier panel and header do not overflow, back link still tappable", q.evaluate("document.documentElement.scrollWidth<=innerWidth+1") and q.query_selector("header.ph a.back").bounding_box()["width"] >= 40)
    b.close()
print("ALL TASK-3 BROWSER CHECKS PASSED")
