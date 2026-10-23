# المرحلة 40: صيدلية تطلب مندوبًا بضغطة واحدة (بلا أجرة/تفاصيل) — ينتهي الطلب لحظة استلام المندوب منها
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8940; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
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
cust, cid = user("01040000001"); ph, pid = user("01040000002"); c1, u1 = user("01040000003"); c2, u2 = user("01040000004")
call("POST", "/providers/apply", {"name_ar": "صيدلية النور", "region_id": Z2, "address": "شارع البحر"}, ph)
call("POST", f"/admin/providers/{pid}/review", {"status": "approved"}, at)
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
def mk(**x): return call("POST", "/provider/delivery-request", x, ph)
def cord(t, oid): return [o for o in call("GET", "/courier/orders", None, t)[1] if o["id"] == oid][0]
def mine(oid): return [o for o in call("GET", "/provider/delivery-requests", None, ph)[1]["items"] if o["id"] == oid][0]

# ---- 1) المفتاح العام: مطفي افتراضيًا، للإدارة فقط، مدخلات صالحة فقط
ok("default off, zero commission", call("GET", "/admin/provider-delivery", None, at)[1] == {"enabled": False, "commission": 0.0})
ok("admin-only (customer 403)", call("GET", "/admin/provider-delivery", None, cust)[0] == 403 and call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 0}, cust)[0] == 403)
for bad in ({"enabled": "yes"}, {"enabled": True, "commission": -1}, {"enabled": True, "commission": "abc"}, {"enabled": True, "commission": 100001}, {"enabled": True, "commission": "nan"}):
    ok(f"invalid settings {bad} rejected", call("POST", "/admin/provider-delivery", bad, at)[0] == 400)
ok("request refused while off", mk()[0] == 403 and sql("SELECT COUNT(*) FROM delivery_orders")[0][0] == 0)
ok("list shows enabled=false", call("GET", "/provider/delivery-requests", None, ph)[1] == {"enabled": False, "items": []})
ok("admin enables (free)", call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 0}, at)[1] == {"enabled": True, "commission": 0.0})

# ---- 2) الصلاحيات: صيدلية معتمدة فقط
ok("customer cannot request", call("POST", "/provider/delivery-request", {}, cust)[0] == 403)
ok("courier cannot request", call("POST", "/provider/delivery-request", {}, c1)[0] == 403)
ok("anonymous cannot request", call("POST", "/provider/delivery-request", {})[0] in (401, 403))
ph2, pid2 = user("01040000005"); call("POST", "/providers/apply", {"name_ar": "صيدلية قيد المراجعة", "region_id": Z2}, ph2)
ok("pending pharmacy cannot request", call("POST", "/provider/delivery-request", {}, ph2)[0] == 403)

# ---- 3) الإنشاء بضغطة واحدة
s, r = mk(request_key="k1"); oid = r["id"]
ok("one tap creates a searching order", s == 201 and r["status"] == "searching")
row = sql("SELECT origin_type,fee,commission,pickup_text,dropoff_text,fare_status,customer_id FROM delivery_orders WHERE id=?", oid)[0]
ok("provider order: no fee, free commission, auto pickup, empty dropoff", row[0] == "provider_pickup" and row[1] == 0 and row[2] == 0 and "صيدلية النور" in row[3] and "شارع البحر" in row[3] and row[4] == "" and row[5] == "approved" and row[6] == pid)
ok("double tap with same key returns same order", mk(request_key="k1")[1].get("id") == oid and sql("SELECT COUNT(*) FROM delivery_orders")[0][0] == 1)
s2, r2 = mk(request_key="k2", dropoff_text="  عمارة 5 شقة 3  "); ok("optional customer address stored trimmed", s2 == 201 and sql("SELECT dropoff_text FROM delivery_orders WHERE id=?", r2["id"])[0][0] == "عمارة 5 شقة 3")
ok("provider list shows the orders", [x["id"] for x in call("GET", "/provider/delivery-requests", None, ph)[1]["items"]] == [r2["id"], oid])

# ---- 4) المندوب: قبول بلا أجرة، ثم الاستلام ينهي الطلب
av = call("GET", "/courier/available", None, c1)[1]
ok("courier sees it as provider pickup", any(a["id"] == oid and a["origin_type"] == "provider_pickup" for a in av))
ok("courier accepts directly (fare approved, no negotiation)", call("POST", f"/courier/orders/{oid}/accept", {}, c1) == (200, {"ok": True, "fee": None, "fare_status": "approved"}))
ok("second courier gets 409", call("POST", f"/courier/orders/{oid}/accept", {}, c2)[0] == 409)
co = cord(c1, oid)
ok("courier sees pharmacy contact after accept", co["origin_type"] == "provider_pickup" and co["customer_phone"] and "صيدلية النور" in co["pickup_text"])
ok("no fare proposal on provider order", call("POST", f"/courier/orders/{oid}/fare", {"fee": 20}, c1)[0] == 409)
ok("cannot skip to picked_up", call("POST", f"/courier/orders/{oid}/status", {"to": "picked_up"}, c1)[0] == 409)
ok("cannot complete before heading", call("POST", f"/courier/orders/{oid}/status", {"to": "completed"}, c1)[0] == 409)
ok("heading_pickup ok", call("POST", f"/courier/orders/{oid}/status", {"to": "heading_pickup"}, c1)[0] == 200)
ok("pharmacy sees courier while active", mine(oid)["courier_name"] and mine(oid)["courier_phone"])
ok("pickup completes the order", call("POST", f"/courier/orders/{oid}/status", {"to": "completed"}, c1)[1] == {"status": "completed"})
ok("free commission: no wallet entry", sql("SELECT COUNT(*) FROM wallet_entries WHERE kind='commission' AND ref_id=?", oid)[0][0] == 0)
m = mine(oid)
ok("pharmacy sees times and no courier phone after finish", m["status"] == "completed" and m["accepted_at"] and m["picked_at"] and m["courier_phone"] is None)
ok("courier cannot move a finished order", call("POST", f"/courier/orders/{oid}/status", {"to": "heading_pickup"}, c1)[0] == 409)

# ---- 5) الإلغاء من الصيدلية قبل الاستلام + تخلّي المندوب
ok("pharmacy cancels a searching order", call("POST", f"/delivery/orders/{r2['id']}/cancel", {}, ph)[1] == {"status": "cancelled"})
s3, r3 = mk(); o3 = r3["id"]; call("POST", f"/courier/orders/{o3}/accept", {}, c2)
ok("courier releases back to searching and fare stays valid", call("POST", f"/courier/orders/{o3}/release", {}, c2)[1] == {"status": "searching"})
ok("another courier can take the released order", call("POST", f"/courier/orders/{o3}/accept", {}, c1)[0] == 200)
call("POST", f"/courier/orders/{o3}/status", {"to": "heading_pickup"}, c1); ok("pharmacy cancels while courier heads to pickup", call("POST", f"/delivery/orders/{o3}/cancel", {}, ph)[1] == {"status": "cancelled"})

# ---- 6) العمولة الثابتة لاحقًا تُخصم عند الاستلام
ok("admin sets fixed commission 5", call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 5}, at)[1]["commission"] == 5)
s4, r4 = mk(); o4 = r4["id"]
ok("order stores commission", sql("SELECT commission,comm_type,comm_value FROM delivery_orders WHERE id=?", o4)[0] == (5.0, "fixed", 5.0))
call("POST", f"/courier/orders/{o4}/accept", {}, c1); call("POST", f"/courier/orders/{o4}/status", {"to": "heading_pickup"}, c1); call("POST", f"/courier/orders/{o4}/status", {"to": "completed"}, c1)
ok("commission charged once at pickup", sql("SELECT user_id,amount FROM wallet_entries WHERE kind='commission' AND ref_type='order' AND ref_id=?", o4) == [(u1, -5.0)])
sql("DELETE FROM wallet_entries WHERE user_id=?", u2)  # مندوب بلا رصيد
s5, r5 = mk(); ok("courier without balance cannot accept (402)", call("POST", f"/courier/orders/{r5['id']}/accept", {}, c2)[0] == 402)

# ---- 7) حد الطلبات المفتوحة + المفتاح يقفل الإنشاء فقط
for _ in range(10): mk()
ok("open-orders cap (10) -> 429", mk()[0] == 429)
call("POST", "/admin/provider-delivery", {"enabled": False, "commission": 5}, at)
ok("switch off blocks creation but history stays readable", mk()[0] == 403 and call("GET", "/provider/delivery-requests", None, ph)[1]["enabled"] is False and len(call("GET", "/provider/delivery-requests", None, ph)[1]["items"]) > 0)

# ---- 8) الطلب العادي لم يتأثر
cc, _ = user("01040000006")
s6, r6 = call("POST", "/delivery/orders", {"pickup_text": "مخبز النور", "dropoff_text": "شارع المدرسة"}, cc)
ok("regular order still created", s6 == 201 and sql("SELECT origin_type FROM delivery_orders WHERE id=?", r6["id"])[0][0] is None)
call("POST", "/courier/online", {"online": True}, c1); call("POST", "/courier/online", {"online": True}, c2)
ok("regular order still needs fare approval", call("POST", f"/courier/orders/{r6['id']}/accept", {}, c1)[1].get("fare_status") == "draft")
print("ALL OK")
