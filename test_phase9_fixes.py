import os, json, threading, urllib.request, urllib.error, tempfile, time, base64, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import fare_ok
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8775), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8775/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); b = x.read(); return x.status, (json.loads(b) if b[:1] in b"{[" else b)
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
uid = lambda t: call("GET", "/me", None, t)[1]["id"]
cr, cust = user("01011111111"), user("01012345678")
apply_docs(call, cr); call("POST", f"/admin/couriers/{uid(cr)}/review", {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "REF0001"}, cr); call("POST", f"/admin/topups/{call('GET', '/admin/topups', None, at)[1][0]['id']}/review", {"status": "approved"}, at)
own = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cr)[1]["id"]
ok("courier's own order hidden from available list", call("GET", "/courier/available", None, cr)[1] == [])
ok("courier cannot accept own order", call("POST", f"/courier/orders/{own}/accept", None, cr)[0] == 403)
ok("own order still searching", call("GET", "/delivery/orders", None, cr)[1][0]["status"] == "searching")
other = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cust)[1]["id"]
ok("courier still sees and accepts others' orders", len(call("GET", "/courier/available", None, cr)[1]) == 1 and call("POST", f"/courier/orders/{other}/accept", None, cr)[0] == 200)
fare_ok(other)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{other}/status", {"to": to}, cr)
call("POST", f"/delivery/orders/{other}/confirm", None, cust); call("POST", f"/delivery/orders/{other}/confirm", None, cust)
ok("commission charged exactly once", sqlite3.connect(os.environ["LAQINO_DB"]).execute("select count(*),sum(amount) from wallet_entries where kind='commission'").fetchone() == (1, -5.0))
for p in ("/listings?limit=abc", "/listings?offset=x", "/medical/search?q=ab&region_id=abc"): ok("400 not 500: " + p, call("GET", p)[0] == 400)
ok("valid limit still works", call("GET", "/listings?limit=5&offset=0")[0] == 200 and call("GET", "/medical/search?q=ab&region_id=3")[0] == 200)
png = __import__("imgutil").png(); fid = call("POST", "/files", {"data": png}, cust)[1]["id"]
audits = lambda: sqlite3.connect(os.environ["LAQINO_DB"]).execute("select count(*) from audit_log where action='file.read'").fetchone()[0]
call("GET", f"/files/{fid}", None, cust); ok("owner read not audited", audits() == 0)
call("GET", f"/files/{fid}", None, at); ok("admin read audited", audits() == 1)
ok("failed read (stranger) not audited as read", call("GET", f"/files/{fid}", None, cr)[0] == 404 and audits() == 1)
t2 = call("POST", "/login", {"phone": "01012345678", "password": "password1"})[1]["token"]
ok("session works before logout", call("GET", "/me", None, t2)[0] == 200)
ok("logout ok", call("POST", "/logout", {}, t2)[0] == 200)
ok("session dead after logout", call("GET", "/me", None, t2)[0] == 401)
ok("other session of same user unaffected", call("GET", "/me", None, cust)[0] == 200)
ok("logout needs auth", call("POST", "/logout", {})[0] == 401)
codes = [call("POST", "/login", {"phone": "01011111111", "password": "bad%d" % i})[0] for i in range(7)]
ok("5 wrong logins -> 401 then 429", codes == [401] * 5 + [429] * 2)
ok("correct password blocked while throttled", call("POST", "/login", {"phone": "01011111111", "password": "password1"})[0] == 429)
ok("other phone unaffected", call("POST", "/login", {"phone": "01012345678", "password": "password1"})[0] == 200)
ok("success resets counter for others", (call("POST", "/login", {"phone": "01099999999", "password": "x"})[0] == 401))
server.throttle_clear()
ok("after window/reset, correct login works", call("POST", "/login", {"phone": "01011111111", "password": "password1"})[0] == 200)
print("ALL PASSED")
