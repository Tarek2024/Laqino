# المرحلة 40 في Chromium حقيقي بمقاس موبايل: زر «اطلب دليفري» في لوحة الصيدلية + شاشة المندوب. يُتخطى بأمان إن لم يتوفر playwright/Chromium.
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
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
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
Z2 = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}["المجد 55"]
ph, pid = user("01041000001"); cu, uid = user("01041000002")
call("POST", "/providers/apply", {"name_ar": "صيدلية النور", "region_id": Z2, "address": "شارع البحر"}, ph); call("POST", f"/admin/providers/{pid}/review", {"status": "approved"}, at)
apply_docs(call, cu); call("POST", f"/admin/couriers/{uid}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "REF0001"}, cu)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
call("POST", "/courier/online", {"online": True}, cu)
def sql(q, *a):
    c = sqlite3.connect(os.environ["LAQINO_DB"]); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
try:
    pw = sync_playwright().start(); br = pw.chromium.launch()
except Exception as e:
    print("SKIP browser part (chromium unavailable):", str(e)[:80]); sys.exit(0)
def page(tok):
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2); ctx.add_init_script("localStorage.setItem('t','%s')" % tok); p = ctx.new_page(); dialogs = []
    p.on("dialog", lambda d: (dialogs.append(d.message), d.accept())); return p, dialogs
p, dlg = page(ph); p.goto(BASE + "/pharmacy.html"); p.wait_for_selector("#sn", state="attached")
ok("button hidden while the admin switch is off", p.locator("#dlw").count() == 0)
call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 0}, at); p.reload(); p.wait_for_selector("#dlb")
ok("luxury button + spinning ring shown when on", p.locator("#dlb").is_visible() and p.locator("#dlr").is_visible() and "اطلب دليفري" in p.locator("#dlb").inner_text())
ok("ring is animated (CSS spin)", "dlspin" in p.eval_on_selector("#dlr", "e=>getComputedStyle(e,'::before').animationName"))
ok("button looks 3D (layered shadow + gradient)", "gradient" in p.eval_on_selector("#dlb", "e=>getComputedStyle(e).backgroundImage") and p.eval_on_selector("#dlb", "e=>getComputedStyle(e).boxShadow").count("rgb") >= 4)
p.screenshot(path=os.path.join(tempfile.gettempdir(), "dl_idle.png"))
p.click("#dlb"); p.wait_for_selector("#dls:has-text('جاري البحث')")
ok("one tap created exactly one searching order", sql("SELECT COUNT(*),MAX(origin_type),MAX(fee) FROM delivery_orders") == [(1, "provider_pickup", 0)])
ok("ring switches to fast 'go' state", "go" in p.get_attribute("#dlr", "class"))
p.screenshot(path=os.path.join(tempfile.gettempdir(), "dl_search.png"))
p.click(".dl-opt summary"); p.fill("#dla", "عمارة 5"); p.click("#dlb"); p.locator("#dll .dl-it").nth(1).wait_for()
ok("optional address saved on the second tap", sql("SELECT dropoff_text FROM delivery_orders ORDER BY id DESC LIMIT 1") == [("عمارة 5",)])
# المندوب
oid = sql("SELECT id FROM delivery_orders ORDER BY id LIMIT 1")[0][0]
cp, _ = page(cu); cp.goto(BASE + "/courier.html"); cp.wait_for_selector("text=استلام من صيدلية")
ok("courier sees provider-pickup offer without fare", cp.locator("text=بدون أجرة داخل التطبيق").first.is_visible())
cp.locator("button", has_text="قبول").first.click(); cp.wait_for_selector("text=أنا في الطريق للصيدلية")
ok("courier card shows pharmacy flow (no 'to customer' steps)", cp.locator("text=في الطريق للعميل").count() == 0 and cp.locator("text=لا أجرة داخل التطبيق لهذا الطلب").first.is_visible())
cp.click("text=أنا في الطريق للصيدلية"); cp.wait_for_selector("text=استلمت الأوردر من الصيدلية"); cp.click("text=استلمت الأوردر من الصيدلية")
for _ in range(50):  # ينتظر اكتمال الطلب فعليًا (نص «مكتمل» يظهر أصلًا في إحصائيات المندوب فلا يصلح شرطًا)
    if sql("SELECT status FROM delivery_orders WHERE id=?", oid) == [("completed",)]: break
    time.sleep(.2)
ok("pickup completes the order in the DB", sql("SELECT status FROM delivery_orders WHERE id=?", oid) == [("completed",)])
p.wait_for_selector("#dll:has-text('تم تسليم الأوردر للمندوب')", timeout=20000)
ok("pharmacy list updates itself and shows timings", "استلام بعد" in p.inner_text("#dll"))
p.screenshot(path=os.path.join(tempfile.gettempdir(), "dl_done.png"))
p.locator(".dl-x").first.click(); p.wait_for_selector("#dll:has-text('ملغي')")
ok("pharmacy cancels the open request from the card", sql("SELECT COUNT(*) FROM delivery_orders WHERE status='cancelled'") == [(1,)])
# الإدارة
ap, _ = page(at); ap.goto(BASE + "/admin.html"); ap.fill("#p", "01000000000"); ap.fill("#w", "AdminPass123"); ap.click('button:has-text("دخول")'); ap.wait_for_selector("nav button")
ap.evaluate("tab='homeui';shell()"); ap.wait_for_selector("#feat-pd", timeout=15000)
ok("admin card reflects current switch (on)", ap.is_checked("#pd-on"))
ap.fill("#pd-comm", "7"); ap.click("#feat-pd button:has-text('حفظ')"); ap.wait_for_selector("#feat-pd:has-text('مفعّل')")
ok("admin saves fixed commission from the UI", call("GET", "/admin/provider-delivery", None, at)[1] == {"enabled": True, "commission": 7.0})
ap.uncheck("#pd-on"); ap.click("#feat-pd button:has-text('حفظ')"); ap.wait_for_selector("#feat-pd:has-text('مطفي')")
ok("admin turns the feature off from the UI", call("GET", "/admin/provider-delivery", None, at)[1]["enabled"] is False)
br.close(); pw.stop(); print("ALL OK")
