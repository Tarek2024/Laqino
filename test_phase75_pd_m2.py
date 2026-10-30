# phase-75 / م2 «دفتر الصيدلية»: مراحل المندوب حتى التسليم + الأوقات + «تم التسليم» اليدوي من الصيدلية + حد التأخير
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, provider_delivery
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8975; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
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
cust, cid = user("01070000001"); ph, pid = user("01070000002"); ph2, pid2 = user("01070000003"); c1, u1 = user("01070000004"); c2, u2 = user("01070000005")
for t, i, n in ((ph, pid, "صيدلية النور"), (ph2, pid2, "صيدلية الأمل")):
    call("POST", "/providers/apply", {"name_ar": n, "region_id": Z2, "address": "شارع البحر"}, t); call("POST", f"/admin/providers/{i}/review", {"status": "approved"}, at)
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 0}, at)
mk = lambda t=ph, **x: call("POST", "/provider/delivery-request", x, t)
cord = lambda t, oid: ([o for o in call("GET", "/courier/orders", None, t)[1] if o["id"] == oid] or [None])[0]
mine = lambda oid, t=ph: ([o for o in call("GET", "/provider/delivery-requests", None, t)[1]["items"] if o["id"] == oid] or [None])[0]


cs = lambda t, oid, to: call("POST", f"/courier/orders/{oid}/status", {"to": to}, t)
bal = lambda u: sql("SELECT COALESCE(SUM(amount),0) FROM wallet_entries WHERE user_id=?", u)[0][0]
call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 7, "late_minutes": 30}, at)
ok("admin returns late_minutes", call("GET", "/admin/provider-delivery", None, at)[1]["late_minutes"] == 30)
ok("bad late_minutes rejected", call("POST", "/admin/provider-delivery", {"enabled": True, "late_minutes": -3}, at)[0] == 400)

# 1) دورة كاملة بيد المندوب + العمولة مرة واحدة عند الاستلام من الصيدلية
oid = mk(request_key="m2a", customer_phone="01001234567", price=50)[1]["id"]
ok("accept", call("POST", f"/courier/orders/{oid}/accept", {}, c1)[0] == 200)
b0 = bal(u1)
ok("cannot skip stages", cs(c1, oid, "heading_customer")[0] == 409 and cs(c1, oid, "completed")[0] == 409)
ok("to pharmacy", cs(c1, oid, "heading_pickup")[0] == 200 and bal(u1) == b0)
ok("picked up charges commission once", cs(c1, oid, "picked_up")[0] == 200 and bal(u1) == b0 - 7)
ok("pharmacy sees picked_up", mine(oid)["status"] == "picked_up" and mine(oid)["picked_at"] is not None)
ok("cannot release after pickup", call("POST", f"/courier/orders/{oid}/release", {}, c1)[0] == 409)
ok("pharmacy cannot cancel after pickup", call("POST", f"/delivery/orders/{oid}/cancel", {}, ph)[0] == 409)
ok("to customer", cs(c1, oid, "heading_customer")[0] == 200 and cord(c1, oid)["pd_cust_phone"] == "01001234567")
ok("delivered", cs(c1, oid, "completed")[0] == 200 and bal(u1) == b0 - 7)
o = mine(oid)
ok("timings present", o["status"] == "completed" and o["delivered_at"] and o["picked_at"] and o["total_secs"] is not None and o["delivered_by"] == "courier" and o["legacy"] is False)
ok("courier loses details after delivery", "pd_cust_phone" not in cord(c1, oid))

# 2) «تم التسليم» اليدوي من الصيدلية
oid2 = mk(request_key="m2b")[1]["id"]; call("POST", f"/courier/orders/{oid2}/accept", {}, c2); cs(c2, oid2, "heading_pickup")
ok("manual delivered rejected before pickup", call("POST", f"/provider/delivery-requests/{oid2}/delivered", {}, ph)[0] == 409)
cs(c2, oid2, "picked_up")
ok("other pharmacy cannot confirm", call("POST", f"/provider/delivery-requests/{oid2}/delivered", {}, ph2)[0] == 404)
ok("pharmacy confirms delivery", call("POST", f"/provider/delivery-requests/{oid2}/delivered", {}, ph)[1]["status"] == "completed")
ok("marked as delivered by pharmacy", mine(oid2)["delivered_by"] == "pharmacy")
ok("no second commission", sql("SELECT COUNT(*) FROM wallet_entries WHERE kind='commission' AND ref_id=?", oid2)[0][0] == 1)
ok("courier cannot advance a closed order", cs(c2, oid2, "heading_customer")[0] == 409)

# 3) تأخير وسرعة: نُحرّك أوقات الأحداث مباشرة
oid3 = mk(request_key="m2c")[1]["id"]; call("POST", f"/courier/orders/{oid3}/accept", {}, c1)
for t in ("heading_pickup", "picked_up"): cs(c1, oid3, t)
sql("UPDATE order_events SET at=at-3600 WHERE order_id=? AND to_status IN('assigned','heading_pickup','picked_up')", oid3)
ok("active order past limit is late", mine(oid3)["late"] is True)
cs(c1, oid3, "heading_customer"); cs(c1, oid3, "completed")
ok("hour-long delivery leg is late, not fast", mine(oid3)["late"] is True and mine(oid3)["fast"] is False)
oid4 = mk(request_key="m2d")[1]["id"]; call("POST", f"/courier/orders/{oid4}/accept", {}, c1)
for t in ("heading_pickup", "picked_up", "heading_customer", "completed"): cs(c1, oid4, t)
ok("seconds-long delivery flagged fast", mine(oid4)["fast"] is True and mine(oid4)["late"] is False)

# 4) أوردر قديم (انتهى عند الاستلام قبل م2) يظل مفهومًا
now = int(time.time())
sql("INSERT INTO delivery_orders(id,customer_id,region_id,pickup_text,dropoff_text,fee,courier_id,status,created_at,updated_at,fare_status,origin_type) VALUES(9001,?,?,?,?,0,?,'completed',?,?,'approved','provider_pickup')", pid, Z2, "x", "", u1, now - 900, now - 600)
for f, t_, a_ in (("searching", "assigned", 800), ("assigned", "heading_pickup", 700), ("heading_pickup", "completed", 600)): sql("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(9001,?,?,?,?)", u1, f, t_, now - a_)
lg = mine(9001)
ok("legacy order keeps pickup time, no delivery", lg["legacy"] is True and lg["picked_at"] == now - 600 and lg["delivered_at"] is None)

# 5) سلسلة مراحل الصيدلية كما صُمّمت؛ والطلب العادي له دورته الأصلية (arrived/awaiting_confirmation) ولم تُمسّ
ok("pharmacy NEXT chain", provider_delivery.NEXT == {"assigned": "heading_pickup", "heading_pickup": "picked_up", "picked_up": "heading_customer", "heading_customer": "completed"})
ok("ordinary orders still hide pd_ keys", all(not k.startswith("pd_") for r_ in call("GET", "/courier/orders", None, c2)[1] if r_.get("origin_type") is None for k in r_))
print("ALL PASS")
