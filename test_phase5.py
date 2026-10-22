import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from testutil import fare_ok
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8770), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8770/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cust, other, cr = user("01012345678"), user("01099999999"), user("01011111111")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at)
ok("customer cannot set commission", call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 8}, cust)[0] == 403)
ok("bad commission rejected", call("POST", "/admin/settings", {"commission_type": "percent", "commission_value": 150}, at)[0] == 400)
ok("admin sets fixed commission 8", call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 8}, at)[0] == 200)
apply_docs(call, cr); me = call("GET", "/me", None, cr)[1]["id"]; call("POST", f"/admin/couriers/{me}/review", {"status": "approved"}, at)
order = {"region_id": 3, "pickup_text": "صيدلية الأمل", "dropoff_text": "شارع النيل بيت 5"}
o1 = call("POST", "/delivery/orders", order, cust)[1]["id"]
call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 15}, at)
o2 = call("POST", "/delivery/orders", order, cust)[1]["id"]
ok("stats empty => null, not invented", (lambda s: s["completion_rate"] is None and s["rating_avg"] is None and s["avg_accept_seconds"] is None)(call("GET", "/courier/stats", None, cr)[1]))
ok("accept blocked with zero balance", call("POST", f"/courier/orders/{o1}/accept", None, cr)[0] == 402)
st, t1 = call("POST", "/courier/topups", {"amount": 20, "transfer_ref": "VC-1001"}, cr)
ok("topup request pending, balance unchanged", st == 201 and call("GET", "/courier/wallet", None, cr)[1]["balance"] == 0)
ok("duplicate transfer ref rejected", call("POST", "/courier/topups", {"amount": 20, "transfer_ref": "VC-1001"}, cr)[0] == 409)
ok("customer cannot approve topup", call("POST", f"/admin/topups/{t1['id']}/review", {"status": "approved"}, other)[0] == 403)
ok("admin approves", call("POST", f"/admin/topups/{t1['id']}/review", {"status": "approved"}, at)[0] == 200)
ok("double approve rejected, credited once", call("POST", f"/admin/topups/{t1['id']}/review", {"status": "approved"}, at)[0] == 409 and call("GET", "/courier/wallet", None, cr)[1]["balance"] == 20)
t2 = call("POST", "/courier/topups", {"amount": 50, "transfer_ref": "VC-1002"}, cr)[1]["id"]
ok("reject needs reason", call("POST", f"/admin/topups/{t2}/review", {"status": "rejected"}, at)[0] == 400)
call("POST", f"/admin/topups/{t2}/review", {"status": "rejected", "reason": "لم يصل التحويل"}, at)
ok("rejected adds nothing", call("GET", "/courier/wallet", None, cr)[1]["balance"] == 20)
ok("old order keeps old commission (8) — accepts", call("POST", f"/courier/orders/{o1}/accept", None, cr)[0] == 200)
ok("reserved balance blocks 2nd order (needs 15, only 12 free)", call("POST", f"/courier/orders/{o2}/accept", None, cr)[0] == 402)
fare_ok(o1)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{o1}/status", {"to": to}, cr)
ok("commission already charged at delivery (phase 28), before customer confirms", call("GET", "/courier/wallet", None, cr)[1]["balance"] == 12)
call("POST", f"/delivery/orders/{o1}/confirm", None, cust)
call("POST", f"/delivery/orders/{o1}/confirm", None, cust)
w = call("GET", "/courier/wallet", None, cr)[1]
ok("commission charged exactly once (20-8=12)", w["balance"] == 12 and sum(1 for e in w["entries"] if e["kind"] == "commission") == 1)
ok("customer cannot rate unfinished/other order", call("POST", f"/delivery/orders/{o2}/rate", {"stars": 5}, cust)[0] == 404 and call("POST", f"/delivery/orders/{o1}/rate", {"stars": 5}, other)[0] == 404)
ok("bad stars rejected", call("POST", f"/delivery/orders/{o1}/rate", {"stars": 9}, cust)[0] == 400)
ok("customer rates", call("POST", f"/delivery/orders/{o1}/rate", {"stars": 4, "comment": "ممتاز"}, cust)[0] == 201)
ok("cannot rate twice", call("POST", f"/delivery/orders/{o1}/rate", {"stars": 1}, cust)[0] == 409)
st_ = call("GET", "/courier/stats", None, cr)[1]
ok("stats computed from real data", st_["accepted"] == 1 and st_["completed"] == 1 and st_["completion_rate"] == 1.0 and st_["rating_avg"] == 4.0 and st_["rating_count"] == 1 and st_["avg_accept_seconds"] is not None)
ok("ratings list hides customer identity", "customer" not in json.dumps(call("GET", "/courier/ratings", None, cr)[1]))
apply_docs(call, other)
ok("non-courier cannot read wallet", call("GET", "/courier/wallet", None, other)[0] == 403)
t3 = call("POST", "/courier/topups", {"amount": 30, "transfer_ref": "VC-1003"}, cr)[1]["id"]; call("POST", f"/admin/topups/{t3}/review", {"status": "approved"}, at)
ok("accepts o2 once balance suffices", call("POST", f"/courier/orders/{o2}/accept", None, cr)[0] == 200)
call("POST", f"/delivery/orders/{o2}/cancel", None, cust)
w2 = call("GET", "/courier/wallet", None, cr)[1]
ok("cancel after assign charges no commission", w2["balance"] == 42 and sum(1 for e in w2["entries"] if e["kind"] == "commission") == 1)
print("ALL PASSED")
