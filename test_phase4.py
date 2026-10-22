import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from testutil import apply_docs, fare_ok, server_fee
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8769), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8769/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cust, other = user("01012345678"), user("01099999999")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
order = {"region_id": 3, "pickup_text": "صيدلية الأمل", "dropoff_text": "شارع النيل بيت 5", "details": "علبة صغيرة"}
s0, r0 = call("POST", "/delivery/orders", order, cust)  # المرحلة 28: لا شرط سعر منطقة
ok("no fee configured => order still accepted (phase 28)", s0 == 201); call("POST", f"/delivery/orders/{r0['id']}/cancel", {}, cust)
ok("customer cannot set fees", call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, cust)[0] == 403)
ok("admin sets fee", call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at)[0] == 200)
st, o = call("POST", "/delivery/orders", {**order, "fee": 1}, cust)
ok("order created; price is not exposed to the customer (default comes from server config)", st == 201 and "fee" not in o and server_fee(o["id"]) == 0)  # المرحلة 28: لا أجرة افتراضية؛ fee من العميل يُتجاهل
oid = o["id"]
couriers = [user("0101111111%d" % i) for i in range(6)]
uid = lambda t: call("GET", "/me", None, t)[1]["id"]
ok("unapproved courier blocked", call("GET", "/courier/available", None, couriers[0])[0] == 403)
for t in couriers:
    apply_docs(call, t); call("POST", f"/admin/couriers/{uid(t)}/review", {"status": "approved"}, at)
ok("customer cannot approve couriers", call("POST", f"/admin/couriers/{uid(couriers[0])}/review", {"status": "approved"}, other)[0] == 403)
ok("order visible to courier w/o addresses", (lambda r: len(r) == 1 and "pickup_text" not in r[0] and "dropoff_text" not in r[0])(call("GET", "/courier/available", None, couriers[0])[1]))
res, bar = [], threading.Barrier(6)
def go(t): bar.wait(); res.append(call("POST", f"/courier/orders/{oid}/accept", None, t)[0])
th = [threading.Thread(target=go, args=(t,)) for t in couriers]; [x.start() for x in th]; [x.join() for x in th]
ok("exactly one courier wins concurrent accept", sorted(res) == [200] + [409] * 5)
winner = next(t for t in couriers if call("GET", "/courier/orders", None, t)[1])
ok("winner sees addresses", call("GET", "/courier/orders", None, winner)[1][0]["dropoff_text"] == order["dropoff_text"])
loser = next(t for t in couriers if t != winner)
ok("loser cannot move order", call("POST", f"/courier/orders/{oid}/status", {"to": "heading_pickup"}, loser)[0] == 404)
ok("cannot skip states", call("POST", f"/courier/orders/{oid}/status", {"to": "picked_up"}, winner)[0] == 409)
fare_ok(oid)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"):
    ok("courier -> " + to, call("POST", f"/courier/orders/{oid}/status", {"to": to}, winner)[0] == 200)
ok("courier cannot confirm for customer", call("POST", f"/delivery/orders/{oid}/confirm", None, winner)[0] == 404)
ok("other customer cannot confirm", call("POST", f"/delivery/orders/{oid}/confirm", None, other)[0] == 404)
ok("customer confirms", call("POST", f"/delivery/orders/{oid}/confirm", None, cust)[1]["status"] == "completed")
ok("cannot confirm twice", call("POST", f"/delivery/orders/{oid}/confirm", None, cust)[0] == 409)
o2 = call("POST", "/delivery/orders", order, cust)[1]["id"]
call("POST", f"/courier/orders/{o2}/accept", None, couriers[1])
ok("courier releases before pickup", call("POST", f"/courier/orders/{o2}/release", None, couriers[1])[1]["status"] == "searching")
ok("order back in available list", len(call("GET", "/courier/available", None, couriers[2])[1]) == 1)
call("POST", f"/courier/orders/{o2}/accept", None, couriers[2])
ok("customer cancels assigned order", call("POST", f"/delivery/orders/{o2}/cancel", None, cust)[1]["status"] == "cancelled")
ok("cancelled not re-offered", call("GET", "/courier/available", None, couriers[3])[1] == [])
print("ALL PASSED")
