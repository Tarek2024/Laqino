"""المرحلة 38 — بروفايل المندوب: صورة يضبطها المندوب، وAPI بيانات فعلية، وصلاحيات الاطلاع، وشاشة العميل (Chromium) بزر الرجوع."""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error, sqlite3, base64
ROOT = os.path.dirname(os.path.abspath(__file__))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
_T = tempfile.mkdtemp(prefix="lq38-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
sys.path.insert(0, ROOT)
import server, testutil
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try:
        x = urllib.request.urlopen(r); b = x.read(); return x.status, (b if raw else json.loads(b))
    except urllib.error.HTTPError as e: return e.code, (e.read() if raw else json.loads(e.read()))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
def png(color):
    from PIL import Image; import io
    b = io.BytesIO(); Image.new("RGB", (600, 400), color).save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}; Z2 = Z["المجد 55"]
cust, cid = user("01038880001", "محمد علي"); other, oid_ = user("01038880002", "عميل آخر"); cu, cuid = user("01038880003", "المندوب كريم"); c2, c2id = user("01038880004", "مندوب جديد")
for t, u in ((cu, cuid), (c2, c2id)):
    testutil.apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 500, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (cu, c2): call("POST", "/courier/online", {"online": True}, t)
def order(token=cust): return call("POST", "/delivery/orders", {"region_id": Z2, "pickup_text": "مخبز النور", "dropoff_text": "شارع المدرسة"}, token)[1]["id"]
def mine(oid): return [o for o in call("GET", "/delivery/orders", None, cust)[1] if o["id"] == oid][0]
def finish(oid):
    call("POST", f"/courier/orders/{oid}/accept", {}, cu); call("POST", f"/courier/orders/{oid}/fare", {"fee": 20}, cu); call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 20}, cust)
    for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{oid}/status", {"to": to}, cu)
    call("POST", f"/delivery/orders/{oid}/confirm", {}, cust)

# ---- 1) قبل أي طلب: لا كشف
ok("customer without an order with courier gets 404", call("GET", f"/couriers/{cuid}/profile", None, cust)[0] == 404)
ok("anonymous rejected", call("GET", f"/couriers/{cuid}/profile")[0] in (401, 403))
# ---- 2) الصورة: يضبطها المندوب فقط
me_before = call("GET", "/courier/status", None, cu)[1]
ok("status exposes user_id + no avatar yet", me_before["user_id"] == cuid and me_before["has_avatar"] is False)
f1 = call("POST", "/files", {"data": png("red")}, cu)[1]["id"]
ok("courier sets avatar", call("POST", "/courier/avatar", {"file_id": f1}, cu)[0] == 200 and call("GET", "/courier/status", None, cu)[1]["has_avatar"] is True)
ok("customer cannot set courier avatar (not courier)", call("POST", "/courier/avatar", {"file_id": f1}, cust)[0] == 403)
ok("cannot use someone else's file", call("POST", "/courier/avatar", {"file_id": f1}, c2)[0] == 400)
doc = sql("SELECT file_id FROM courier_documents WHERE courier_id=? LIMIT 1", cuid)[0][0]
ok("verification document cannot become avatar", call("POST", "/courier/avatar", {"file_id": doc}, cu)[0] == 409)
ok("avatar file protected from /files delete", call("POST", f"/files/{f1}/delete", {}, cu)[0] == 409)
f2 = call("POST", "/files", {"data": png("blue")}, cu)[1]["id"]
ok("courier replaces avatar", call("POST", "/courier/avatar", {"file_id": f2}, cu)[0] == 200)
ok("old avatar row + disk file removed", sql("SELECT COUNT(*) FROM files WHERE id=?", f1)[0][0] == 0 and sql("SELECT avatar_file_id FROM couriers WHERE user_id=?", cuid)[0][0] == f2)
ok("avatar is separate from ID selfie/documents", sql("SELECT COUNT(*) FROM courier_documents WHERE file_id=?", f2)[0][0] == 0)
# ---- 3) أوامر: اقتراح أجرة => يظهر courier_id للعميل؛ قبله لا
o1 = order(); call("POST", f"/courier/orders/{o1}/accept", {}, cu)
ok("draft fare: courier id & name hidden from customer", mine(o1)["courier_id"] is None and mine(o1)["courier_name"] is None)
ok("draft fare: profile still 404", call("GET", f"/couriers/{cuid}/profile", None, cust)[0] == 404)
call("POST", f"/courier/orders/{o1}/fare", {"fee": 20}, cu)
ok("proposed fare exposes courier_id", mine(o1)["courier_id"] == cuid)
st, pr = call("GET", f"/couriers/{cuid}/profile", None, cust)
ok("customer with proposed fare can open profile", st == 200 and pr["name"] == "المندوب كريم" and pr["has_photo"] and pr["rating_count"] == 0 and pr["rating_avg"] is None and pr["completed"] == 0 and pr["comments"] == [])
ok("availability true when online", pr["available"] is True)
ok("other customer still 404", call("GET", f"/couriers/{cuid}/profile", None, other)[0] == 404)
ok("other courier 404", call("GET", f"/couriers/{cuid}/profile", None, c2)[0] == 404)
ph = call("GET", f"/couriers/{cuid}/photo", None, cust, raw=True)
ok("photo served to authorised customer as image", ph[0] == 200 and ph[1][:4] == b"\x89PNG")
ok("photo 404 to stranger", call("GET", f"/couriers/{cuid}/photo", None, other, raw=True)[0] == 404)
ok("courier sees own profile / admin sees any", call("GET", f"/couriers/{cuid}/profile", None, cu)[0] == 200 and call("GET", f"/couriers/{cuid}/profile", None, at)[0] == 200)
ok("no avatar -> 404 photo, has_photo false", call("GET", f"/couriers/{c2id}/photo", None, at, raw=True)[0] == 404 and call("GET", f"/couriers/{c2id}/profile", None, at)[1]["has_photo"] is False)
ok("profile never leaks phone", "phone" not in json.dumps(pr))
# ---- 4) الفعلي: إكمال + تقييمات
call("POST", f"/delivery/orders/{o1}/fare/approve", {"fee": 20}, cust)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{o1}/status", {"to": to}, cu)
call("POST", f"/delivery/orders/{o1}/confirm", {}, cust)
ok("rating inserted", call("POST", f"/delivery/orders/{o1}/rate", {"stars": 5, "comment": "ممتاز وسريع"}, cust)[0] == 201)
o2 = order(); finish(o2); call("POST", f"/delivery/orders/{o2}/rate", {"stars": 4}, cust)  # بلا تعليق
o3 = order(); call("POST", f"/courier/orders/{o3}/accept", {}, cu); call("POST", f"/courier/orders/{o3}/fare", {"fee": 30}, cu); call("POST", f"/delivery/orders/{o3}/fare/reject", {"fee": 30}, cust)  # قُبل ولم يكتمل
pr = call("GET", f"/couriers/{cuid}/profile", None, cust)[1]
ok("rating avg/count real (4.5 over 2)", pr["rating_avg"] == 4.5 and pr["rating_count"] == 2)
ok("completed = 2", pr["completed"] == 2)
ok("completion rate = 2 accepted-by-3 (0.667)", pr["completion_rate"] == round(2 / 3, 3))
ok("only commented ratings listed, first name only", len(pr["comments"]) == 1 and pr["comments"][0]["comment"] == "ممتاز وسريع" and pr["comments"][0]["customer"] == "محمد" and pr["comments"][0]["stars"] == 5)
ok("matches /courier/stats", call("GET", "/courier/stats", None, cu)[1]["completed"] == pr["completed"] and call("GET", "/courier/stats", None, cu)[1]["rating_avg"] == pr["rating_avg"])
ok("completed order keeps access", call("GET", f"/couriers/{cuid}/profile", None, cust)[0] == 200)
call("POST", "/courier/online", {"online": False}, cu)
ok("availability false when offline", call("GET", f"/couriers/{cuid}/profile", None, cust)[1]["available"] is False)
call("POST", "/admin/couriers/%d/review" % cuid, {"status": "suspended", "reason": "x"}, at)
ok("suspended courier profile hidden", call("GET", f"/couriers/{cuid}/profile", None, cust)[0] == 404)
call("POST", "/admin/couriers/%d/review" % cuid, {"status": "approved"}, at); call("POST", "/courier/online", {"online": True}, cu)

# ---- 5) المتصفح
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser (playwright not installed)"); print("ALL PASS"); sys.exit(0)
ignored = ("ERR_NAME_NOT_RESOLVED", "ERR_TUNNEL_CONNECTION_FAILED", "ERR_INTERNET_DISCONNECTED", "Failed to load resource", "navigator.vibrate")
o4 = order(); call("POST", f"/courier/orders/{o4}/accept", {}, cu); call("POST", f"/courier/orders/{o4}/fare", {"fee": 25}, cu)  # بانتظار موافقة العميل
shots = os.environ.get("LAQINO_SHOTS")
with sync_playwright() as p:
    b = p.chromium.launch()
    def page(token, w=390, h=844):
        ctx = b.new_context(viewport={"width": w, "height": h}, locale="ar-EG", service_workers="block"); pg = ctx.new_page(); pg.errs = []
        pg.on("pageerror", lambda e: pg.errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and not any(x in m.text for x in ignored) and pg.errs.append(m.text))
        pg.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','%d');" % (token, Z2)); return pg
    pg = page(cust); pg.goto(BASE + "/"); pg.wait_for_selector("#t3"); pg.click("#t3"); pg.wait_for_selector(".cpm")
    ok("courier mini-card with name shown in order", "المندوب كريم" in pg.inner_text(".cpm"))
    ok("fare decision buttons still present", pg.locator("button:has-text('موافقة وبدء التوصيل')").count() == 1 and pg.locator("button:has-text('رفض الأجرة')").count() == 1)
    pg.wait_for_selector(".cpm .cpa img"); ok("avatar photo loaded into card", True)
    pg.click(".cpm"); pg.wait_for_selector("#cpv .cphero")
    t = pg.inner_text("#cpv")
    for s in ("المندوب كريم", "متاح الآن", "4.5", "2 تقييم", "طلبات مكتملة", "معدل إكمال الطلبات", "50%", "ممتاز وسريع", "محمد", "تعليقات العملاء"): ok("profile shows: " + s, s in t)
    ok("hero avatar image", pg.locator("#cpv .cphero img").count() == 1)
    pg.wait_for_timeout(400)
    if shots: pg.screenshot(path=shots + "/profile.png")
    pg.click("#cpv .cpb"); ok("back closes profile", pg.locator("#cpv").count() == 0)
    ok("back returns to same order with decision buttons", pg.locator("button:has-text('موافقة وبدء التوصيل')").count() == 1)
    pg.click(".cpm .cpt b"); pg.wait_for_selector("#cpv .cphero"); pg.keyboard.press("Escape"); ok("Escape closes", pg.locator("#cpv").count() == 0)
    pg.click(".cpm .cpa"); pg.wait_for_selector("#cpv .cphero"); pg.click("#cpv .cpf button"); ok("footer back button closes", pg.locator("#cpv").count() == 0)
    # قرار الموافقة يعمل بعد الرجوع
    pg.click("button:has-text('موافقة وبدء التوصيل')"); pg.wait_for_timeout(800)
    ok("approval after viewing profile works", sql("SELECT fare_status FROM delivery_orders WHERE id=?", o4)[0][0] == "approved")
    ok("no JS errors on customer", not pg.errs)
    # تقييم بتعليق من واجهة العميل ثم ظهوره في البروفايل
    o5 = order(); finish(o5)
    pg.evaluate("go(3)"); pg.wait_for_selector("#rc%d" % o5)
    ok("rating form has comment box + stars", pg.locator("#s%d" % o5).count() == 1)
    pg.select_option("#s%d" % o5, "3"); pg.fill("#rc%d" % o5, "تأخر شوية لكن محترم"); pg.click("button:has-text('قيّم المندوب')"); pg.wait_for_timeout(800)
    ok("UI rating saved with comment", sql("SELECT stars,comment FROM ratings WHERE order_id=?", o5) == [(3, "تأخر شوية لكن محترم")])
    pg.wait_for_selector(".cpm"); pg.click(".cpm"); pg.wait_for_selector("#cpv .cphero")
    ok("new comment shown in profile", "تأخر شوية لكن محترم" in pg.inner_text("#cpv")); pg.keyboard.press("Escape")
    pg.evaluate("go(3)"); pg.wait_for_selector("text=طلباتي")
    # لوحة المندوب: كارت الصورة + تغيير
    cp = page(cu); cp.goto(BASE + "/courier.html"); cp.wait_for_selector(".pfc")
    ok("courier sees profile card with photo", cp.locator(".pfc .av img").count() == 1 and "تغيير الصورة الشخصية" in cp.inner_text(".pfc"))
    import io; from PIL import Image
    pth = _T + "/new.png"; Image.new("RGB", (900, 700), "green").save(pth)
    cp.set_input_files("#avf", pth); cp.wait_for_timeout(1500)
    ok("avatar changed from courier UI", sql("SELECT avatar_file_id FROM couriers WHERE user_id=?", cuid)[0][0] != f2 and sql("SELECT COUNT(*) FROM files WHERE id=?", f2)[0][0] == 0)
    nb = call("GET", f"/couriers/{cuid}/photo", None, at, raw=True)[1]
    ok("new photo downscaled JPEG", nb[:3] == b"\xff\xd8\xff")
    c2p = page(c2); c2p.goto(BASE + "/courier.html"); c2p.wait_for_selector(".pfc")
    ok("courier without photo: add button + initial", "إضافة صورة شخصية" in c2p.inner_text(".pfc"))
    cp.wait_for_timeout(300)
    ok("no JS errors on courier", not cp.errs and not c2p.errs)
    # شاشة عريضة
    w = page(cust, 1280, 800); w.goto(BASE + "/"); w.wait_for_selector("#t3"); w.click("#t3"); w.wait_for_selector(".cpm"); w.click(".cpm"); w.wait_for_selector("#cpv .cphero")
    ok("desktop profile opens", "ملف المندوب" in w.inner_text("#cpv")); w.keyboard.press("Escape")
    b.close()
print("ALL PASS")
