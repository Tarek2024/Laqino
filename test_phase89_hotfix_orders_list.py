"""إصلاح phase-89: GET /api/delivery/orders لا ينهار (KeyError items_total) لطلب دليفري عادي بعد اقتراح الأجرة."""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.abspath(__file__))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
_T = tempfile.mkdtemp(prefix="lq89-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
sys.path.insert(0, ROOT)
import server, testutil
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
Z1 = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}["فرج الكبرى / الكوم"]
cust, cid = user("01044440001", "عميل"); c1, u1 = user("01044440002", "المندوب أحمد")
testutil.apply_docs(call, c1); call("POST", f"/admin/couriers/{u1}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF0001"}, c1)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
call("POST", "/courier/online", {"online": True}, c1)
oid = call("POST", "/delivery/orders", {"region_id": Z1, "pickup_text": "مخبز النور", "dropoff_text": "شارع المدرسة"}, cust)[1]["id"]
s, rows = call("GET", "/delivery/orders", None, cust); ok("searching: 200", s == 200 and rows[0]["status"] == "searching")
call("POST", f"/courier/orders/{oid}/accept", None, c1)
s, rows = call("GET", "/delivery/orders", None, cust); ok("assigned (no fee yet): 200", s == 200)
call("POST", f"/courier/orders/{oid}/fare", {"fee": 18}, c1)
s, rows = call("GET", "/delivery/orders", None, cust)
ok("fare proposed: 200 (كان 500 قبل الإصلاح)", s == 200 and rows[0]["fee"] == 18 and rows[0]["courier_name"])
ok("plain order carries no shop fields", all(k not in rows[0] for k in ("items_total", "shop_status", "shop_items", "place_kind")) and "grand_total" not in rows[0])
s, _ = call("POST", f"/delivery/orders/{oid}/fare/approve", {"fee": 18}, cust); ok("approve fare", s == 200)
s, rows = call("GET", "/delivery/orders", None, cust); ok("approved (active): 200", s == 200 and rows[0]["fare_status"] == "approved")
print("ALL PASSED")
