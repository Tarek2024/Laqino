# المرحلة 27: أجرة يقترحها العميل (اختيارية) — المندوب يقبلها مباشرة أو يعدّلها ثم يوافق/يرفض العميل
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8927; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
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
call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}
Z1, Z2 = Z["فرج الكبرى / الكوم"], Z["المجد 55"]  # الافتراضي 15 و120
cust, cid = user("01027000001"); c1, u1 = user("01027000002"); c2, u2 = user("01027000003")
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
def order(rid=Z2, **x): return call("POST", "/delivery/orders", {"region_id": rid, "pickup_text": "مخبز النور", "dropoff_text": "شارع المدرسة", **x}, cust)
def mine(oid): return [o for o in call("GET", "/delivery/orders", None, cust)[1] if o["id"] == oid][0]
def cord(t, oid): return [o for o in call("GET", "/courier/orders", None, t)[1] if o["id"] == oid][0]
def avail(t): return call("GET", "/courier/available", None, t)[1]
def walk(t, oid):
    for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"):
        if call("POST", f"/courier/orders/{oid}/status", {"to": to}, t)[0] != 200: return False
    return True
def comm_rows(oid): return sql("SELECT user_id,amount FROM wallet_entries WHERE kind='commission' AND ref_type='order' AND ref_id=?", oid)

# ---- 1) تحقق المدخلات على الخادم
for bad in (0, -5, "abc", 100001, "nan", "inf", [], {}):
    ok(f"offer_fee {bad!r} rejected", order(offer_fee=bad)[0] == 400)
ok("no order created by invalid offers", sql("SELECT COUNT(*) FROM delivery_orders")[0][0] == 0)
ok("empty string offer = no offer", order(offer_fee="")[0] == 201 and order(offer_fee="  ")[0] == 201 and order(offer_fee=None)[0] == 201)
ok("old flow rows have offer_fee NULL", sql("SELECT COUNT(*) FROM delivery_orders WHERE offer_fee IS NOT NULL")[0][0] == 0)
for (o,) in sql("SELECT id FROM delivery_orders"): call("POST", f"/delivery/orders/{o}/cancel", {}, cust)

# ---- 2) الطلب بسعر العميل
s, r = order(offer_fee=15); oid = r["id"]
ok("create with offer 15", s == 201)
ok("stored: fee=15, offer_fee=15 (region default was 120)", sql("SELECT fee,offer_fee FROM delivery_orders WHERE id=?", oid)[0] == (15, 15))
ok("customer sees own offer, no courier fee yet", mine(oid)["offer_fee"] == 15 and mine(oid)["fee"] is None and mine(oid)["courier_name"] is None)
av = avail(c1); ok("courier available shows offer 15", [o["id"] for o in av] == [oid] and av[0]["offer_fee"] == 15)
ok("available hides addresses", "pickup_text" not in av[0] and "dropoff_text" not in av[0])

# ---- 3) قبول مباشر بسعر العميل
s, r = call("POST", f"/courier/orders/{oid}/accept", None, c1)
ok("accept at customer's price: approved, fee 15", s == 200 and r["fare_status"] == "approved" and r["fee"] == 15)
o = cord(c1, oid); ok("courier sees approved 15 and customer contact", o["fee"] == 15 and o["fare_status"] == "approved" and o["customer_phone"] is not None)
m = mine(oid); ok("customer sees courier + fee 15 approved", m["fee"] == 15 and m["fare_status"] == "approved" and m["courier_name"] is not None)
ok("no second approval needed: courier can start", call("POST", f"/courier/orders/{oid}/status", {"to": "heading_pickup"}, c1)[0] == 200)
ok("commission reserved on offer (4)", sql("SELECT commission FROM delivery_orders WHERE id=?", oid)[0][0] == 4)
ok("audit logged", sql("SELECT COUNT(*) FROM audit_log WHERE action='order.fare_accepted_offer' AND target=?", str(oid))[0][0] == 1)
ok("walk to awaiting_confirmation", all(call("POST", f"/courier/orders/{oid}/status", {"to": to}, c1)[0] == 200 for to in ("picked_up", "heading_customer", "arrived", "awaiting_confirmation")))
call("POST", f"/delivery/orders/{oid}/confirm", {}, cust)
ok("completed with commission charged once", len(comm_rows(oid)) == 1 and comm_rows(oid)[0][1] == -4)

# ---- 4) عرض مضاد ثم رفض العميل: يرجع الطلب للباقين بسعر العميل الأصلي
s, r = order(offer_fee=15); oid2 = r["id"]
s, r = call("POST", f"/courier/orders/{oid2}/accept", {"counter": True}, c1)
ok("counter accept -> draft, reference fee = customer's 15", s == 200 and r["fare_status"] == "draft" and r["fee"] == 15)
o = cord(c1, oid2); ok("draft shows offer_fee and hides customer contact", o["offer_fee"] == 15 and o["customer_phone"] is None)
ok("courier cannot start before agreement", call("POST", f"/courier/orders/{oid2}/status", {"to": "heading_pickup"}, c1)[0] == 409)
ok("courier proposes 20 (no cap)", call("POST", f"/courier/orders/{oid2}/fare", {"fee": 20}, c1)[1]["fare_status"] == "proposed")
m = mine(oid2); ok("customer sees proposal 20 and still own offer 15", m["fee"] == 20 and m["offer_fee"] == 15 and m["fare_status"] == "proposed")
ok("customer rejects", call("POST", f"/delivery/orders/{oid2}/fare/reject", {"fee": 20}, cust)[0] == 200)
ok("back to searching, offer_fee intact", sql("SELECT status,offer_fee FROM delivery_orders WHERE id=?", oid2)[0] == ("searching", 15))
ok("courier1 no longer sees it", oid2 not in [o["id"] for o in avail(c1)])
av2 = [o for o in avail(c2) if o["id"] == oid2]; ok("courier2 sees it with offer 15", len(av2) == 1 and av2[0]["offer_fee"] == 15)
s, r = call("POST", f"/courier/orders/{oid2}/accept", None, c2)
ok("courier2 accepts at 15 -> approved", s == 200 and r["fare_status"] == "approved" and sql("SELECT fee FROM delivery_orders WHERE id=?", oid2)[0][0] == 15)

# ---- 5) عرض مضاد ثم موافقة العميل
s, r = order(offer_fee=15); oid3 = r["id"]
call("POST", f"/courier/orders/{oid3}/accept", {"counter": True}, c1); call("POST", f"/courier/orders/{oid3}/fare", {"fee": 25}, c1)
ok("customer approves 25", call("POST", f"/delivery/orders/{oid3}/fare/approve", {"fee": 25}, cust)[0] == 200 and mine(oid3)["fee"] == 25)
ok("start allowed after approval", call("POST", f"/courier/orders/{oid3}/status", {"to": "heading_pickup"}, c1)[0] == 200)

# ---- 6) بلا سعر من العميل: التدفق القديم كما هو
s, r = order(rid=Z1); oid4 = r["id"]
ok("no offer: available shows offer_fee null", [o for o in avail(c2) if o["id"] == oid4][0]["offer_fee"] is None)
s, r = call("POST", f"/courier/orders/{oid4}/accept", None, c2)
ok("no offer: accept -> draft with region default 15", s == 200 and r["fare_status"] == "draft" and cord(c2, oid4)["fee"] == 15 and cord(c2, oid4)["offer_fee"] is None)
ok("counter flag ignored when no offer", True)

# ---- 7) العمولة النسبية تُحسب من سعر العميل
call("POST", "/admin/settings", {"commission_type": "percent", "commission_value": 10}, at)
s, r = order(offer_fee=50); oid5 = r["id"]
ok("percent commission on offered 50 = 5", sql("SELECT fee,commission FROM delivery_orders WHERE id=?", oid5)[0] == (50, 5))
call("POST", f"/courier/orders/{oid5}/accept", None, c2)
ok("commission stays 5 after direct accept", sql("SELECT commission,fare_status FROM delivery_orders WHERE id=?", oid5)[0] == (5, "approved"))

# ---- 8) رصيد غير كافٍ
c3, u3 = user("01027000004"); apply_docs(call, c3); call("POST", f"/admin/couriers/{u3}/review", {"status": "approved"}, at); call("POST", "/courier/online", {"online": True}, c3)
s, r = order(offer_fee=5000); oid6 = r["id"]
s, _ = call("POST", f"/courier/orders/{oid6}/accept", None, c3)
ok("insufficient wallet cannot accept offered order (402)", s == 402 and sql("SELECT status FROM delivery_orders WHERE id=?", oid6)[0][0] == "searching")
print("ALL PASS")
