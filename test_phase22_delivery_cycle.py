# مراجعة دورة الدليفري: رمز تسليم طلبات الصيدلية + إعادة تعيين الإدارة + تخلّي المندوب
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs, fare_ok
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
BASE = "http://127.0.0.1:8797"; DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8797), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
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
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
cust, cid = user("01011110001"); ph, pid = user("01011110002"); c1, u1 = user("01011110003"); c2, u2 = user("01011110004")
call("POST", "/providers/apply", {"name_ar": "صيدلية الأمل", "region_id": 3, "address": "شارع النيل"}, ph); call("POST", f"/admin/providers/{pid}/review", {"status": "approved"}, at)
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at)
    call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
ids = lambda t: [(x["id"], x["taken"]) for x in call("GET", "/courier/available", None, t)[1]]
def walk(t, oid):
    fare_ok(oid)
    for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"):
        s, r = call("POST", f"/courier/orders/{oid}/status", {"to": to}, t)
        if s != 200: return False
    return True

# ---- 1) طلب توصيل أنشأه العميل من رد صيدلية يجب أن يحمل رمز تسليم
inq = call("POST", "/medical/inquiries", {"medicine_name": "بنادول اكسترا", "region_id": 3}, cust)[1]["id"]
call("POST", f"/provider/inquiries/{inq}/respond", {"status": "available", "price": 50}, ph)
s, o = call("POST", "/medical/delivery", {"source_type": "inquiry", "source_id": inq, "provider_id": pid, "dropoff_text": "شارع الجمهورية 10"}, cust); oid = o["id"]
ok("pharmacy-linked order created", s == 201)
row = sql("SELECT delivery_code,search_started_at,created_at FROM delivery_orders WHERE id=?", oid)[0]
ok("pharmacy-linked order has a 6-digit delivery code", row[0] and len(row[0]) == 6 and row[0].isdigit())
ok("pharmacy-linked order has a search window start", row[1] == row[2] and row[1] > 0)
ok("courier accepts it", call("POST", f"/courier/orders/{oid}/accept", {}, c1)[0] == 200)
ok("customer sees the code once a courier is assigned", [x for x in call("GET", "/delivery/orders", None, cust)[1] if x["id"] == oid][0]["delivery_code"] == row[0])
ok("courier walks the order to awaiting_confirmation", walk(c1, oid))
ok("wrong code rejected", call("POST", f"/courier/orders/{oid}/handover", {"code": "000000" if row[0] != "000000" else "111111"}, c1)[0] == 403)
ok("correct code completes it and charges the commission once", call("POST", f"/courier/orders/{oid}/handover", {"code": row[0]}, c1)[0] == 200 and sql("SELECT COUNT(*),SUM(amount) FROM wallet_entries WHERE kind='commission' AND ref_id=?", oid)[0] == (1, -4.0))

# ---- 2) إعادة تعيين الإدارة: كل المناديب (حتى من عُرض عليهم الطلب سابقًا) يرونه من جديد ويصلهم تنبيه
s, o2 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "صيدلية الشفاء", "dropoff_text": "بيت 7"}, cust); o2 = o2["id"]
ok("both couriers are offered the new order", (o2, 0) in ids(c1) and (o2, 0) in ids(c2))
ok("c1 accepts; c2 loses it", call("POST", f"/courier/orders/{o2}/accept", {}, c1)[0] == 200 and call("POST", f"/courier/orders/{o2}/accept", {}, c2)[0] in (200, 409) and sql("SELECT status FROM delivery_orders WHERE id=?", o2)[0][0] == "assigned" and sql("SELECT courier_id FROM delivery_orders WHERE id=?", o2)[0][0] == u1)
sql("UPDATE order_offers SET responded_at=responded_at-500,offered_at=offered_at-500 WHERE order_id=?", o2)
sql("UPDATE delivery_orders SET search_started_at=search_started_at-900,created_at=created_at-900 WHERE id=?", o2)
ok("admin reassign works", call("POST", f"/admin/orders/{o2}/reassign", {}, at)[0] == 200)
r = sql("SELECT status,courier_id,search_started_at FROM delivery_orders WHERE id=?", o2)[0]
ok("reassign restarts the search window (not stale)", r[0] == "searching" and r[1] is None and r[2] >= int(time.time()) - 5)
ok("reassign clears old offer rows", sql("SELECT COUNT(*) FROM order_offers WHERE order_id=?", o2)[0][0] == 0)
ok("a courier who lost it earlier sees it again after reassign", (o2, 0) in ids(c2))
ok("and can accept it", call("POST", f"/courier/orders/{o2}/accept", {}, c2)[0] == 200)

# ---- 3) تخلّي المندوب
ok("courier releases an assigned order", call("POST", f"/courier/orders/{o2}/release", {}, c2)[0] == 200)
ok("released order goes back to searching with a fresh window", sql("SELECT status,courier_id FROM delivery_orders WHERE id=?", o2)[0] == ("searching", None))
ok("other courier sees the released order", (o2, 0) in ids(c1))
ok("cannot release a cancelled order (no resurrection)", (call("POST", f"/delivery/orders/{o2}/cancel", {}, cust)[0] == 200) and call("POST", f"/courier/orders/{o2}/release", {}, c2)[0] in (404, 409) and sql("SELECT status FROM delivery_orders WHERE id=?", o2)[0][0] == "cancelled")

# ---- 4) أجرة التوصيل تُورَّث للمناطق التابعة (قرية/حي) — كان العميل يرى «الدليفري غير متاح» رغم وجود مندوب متصل
sql("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(50,3,'village','eg-kfs-riyad-v1','قرية تابعة',1)")
sql("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(51,50,'zone','eg-kfs-riyad-v1-z','حي داخل القرية',1)")
sql("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(52,3,'village','eg-kfs-riyad-off','قرية معطلة',0)")
sql("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(60,2,'markaz','eg-kfs-other-mk','مركز بلا أجرة',1)")
ok("fee endpoint: village inherits the markaz fee", call("GET", "/delivery/fee?region_id=50")[1]["available"] is True)
ok("fee endpoint: nested zone inherits it too", call("GET", "/delivery/fee?region_id=51")[1]["available"] is True)
ok("fee endpoint: inactive region and unpriced markaz stay unavailable", call("GET", "/delivery/fee?region_id=52")[1]["available"] is False and call("GET", "/delivery/fee?region_id=60")[1]["available"] is False)
ok("fee endpoint: garbage region id is tolerated", call("GET", "/delivery/fee?region_id=abc")[1]["available"] is False and call("GET", "/delivery/fee")[1]["available"] is False)
s, v = call("POST", "/delivery/orders", {"region_id": 50, "pickup_text": "صيدلية القرية", "dropoff_text": "بيت في القرية"}, cust)
ok("customer can order from a village under a priced markaz", s == 201 and "fee" not in v)
ok("phase 28: no region price requirement; an inactive/garbage region_id is ignored (internal default used)", call("POST", "/delivery/orders", {"region_id": 60, "pickup_text": "aaa", "dropoff_text": "bbb"}, cust)[0] == 201 and call("POST", "/delivery/orders", {"region_id": 52, "pickup_text": "aaa", "dropoff_text": "bbb"}, cust)[0] == 201)
ok("the online markaz courier sees the village order", (v["id"], 0) in ids(c1))
ok("and can accept it", call("POST", f"/courier/orders/{v['id']}/accept", {}, c1)[0] == 200)
print("ALL PASSED")
