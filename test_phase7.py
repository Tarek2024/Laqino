import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8772), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8772/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cust, cr, cr2 = user("01012345678"), user("01011111111"), user("01022222222")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
uid = lambda t: call("GET", "/me", None, t)[1]["id"]
ok("reports empty => zeros, no invented data", (lambda r: r["orders_by_status"] == [] and r["completed_fees"] == 0 and r["commission_collected"] == 0 and r["completed_by_region"] == [])(call("GET", "/admin/reports", None, at)[1]))
ok("customer blocked from users/reports/audit", all(call("GET", p, None, cust)[0] == 403 for p in ("/admin/users", "/admin/reports", "/admin/audit")))
ok("admin lists users", len(call("GET", "/admin/users", None, at)[1]) == 4)
ok("search users", len(call("GET", "/admin/users?q=0101111", None, at)[1]) == 1)
ok("admin sets role staff", call("POST", f"/admin/users/{uid(cust)}/role", {"role": "staff"}, at)[0] == 200 and call("GET", "/me", None, cust)[1]["role"] == "staff")
ok("cannot grant admin or courier by role API", call("POST", f"/admin/users/{uid(cr)}/role", {"role": "admin"}, at)[0] == 400 and call("POST", f"/admin/users/{uid(cr)}/role", {"role": "courier"}, at)[0] == 400)
ok("cannot change own/admin role", call("POST", "/admin/users/1/role", {"role": "customer"}, at)[0] == 409)
ok("staff cannot change roles", call("POST", f"/admin/users/{uid(cr)}/role", {"role": "seller"}, cust)[0] == 403)
call("POST", f"/admin/users/{uid(cust)}/role", {"role": "customer"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 8}, at)
for t in (cr, cr2):
    apply_docs(call, t); call("POST", f"/admin/couriers/{uid(t)}/review", {"status": "approved"}, at)
    k = call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "VC-" + str(uid(t)) + "00"}, t)[1]["id"]; call("POST", f"/admin/topups/{k}/review", {"status": "approved"}, at)
o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "أ أ أ", "dropoff_text": "ب ب ب"}, cust)[1]["id"]
call("POST", f"/courier/orders/{o}/accept", None, cr)
ok("customer cannot reassign", call("POST", f"/admin/orders/{o}/reassign", {}, cust)[0] == 403)
ok("admin reassigns assigned order", call("POST", f"/admin/orders/{o}/reassign", {}, at)[1]["status"] == "searching")
ok("first courier lost the order", call("GET", "/courier/orders", None, cr)[1] == [] and call("POST", f"/courier/orders/{o}/status", {"to": "heading_pickup"}, cr)[0] == 404)
ok("second courier accepts after reassign", call("POST", f"/courier/orders/{o}/accept", None, cr2)[0] == 200)
ok("admin cancels active order", call("POST", f"/admin/orders/{o}/cancel", {}, at)[1]["status"] == "cancelled")
ok("cannot cancel twice", call("POST", f"/admin/orders/{o}/cancel", {}, at)[0] == 409)
ok("cancel charged no commission", call("GET", "/courier/wallet", None, cr2)[1]["balance"] == 100)
call("POST", f"/admin/couriers/{uid(cr2)}/review", {"status": "suspended"}, at)
ok("suspended courier blocked", call("GET", "/courier/available", None, cr2)[0] == 403)
a = call("GET", "/admin/audit", None, at)[1]; acts = {x["action"] for x in a}
ok("audit records admin actions", {"order.reassign", "order.cancel", "user.role", "courier.suspended", "topup.approved"} <= acts)
r = call("GET", "/admin/reports", None, at)[1]
ok("reports computed from real data", r["topups_credited"] == 200 and any(x["status"] == "cancelled" and x["n"] == 1 for x in r["orders_by_status"]))
print("ALL PASSED")
