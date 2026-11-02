# المرحلة 84 (م3): دليفري طلبات العملاء من المحلات — اسم/رقم المندوب فور القبول (للعميل وللمحل)، تحويل تلقائي بعد الطلب، تحديث أسرع لشاشة المحل.
# + حماية: الأوردر العادي، أوردر الصيدلية (provider_pickup)، واستلام المحل (shop_pickup) لا يتأثروا. قاعدة مؤقتة معزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8984; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__))
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
own, _ = user("01190000001"); cust, cid = user("01190000003"); other, _ = user("01190000004"); phm, phid = user("01190000008"); c1, u1 = user("01190000005", "أحمد المندوب"); c2, u2 = user("01190000006", "محمود المندوب")
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

# ---- 1) أوردر محل: اسم ورقم المندوب فور القبول (قبل اقتراح الأجرة)
s, r = call("POST", "/shops/%d/order" % S, GOOD, cust); oid = r["id"]
ok("shop order created (searching)", s == 201 and r["status"] == "searching")
m = mine(cust, oid); ok("searching: no courier info yet", m["courier_name"] is None and m["courier_phone"] is None and shop_row(oid)["courier_name"] is None)
ok("courier accepts (fare draft: normal cycle kept)", call("POST", f"/courier/orders/{oid}/accept", {}, c1) == (200, {"ok": True, "fee": 25.0, "fare_status": "draft"}) or call("GET", "/courier/orders", None, c1)[1][0]["fare_status"] == "draft")
m = mine(cust, oid)
ok("customer sees courier NAME and PHONE immediately on accept (fare still draft)", m["status"] == "assigned" and m["fare_status"] == "draft" and m["courier_name"] == "أحمد المندوب" and m["courier_phone"] == P1)
ok("customer still does not get courier_id/fee before fare proposal (profile link/fare unchanged)", m["courier_id"] is None and m["fee"] is None)
sr = shop_row(oid)
ok("shop sees courier NAME and PHONE immediately on accept", sr["status"] == "assigned" and sr["courier_name"] == "أحمد المندوب" and sr["courier_phone"] == P1)
ok("another customer / non-owner cannot see it", call("GET", "/delivery/orders", None, other)[1] == [] and call("GET", "/owner/shops/%d/orders" % S, None, other)[0] == 404)
ok("courier proposes fare (normal cycle)", call("POST", f"/courier/orders/{oid}/fare", {"fee": 20}, c1)[1]["fare_status"] == "proposed")
m = mine(cust, oid); ok("proposed: name+phone still visible, fare shown", m["courier_name"] == "أحمد المندوب" and m["courier_phone"] == P1 and m["fee"] == 20 and m["courier_id"] == u1)
ok("customer rejects fare -> back to searching, courier info hidden from customer and shop", call("POST", f"/delivery/orders/{oid}/fare/reject", {"fee": 20}, cust)[0] == 200 and mine(cust, oid)["status"] == "searching" and mine(cust, oid)["courier_phone"] is None and shop_row(oid)["courier_phone"] is None)
ok("second courier accepts + proposes; customer approves", call("POST", f"/courier/orders/{oid}/accept", {}, c2)[0] == 200 and call("POST", f"/courier/orders/{oid}/fare", {"fee": 22}, c2)[0] == 200 and call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 22}, cust)[0] == 200)
m = mine(cust, oid); ok("approved: second courier info for customer and shop", m["courier_name"] == "محمود المندوب" and m["courier_phone"] == P2 and shop_row(oid)["courier_phone"] == P2)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived"):
    call("POST", f"/courier/orders/{oid}/status", {"to": to}, c2)
ok("courier info stays during the active delivery", mine(cust, oid)["courier_phone"] == P2 and shop_row(oid)["courier_phone"] == P2)
sql("UPDATE delivery_orders SET status='completed' WHERE id=?", oid)
ok("after completion phone is hidden again (privacy window unchanged)", mine(cust, oid)["courier_phone"] is None and shop_row(oid)["courier_phone"] is None)

# ---- 2) الأوردر العادي: لم يتأثر (الاسم بعد اقتراح الأجرة، الرقم بعد الموافقة)
s, r = call("POST", "/delivery/orders", {"region_id": Z2, "pickup_text": "سوق البلد", "dropoff_text": "شارع النصر 4", "details": "x", "request_key": "n1"}, cust); no = r["id"]
ok("normal order created", s == 201)
call("POST", f"/courier/orders/{no}/accept", {}, c1); m = mine(cust, no)
ok("NORMAL order, draft: NO courier name/phone (unchanged)", m["status"] == "assigned" and m["fare_status"] == "draft" and m["courier_name"] is None and m["courier_phone"] is None)
call("POST", f"/courier/orders/{no}/fare", {"fee": 15}, c1); m = mine(cust, no)
ok("NORMAL order, proposed: name only, no phone (unchanged)", m["courier_name"] == "أحمد المندوب" and m["courier_phone"] is None)
call("POST", f"/delivery/orders/{no}/fare/approve", {"fee": 15}, cust); m = mine(cust, no)
ok("NORMAL order, approved: name + phone (unchanged)", m["courier_name"] == "أحمد المندوب" and m["courier_phone"] == P1)
call("POST", f"/delivery/orders/{no}/cancel", {}, cust)

# ---- 3) الصيدلية: طلب مندوب من الصيدلية (provider_pickup) — القبول المباشر وبيانات المندوب للصيدلية كما كانت
s, r = call("POST", "/provider/delivery-request", {"request_key": "p1"}, phm); po = r["id"]
ok("pharmacy order created", s == 201 and sql("SELECT origin_type FROM delivery_orders WHERE id=?", po)[0][0] == "provider_pickup")
ok("pharmacy order accepted directly, fare approved (unchanged)", call("POST", f"/courier/orders/{po}/accept", {}, c1) == (200, {"ok": True, "fee": None, "fare_status": "approved"}))
pm = [x for x in call("GET", "/provider/delivery-requests", None, phm)[1]["items"] if x["id"] == po][0]
ok("pharmacy sees courier name+phone while active (unchanged)", pm["courier_name"] == "أحمد المندوب" and pm["courier_phone"] == P1)
for to in ("heading_pickup", "picked_up", "heading_customer"): call("POST", f"/courier/orders/{po}/status", {"to": to}, c1)
call("POST", f"/provider/delivery-requests/{po}/delivered", {}, phm)
pm = [x for x in call("GET", "/provider/delivery-requests", None, phm)[1]["items"] if x["id"] == po][0]
ok("pharmacy order completes; phone hidden after finish (unchanged)", pm["status"] == "completed" and pm["courier_phone"] is None)

# ---- 4) استلام المحل (shop_pickup): كما هو
s, r = call("POST", "/owner/shops/%d/delivery-request" % S, {"request_key": "sp1"}, own); sp = r["id"]
ok("shop_pickup created, accepted directly (unchanged)", s == 201 and call("POST", f"/courier/orders/{sp}/accept", {}, c1) == (200, {"ok": True, "fee": None, "fare_status": "approved"}))
sr = [x for x in call("GET", "/owner/shops/%d/delivery-requests" % S, None, own)[1]["items"] if x["id"] == sp][0]
ok("shop_pickup shows courier to the shop (unchanged)", sr["courier_name"] == "أحمد المندوب" and sr["courier_phone"] == P1)
ok("shop_pickup is not listed among customer orders", all(x["id"] != sp for x in call("GET", "/owner/shops/%d/orders" % S, None, own)[1]["items"]))
call("POST", f"/delivery/orders/{sp}/cancel", {}, own)

# ---- 5) ملفات الواجهة
rd = lambda f: open(os.path.join(HERE, "static", f), encoding="utf-8").read()
ok("shop.html polls every 4s (was 12s) and refreshes on return", "setInterval(poll,4000)" in rd("shop.html") and "setInterval(poll,12000)" not in rd("shop.html") and "visibilitychange" in rd("shop.html"))
ok("shops.html redirects to /#orders after the order", "location.href='/#orders'" in rd("shops.html"))
ok("index.html handles #orders -> orders tab", "location.hash==='#orders'" in rd("index.html"))

# ---- 6) متصفح حقيقي: طلب من المحل ← تحويل تلقائي لتبويب الطلبات ويظهر الطلب؛ ثم المندوب يقبل فيظهر اسمه ورقمه لوحده عند العميل وعند المحل
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch(); errs = []
    def page(tok, vw=390):
        ctx = br.new_context(viewport={"width": vw, "height": 820}); ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','%d')" % (tok, Z2)); pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); return pg
    def until(pg, js, timeout=12):  # CSP بلا unsafe-eval: نستعمل polling عبر evaluate لا wait_for_function
        t = time.time()
        while time.time() - t < timeout:
            if pg.evaluate(js): return True
            pg.wait_for_timeout(250)
        return False
    shop_pg = page(own); shop_pg.goto(BASE + "/shop.html#o"); shop_pg.wait_for_selector("#oslot", timeout=10000)
    pg = page(cust); pg.goto(BASE + "/shops.html#s%d" % S); pg.wait_for_selector(".gi", timeout=8000)
    pg.click(".gi:has-text('كشري') button[aria-label='أكثر']"); pg.fill("#da", "عمارة 9 شقة 2"); pg.click("#ob")
    pg.wait_for_selector("text=تم إرسال طلبك", timeout=5000)
    pg.wait_for_url(re.compile(r"/$|/\?|/#"), timeout=8000); pg.wait_for_selector(".od", timeout=10000)
    ok("customer auto-redirected from shop page to home/orders after ordering", pg.url.rstrip("/").endswith(str(PORT)) and "#orders" not in pg.url)
    ok("orders tab shown (حسابي ← طلباتي) with the new order searching", "طلباتي" in pg.inner_text("body") and "قيد البحث" in pg.inner_text("body"))
    new = sql("SELECT id FROM delivery_orders WHERE origin_type='shop_order' ORDER BY id DESC LIMIT 1")[0][0]
    ok("the new order card is on screen", ("#%d" % new) in pg.inner_text("body"))
    # الشاشة لسه مفتوحة؛ المندوب يقبل من الخادم → تظهر بيانات المندوب بدون تحديث يدوي
    CARD_C = "(([...document.querySelectorAll('.od')].find(e=>e.innerText.trim().startsWith('#%d'))||{}).innerText||'')" % new
    CARD_S = "(([...document.querySelectorAll('#oslot .card')].find(e=>e.innerText.includes('طلب #%d'))||{}).innerText||'')" % new
    ok("shop screen picked up the new customer order by itself (no manual refresh)", until(shop_pg, "%s.length>0" % CARD_S, 8) and "أحمد" not in shop_pg.evaluate(CARD_S))
    ok("courier accepts the browser-made order", call("POST", f"/courier/orders/{new}/accept", {}, c1)[0] == 200)
    g1 = until(pg, "%s.includes('أحمد المندوب')" % CARD_C)
    ok("customer: THIS order's card shows courier name+phone by itself after accept", g1 and P1 in pg.evaluate(CARD_C))
    CARD_S = "(([...document.querySelectorAll('#oslot .card')].find(e=>e.innerText.includes('طلب #%d'))||{}).innerText||'')" % new
    t0 = time.time(); got = until(shop_pg, "%s.includes('أحمد المندوب')" % CARD_S, 12)
    ok("shop: THIS order's card shows courier name+phone by itself, within ~6s of accept", got and time.time() - t0 < 7 and P1 in shop_pg.evaluate(CARD_S))
    # direct #orders deep link
    pg2 = page(cust); pg2.goto(BASE + "/#orders"); pg2.wait_for_selector(".od", timeout=10000)
    ok("deep link /#orders opens the orders tab and cleans the hash", "#orders" not in pg2.url and "طلباتي" in pg2.inner_text("body"))
    pg3 = page(cust); pg3.goto(BASE + "/"); pg3.wait_for_timeout(1500)
    ok("plain / still opens home (not orders)", "طلباتي" not in pg3.inner_text("body") or pg3.locator(".od").count() == 0)
    ok("no JS page errors", errs == []) if errs == [] else (print(errs) or exit(1))
    br.close()
print("ALL OK")
