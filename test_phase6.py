import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8771), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request("http://127.0.0.1:8771" + ("" if raw else "/api") + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, (x.read().decode() if raw else json.loads(x.read()))
    except urllib.error.HTTPError as e: return e.code, (e.read().decode() if raw else json.loads(e.read()))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
call("POST", "/register", {"phone": "01012345678", "name": "<b>x</b>", "password": "password1"})
ct = call("POST", "/login", {"phone": "01012345678", "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
ok("admin page served", call("GET", "/admin.html", raw=True)[0] == 200 and "إدارة لاقينو" in call("GET", "/admin.html", raw=True)[1])
ok("settings endpoint admin-only", call("GET", "/admin/settings", None, ct)[0] == 403 and call("GET", "/admin/settings")[0] == 401)
ok("orders endpoint admin-only", call("GET", "/admin/orders", None, ct)[0] == 403)
ok("admin reads disabled RX defaults and the 10 seeded Riyad zones", (lambda r: r["settings"].get("rx_claim_mode") == "0" and r["settings"].get("rx_routing_mode") == "direct" and r["settings"].get("rx_claim_timeout_minutes") == "10" and r["settings"].get("rx_total_timeout_minutes") == "60" and len(r["fees"]) == 10)(call("GET", "/admin/settings", None, at)[1]))
call("POST", "/admin/settings", {"commission_type": "percent", "commission_value": 10}, at); call("POST", "/admin/region-fees", {"region_id": 3, "fee": 50}, at)
st = call("GET", "/admin/settings", None, at)[1]
ok("settings reflect saved values", st["settings"]["commission_type"] == "percent" and st["fees"][0]["fee"] == 50)
o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "أ أ أ", "dropoff_text": "ب ب ب"}, ct)[1]
ok("phase 28: no default price => percent commission is 0 until a fare exists", call("GET", "/admin/orders", None, at)[1][0]["commission"] == 0.0)
ok("admin sees tricky customer name raw (page escapes it)", call("GET", "/admin/orders", None, at)[1][0]["customer"] == "<b>x</b>")
ok("admin lists regions incl. inactive", len(call("GET", "/regions?all=1&parent_id=2", None, at)[1]) == 1)
print("ALL PASSED")
