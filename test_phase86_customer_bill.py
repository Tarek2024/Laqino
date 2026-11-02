# المرحلة 86 (م5): شاشة طلب العميل — أصناف الطلب وكمياتها وأثمانها وأجرة التوصيل والإجمالي. قاعدة مؤقتة معزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8986; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__))
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
own, _ = user("01590000001"); cust, cid = user("01590000003"); other, _ = user("01590000004"); phm, phid = user("01590000008"); c1, u1 = user("01590000005", "أحمد المندوب"); c2, u2 = user("01590000006", "محمود المندوب")
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
P1 = sql("SELECT phone FROM users WHERE id=?", u1)[0][0]; P2 = sql("SELECT phone FROM users WHERE id=?", u2)[0][0]
call("POST", "/admin/shops-settings", {"enabled": True}, at); call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 2}, at); call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 0}, at)
S = call("POST", "/shops/apply", {"type_id": 1, "name_ar": "مطعم الأمل", "address": "شارع النصر", "phone": "01012345678", "region_id": Z2}, own)[1]["id"]
call("POST", "/admin/shops/%d/review" % S, {"status": "approved"}, at); call("POST", "/owner/shops/%d/open" % S, {}, own)
i1 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "كشري", "price": 35.5}, own)[1]["id"]; i2 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "فول <b>سادة</b>", "price": 10}, own)[1]["id"]
call("POST", "/providers/apply", {"name_ar": "صيدلية النور", "region_id": Z2, "address": "شارع البحر"}, phm)
call("POST", f"/admin/providers/{phid}/review", {"status": "approved"}, at)
def mine(t, oid): return [o for o in call("GET", "/delivery/orders", None, t)[1] if o["id"] == oid][0]
def shop_row(oid): return [o for o in call("GET", "/owner/shops/%d/orders" % S, None, own)[1]["items"] if o["id"] == oid][0]
GOOD = {"items": [{"item_id": i1, "qty": 2}], "dropoff_text": "عمارة 5 شقة 3"}


GOOD2 = {"items": [{"item_id": i1, "qty": 2}, {"item_id": i2, "qty": 3}], "dropoff_text": "عمارة 5 شقة 3", "note": "من غير بصل"}
s, r = call("POST", "/shops/%d/order" % S, GOOD2, cust); oid = r["id"]
# ---- 1) قبل اقتراح الأجرة: الأصناف والأثمان وإجمالي الأصناف؛ الأجرة لسه مخفية
m = mine(cust, oid)
ok("items with qty, unit price and line totals", m["shop_items"] == [{"name": "كشري", "price": 35.5, "qty": 2, "line_total": 71.0}, {"name": "فول <b>سادة</b>", "price": 10.0, "qty": 3, "line_total": 30.0}])
ok("items_total=101, shop name and note present", m["items_total"] == 101.0 and m["shop_name"] == "مطعم الأمل" and m["shop_note"] == "من غير بصل")
ok("delivery fee and grand total hidden until the courier proposes", m["delivery_fee"] is None and m["grand_total"] is None and m["fee"] is None)
call("POST", f"/courier/orders/{oid}/accept", {}, c1); m = mine(cust, oid)
ok("still hidden at draft (courier accepted, no proposal yet)", m["delivery_fee"] is None and m["grand_total"] is None)
call("POST", f"/courier/orders/{oid}/fare", {"fee": 20.5}, c1); m = mine(cust, oid)
ok("fare proposed: fee 20.5 and grand total 121.5 (items + delivery)", m["delivery_fee"] == 20.5 and m["grand_total"] == 121.5 and m["items_total"] == 101.0)
call("POST", f"/delivery/orders/{oid}/fare/reject", {"fee": 20.5}, cust); m = mine(cust, oid)
ok("fare rejected -> fee/total hidden again, items intact", m["delivery_fee"] is None and m["grand_total"] is None and len(m["shop_items"]) == 2)
call("POST", f"/courier/orders/{oid}/accept", {}, c2); call("POST", f"/courier/orders/{oid}/fare", {"fee": 22}, c2); call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 22}, cust); m = mine(cust, oid)
ok("approved fee 22: grand total 123", m["delivery_fee"] == 22 and m["grand_total"] == 123.0)
ok("price change after the order does not alter the customer's bill (snapshot)", call("POST", "/owner/shops/%d/items/%d/edit" % (S, i1), {"price": 99}, own)[0] == 200 and mine(cust, oid)["items_total"] == 101.0 and mine(cust, oid)["shop_items"][0]["price"] == 35.5)
ok("another customer never sees these items", all(x["id"] != oid for x in call("GET", "/delivery/orders", None, other)[1]))
# ---- 2) أنواع تانية: بلا حقول الأصناف إطلاقًا
n = call("POST", "/delivery/orders", {"region_id": Z2, "pickup_text": "سوق البلد", "dropoff_text": "شارع النصر 4", "details": "x", "request_key": "n1"}, cust)[1]["id"]
nm = mine(cust, n); ok("normal order: no shop bill fields", not any(k in nm for k in ("shop_items", "items_total", "grand_total", "delivery_fee", "shop_name", "shop_note", "items_json")))
po = call("POST", "/provider/delivery-request", {"request_key": "p1"}, phm)
ok("pharmacy order never reaches the customer list of items (provider is the 'customer')", all("shop_items" not in x and "items_json" not in x for x in call("GET", "/delivery/orders", None, phm)[1]))
ok("raw items_json is never exposed", all("items_json" not in x for x in call("GET", "/delivery/orders", None, cust)[1]))
# ---- 3) المتصفح: الشاشة نفسها
rd = lambda f: open(os.path.join(HERE, "static", f), encoding="utf-8").read()
ok("index.html renders the bill block", "shopBill(x)" in rd("index.html") and "الإجمالي" in rd("index.html"))
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch(); errs = []
    ctx = br.new_context(viewport={"width": 390, "height": 820}); ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','%d')" % (cust, Z2)); pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    def until(js, timeout=12):
        t = time.time()
        while time.time() - t < timeout:
            if pg.evaluate(js): return True
            pg.wait_for_timeout(250)
        return False
    pg.goto(BASE + "/#orders"); pg.wait_for_selector(".od .shbill", timeout=10000)
    bill = lambda i: "(([...document.querySelectorAll('.od')].find(e=>e.innerText.trim().startsWith('#%d'))||document.body).querySelector('.shbill')||{innerText:''}).innerText" % i
    BILL = bill(oid)
    t = pg.evaluate(BILL)
    ok("bill shows both items with qty and prices", "2× كشري" in t and "71" in t and "3× فول <b>سادة</b>" in t and "30" in t and "35.5" in t)
    ok("bill shows items total 101, delivery 22 and grand total 123", "ثمن الأصناف" in t and "101" in t and "22" in t and "الإجمالي" in t and "123" in t)
    ok("HTML in item names is escaped (no injected element)", pg.locator(".od .shbill b:has-text('سادة')").count() == 0 and pg.evaluate("document.querySelectorAll('.od .shbill b').length") >= 3)
    b2 = call("POST", "/shops/%d/order" % S, {**GOOD2, "request_key": "b2"}, cust)[1]["id"]
    pg.evaluate("go(3)"); ok("new order (no fare yet): shows 'المندوب هيقترحها' and total so far without delivery", until("%s.includes('هيقترحها')" % bill(b2)) and "الإجمالي حاليًا" in pg.evaluate(bill(b2)))
    ok("no JS page errors", errs == []) if errs == [] else (print(errs) or exit(1))
    br.close()
print("ALL OK")
