import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from testutil import fare_ok
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8773), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request("http://127.0.0.1:8773" + ("" if raw else "/api") + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, (x.read().decode("utf-8", "replace") if raw else json.loads(x.read()))
    except urllib.error.HTTPError as e: return e.code, (e.read().decode("utf-8", "replace") if raw else json.loads(e.read()))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cust, cr = user("01012345678"), user("01011111111")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
ok("home page serves, mascot and logo assets reachable", "لاقينو" in call("GET", "/", raw=True)[1] and call("GET", "/assets/mascot.jpg", raw=True)[0] == 200 and call("GET", "/assets/logo.jpg", raw=True)[0] == 200)
ok("fee null where delivery not configured", call("GET", "/delivery/fee?region_id=3")[1] == {"available": False})
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 35}, at)
ok("availability (no price) shown before ordering", call("GET", "/delivery/fee?region_id=3")[1] == {"available": True})
uid = call("GET", "/me", None, cr)[1]["id"]; apply_docs(call, cr); call("POST", f"/admin/couriers/{uid}/review", {"status": "approved"}, at)
o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "أ أ أ", "dropoff_text": "ب ب ب"}, cust)[1]["id"]
call("POST", f"/courier/orders/{o}/accept", None, cr)
fare_ok(o)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{o}/status", {"to": to}, cr)
call("POST", f"/delivery/orders/{o}/confirm", None, cust)
ok("order list says not rated yet", call("GET", "/delivery/orders", None, cust)[1][0]["rated"] == 0)
call("POST", f"/delivery/orders/{o}/rate", {"stars": 5}, cust)
ok("order list says rated after rating", call("GET", "/delivery/orders", None, cust)[1][0]["rated"] == 1)
print("ALL PASSED")
