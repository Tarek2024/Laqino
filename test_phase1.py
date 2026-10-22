import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8765), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8765/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
ok("register", call("POST", "/register", {"phone": "01012345678", "name": "عميل", "password": "password1"})[0] == 201)
ok("duplicate rejected", call("POST", "/register", {"phone": "01012345678", "name": "x", "password": "password1"})[0] == 409)
ok("bad login", call("POST", "/login", {"phone": "01012345678", "password": "wrong"})[0] == 401)
ct = call("POST", "/login", {"phone": "01012345678", "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
ok("customer cannot create region", call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "v1", "name_ar": "قرية"}, ct)[0] == 403)
ok("anonymous blocked", call("POST", "/admin/regions", {}, None)[0] == 401)
st, r = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "v1", "name_ar": "قرية تجريبية للاختبار", "is_active": False}, at)
ok("admin creates inactive region", st == 201)
ok("inactive hidden from public", all(x["id"] != r["id"] for x in call("GET", "/regions?parent_id=3")[1]))
ok("cannot pick inactive region", call("POST", "/me/region", {"region_id": r["id"]}, ct)[0] == 400)
ok("admin activates", call("POST", f"/admin/regions/{r['id']}/active", {"is_active": True}, at)[0] == 200)
ok("now visible", any(x["id"] == r["id"] for x in call("GET", "/regions?parent_id=3")[1]))
ok("customer saves region", call("POST", "/me/region", {"region_id": r["id"]}, ct)[0] == 200)
ok("region persisted", call("GET", "/me", None, ct)[1]["region_id"] == r["id"])
ok("role cannot be self-assigned", call("POST", "/register", {"phone": "01112345678", "name": "x", "password": "password1", "role": "admin"})[0] == 201 and call("GET", "/me", None, call("POST", "/login", {"phone": "01112345678", "password": "password1"})[1]["token"])[1]["role"] == "customer")
print("ALL PASSED")
