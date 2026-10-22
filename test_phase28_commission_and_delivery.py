# المرحلة 28: خصم العمولة عند وصول المندوب (awaiting_confirmation) + عكسها + محفظة (متاح/محجوز) + طلب توصيل بلا اختيار منطقة
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8928; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
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
cust, cid = user("01028000001"); cu, uid = user("01028000002")
apply_docs(call, cu); call("POST", f"/admin/couriers/{uid}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 1000, "transfer_ref": "REF0028"}, cu)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
call("POST", "/courier/online", {"online": True}, cu)
def setc(t, v): call("POST", "/admin/settings", {"commission_type": t, "commission_value": v}, at)
def order(**x): return call("POST", "/delivery/orders", {"pickup_text": "مخبز النور", "dropoff_text": "شارع المدرسة", **x}, cust)  # بلا region_id
def wal(): return call("GET", "/courier/wallet", None, cu)[1]
def rows(oid, k="commission"): return sql("SELECT amount FROM wallet_entries WHERE kind=? AND ref_type='order' AND ref_id=?", k, oid)
def to_arrived(oid, fee):
    s, r = call("POST", f"/courier/orders/{oid}/accept", None, cu)
    if fee is not None:
        ok(f"propose {fee}", call("POST", f"/courier/orders/{oid}/fare", {"fee": fee}, cu)[0] == 200); ar = call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": fee}, cust); ok("customer approves " + str(ar), ar[0] == 200)
    for to in ("heading_pickup", "picked_up", "heading_customer", "arrived"): ok("to " + to, call("POST", f"/courier/orders/{oid}/status", {"to": to}, cu)[0] == 200)
def arrive_done(oid): return call("POST", f"/courier/orders/{oid}/status", {"to": "awaiting_confirmation"}, cu)

# ---- 1) طلب بلا منطقة
s, r = order(); ok("order without region_id and without offer -> 201", s == 201)
o1 = r["id"]; reg = sql("SELECT region_id,fee FROM delivery_orders WHERE id=?", o1)[0]
ok("internal region = Riyad markaz, no default fee (0)", reg == (3, 0))
ok("region_id from client is ignored if invalid", order(region_id=999999)[0] == 201)
ok("GPS coordinates stored", order(dropoff_lat=31.31, dropoff_lng=30.92)[0] == 201 and sql("SELECT COUNT(*) FROM delivery_orders WHERE dropoff_lat=31.31")[0][0] == 1)
for (i,) in sql("SELECT id FROM delivery_orders"): call("POST", f"/delivery/orders/{i}/cancel", {}, cust)
# مندوب مسجّل على مستوى منطقة (فرعية) يرى الطلب
Z = [r for r in call("GET", "/regions?parent_id=3")[1]][0]["id"]
cz, zid = user("01028000003"); apply_docs(call, cz); call("POST", f"/admin/couriers/{zid}/review", {"status": "approved"}, at)
sql("UPDATE couriers SET region_id=? WHERE user_id=?", Z, zid); call("POST", "/courier/topups", {"amount": 200, "transfer_ref": "REFZ28"}, cz)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
call("POST", "/courier/online", {"online": True}, cz)
s, r = order(offer_fee=20); oz = r["id"]
ok("zone-level courier sees the region-less order", oz in [o["id"] for o in call("GET", "/courier/available", None, cz)[1]])
call("POST", f"/delivery/orders/{oz}/cancel", {}, cust)

# ---- 2) قيمة ثابتة 4: كل مسارات الإغلاق
setc("fixed", 4)
def scenario(name, closer, fee=15):
    s, r = order(offer_fee=fee); oid = r["id"]; b0 = wal()
    to_arrived(oid, None)
    w = wal(); ok(name + ": reserved only before delivery (balance unchanged, held 4)", w["balance"] == b0["balance"] and w["held"] == 4 and w["available"] == b0["balance"] - 4 and not rows(oid))
    ok(name + ": arrive -> awaiting_confirmation", arrive_done(oid)[0] == 200)
    w = wal(); ok(name + ": commission charged ONCE at delivery", rows(oid) == [(-4,)])
    ok(name + ": balance dropped by 4 and held back to 0 (no double count)", w["balance"] == b0["balance"] - 4 and w["held"] == 0 and w["available"] == w["balance"])
    closer(oid); ok(name + ": closed (completed)", sql("SELECT status FROM delivery_orders WHERE id=?", oid)[0][0] == "completed")
    ok(name + ": still ONE commission row, balance unchanged by closing", rows(oid) == [(-4,)] and wal()["balance"] == b0["balance"] - 4)
    return oid
scenario("customer confirm", lambda oid: call("POST", f"/delivery/orders/{oid}/confirm", {}, cust))
def otp(oid): ok("otp ok", call("POST", f"/courier/orders/{oid}/handover", {"code": sql("SELECT delivery_code FROM delivery_orders WHERE id=?", oid)[0][0]}, cu)[0] == 200)
scenario("otp code", otp)
scenario("admin complete", lambda oid: ok("admin", call("POST", f"/admin/orders/{oid}/complete", {"reason": "اختبار"}, at)[0] == 200))
def auto(oid): sql("UPDATE delivery_orders SET updated_at=? WHERE id=?", int(time.time()) - 25 * 3600, oid); call("GET", "/delivery/orders", None, cust)
scenario("auto confirm 24h", auto)

# ---- 3) نسبة 10%
setc("percent", 10)
oid = scenario("percent 10% of 80", lambda oid: call("POST", f"/delivery/orders/{oid}/confirm", {}, cust), fee=80) if False else None
s, r = order(offer_fee=80); oid = r["id"]; b0 = wal()["balance"]; to_arrived(oid, None); arrive_done(oid)
ok("percent: 8 charged at delivery", rows(oid) == [(-8.0,)] and wal()["balance"] == b0 - 8)
call("POST", f"/delivery/orders/{oid}/confirm", {}, cust); ok("percent: no double on confirm", rows(oid) == [(-8.0,)])
# نسبة بلا أجرة عميل: العمولة تُحسب عند اقتراح المندوب
s, r = order(); oid = r["id"]; b0 = wal()["balance"]; to_arrived(oid, 50); arrive_done(oid)
ok("percent after courier fare 50: 5 charged", rows(oid) == [(-5.0,)] and wal()["balance"] == b0 - 5)
call("POST", f"/delivery/orders/{oid}/confirm", {}, cust)

# ---- 4) العكس
setc("fixed", 4)
s, r = order(offer_fee=15); od = r["id"]; b0 = wal()["balance"]; to_arrived(od, None); arrive_done(od)
ok("reverse needs reason", call("POST", f"/admin/orders/{od}/reverse-commission", {}, at)[0] == 400)
ok("customer disputes after charge", call("POST", f"/delivery/orders/{od}/dispute", {"reason": "لم أستلم"}, cust)[0] == 200)
ok("reverse on DISPUTED order works", call("POST", f"/admin/orders/{od}/reverse-commission", {"reason": "نزاع"}, at) == (200, {"reversed": 4}))
ok("wallet restored", wal()["balance"] == b0 and rows(od, "reversal") == [(4,)])
ok("second reverse refused (409)", call("POST", f"/admin/orders/{od}/reverse-commission", {"reason": "تاني"}, at)[0] == 409)
ok("admin completes after reversal: NOT charged again", call("POST", f"/admin/orders/{od}/complete", {"reason": "اختبار"}, at)[0] == 200 and wal()["balance"] == b0)
s, r = order(offer_fee=15); oa = r["id"]; b0 = wal()["balance"]; to_arrived(oa, None); arrive_done(oa)
ok("reverse on awaiting_confirmation works", call("POST", f"/admin/orders/{oa}/reverse-commission", {"reason": "خطأ"}, at)[0] == 200 and wal()["balance"] == b0)
call("POST", f"/delivery/orders/{oa}/confirm", {}, cust); ok("closing after reverse does not recharge", wal()["balance"] == b0 and len(rows(oa)) == 1)
s, r = order(offer_fee=15); oc = r["id"]; b0 = wal()["balance"]; to_arrived(oc, None); arrive_done(oc)
ok("admin cancels awaiting order", call("POST", f"/admin/orders/{oc}/cancel", {}, at)[0] == 200)
ok("admin cancel auto-reverses the charge once", wal()["balance"] == b0 and rows(oc, "reversal") == [(4,)])
ok("manual reverse on already-reversed cancelled order -> 409", call("POST", f"/admin/orders/{oc}/reverse-commission", {"reason": "إلغاء"}, at)[0] == 409 and wal()["balance"] == b0)
# إلغاء من المندوب/العميل قبل التسليم لا يمس العمولة (لم تُخصم)
s, r = order(offer_fee=15); on = r["id"]
ok("reverse with no charge -> 409", call("POST", f"/admin/orders/{on}/reverse-commission", {"reason": "اختبار"}, at)[0] == 409)
call("POST", f"/delivery/orders/{on}/cancel", {}, cust)

# ---- 5) المحفظة: متاح ومحجوز لطلب جارٍ
s, r = order(offer_fee=15); op = r["id"]; w0 = wal(); call("POST", f"/courier/orders/{op}/accept", None, cu); w1 = wal()
ok("in-progress order: balance same, held 4, available = balance-4", w1["balance"] == w0["balance"] and w1["held"] == 4 and w1["available"] == w0["balance"] - 4)
ok("admin courier wallet agrees", call("GET", f"/admin/couriers/{uid}/wallet", None, at)[1]["available_balance"] == w1["available"])
print("ALL PASS")
