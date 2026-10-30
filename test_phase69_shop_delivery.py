# المرحلة 69 (م4 من خطة المحلات): الدليفري للمحلات — المحل يطلب مندوب (مثل الصيدلية) + العميل يطلب من المحل ويوصله المندوب. قاعدة مؤقتة معزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8971; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}; Z2 = Z["المجد 55"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at); call("POST", "/admin/region-fees", {"region_id": Z2, "fee": 25}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
own, oid_ = user("01090000001"); own2, _ = user("01090000002"); cust, cid = user("01090000003"); cust2, _ = user("01090000004"); stf, sid_ = user("01090000007"); c1, u1 = user("01090000005"); c2, u2 = user("01090000006")
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
call("POST", "/admin/shops-settings", {"enabled": True}, at)
def mkshop(t, tid, nm, approve=True):
    r = call("POST", "/shops/apply", {"type_id": tid, "name_ar": nm, "address": "شارع النصر", "phone": "01012345678", "region_id": Z2}, t)[1]["id"]
    if approve: call("POST", "/admin/shops/%d/review" % r, {"status": "approved"}, at)
    return r
S1 = mkshop(own, 1, "مطعم الأمل"); S2 = mkshop(own2, 2, "سوبر ماركت النور"); SP = mkshop(cust2, 3, "حلويات معلقة", approve=False)
call("POST", "/owner/shops/%d/open" % S1, {}, own)
I = lambda s: "/owner/shops/%d/items" % s
i1 = call("POST", I(S1), {"name_ar": "كشري", "price": 35.5}, own)[1]["id"]; i2 = call("POST", I(S1), {"name_ar": "فول", "price": 10}, own)[1]["id"]
i3 = call("POST", I(S1), {"name_ar": "طعمية", "price": 8, "is_available": False}, own)[1]["id"]; ix = call("POST", I(S2), {"name_ar": "أرز", "price": 20}, own2)[1]["id"]
def pk(s, **x): return call("POST", "/owner/shops/%d/delivery-request" % s, x, own)
def ordr(**x): return call("POST", "/shops/%d/order" % S1, x, cust)
def cord(t, oid): return [o for o in call("GET", "/courier/orders", None, t)[1] if o["id"] == oid][0]
def notifs(t): return call("GET", "/notifications", None, t)[1]
GOOD = {"items": [{"item_id": i1, "qty": 2}, {"item_id": i2, "qty": 1}], "dropoff_text": "عمارة 5 شقة 3"}

# ---- 1) المفتاح: مطفي افتراضيًا، للمدير فقط، مدخلات صالحة فقط
ok("default off, zero commission", call("GET", "/admin/shop-delivery", None, at)[1] == {"enabled": False, "commission": 0.0, "late_minutes": 45})
ok("customers get 403, anonymous 401", call("GET", "/admin/shop-delivery", None, cust)[0] == 403 and call("POST", "/admin/shop-delivery", {"enabled": True}, cust)[0] == 403 and call("GET", "/admin/shop-delivery")[0] == 401)
sql("UPDATE users SET role='staff' WHERE id=?", sid_)
ok("staff can read but not write (the shops admin tab opens for staff)", call("GET", "/admin/shop-delivery", None, stf)[1] == {"enabled": False, "commission": 0.0, "late_minutes": 45} and call("POST", "/admin/shop-delivery", {"enabled": True}, stf)[0] == 403)
for bad in ({"enabled": "yes"}, {"enabled": True, "commission": -1}, {"enabled": True, "commission": "abc"}, {"enabled": True, "commission": 100001}, {"enabled": True, "commission": "nan"}):
    ok(f"invalid settings {bad} rejected", call("POST", "/admin/shop-delivery", bad, at)[0] == 400)
ok("both directions refused while off", pk(S1)[0] == 403 and ordr(**GOOD)[0] == 403 and sql("SELECT COUNT(*) FROM delivery_orders")[0][0] == 0)
ok("shop list says enabled=false while off", call("GET", "/owner/shops/%d/delivery-requests" % S1, None, own)[1] == {"enabled": False, "late_minutes": 45, "items": []})
ok("admin enables with commission 2", call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 2}, at)[1] == {"enabled": True, "commission": 2.0, "late_minutes": 45})
call("POST", "/admin/shops-settings", {"enabled": False}, at); ok("shops_enabled off also blocks (both switches required)", pk(S1)[0] == 403 and ordr(**GOOD)[0] == 403)
call("POST", "/admin/shops-settings", {"enabled": True}, at)

# ---- 2) المحل يطلب مندوب: الصلاحيات
ok("anonymous 401", call("POST", "/owner/shops/%d/delivery-request" % S1, {})[0] == 401)
ok("another owner gets 404 (existence not leaked)", call("POST", "/owner/shops/%d/delivery-request" % S1, {}, own2)[0] == 404 and call("GET", "/owner/shops/%d/delivery-requests" % S1, None, own2)[0] == 404)
ok("pending-shop owner gets 403", call("POST", "/owner/shops/%d/delivery-request" % SP, {}, cust2)[0] == 403)
ok("a courier or customer cannot", call("POST", "/owner/shops/%d/delivery-request" % S1, {}, c1)[0] == 404 and call("POST", "/owner/shops/%d/delivery-request" % S1, {}, cust)[0] == 404)

# ---- 3) المحل يطلب مندوب: ضغطة واحدة، بلا أجرة، ينتهي عند الاستلام
s, r = pk(S1, request_key="k1"); po = r["id"]
ok("one tap creates a searching order", s == 201 and r["status"] == "searching")
row = sql("SELECT origin_type,fee,commission,pickup_text,dropoff_text,fare_status,customer_id,comm_type FROM delivery_orders WHERE id=?", po)[0]
ok("shop pickup: no fee, commission from shop setting, auto pickup text, approved fare", row[0] == "shop_pickup" and row[1] == 0 and row[2] == 2 and "مطعم الأمل" in row[3] and "شارع النصر" in row[3] and row[4] == "" and row[5] == "approved" and row[6] == oid_ and row[7] == "fixed")
ok("linked to the shop", sql("SELECT shop_id,kind FROM shop_delivery_links WHERE order_id=?", po)[0] == (S1, "shop_pickup"))
ok("double tap with the same key returns the same order", pk(S1, request_key="k1")[1].get("id") == po and sql("SELECT COUNT(*) FROM delivery_orders")[0][0] == 1)
s2, r2 = pk(S1, request_key="k2", dropoff_text="  عمارة 9  "); ok("optional customer address stored trimmed", s2 == 201 and sql("SELECT dropoff_text FROM delivery_orders WHERE id=?", r2["id"])[0][0] == "عمارة 9")
ok("list is per shop", [x["id"] for x in call("GET", "/owner/shops/%d/delivery-requests" % S1, None, own)[1]["items"]] == [r2["id"], po] and call("GET", "/owner/shops/%d/delivery-requests" % S2, None, own2)[1]["items"] == [])
ok("courier sees it as shop pickup with no fee negotiation", any(a["id"] == po and a["origin_type"] == "shop_pickup" for a in call("GET", "/courier/available", None, c1)[1]))
ok("courier accepts directly (fare approved)", call("POST", f"/courier/orders/{po}/accept", {}, c1) == (200, {"ok": True, "fee": None, "fare_status": "approved"}))
ok("second courier gets 409", call("POST", f"/courier/orders/{po}/accept", {}, c2)[0] == 409)
co = cord(c1, po); ok("courier sees shop contact after accept", co["origin_type"] == "shop_pickup" and co["customer_phone"] and "مطعم الأمل" in co["pickup_text"])
ok("no fare proposal / cannot skip stages", call("POST", f"/courier/orders/{po}/fare", {"fee": 20}, c1)[0] == 409 and call("POST", f"/courier/orders/{po}/status", {"to": "picked_up"}, c1)[0] == 409 and call("POST", f"/courier/orders/{po}/status", {"to": "completed"}, c1)[0] == 409)  # م79: نفس مسار الصيدلية
ok("heading_pickup ok", call("POST", f"/courier/orders/{po}/status", {"to": "heading_pickup"}, c1)[0] == 200)
m = [x for x in call("GET", "/owner/shops/%d/delivery-requests" % S1, None, own)[1]["items"] if x["id"] == po][0]
ok("shop sees courier name and phone while active", m["courier_name"] and m["courier_phone"])
ok("pickup (picked_up) charges the pickup commission once, order still open", call("POST", f"/courier/orders/{po}/status", {"to": "picked_up"}, c1)[1] == {"status": "picked_up"} and sql("SELECT COUNT(*),SUM(amount) FROM wallet_entries WHERE kind='commission' AND ref_id=?", po)[0] == (1, -2.0))
ok("cannot skip heading_customer", call("POST", f"/courier/orders/{po}/status", {"to": "completed"}, c1)[0] == 409)
ok("heading_customer ok", call("POST", f"/courier/orders/{po}/status", {"to": "heading_customer"}, c1)[1] == {"status": "heading_customer"})
ok("delivery to the customer completes it; commission still charged once", call("POST", f"/courier/orders/{po}/status", {"to": "completed"}, c1)[1] == {"status": "completed"} and sql("SELECT COUNT(*),SUM(amount) FROM wallet_entries WHERE kind='commission' AND ref_id=?", po)[0] == (1, -2.0))
m = [x for x in call("GET", "/owner/shops/%d/delivery-requests" % S1, None, own)[1]["items"] if x["id"] == po][0]
ok("shop sees times, delivered_at and no courier phone after finish", m["status"] == "completed" and m["accepted_at"] and m["picked_at"] and m["delivered_at"] and m["courier_phone"] is None and m["delivered_by"] == "courier" and not m["legacy"])
ok("shop cancels a searching pickup via the normal cancel route", call("POST", f"/delivery/orders/{r2['id']}/cancel", {}, own)[1] == {"status": "cancelled"})
s3, r3 = pk(S1); o3 = r3["id"]; call("POST", f"/courier/orders/{o3}/accept", {}, c2)
ok("courier releases back to searching and another takes it", call("POST", f"/courier/orders/{o3}/release", {}, c2)[1] == {"status": "searching"} and call("POST", f"/courier/orders/{o3}/accept", {}, c1)[0] == 200)
call("POST", f"/delivery/orders/{o3}/cancel", {}, own)
ok("a shop owner cannot take their own pickup order as a courier", call("POST", f"/courier/orders/{o3}/accept", {}, own)[0] == 403)

# ---- 4) العميل يطلب من المحل: القائمة والتحقق
s, mn = call("GET", "/shops/%d/menu" % S1)
ok("menu is public, only available items, no images/phone", s == 200 and [x["name_ar"] for x in mn["items"]] == ["كشري", "فول"] and mn["shop"]["is_open"] is True and "phone" not in mn["shop"] and mn["items"][0]["price"] == 35.5)
ok("menu of a pending/unknown shop is 404", call("GET", "/shops/%d/menu" % SP)[0] == 404 and call("GET", "/shops/99999/menu")[0] == 404)
ok("anonymous cannot order", call("POST", "/shops/%d/order" % S1, GOOD)[0] == 401)
ok("owner cannot order from own shop", call("POST", "/shops/%d/order" % S1, GOOD, own)[0] == 403)
ok("pending shop: 404", call("POST", "/shops/%d/order" % SP, GOOD, cust)[0] == 404)
call("POST", "/owner/shops/%d/close" % S1, {}, own); ok("closed shop: 409", ordr(**GOOD)[0] == 409); call("POST", "/owner/shops/%d/open" % S1, {}, own)
bad = lambda **b: ordr(**{**GOOD, **b})[0]
ok("items must be a non-empty list within limits", bad(items=[]) == 400 and bad(items="x") == 400 and bad(items=None) == 400 and bad(items=[{"item_id": i1, "qty": 1}] * 2) == 400 and bad(items=[{"item_id": i, "qty": 1} for i in range(1000, 1021)]) == 400)
ok("qty validation (0, negative, >50, bool, str, float)", all(bad(items=[{"item_id": i1, "qty": q}]) == 400 for q in (0, -1, 51, True, "2", 1.5)))
ok("item id validation (bool, str, other shop's item, unknown, zero, negative, beyond sqlite range)", all(bad(items=[{"item_id": i, "qty": 1}]) == 400 for i in (True, str(i1), ix, 99999, None, 0, -3, 2 ** 63, 10 ** 30)))
ok("unavailable item: 409", bad(items=[{"item_id": i3, "qty": 1}]) == 409)
tmp = call("POST", I(S1), {"name_ar": "مؤقت", "price": 5}, own)[1]["id"]; call("POST", I(S1) + "/%d/delete" % tmp, {}, own)
ok("deleted item rejected", bad(items=[{"item_id": tmp, "qty": 1}]) == 400)
ok("dropoff required (>=3 chars)", bad(dropoff_text="") == 400 and bad(dropoff_text="ab") == 400)
ok("invalid coordinates rejected", bad(dropoff_lat="x", dropoff_lng=1) == 400 and bad(dropoff_lat=95, dropoff_lng=1) == 400)
ok("nothing was created by the invalid requests", sql("SELECT COUNT(*) FROM shop_delivery_links WHERE kind='shop_order'")[0][0] == 0)

# ---- 5) العميل يطلب من المحل: الإنشاء
s, r = ordr(**GOOD, note="  من غير  بصل  ", request_key="ok1", dropoff_lat=30.0, dropoff_lng=31.0); oo = r["id"]
ok("order created (201, total 81.0, delivery code)", s == 201 and r["status"] == "searching" and r["items_total"] == 81.0 and len(r["delivery_code"]) == 6)
row = sql("SELECT origin_type,fee,commission,pickup_text,dropoff_text,details,fare_status,customer_id,region_id,comm_type,comm_value,dropoff_lat FROM delivery_orders WHERE id=?", oo)[0]
ok("normal-flow order: region fee 25 (the shop's region), commission 4 (platform setting, not the pickup 2), fare 'none', pickup=shop, region=shop region", row[0] == "shop_order" and row[1] == 25 and row[2] == 4 and "مطعم الأمل" in row[3] and row[4] == "عمارة 5 شقة 3" and row[6] == "none" and row[7] == cid and row[8] == Z2 and row[9] == "fixed" and row[10] == 4 and row[11] == 30.0)
ok("details give the courier the order number, items and the normalized note — no prices", ("رقم الطلب %d" % oo) in row[5] and "2× كشري" in row[5] and "1× فول" in row[5] and "ملاحظة: من غير بصل" in row[5] and "35" not in row[5])
lk = sql("SELECT shop_id,kind,items_total,note,items_json FROM shop_delivery_links WHERE order_id=?", oo)[0]
ok("link snapshots items (name/price/qty) and note", lk[:4] == (S1, "shop_order", 81.0, "من غير بصل") and json.loads(lk[4]) == [{"id": i1, "name": "كشري", "price": 35.5, "qty": 2}, {"id": i2, "name": "فول", "price": 10, "qty": 1}])
ok("same request_key returns the same order (no duplicate)", ordr(**GOOD, request_key="ok1")[1] == {"id": oo, "status": "searching", "delivery_code": r["delivery_code"], "duplicate": True} and sql("SELECT COUNT(*) FROM shop_delivery_links WHERE kind='shop_order'")[0][0] == 1)
nt = notifs(own); nt = nt.get("items", nt) if isinstance(nt, dict) else nt
ok("shop owner got a 'new order' notification pointing at the shop orders tab", any(n.get("kind") == "shop.order" and n.get("ref_id") == oo and n.get("link") == "shoporders" for n in nt))
ok("price change after the order does not alter the snapshot", call("POST", I(S1) + "/%d/edit" % i1, {"price": 99}, own)[0] == 200 and json.loads(sql("SELECT items_json FROM shop_delivery_links WHERE order_id=?", oo)[0][0])[0]["price"] == 35.5)
ok("customer's open-orders cap applies (5)", all(ordr(**GOOD)[0] == 201 for _ in range(4)) and ordr(**GOOD)[0] == 429)
for x in sql("SELECT order_id FROM shop_delivery_links WHERE kind='shop_order' AND order_id!=?", oo): call("POST", f"/delivery/orders/{x[0]}/cancel", {}, cust)

# ---- 6) المحل يرى الطلبات
lst = call("GET", "/owner/shops/%d/orders" % S1, None, own)[1]
it = [x for x in lst["items"] if x["id"] == oo][0]
ok("shop sees the order with items, total, note and no customer data", it["items_total"] == 81.0 and it["note"] == "من غير بصل" and [(x["name"], x["qty"]) for x in it["items"]] == [("كشري", 2), ("فول", 1)] and set(it) == {"id", "status", "created_at", "items", "items_total", "note", "courier_name", "courier_phone", "can_reject"} and it["courier_name"] is None and it["can_reject"])
ok("another shop owner cannot list or reject them", call("GET", "/owner/shops/%d/orders" % S1, None, own2)[0] == 404 and call("POST", "/owner/shops/%d/orders/%d/reject" % (S2, oo), {}, own2)[0] == 404 and call("POST", "/owner/shops/%d/orders/%d/reject" % (S1, oo), {}, own2)[0] == 404)
ok("a pickup order cannot be rejected through the orders route", call("POST", "/owner/shops/%d/orders/%d/reject" % (S1, po), {}, own)[0] == 404)

# ---- 7) دورة الطلب العادية كاملة: قبول → أجرة → موافقة → توصيل → تأكيد
ok("courier sees it as shop order", any(a["id"] == oo and a["origin_type"] == "shop_order" for a in call("GET", "/courier/available", None, c1)[1]))
ok("accept goes to fare draft (not direct)", call("POST", f"/courier/orders/{oo}/accept", {}, c1) == (200, {"ok": True, "fee": 25, "fare_status": "draft"}))
ok("cannot start before the customer approves the fare", call("POST", f"/courier/orders/{oo}/status", {"to": "heading_pickup"}, c1)[0] == 409)
ok("courier proposes 35, customer approves", call("POST", f"/courier/orders/{oo}/fare", {"fee": 35}, c1)[0] == 200 and call("POST", f"/delivery/orders/{oo}/fare/approve", {"fee": 35}, cust)[0] == 200)
it = [x for x in call("GET", "/owner/shops/%d/orders" % S1, None, own)[1]["items"] if x["id"] == oo][0]
ok("shop sees courier after fare approval", it["courier_name"] and it["courier_phone"])
ok("normal stages: heading_pickup → picked_up → heading_customer → arrived → awaiting_confirmation", all(call("POST", f"/courier/orders/{oo}/status", {"to": t}, c1)[0] == 200 for t in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation")))
ok("shop can no longer reject after pickup", call("POST", "/owner/shops/%d/orders/%d/reject" % (S1, oo), {}, own)[0] == 409)
code = sql("SELECT delivery_code FROM delivery_orders WHERE id=?", oo)[0][0]
ok("wrong code refused; customer confirms; commission 35→fixed 4 charged once", call("POST", f"/courier/orders/{oo}/handover", {"code": "000000" if code != "000000" else "111111"}, c1)[0] == 403 and call("POST", f"/delivery/orders/{oo}/confirm", {}, cust)[0] == 200 and sql("SELECT COUNT(*),SUM(amount) FROM wallet_entries WHERE kind='commission' AND ref_id=?", oo)[0] == (1, -4.0))

# ---- 8) رفض المحل قبل الاستلام
s, r = ordr(**GOOD); o8 = r["id"]
ok("shop rejects a searching order", call("POST", "/owner/shops/%d/orders/%d/reject" % (S1, o8), {}, own)[1] == {"status": "cancelled"} and sql("SELECT status FROM delivery_orders WHERE id=?", o8)[0][0] == "cancelled")
ok("reject writes an order event by the shop owner", sql("SELECT actor_id,from_status,to_status FROM order_events WHERE order_id=? AND to_status='cancelled'", o8)[0] == (oid_, "searching", "cancelled"))
ok("rejecting twice is 409", call("POST", "/owner/shops/%d/orders/%d/reject" % (S1, o8), {}, own)[0] == 409)
s, r = ordr(**GOOD); o9 = r["id"]; call("POST", f"/courier/orders/{o9}/accept", {}, c2)
ok("shop rejects after a courier accepted (before pickup) and the courier loses it", call("POST", "/owner/shops/%d/orders/%d/reject" % (S1, o9), {}, own)[1] == {"status": "cancelled"} and call("POST", f"/courier/orders/{o9}/status", {"to": "heading_pickup"}, c2)[0] == 409)
ok("customer sees the cancelled order", [x for x in call("GET", "/delivery/orders", None, cust)[1] if x["id"] == o9][0]["status"] == "cancelled")

# ---- 9) منطقة المحل بلا أجرة: لا طلب
call("POST", "/admin/shops-settings", {"enabled": True}, at)
saved = sql("SELECT region_id,fee FROM region_fees"); sql("DELETE FROM region_fees")
ok("no region fee for the shop's region: order refused (400) and nothing created", ordr(**GOOD)[0] == 400)
for rid_, fee_ in saved: call("POST", "/admin/region-fees", {"region_id": rid_, "fee": fee_}, at)

# ---- 10) تنظيف: الإشعارات لا تتأثر بحذف/إعادة تثبيت
import shop_delivery, shops
cn = server.db(); shops.install(cn); shop_delivery.install(cn)
ok("install is idempotent and keeps exactly one order trigger", cn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name='ntf_shop_dl_new'").fetchone()[0] == 1); cn.close()
print("ALL PASSED")
