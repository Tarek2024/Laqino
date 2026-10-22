# المرحلة 25: الأجرة التفاوضية (مناطق ثابتة + أجرة افتراضية بحدّين + اقتراح المندوب + موافقة/رفض العميل + عمولة مرة واحدة)
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
server.init("01000000000", "AdminPass123")  # التشغيل المتكرر لا يكرّر المناطق ولا يكتب فوق الأسعار
BASE = "http://127.0.0.1:8841"; DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8841), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
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

# ---- المناطق والأسعار الافتراضية
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}
EXPECT = {"فرج الكبرى / الكوم": 15, "المثلث / البرية (عزبة البط)": 25, "الحصفة / الثابت": 35, "أبو مصطفى": 40, "منشأة سلامة": 45, "الضبعة / الرصيف": 50, "الوزارية": 60, "العاقولة": 90, "بقلولة / العمران": 100, "المجد 55": 120}
ok("10 zones seeded under Riyad", set(Z) == set(EXPECT) and sql("SELECT COUNT(*) FROM regions WHERE parent_id=3")[0][0] == 10)
fees = {f["name_ar"]: f for f in call("GET", "/admin/settings", None, at)[1]["fees"]}
ok("default prices exact", all(fees[n]["fee"] == v for n, v in EXPECT.items()))
Z1, Z2 = Z["فرج الكبرى / الكوم"], Z["المجد 55"]
ok("fee endpoint exposes availability only", call("GET", f"/delivery/fee?region_id={Z1}")[1] == {"available": True})
ok("admin rejects negative fee", call("POST", "/admin/region-fees", {"region_id": Z1, "fee": -1}, at)[0] == 400)

# ---- أطراف
cust, cid = user("01022220001"); c1, u1 = user("01022220002"); c2, u2 = user("01022220003")
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
def order(rid=Z1, **x): return call("POST", "/delivery/orders", {"region_id": rid, "pickup_text": "مخبز النور", "dropoff_text": "شارع المدرسة", **x}, cust)
def mine(oid): return [o for o in call("GET", "/delivery/orders", None, cust)[1] if o["id"] == oid][0]
def cord(t, oid): return [o for o in call("GET", "/courier/orders", None, t)[1] if o["id"] == oid][0]
def walk(t, oid):
    for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"):
        if call("POST", f"/courier/orders/{oid}/status", {"to": to}, t)[0] != 200: return False
    return True
def comm_rows(oid): return sql("SELECT user_id,amount FROM wallet_entries WHERE kind='commission' AND ref_type='order' AND ref_id=?", oid)

# ---- 1) العميل ينشئ الطلب دون سعر
s, r = order(); oid = r["id"]
ok("create: 201 and no price in response", s == 201 and "fee" not in r)
ok("customer list: no fee, no courier yet", mine(oid)["fee"] is None and mine(oid)["courier_name"] is None)
av = call("GET", "/courier/available", None, c1)[1]
ok("courier available list shows no price", [o["id"] for o in av] == [oid] and all("fee" not in o for o in av))

# ---- 2) المندوب يقبل فتظهر الأجرة الافتراضية
ok("courier1 accepts", call("POST", f"/courier/orders/{oid}/accept", None, c1)[0] == 200)
o = cord(c1, oid)
ok("courier sees default 15, draft", o["fee"] == 15 and o["fare_status"] == "draft")
ok("customer contact hidden from courier before approval", o["customer_phone"] is None and o["customer_name"] is None)
ok("customer still sees no price/courier in draft", mine(oid)["fee"] is None and mine(oid)["courier_name"] is None and mine(oid)["fare_status"] == "draft")
ok("cannot start delivery before approval", call("POST", f"/courier/orders/{oid}/status", {"to": "heading_pickup"}, c1)[0] == 409)
ok("customer cannot approve a draft", call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 15}, cust)[0] == 409)

# ---- الحدود على الخادم
for bad in (-5, 0, 1e9, "abc", None): ok("server rejects fare %r" % (bad,), call("POST", f"/courier/orders/{oid}/fare", {"fee": bad}, c1)[0] == 400)
ok("other courier cannot set fare", call("POST", f"/courier/orders/{oid}/fare", {"fee": 15}, c2)[0] == 404)
ok("customer cannot set fare via courier api", call("POST", f"/courier/orders/{oid}/fare", {"fee": 15}, cust)[0] in (403, 404))
ok("no limits: courier may go below/above default (9 and 21 accepted)", call("POST", f"/courier/orders/{oid}/fare", {"fee": 9}, c1)[0] == 200 and call("POST", f"/courier/orders/{oid}/fare", {"fee": 21}, c1)[0] == 200)
ok("courier proposes 18", call("POST", f"/courier/orders/{oid}/fare", {"fee": 18}, c1)[0] == 200)
m = mine(oid)
ok("customer sees courier name + proposed fare", m["fee"] == 18 and m["courier_name"] and m["fare_status"] == "proposed" and m["courier_phone"] is None)
ok("customer got fare notification", sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='order.fare' AND ref_id=?", cid, oid)[0][0] >= 1)
ok("courier cannot start before customer approves", call("POST", f"/courier/orders/{oid}/status", {"to": "heading_pickup"}, c1)[0] == 409)

# ---- 3) موافقة العميل
ok("stale fee approval rejected (race guard)", call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 15}, cust)[0] == 409)
ok("approval requires the fee", call("POST", f"/delivery/orders/{oid}/fare/approve", {}, cust)[0] == 400)
ok("another customer cannot approve", call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 18}, c2)[0] == 404)
ok("customer approves 18", call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 18}, cust)[0] == 200)
ok("approve twice -> 409", call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 18}, cust)[0] == 409)
ok("courier cannot change fare after approval", call("POST", f"/courier/orders/{oid}/fare", {"fee": 12}, c1)[0] == 409)
o = cord(c1, oid)
ok("courier now sees customer contact", o["customer_phone"] and o["fee"] == 18)
ok("courier notified of approval", sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='order.fare' AND ref_id=?", u1, oid)[0][0] == 1)
ok("customer sees courier phone after approval", mine(oid)["courier_phone"])
ok("delivery walk allowed after approval", walk(c1, oid))

# ---- عمولة مرة واحدة
bal0 = call("GET", "/courier/wallet", None, c1)[1]["balance"]
ok("customer confirm -> completed", call("POST", f"/delivery/orders/{oid}/confirm", None, cust)[0] == 200)
ok("exactly one commission entry (-4)", comm_rows(oid) == [(u1, -4.0)])
ok("confirm again rejected", call("POST", f"/delivery/orders/{oid}/confirm", None, cust)[0] == 409)
code = sql("SELECT delivery_code FROM delivery_orders WHERE id=?", oid)[0][0]
ok("handover after completion rejected", call("POST", f"/courier/orders/{oid}/handover", {"code": code}, c1)[0] in (404, 409))
cn = server.db(); server.charge_commission(cn, oid); server.charge_commission(cn, oid); cn.commit(); cn.close()
ok("charge_commission idempotent", comm_rows(oid) == [(u1, -4.0)] and call("GET", "/courier/wallet", None, c1)[1]["balance"] == bal0)  # المرحلة 28: العمولة تُخصم عند التسليم (قبل bal0)، فلا خصم إضافي بعد الإغلاق

# ---- 4) رفض العميل: يعود للباقين ولا يُعرض للمندوب المرفوض
s, r = order(Z2); oid2 = r["id"]
ok("far zone order accepted by c1: default 120", call("POST", f"/courier/orders/{oid2}/accept", None, c1)[0] == 200 and cord(c1, oid2)["fee"] == 120)
ok("c2 sees order as taken meanwhile", [x["taken"] for x in call("GET", "/courier/available", None, c2)[1] if x["id"] == oid2] in ([1], []))
ok("c1 sends default 120", call("POST", f"/courier/orders/{oid2}/fare", {"fee": 120}, c1)[0] == 200)
ok("customer rejects", call("POST", f"/delivery/orders/{oid2}/fare/reject", {"fee": 120}, cust)[0] == 200)
row = sql("SELECT status,courier_id,fare_status FROM delivery_orders WHERE id=?", oid2)[0]
ok("order back to searching, unassigned, fare reset", row == ("searching", None, "none"))
ok("c1 never sees it again", all(x["id"] != oid2 for x in call("GET", "/courier/available", None, c1)[1]))
ok("c1 cannot accept it again", call("POST", f"/courier/orders/{oid2}/accept", None, c1)[0] == 409)
ok("c2 sees it as open (not taken)", [x["taken"] for x in call("GET", "/courier/available", None, c2)[1] if x["id"] == oid2] == [0])
ok("c1 (old courier) notified of release", sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='order.released' AND ref_id=?", u1, oid2)[0][0] == 1)
ok("customer list hides price again", mine(oid2)["fee"] is None and mine(oid2)["courier_name"] is None)
ok("reject audited", sql("SELECT COUNT(*) FROM audit_log WHERE action='order.fare_rejected' AND target=?", str(oid2))[0][0] == 1)
ok("c2 accepts and proposes 100", call("POST", f"/courier/orders/{oid2}/accept", None, c2)[0] == 200 and call("POST", f"/courier/orders/{oid2}/fare", {"fee": 100}, c2)[0] == 200)
ok("c2 re-proposes 130, old fee approval now stale", call("POST", f"/courier/orders/{oid2}/fare", {"fee": 130}, c2)[0] == 200 and call("POST", f"/delivery/orders/{oid2}/fare/approve", {"fee": 100}, cust)[0] == 409)
ok("customer approves 130", call("POST", f"/delivery/orders/{oid2}/fare/approve", {"fee": 130}, cust)[0] == 200)
ok("walk + handover by code", walk(c2, oid2) and call("POST", f"/courier/orders/{oid2}/handover", {"code": sql("SELECT delivery_code FROM delivery_orders WHERE id=?", oid2)[0][0]}, c2)[0] == 200)
ok("single commission for c2", comm_rows(oid2) == [(u2, -4.0)])
ok("customer confirm after handover does not double charge", call("POST", f"/delivery/orders/{oid2}/confirm", None, cust)[0] == 409 and len(comm_rows(oid2)) == 1)

# ---- عمولة نسبية تُحسب على الأجرة النهائية المتفق عليها
call("POST", "/admin/settings", {"commission_type": "percent", "commission_value": 10}, at)
s, r = order(Z1); oid3 = r["id"]
call("POST", f"/courier/orders/{oid3}/accept", None, c1); call("POST", f"/courier/orders/{oid3}/fare", {"fee": 20}, c1); call("POST", f"/delivery/orders/{oid3}/fare/approve", {"fee": 20}, cust)
ok("percent commission computed on agreed fee (10% of 20 = 2)", sql("SELECT commission FROM delivery_orders WHERE id=?", oid3)[0][0] == 2.0)
walk(c1, oid3); call("POST", f"/delivery/orders/{oid3}/confirm", None, cust)
ok("percent commission charged once", comm_rows(oid3) == [(u1, -2.0)])

# ---- تخلّي المندوب وإلغاء العميل وتعديل الإدارة
call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
s, r = order(Z1); oid4 = r["id"]
call("POST", f"/courier/orders/{oid4}/accept", None, c1); call("POST", f"/courier/orders/{oid4}/fare", {"fee": 19}, c1)
ok("courier release resets fare", call("POST", f"/courier/orders/{oid4}/release", {}, c1)[0] == 200 and sql("SELECT status,fare_status,courier_id FROM delivery_orders WHERE id=?", oid4)[0] == ("searching", "none", None))
call("POST", f"/courier/orders/{oid4}/accept", None, c2)
ok("accept again starts a fresh draft at the default", cord(c2, oid4)["fare_status"] == "draft" and cord(c2, oid4)["fee"] == 15)
ok("customer can cancel during draft", call("POST", f"/delivery/orders/{oid4}/cancel", None, cust)[0] == 200)
ok("admin updates price and limits", call("POST", "/admin/region-fees", {"region_id": Z1, "fee": 20}, at)[0] == 200)
s, r = order(Z1); oid5 = r["id"]; call("POST", f"/courier/orders/{oid5}/accept", None, c1)
ok("new default applied (20)", cord(c1, oid5)["fee"] == 20)
ok("courier proposes 23 freely", call("POST", f"/courier/orders/{oid5}/fare", {"fee": 23}, c1)[0] == 200)
ok("non-admin cannot change prices", call("POST", "/admin/region-fees", {"region_id": Z1, "fee": 1}, cust)[0] in (401, 403))
# admin reassign resets
call("POST", f"/admin/orders/{oid5}/reassign", {}, at)
ok("admin reassign resets fare", sql("SELECT status,fare_status FROM delivery_orders WHERE id=?", oid5)[0] == ("searching", "none"))
# init is idempotent and keeps admin edits
server.init("01000000000", "AdminPass123")
ok("re-init keeps admin edits and adds no duplicates", sql("SELECT fee FROM region_fees WHERE region_id=?", Z1)[0][0] == 20 and sql("SELECT COUNT(*) FROM regions WHERE parent_id=3")[0][0] == 10)
# legacy in-flight rows keep working
sql("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,fee,courier_id,status,commission,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", cid, Z1, "legacy a", "legacy b", 25, u2, "assigned", 4, 1, 1)
lid = sql("SELECT MAX(id) FROM delivery_orders")[0][0]
ok("legacy assigned order (fare_status default) still advances", call("POST", f"/courier/orders/{lid}/status", {"to": "heading_pickup"}, c2)[0] == 200)
print("ALL PASS")
