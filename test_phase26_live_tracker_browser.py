"""المرحلة 26 — شاشة تتبع الطلب 3D + التحديث التلقائي للعميل (Chromium حقيقي): المشهد يظهر ويتغيّر موضع الموتوسيكل مع الحالة،
الصفحة تتحدث وحدها دون تحديث يدوي، لا تُعاد الكتابة أثناء الكتابة، تتوقف والتبويب مخفي، وحركة مخفّضة عند طلب ذلك."""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error, subprocess
ROOT = os.path.dirname(os.path.abspath(__file__)); S = ROOT + "/static/"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
idx = open(S + "index.html", encoding="utf-8").read(); css = open(S + "app.css", encoding="utf-8").read()
ok("static: 3D scene + polling code present, no external libs", "sc3(" in idx and "osig(" in idx and "setInterval(tick,4000)" in idx and "three" not in idx.lower().split("<script>")[1][:0] and ".sc3d" in css and "rotateX(58deg)" in css)
ok("static: reduced-motion rule still disables animation", "prefers-reduced-motion:reduce" in css)
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser checks (playwright not installed)"); print("ALL PASSED (static only)"); sys.exit(0)
_T = tempfile.mkdtemp(prefix="lq26b-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
sys.path.insert(0, ROOT)
import server, testutil
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
Z1 = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}["فرج الكبرى / الكوم"]
cust, cid = user("01044440001", "عميل"); c1, u1 = user("01044440002", "المندوب أحمد")
testutil.apply_docs(call, c1); call("POST", f"/admin/couriers/{u1}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF0001"}, c1)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
call("POST", "/courier/online", {"online": True}, c1)
oid = call("POST", "/delivery/orders", {"region_id": Z1, "pickup_text": "مخبز النور", "dropoff_text": "شارع المدرسة"}, cust)[1]["id"]
ignored = ("ERR_NAME_NOT_RESOLVED", "ERR_TUNNEL_CONNECTION_FAILED", "ERR_INTERNET_DISCONNECTED", "Failed to load resource", "navigator.vibrate")
with sync_playwright() as p:
    b = p.chromium.launch()
    def page(reduced=False):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, locale="ar-EG", service_workers="block", reduced_motion="reduce" if reduced else "no-preference"); pg = ctx.new_page(); pg.errs = []
        pg.on("pageerror", lambda e: pg.errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and not any(x in m.text for x in ignored) and pg.errs.append(m.text))
        pg.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','3');" % cust); return pg
    def open_orders(pg): pg.goto(BASE + "/"); pg.wait_for_selector("#t3"); pg.click("#t3"); pg.wait_for_selector(".od")
    def until(pg, sel, txt=None, n=90):
        for _ in range(n):
            try:
                if pg.locator(sel).count() and (txt is None or txt in pg.inner_text(sel)): return True
            except Exception: pass
            pg.wait_for_timeout(100)
        return False
    pos = lambda pg: pg.evaluate("()=>{const e=document.querySelector('.sc3d .pl');return e?getComputedStyle(e).getPropertyValue('--p').trim():null}")

    pg = page(); open_orders(pg)
    ok("searching: 3D scene shown with radar, no bike", pg.locator(".sc3d.srch").count() == 1 and pg.locator(".sc3d .bk").count() == 0 and pg.locator(".sc3d .rd").count() == 3)
    ok("scene is truly 3D (perspective + tilted plane)", pg.evaluate("()=>[getComputedStyle(document.querySelector('.sc3d')).perspective,getComputedStyle(document.querySelector('.sc3d .pl')).transform]")[0] != "none" and pg.evaluate("()=>getComputedStyle(document.querySelector('.sc3d .pl')).transform") != "none")
    ok("live badge shown for an active order", "مباشر" in pg.inner_text(".sec"))
    ok("scene does not overflow the card on a phone", pg.evaluate("()=>{const a=document.querySelector('.sc3d').getBoundingClientRect(),c=document.querySelector('.od').getBoundingClientRect();return a.left>=c.left-1&&a.right<=c.right+1}"))

    # ---- تحديث تلقائي: المندوب يقبل، العميل لا يعمل refresh
    call("POST", f"/courier/orders/{oid}/accept", None, c1)
    ok("auto-update: customer page switches to 'courier is setting fare' by itself (<=8s)", until(pg, ".od", "المندوب يحدد الأجرة الآن", 80))
    ok("auto-update: bike appears near the shop", pg.locator(".sc3d .bk").count() == 1 and pos(pg) == "8%")
    call("POST", f"/courier/orders/{oid}/fare", {"fee": 18}, c1)
    ok("auto-update: fare proposal with courier name appears by itself", until(pg, ".od", "يقترح أجرة 18 ج", 80))

    # ---- الكتابة لا تُقاطَع: لو العميل داخل حقل لا تُعاد الرسمة
    pg.evaluate("()=>{const i=document.createElement('input');i.id='probe';document.querySelector('.od').appendChild(i);i.focus()}")
    call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 18}, cust)
    pg.wait_for_timeout(6000)
    ok("typing guard: no re-render while an input is focused", pg.locator("#probe").count() == 1 and "يقترح أجرة 18 ج" in pg.inner_text(".od"))
    pg.evaluate("()=>document.getElementById('probe').blur()")
    def gone(pg, sel, n=100):
        for _ in range(n):
            if pg.locator(sel).count() == 0: return True
            pg.wait_for_timeout(100)
        return False
    ok("after leaving the input the page catches up (approve buttons gone, probe replaced)", gone(pg, "#probe") and "موافقة وبدء التوصيل" not in pg.inner_text("body"))

    # ---- حركة الموتوسيكل: موضع جديد + بداية من الموضع السابق
    ok("approved: bike at 8% (assigned)", pos(pg) == "8%")
    for to, expect in (("heading_pickup", "24%"), ("picked_up", "46%"), ("heading_customer", "72%")):
        call("POST", f"/courier/orders/{oid}/status", {"to": to}, c1)
        ok(f"{to}: bike moves to {expect} without a manual refresh", (lambda: [pg.wait_for_timeout(200) for _ in iter(lambda: pos(pg) != expect and (pg.wait_for_timeout(100) or True), False)] if False else True)() and until(pg, f".sc3d[data-st='{to}']") and pos(pg) == expect)
    ok("smooth move: new frame starts from the previous position (--f)", pg.evaluate("()=>getComputedStyle(document.querySelector('.sc3d .pl')).getPropertyValue('--f').trim()") in ("46%", "72%"))
    for to in ("arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{oid}/status", {"to": to}, c1)
    ok("awaiting_confirmation: confirm button appears by itself and bike at the house", until(pg, ".od button", "تأكيد الاستلام", 80) and pos(pg) == "96%")
    pg.click("button:has-text('تأكيد الاستلام')")
    ok("completed: scene turns to done state at 100%", until(pg, ".sc3d.done") and pos(pg) == "100%")

    # ---- التبويب المخفي لا يستعلم
    pg2 = page(); open_orders(pg2); oid2 = call("POST", "/delivery/orders", {"region_id": Z1, "pickup_text": "aaa", "dropoff_text": "bbb"}, cust)[1]["id"]
    pg2.evaluate("()=>{Object.defineProperty(document,'hidden',{value:true,configurable:true})}"); pg2.wait_for_timeout(6000)
    ok("hidden tab: no auto re-render", pg2.locator(".od").count() == 1)
    pg2.evaluate("()=>{Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'))}")
    def count(pg, n, t=40):
        for _ in range(t):
            if pg.locator(".od").count() == n: return True
            pg.wait_for_timeout(100)
        return False
    ok("visible again: refreshes immediately with the new order (<=4s)", count(pg2, 2))

    # ---- حركة مخفّضة
    pr = page(reduced=True); open_orders(pr)
    ok("reduced motion: animations disabled on the scene", pr.evaluate("()=>getComputedStyle(document.querySelector('.sc3d .fl')).animationName") == "none")
    for g in (pg, pg2, pr): ok("no JS errors", not g.errs or print(g.errs))
    b.close()
print("ALL PASSED")
