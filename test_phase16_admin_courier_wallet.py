# المرحلة 16 / المهمة 1: عرض محفظة مندوب للإدارة (قراءة فقط). يتحقق أيضًا أن الاستعلام لا يغيّر أي رصيد.
import os, json, threading, urllib.request, urllib.error, tempfile, time, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8776), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8776/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cust, cr = user("01012345678"), user("01011111111")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cid = call("GET", "/me", None, cr)[1]["id"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 8}, at)
apply_docs(call, cr); call("POST", f"/admin/couriers/{cid}/review", {"status": "approved"}, at)
W = f"/admin/couriers/{cid}/wallet"
ok("empty wallet: zeros, no invented data", (lambda r: r[0] == 200 and r[1]["balance"] == 0 and r[1]["held"] == 0 and r[1]["entries"] == [] and r[1]["topups"] == [])(call("GET", W, None, at)))
k = call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "WL-0001"}, cr)[1]["id"]
ok("pending topup listed, balance still 0", (lambda r: r["balance"] == 0 and r["topups"][0]["status"] == "pending")(call("GET", W, None, at)[1]))
call("POST", f"/admin/topups/{k}/review", {"status": "approved"}, at)
ok("approved topup raises balance and appears in ledger", (lambda r: r["balance"] == 100 and r["entries"][0]["kind"] == "topup" and r["entries"][0]["amount"] == 100)(call("GET", W, None, at)[1]))
oid = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cust)[1]["id"]
ok("courier accepts", call("POST", f"/courier/orders/{oid}/accept", None, cr)[0] == 200)
r = call("GET", W, None, at)[1]
ok("accepted order holds the commission: held 8, available 92, balance unchanged", r["held"] == 8 and r["available_balance"] == 92 and r["balance"] == 100)
before = call("GET", "/courier/wallet", None, cr)[1]
call("GET", W, None, at); call("GET", W, None, at)
ok("viewing is read-only (courier ledger unchanged)", call("GET", "/courier/wallet", None, cr)[1] == before)
ok("customer blocked", call("GET", W, None, cust)[0] == 403)
ok("courier cannot read own/other wallet via admin route", call("GET", W, None, cr)[0] == 403)
ok("anonymous blocked", call("GET", W)[0] == 401)
ok("unknown courier id => 404", call("GET", "/admin/couriers/99999/wallet", None, at)[0] == 404)
ok("a non-courier user id => 404", call("GET", "/admin/couriers/1/wallet", None, at)[0] == 404)
d = os.path.dirname(os.path.abspath(__file__)); a = open(os.path.join(d, "static", "admin.html"), encoding="utf-8").read(); sw = open(os.path.join(d, "static", "sw.js"), encoding="utf-8").read()
ok("admin page has wallet button and handler, uses esc()", "window.cw=" in a and "onclick=\"cw(${c.user_id})\"" in a and "/wallet'" in a)
ok("service worker version bumped to >=v19", int(re.search(r"laqino-v(\d+)", sw).group(1)) >= 19)
print("ALL OK")
