# المرحلة 11 / A-1: ترويسة CSP، واعتماد الشحن المتزامن لا يُضيف الرصيد أكثر من مرة.
import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8781), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
B = "http://127.0.0.1:8781"
def call(m, p, d=None, t=None):
    r = urllib.request.Request(B + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
# --- CSP على الصفحات والـ API والأخطاء
for path in ("/", "/admin.html", "/courier.html", "/pharmacy.html", "/api/regions", "/nope.html"):
    try: h = urllib.request.urlopen(B + path).headers
    except urllib.error.HTTPError as e: h = e.headers
    csp = h.get("Content-Security-Policy") or ""
    ok(f"CSP on {path}", "object-src 'none'" in csp and "frame-ancestors 'none'" in csp and "connect-src 'self'" in csp and "base-uri 'self'" in csp)
ok("CSP allows no foreign script host", "script-src 'self' 'unsafe-inline';" in csp and "http" not in csp.split("script-src")[1].split(";")[0])
# --- اعتماد الشحن المتزامن
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cr = user("01011111111"); at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
apply_docs(call, cr); me = call("GET", "/me", None, cr)[1]["id"]; call("POST", f"/admin/couriers/{me}/review", {"status": "approved"}, at)
tid = call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "VC-C1"}, cr)[1]["id"]
res = []
def go(): res.append(call("POST", f"/admin/topups/{tid}/review", {"status": "approved"}, at)[0])
ts = [threading.Thread(target=go) for _ in range(12)]; [t.start() for t in ts]; [t.join() for t in ts]
w = call("GET", "/courier/wallet", None, cr)[1]
ok("12 concurrent approvals: exactly one 200, rest 409", sorted(res) == [200] + [409] * 11)
ok("balance credited once (100)", w["balance"] == 100 and sum(1 for e in w["entries"] if e["kind"] == "topup") == 1)
# اعتماد ثم رفض متزامنين على طلب آخر: حالة نهائية واحدة فقط
t2 = call("POST", "/courier/topups", {"amount": 50, "transfer_ref": "VC-C2"}, cr)[1]["id"]
r2 = []
def a(): r2.append(("a", call("POST", f"/admin/topups/{t2}/review", {"status": "approved"}, at)[0]))
def b(): r2.append(("r", call("POST", f"/admin/topups/{t2}/review", {"status": "rejected", "reason": "x"}, at)[0]))
ts = [threading.Thread(target=f) for f in (a, b)]; [t.start() for t in ts]; [t.join() for t in ts]
w = call("GET", "/courier/wallet", None, cr)[1]; won = [k for k, c in r2 if c == 200]
ok("approve vs reject race: one winner, balance consistent", len(won) == 1 and w["balance"] == (150 if won == ["a"] else 100))
print("ALL PASSED")
