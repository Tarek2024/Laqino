# المرحلة 85 (م4): دورة المحل — «قبلت الطلب» ثم «جاهز للاستلام» (عمود shop_status في shop_delivery_links فقط) + مراحل واضحة وإشعار للعميل. قاعدة مؤقتة معزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8985; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__))
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph, nm=None):
    call("POST", "/register", {"phone": ph, "name": nm or "u" + ph[-3:], "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
Z2 = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}["المجد 55"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at); call("POST", "/admin/region-fees", {"region_id": Z2, "fee": 25}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
own, _ = user("01290000001"); cust, cid = user("01290000003"); other, _ = user("01290000004"); phm, phid = user("01290000008"); c1, u1 = user("01290000005", "أحمد المندوب"); c2, u2 = user("01290000006", "محمود المندوب")
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
P1 = sql("SELECT phone FROM users WHERE id=?", u1)[0][0]; P2 = sql("SELECT phone FROM users WHERE id=?", u2)[0][0]
call("POST", "/admin/shops-settings", {"enabled": True}, at); call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 2}, at); call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 0}, at)
S = call("POST", "/shops/apply", {"type_id": 1, "name_ar": "مطعم الأمل", "address": "شارع النصر", "phone": "01012345678", "region_id": Z2}, own)[1]["id"]
call("POST", "/admin/shops/%d/review" % S, {"status": "approved"}, at); call("POST", "/owner/shops/%d/open" % S, {}, own)
i1 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "كشري", "price": 35.5}, own)[1]["id"]
call("POST", "/providers/apply", {"name_ar": "صيدلية النور", "region_id": Z2, "address": "شارع البحر"}, phm)
call("POST", f"/admin/providers/{phid}/review", {"status": "approved"}, at)
def mine(t, oid): return [o for o in call("GET", "/delivery/orders", None, t)[1] if o["id"] == oid][0]
def shop_row(oid): return [o for o in call("GET", "/owner/shops/%d/orders" % S, None, own)[1]["items"] if o["id"] == oid][0]
GOOD = {"items": [{"item_id": i1, "qty": 2}], "dropoff_text": "عمارة 5 شقة 3"}


def srow(oid): return [o for o in call("GET", "/owner/shops/%d/orders" % S, None, own)[1]["items"] if o["id"] == oid][0]
def dstat(oid): return sql("SELECT status,updated_at,fare_status,courier_id FROM delivery_orders WHERE id=?", oid)[0]
def notes(t): return [n for n in call("GET", "/notifications", None, t)[1]["items"] if n["kind"] == "shop.stage"]
s, r = call("POST", "/shops/%d/order" % S, GOOD, cust); oid = r["id"]; before = dstat(oid)

# ---- 1) الحالة الابتدائية
ok("new order: shop sees shop_status=new and can progress", srow(oid)["shop_status"] == "new" and srow(oid)["can_progress"] is True)
ok("customer sees shop_status=new", mine(cust, oid)["shop_status"] == "new")
ok("ready before accept -> 409", call("POST", "/owner/shops/%d/orders/%d/ready" % (S, oid), {}, own)[0] == 409 and srow(oid)["shop_status"] == "new")

# ---- 2) الصلاحيات
A = lambda t, a, o=None: call("POST", "/owner/shops/%d/orders/%d/%s" % (S, o or oid, a), {}, t)
ok("anonymous 401, customer 404, other user 404, courier 404", A(None, "accept")[0] == 401 and A(cust, "accept")[0] == 404 and A(other, "accept")[0] == 404 and A(c1, "accept")[0] == 404 and srow(oid)["shop_status"] == "new")
ok("unknown order 404", A(own, "accept", 99999)[0] == 404)
sp = call("POST", "/owner/shops/%d/delivery-request" % S, {"request_key": "x1"}, own)[1]["id"]
ok("shop_pickup order cannot be accepted via customer-order cycle (404)", A(own, "accept", sp)[0] == 404)
call("POST", f"/delivery/orders/{sp}/cancel", {}, own)

# ---- 3) الدورة
r1 = A(own, "accept"); ok("accept -> accepted", r1 == (200, {"id": oid, "shop_status": "accepted"}) and srow(oid)["shop_status"] == "accepted" and srow(oid)["shop_accepted_at"])
ok("accept twice -> 409", A(own, "accept")[0] == 409)
ok("customer sees accepted + a notification", mine(cust, oid)["shop_status"] == "accepted" and [n["title"] for n in notes(cust)] == ["المحل قبل طلبك"] and notes(cust)[0]["link"] == "orders")
ok("delivery_orders untouched by accept (status/fare/courier/updated_at)", dstat(oid) == before)
r2 = A(own, "ready"); ok("ready -> ready", r2 == (200, {"id": oid, "shop_status": "ready"}) and srow(oid)["shop_ready_at"] and mine(cust, oid)["shop_status"] == "ready")
ok("ready twice -> 409", A(own, "ready")[0] == 409)
ok("second notification 'ready' for the customer, none for shop owner/courier", [n["title"] for n in notes(cust)] == ["طلبك جاهز للاستلام من المحل", "المحل قبل طلبك"] or [n["title"] for n in notes(cust)] == ["المحل قبل طلبك", "طلبك جاهز للاستلام من المحل"])
ok("no shop.stage notification leaked to the owner or couriers", notes(own) == [] and notes(c1) == [] and notes(c2) == [])
ok("delivery_orders still untouched after ready", dstat(oid) == before)
ok("courier cycle works normally after shop ready (accept, propose, approve)", call("POST", f"/courier/orders/{oid}/accept", {}, c1)[0] == 200 and call("POST", f"/courier/orders/{oid}/fare", {"fee": 20}, c1)[0] == 200 and call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 20}, cust)[0] == 200)
ok("shop status survives courier steps", srow(oid)["shop_status"] == "ready" and mine(cust, oid)["shop_status"] == "ready")
call("POST", f"/courier/orders/{oid}/status", {"to": "heading_pickup"}, c1); call("POST", f"/courier/orders/{oid}/status", {"to": "picked_up"}, c1)
ok("after pickup the shop can no longer change status (409)", srow(oid)["can_progress"] is False and A(own, "accept")[0] == 409 and A(own, "ready")[0] == 409)

# ---- 4) تخطّي «القبول» ممنوع، والإلغاء يقفل الدورة، والطلب العادي بلا حقول المحل
s, r = call("POST", "/shops/%d/order" % S, {**GOOD, "request_key": "z2"}, cust); o2 = r["id"]
A(own, "accept", o2); call("POST", "/owner/shops/%d/orders/%d/reject" % (S, o2), {}, own)
ok("rejected order: cycle closed (409) and customer sees cancelled", A(own, "ready", o2)[0] == 409 and mine(cust, o2)["status"] == "cancelled")
n = call("POST", "/delivery/orders", {"region_id": Z2, "pickup_text": "سوق البلد", "dropoff_text": "شارع النصر 4", "details": "x", "request_key": "n1"}, cust)[1]["id"]
nm = mine(cust, n); ok("normal order has no shop_* fields at all", not any(k.startswith("shop_") for k in nm))
call("POST", f"/delivery/orders/{n}/cancel", {}, cust)

# ---- 5) ترحيل قاعدة قديمة (من غير الأعمدة الجديدة) آمن ويحفظ الصفوف
import shop_delivery
cx = sqlite3.connect(DB); cx.execute("PRAGMA foreign_keys=OFF")
cx.execute("ALTER TABLE shop_delivery_links RENAME TO sdl_new"); cx.execute("CREATE TABLE shop_delivery_links(order_id INTEGER PRIMARY KEY REFERENCES delivery_orders(id), shop_id INTEGER NOT NULL REFERENCES shops(id), kind TEXT NOT NULL CHECK(kind IN('shop_pickup','shop_order')), items_json TEXT, items_total REAL, note TEXT, created_at INTEGER NOT NULL)")
cx.execute("INSERT INTO shop_delivery_links SELECT order_id,shop_id,kind,items_json,items_total,note,created_at FROM sdl_new"); cx.execute("DROP TABLE sdl_new"); cx.commit()
cnt = cx.execute("SELECT COUNT(*) FROM shop_delivery_links").fetchone()[0]
shop_delivery.install(cx); shop_delivery.install(cx)  # مرتين: idempotent
cols = {r[1] for r in cx.execute("PRAGMA table_info(shop_delivery_links)")}
ok("old schema migrated twice safely: new columns exist, rows kept, default 'new'", {"shop_status", "shop_accepted_at", "shop_ready_at"} <= cols and cx.execute("SELECT COUNT(*) FROM shop_delivery_links").fetchone()[0] == cnt and cx.execute("SELECT COUNT(DISTINCT shop_status) FROM shop_delivery_links WHERE shop_status='new'").fetchone()[0] == 1)
cx.close()

# ---- 6) واجهات + متصفح حقيقي
rd = lambda f: open(os.path.join(HERE, "static", f), encoding="utf-8").read()
ok("shop.html has accept/ready buttons wired", "ordacc(" in rd("shop.html") and "ordrdy(" in rd("shop.html") and "قبلت الطلب" in rd("shop.html") and "جاهز للاستلام" in rd("shop.html"))
ok("index.html renders shop stages and polls on shop_status changes", "shopTrk(x)" in rd("index.html") and "x.shop_status," in rd("index.html"))
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch(); errs = []
    def page(tok):
        ctx = br.new_context(viewport={"width": 390, "height": 820}); ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','%d')" % (tok, Z2)); pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); return pg
    def until(pg, js, timeout=12):
        t = time.time()
        while time.time() - t < timeout:
            if pg.evaluate(js): return True
            pg.wait_for_timeout(250)
        return False
    s, r = call("POST", "/shops/%d/order" % S, {**GOOD, "request_key": "b1"}, cust); b = r["id"]
    shop_pg = page(own); shop_pg.goto(BASE + "/shop.html#o"); shop_pg.wait_for_selector("#oslot", timeout=10000)
    cu = page(cust); cu.goto(BASE + "/#orders"); cu.wait_for_selector(".od", timeout=10000)
    CC = "(([...document.querySelectorAll('.od')].find(e=>e.innerText.trim().startsWith('#%d'))||{}).innerText||'')" % b
    SC = "(([...document.querySelectorAll('#oslot .card')].find(e=>e.innerText.includes('طلب #%d'))||{}).innerText||'')" % b
    ok("customer card shows the stage list (sent=done, shop pending)", until(cu, "document.querySelectorAll('.od .shtrk').length>0") and "تم إرسال الطلب" in cu.evaluate(CC) and "المحل قبل الطلب" in cu.evaluate(CC))
    ok("shop card shows the accept button (not the ready one yet)", until(shop_pg, "%s.includes('قبلت الطلب')" % SC) and "button" and shop_pg.locator("#oslot .card:has-text('طلب #%d') button:has-text('جاهز للاستلام')" % b).count() == 0)
    shop_pg.click("#oslot .card:has-text('طلب #%d') button:has-text('قبلت الطلب')" % b); shop_pg.wait_for_selector("#oslot .card:has-text('طلب #%d') button:has-text('جاهز للاستلام')" % b, timeout=8000)
    ok("accepted in UI: button switches to ready; DB shop_status=accepted", sql("SELECT shop_status FROM shop_delivery_links WHERE order_id=?", b)[0][0] == "accepted")
    ok("customer screen updates by itself: 'المحل قبل الطلب' is now done", until(cu, "document.querySelector('.od .shtrk li.d:nth-child(2)')!==null"))
    shop_pg.click("#oslot .card:has-text('طلب #%d') button:has-text('جاهز للاستلام')" % b); shop_pg.wait_for_selector("#oslot .card:has-text('طلب #%d') :text('جاهز للاستلام — بانتظار المندوب')" % b, timeout=8000)
    ok("customer screen shows 'جاهز للاستلام من المحل' as the current stage", until(cu, "(document.querySelector('.od .shtrk li.c')||{}).innerText==='جاهز للاستلام من المحل'"))
    ok("customer got both notifications (bell API)", [n["title"] for n in call("GET", "/notifications", None, cust)[1]["items"] if n["ref_id"] == b and n["kind"] == "shop.stage"].__len__() == 2)
    ok("no JS page errors", errs == []) if errs == [] else (print(errs) or exit(1))
    br.close()
print("ALL OK")
