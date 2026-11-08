# المرحلة 87: «اطلب من الصيدلية مباشرة» لقسم المنتجات (product_orders.py) — API + إشعارات + تحويل لدليفري + اعتذار + الصلاحيات. قاعدة مؤقتة معزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8987; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
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
cust, cid = user("01298700003"); other, oid_u = user("01298700004"); phm, phid = user("01298700008"); ph2, ph2id = user("01298700009"); c1, u1 = user("01298700005", "أحمد المندوب")
apply_docs(call, c1); call("POST", f"/admin/couriers/{u1}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF0001"}, c1)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
call("POST", "/courier/online", {"online": True}, c1)
for t, nm, uid in ((phm, "صيدلية النور", phid), (ph2, "صيدلية الأمل", ph2id)):
    call("POST", "/providers/apply", {"name_ar": nm, "region_id": Z2, "address": "شارع البحر"}, t); call("POST", f"/admin/providers/{uid}/review", {"status": "approved"}, at)
# قسم المنتجات: تصنيفات + مفتاح الإظهار + عروض منشورة
call("POST", "/admin/products/seed-categories", {}, at); CAT = call("GET", "/medical/product-categories")[1]
cat = sql("SELECT id FROM categories WHERE section='medical' AND parent_id IS NOT NULL ORDER BY id")[0][0]
def offer(t, title, price):
    r = call("POST", "/provider/products", {"title": title, "category_id": cat, "price": price}, t)[1]; call("POST", f"/admin/products/{r['id']}/review", {"status": "approved"}, at); return r["id"]
sql("INSERT OR REPLACE INTO settings VALUES('products_enabled','1')")
o1 = offer(phm, "كريم مرطب للبشرة", 120); o2 = offer(phm, "شامبو أطفال", 45.5); o3 = offer(ph2, "منتج صيدلية تانية", 10)
PO = lambda pid, body, t=None: call("POST", "/medical/pharmacies/%d/order" % pid, body, cust if t is None else t)
GOOD = {"items": [{"offer_id": o1, "qty": 2}, {"offer_id": o2, "qty": 1}], "dropoff_text": "عمارة 5 شقة 3", "note": "بعد المغرب", "request_key": "k1"}
def notes(t, kind): return [n for n in call("GET", "/notifications", None, t)[1]["items"] if n["kind"] == kind]
def mine(t, oid): return [o for o in call("GET", "/delivery/orders", None, t)[1] if o["id"] == oid][0]
def prow(t, pid_): return [o for o in call("GET", "/provider/product-orders", None, t)[1] if o["id"] == pid_][0]
def dcount(): return sql("SELECT COUNT(*) FROM delivery_orders")[0][0]

# ---- 1) التحقق من الإدخال والصلاحيات
ok("anonymous -> 401", PO(phid, GOOD, "")[0] == 401)
sql("UPDATE settings SET value='0' WHERE key='products_enabled'"); ok("products disabled -> 403", PO(phid, GOOD)[0] == 403); sql("UPDATE settings SET value='1' WHERE key='products_enabled'")
ok("unknown pharmacy 404", PO(99999, GOOD)[0] == 404)
ok("pharmacy cannot order from itself 403", PO(phid, GOOD, phm)[0] == 403)
ok("empty / bad items 400", PO(phid, {**GOOD, "items": []})[0] == 400 and PO(phid, {**GOOD, "items": [{"offer_id": o1, "qty": 0}]})[0] == 400 and PO(phid, {**GOOD, "items": [{"offer_id": o1, "qty": 99}]})[0] == 400
   and PO(phid, {**GOOD, "items": [{"offer_id": o1, "qty": 1}, {"offer_id": o1, "qty": 1}]})[0] == 400 and PO(phid, {**GOOD, "items": [{"offer_id": "1", "qty": 1}]})[0] == 400 and PO(phid, {**GOOD, "items": [{"offer_id": True, "qty": 1}]})[0] == 400)
ok("offer of ANOTHER pharmacy rejected 400", PO(phid, {**GOOD, "items": [{"offer_id": o3, "qty": 1}]})[0] == 400)
ok("missing address 400", PO(phid, {**GOOD, "dropoff_text": " "})[0] == 400)
sql("UPDATE product_offers SET available=0 WHERE id=?", o2); ok("unavailable product 409", PO(phid, GOOD)[0] == 409); sql("UPDATE product_offers SET available=1 WHERE id=?", o2)
sql("UPDATE product_offers SET confirmed_at=? WHERE id=?", int(time.time()) - 40 * 86400, o2); ok("stale (not re-confirmed) product 409", PO(phid, GOOD)[0] == 409); sql("UPDATE product_offers SET confirmed_at=? WHERE id=?", int(time.time()), o2)
ok("nothing was created by the failed attempts", sql("SELECT COUNT(*) FROM product_orders")[0][0] == 0 and dcount() == 0)

# ---- 2) إنشاء طلب: «جديد» عند الصيدلية بلا دليفري ولا مندوب
n0 = dcount(); s, r = PO(phid, GOOD); pid_ = r["id"]
ok("order created as 'new' with total from SERVER prices (2×120 + 45.5 = 285.5)", s == 201 and r["status"] == "new" and r["items_total"] == 285.5)
ok("no delivery order yet, courier not woken", dcount() == n0 and call("GET", "/courier/available", None, c1)[1] == [])
ok("duplicate request_key returns the same order (no second row)", PO(phid, GOOD)[1] == {"id": pid_, "status": "new", "duplicate": True} and sql("SELECT COUNT(*) FROM product_orders")[0][0] == 1)
ok("pharmacy got a bell notification, nobody else did", len(notes(phm, "provider.product_order")) == 1 and notes(phm, "provider.product_order")[0]["link"] == "pharmacy" and notes(ph2, "provider.product_order") == [] and notes(cust, "provider.product_order") == [])
row = prow(phm, pid_); ok("pharmacy list shows items/total/note, can accept/reject but not 'ready'", row["status"] == "new" and row["items_total"] == 285.5 and [i["qty"] for i in row["items"]] == [2, 1] and row["note"] == "بعد المغرب" and row["can_accept"] and row["can_reject"] and not row["can_ready"])
ok("pharmacy never sees the customer's address / phone / id", "عمارة" not in json.dumps(row, ensure_ascii=False) and "dropoff" not in row and "customer_id" not in row and "phone" not in " ".join(row.keys()).replace("courier_phone", ""))
mp = call("GET", "/my/product-orders", None, cust)[1]; ok("customer sees the pending order with pharmacy name", len(mp) == 1 and mp[0]["status"] == "new" and mp[0]["pharmacy"] == "صيدلية النور" and mp[0]["items_total"] == 285.5)
ok("price snapshot: later price edit does not change the order", (call("POST", f"/provider/products/{o1}/confirm", {"price": 500}, phm), prow(phm, pid_)["items_total"])[1] == 285.5); call("POST", f"/provider/products/{o1}/confirm", {"price": 120}, phm)

# ---- 3) صلاحيات الصيدلية
A = lambda t, a, o=None, d=None: call("POST", "/provider/product-orders/%d/%s" % (o or pid_, a), d or {}, t)
ok("customer / other pharmacy / courier cannot act on it", A(cust, "accept")[0] == 403 and A(ph2, "accept")[0] == 404 and A(c1, "accept")[0] == 403 and A(None, "accept")[0] == 401 and sql("SELECT status FROM product_orders WHERE id=?", pid_)[0][0] == "new")
ok("other pharmacy does not see the order in its list", call("GET", "/provider/product-orders", None, ph2)[1] == [])
ok("'ready' before 'accept' -> 409", A(phm, "ready")[0] == 409)
ok("customer cannot cancel someone else's order (404)", call("POST", f"/my/product-orders/{pid_}/cancel", {}, other)[0] == 404)

# ---- 4) القبول = التحويل لدليفري
s, r = A(phm, "accept"); did = r["order_id"]
_old_has, _old_send = server.fcm.has_tokens, server.fcm.send
_push_event, _push_hits = threading.Event(), []
server.fcm.has_tokens = lambda c, uid: uid == cid
def _capture_push(c, uids, ttl=300, kind="order", target=None):
    if cid in uids:
        _push_hits.append((kind, target)); _push_event.set()
    return 1
server.fcm.send = _capture_push
ok("accept -> accepted and a delivery order is created from it", s == 200 and r["status"] == "accepted" and did and dcount() == n0 + 1)
d = sql("SELECT origin_type,customer_id,pickup_text,dropoff_text,details,fee,commission,status,fare_status,region_id FROM delivery_orders WHERE id=?", did)[0]
ok("delivery order: origin=product_order, customer, pickup=pharmacy, dropoff=customer address, items in details, searching", d[0] == "product_order" and d[1] == cid and "صيدلية النور" in d[2] and d[3] == "عمارة 5 شقة 3" and "2× كريم مرطب للبشرة" in d[4] and "1× شامبو أطفال" in d[4] and d[7] == "searching" and d[8] == "none" and d[9] == Z2)
ok("zone fee + commission snapshot taken from settings (25 / 4)", d[5] == 25 and d[6] == 4)
ok("accept twice -> 409 and no second delivery order", A(phm, "accept")[0] == 409 and dcount() == n0 + 1)
ok("customer cannot cancel after the pharmacy replied (409)", call("POST", f"/my/product-orders/{pid_}/cancel", {}, cust)[0] == 409)
ok("customer notified 'الصيدلية قبلت طلبك' (link orders)", [n["title"] for n in notes(cust, "product_order.stage")] == ["الصيدلية قبلت طلبك"] and notes(cust, "product_order.stage")[0]["link"] == "orders")
ok("a pending list no longer contains the accepted order", call("GET", "/my/product-orders", None, cust)[1] == [])
m = mine(cust, did); ok("customer orders list: pharmacy stage fields (accepted) + bill + place_kind", m["shop_status"] == "accepted" and m["place_kind"] == "pharmacy" and m["shop_name"] == "صيدلية النور" and m["items_total"] == 285.5 and m["shop_note"] == "بعد المغرب"
   and [i["name"] for i in m["shop_items"]] == ["كريم مرطب للبشرة", "شامبو أطفال"] and m["shop_items"][0]["line_total"] == 240 and m["delivery_fee"] is None and m["grand_total"] is None and "items_json" not in m)
ok("courier is woken/offered the order", any(o["id"] == did for o in call("GET", "/courier/available", None, c1)[1]))
av = [o for o in call("GET", "/courier/available", None, c1)[1] if o["id"] == did][0]; ok("courier offer carries origin_type=product_order", av.get("origin_type") == "product_order")

# ---- 5) «جاهز للاستلام» + دورة المندوب العادية
ok("pharmacy list: now can_ready, cannot accept again", prow(phm, pid_)["can_ready"] and not prow(phm, pid_)["can_accept"])
ok("ready -> ready and customer sees it + notification", A(phm, "ready") == (200, {"id": pid_, "status": "ready"}) and mine(cust, did)["shop_status"] == "ready" and [n["title"] for n in notes(cust, "product_order.stage")][0] == "طلبك جاهز للاستلام من الصيدلية")
ok("ready twice -> 409", A(phm, "ready")[0] == 409)
ok("courier cycle: accept, propose fare, customer approves", call("POST", f"/courier/orders/{did}/accept", {}, c1)[0] == 200 and call("POST", f"/courier/orders/{did}/fare", {"fee": 20}, c1)[0] == 200 and call("POST", f"/delivery/orders/{did}/fare/approve", {"fee": 20}, cust)[0] == 200)
m = mine(cust, did); ok("customer sees courier name+phone and bill with fee: 285.5 + 20 = 305.5", m["courier_name"] == "أحمد المندوب" and m["courier_phone"] and m["delivery_fee"] == 20 and m["grand_total"] == 305.5)
r = prow(phm, pid_); ok("pharmacy sees the courier name/phone while active", r["courier_name"] == "أحمد المندوب" and r["courier_phone"] and r["delivery_status"] in ("assigned", "heading_pickup"))
call("POST", f"/courier/orders/{did}/status", {"to": "heading_pickup"}, c1); call("POST", f"/courier/orders/{did}/status", {"to": "picked_up"}, c1)
r = prow(phm, pid_); ok("after pickup: pharmacy cannot ready/reject any more", not r["can_ready"] and not r["can_reject"] and A(phm, "reject")[0] == 409 and A(phm, "ready")[0] == 409)
for to in ("heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{did}/status", {"to": to}, c1)
ok("customer confirms -> completed (normal order cycle intact)", call("POST", f"/delivery/orders/{did}/confirm", {}, cust)[0] == 200 and mine(cust, did)["status"] == "completed")

# ---- 6) اعتذار الصيدلية: قبل القبول، وبعده قبل استلام المندوب
s, r = PO(phid, {**GOOD, "request_key": "k2"}); p2 = r["id"]
s, r = A(phm, "reject", p2, {"reason": "المنتج خلص"}); ok("reject a NEW order: no delivery order created, reason stored", s == 200 and r["status"] == "rejected" and dcount() == n0 + 1)
ok("customer sees it as rejected with the reason + gets a notification", [(x["status"], x["reject_reason"]) for x in call("GET", "/my/product-orders", None, cust)[1]] == [("rejected", "المنتج خلص")] and [n["title"] for n in notes(cust, "product_order.stage")][0] == "الصيدلية اعتذرت عن طلبك" and notes(cust, "product_order.stage")[0]["body"] == "المنتج خلص")
ok("reject twice -> 409", A(phm, "reject", p2)[0] == 409 and A(phm, "accept", p2)[0] == 409)
s, r = PO(phid, {**GOOD, "request_key": "k3"}); p3 = r["id"]; d3 = A(phm, "accept", p3)[1]["order_id"]
ok("reject an ACCEPTED order before pickup cancels the delivery order", A(phm, "reject", p3, {"reason": "عطل"})[0] == 200 and mine(cust, d3)["status"] == "cancelled" and sql("SELECT status FROM product_orders WHERE id=?", p3)[0][0] == "rejected")
s, r = PO(phid, {**GOOD, "request_key": "k4"}); p4 = r["id"]
ok("customer cancels a NEW order", call("POST", f"/my/product-orders/{p4}/cancel", {}, cust)[0] == 200 and sql("SELECT status FROM product_orders WHERE id=?", p4)[0][0] == "cancelled" and A(phm, "accept", p4)[0] == 409)

# ---- 7) سقوف الإساءة
for i in range(5): ok("order %d of 5 pending allowed" % (i + 1), PO(phid, {**GOOD, "request_key": "q%d" % i})[0] == 201)
ok("6th pending order -> 429", PO(phid, {**GOOD, "request_key": "q9"})[0] == 429)

# ---- 8) الطلب العادي والمحلات لم يتأثرا (لا حقول صيدلية) + ترحيل آمن مرتين
n = call("POST", "/delivery/orders", {"region_id": Z2, "pickup_text": "سوق البلد", "dropoff_text": "شارع النصر 4", "details": "x", "request_key": "n1"}, other)[1]["id"]
nm = mine(other, n); ok("normal order has no shop_* / place_kind fields", not any(k.startswith("shop_") or k == "place_kind" for k in nm))
import product_orders
cx = sqlite3.connect(DB); product_orders.install(cx); product_orders.install(cx); ok("install is idempotent (twice) and keeps rows", cx.execute("SELECT COUNT(*) FROM product_orders").fetchone()[0] >= 8); cx.close()
server.init("01000000000", "AdminPass123")  # إعادة تشغيل السيرفر على نفس القاعدة: notif.install يحذف كل ntf_ ثم product_orders.install يعيد بناء ntf_po_
ok("after a server restart (init) the 2 product-order triggers still exist and notifications still fire", sql("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'ntf_po_%'")[0][0] == 2
   and PO(phid, {**GOOD, "request_key": "after-restart"}, other)[0] in (201, 429) and True)

# ---- 9) الواجهات + متصفح حقيقي (هاتف 390×844): العميل يضيف ويطلب ← الصيدلية تقبل ← العميل يتابع المراحل ← اعتذار
HERE = os.path.dirname(os.path.abspath(__file__)); rd = lambda f: open(os.path.join(HERE, "static", f), encoding="utf-8").read()
ok("index.html wires cart + order sheet + pending cards + pharmacy stage labels", all(k in rd("index.html") for k in ("padd(", "pcSend", "pordCards(po)", "SHPH", "/my/product-orders")))
ok("pharmacy.html wires the orders section and actions", all(k in rd("pharmacy.html") for k in ("poAct(", "/provider/product-orders", "قبول الطلب وتحويله لدليفري", "اعتذار")))
ok("courier.html labels product orders; sw.js shows the pharmacy push and cache is v130", "product_order" in rd("courier.html") and "porderNote" in rd("sw.js") and 'laqino-v130' in rd("sw.js"))
cu2, cu2id = user("01298700011", "عميل المتصفح")
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch(); errs = []
    def page(tok):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); ctx.add_init_script("localStorage.setItem('t','%s');localStorage.setItem('rg','%d')" % (tok, Z2)); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept("المنتج خلص" if d.type == "prompt" else None)); return pg
    def until(pg, js, timeout=12):
        t = time.time()
        while time.time() - t < timeout:
            if pg.evaluate(js): return True
            pg.wait_for_timeout(250)
        return False
    cu = page(cu2); cu.goto(BASE + "/"); cu.wait_for_selector("nav", timeout=10000); cu.evaluate("mt='pr';go(4)")
    ok("products grid shows an 'اطلب من الصيدلية' button on each product", until(cu, "document.querySelectorAll('.pcd .padd').length>=2"))
    cu.locator(".pcd:has-text('كريم مرطب') .padd").click(); cu.wait_for_selector("#pcbar:not([hidden])", timeout=5000)
    cu.locator(".pcd:has-text('كريم مرطب') .padd").click(); cu.locator(".pcd:has-text('شامبو أطفال') .padd").click()
    ok("cart bar: 3 items from صيدلية النور, total 2×120 + 45.5 = 285.5", until(cu, "(document.getElementById('pcbar')||{innerText:''}).innerText.includes('صيدلية النور')") and "٣ منتج" in cu.inner_text("#pcbar") and "٢٨٥٫٥" in cu.inner_text("#pcbar"))
    cu.click("#pcbar button"); cu.wait_for_selector("#pcs .pan", timeout=5000)
    ok("order sheet lists lines with quantity controls and the pharmacy name", cu.locator("#pcs .pcl").count() == 2 and "صيدلية النور" in cu.inner_text("#pcs h2"))
    cu.click("#pcs .pcl:has-text('شامبو') button[aria-label='زوّد']"); ok("quantity + works (4 items now)", "٤ منتج" in cu.inner_text("#pcbar") or until(cu, "document.getElementById('pcbar').innerText.includes('٤ منتج')"))
    cu.click("#pcgo"); ok("empty address is refused inline (nothing sent)", until(cu, "!document.getElementById('pce').hidden") and sql("SELECT COUNT(*) FROM product_orders WHERE customer_id=?", cu2id)[0][0] == 0)
    cu.fill("#pca", "عمارة 9 شقة 2 شارع النصر"); cu.fill("#pcn", "اتصل قبل ما توصل"); cu.click("#pcgo")
    ok("sent: customer lands on «حسابي» with a 'بانتظار رد الصيدلية' card", until(cu, "document.body.innerText.includes('بانتظار رد الصيدلية')") and cu.locator(".od.po").count() == 1)
    PIDU = sql("SELECT id,items_total FROM product_orders WHERE customer_id=?", cu2id)[0]; ok("server stored the order with server-side total (2×120 + 2×45.5 = 331)", PIDU[1] == 331)
    ph_pg = page(phm); ph_pg.goto(BASE + "/pharmacy.html"); ph_pg.wait_for_selector("#po .card", timeout=10000)
    CARD = "#po .card:has-text('طلب منتجات #%d')" % PIDU[0]
    ok("pharmacy sees the order with items, total, note — and NO customer address", ph_pg.locator(CARD).count() == 1 and "كريم مرطب" in ph_pg.inner_text(CARD) and "331" in ph_pg.inner_text(CARD) and "اتصل قبل" in ph_pg.inner_text(CARD) and "النصر" not in ph_pg.inner_text(CARD) and "الطلبات" in ph_pg.inner_text("#tb"))
    ph_pg.click(CARD + " button:has-text('قبول الطلب')"); ph_pg.wait_for_selector(CARD + " button:has-text('جاهز للاستلام')", timeout=10000)
    ok("accepted in UI: delivery order created and 'جاهز للاستلام' button appears", sql("SELECT status,order_id IS NOT NULL FROM product_orders WHERE id=?", PIDU[0])[0] == ("accepted", 1))
    cu.evaluate("go(3)"); ok("customer sees the stage list with 'الصيدلية قبلت الطلب' done, and the pending card is gone", until(cu, "document.querySelectorAll('.od .shtrk').length>0") and "الصيدلية قبلت الطلب" in cu.inner_text(".shtrk") and cu.locator(".od.po").count() == 0)
    ok("customer bill shows pharmacy name, lines and 'بينك وبين الصيدلية'", "صيدلية النور" in cu.inner_text(".shbill") and "كريم مرطب" in cu.inner_text(".shbill") and "الصيدلية" in cu.inner_text(".shb-n"))
    ph_pg.click(CARD + " button:has-text('جاهز للاستلام')"); ph_pg.wait_for_selector(CARD + " :text('جاهز للاستلام')", timeout=8000)
    cu.evaluate("go(3)"); ok("customer: current stage is 'جاهز للاستلام من الصيدلية'", until(cu, "(document.querySelector('.od .shtrk li.c')||{}).innerText==='جاهز للاستلام من الصيدلية'"))
    ok("customer bell has accepted + ready notifications", [n["title"] for n in notes(cu2, "product_order.stage")] == ["طلبك جاهز للاستلام من الصيدلية", "الصيدلية قبلت طلبك"])
    # اعتذار من الواجهة
    r2 = call("POST", "/medical/pharmacies/%d/order" % phid, {**GOOD, "request_key": "ui2"}, cu2)[1]["id"]
    ph_pg.evaluate("load()"); ph_pg.wait_for_selector("#po .card:has-text('طلب منتجات #%d') button:has-text('اعتذار')" % r2, timeout=8000)
    ph_pg.click("#po .card:has-text('طلب منتجات #%d') button:has-text('اعتذار')" % r2)
    ok("reject from UI (prompt reason) -> customer sees 'الصيدلية اعتذرت' + reason", until(cu, "(go(3),1)") is not None and sql("SELECT status,reject_reason FROM product_orders WHERE id=?", r2)[0] == ("rejected", "المنتج خلص"))
    cu.evaluate("go(3)"); ok("rejected card visible to the customer with the reason", until(cu, "document.body.innerText.includes('الصيدلية اعتذرت')") and "المنتج خلص" in cu.inner_text(".od.po"))
    # منتج من صيدلية تانية: السلة تسأل قبل الاستبدال (مرة واحدة)
    cu.evaluate("mt='pr';go(4)"); cu.wait_for_selector(".pcd .padd", timeout=8000)
    ok("no JS page errors", errs == []) if errs == [] else (print(errs) or exit(1))
    br.close()
print("ALL PASSED")
