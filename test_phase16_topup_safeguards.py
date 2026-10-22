# المرحلة 16 / المهمة 2: حد لطلبات الشحن المعلّقة + سقف ساعي + تعليمات التحويل (يضبطها الأدمن ويراها المندوب).
import os, json, threading, urllib.request, urllib.error, tempfile, time, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8777), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8777/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cust, cr, cr2 = user("01012345678"), user("01011111111"), user("01022222222")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
for t in (cr, cr2): apply_docs(call, t); call("POST", f"/admin/couriers/{call('GET','/me',None,t)[1]['id']}/review", {"status": "approved"}, at)
TS = "/admin/topup-settings"; top = lambda ref, t=cr, amt=50: call("POST", "/courier/topups", {"amount": amt, "transfer_ref": ref}, t)
ok("defaults: no instructions, cap 3", call("GET", TS, None, at)[1] == {"instructions": "", "max_pending": 3})
ok("courier wallet shows empty instructions (nothing invented)", call("GET", "/courier/wallet", None, cr)[1]["topup_instructions"] == "")
ok("non-admin cannot read/write settings", all(call(m, TS, {} if m == "POST" else None, t)[0] == 403 for t in (cust, cr) for m in ("GET", "POST")) and call("GET", TS)[0] == 401)
ok("instructions saved + visible to courier", call("POST", TS, {"instructions": "  حوّل على المحفظة المحددة من الإدارة  "}, at)[0] == 200 and call("GET", "/courier/wallet", None, cr)[1]["topup_instructions"] == "حوّل على المحفظة المحددة من الإدارة")
ok("instructions over 500 chars rejected", call("POST", TS, {"instructions": "x" * 501}, at)[0] == 400)
ok("max_pending bounds enforced", all(call("POST", TS, {"max_pending": v}, at)[0] == 400 for v in (0, 21, "a", None)))
ok("first 3 pending accepted", all(top("PD-000%d" % i)[0] == 201 for i in range(1, 4)))
r = top("PD-0004"); ok("4th pending blocked with 429", r[0] == 429)
ok("cap is per courier (other courier unaffected)", top("PD-0005", cr2)[0] == 201)
ok("validation (400) still takes precedence", top("ab")[0] == 400)
tid = call("GET", "/courier/wallet", None, cr)[1]["topups"][0]["id"]
call("POST", f"/admin/topups/{tid}/review", {"status": "rejected", "reason": "no transfer"}, at)
ok("after review a slot frees up", top("PD-0006")[0] == 201)
ok("admin lowers cap to 1 => blocked at once", call("POST", TS, {"max_pending": 1}, at)[0] == 200 and top("PD-0007")[0] == 429)
ok("approving keeps wallet idempotent/unaffected by cap", all(call("POST", f"/admin/topups/{t['id']}/review", {"status": "approved"}, at)[0] == 200 for t in call("GET", "/courier/wallet", None, cr)[1]["topups"] if t["status"] == "pending") and call("GET", "/courier/wallet", None, cr)[1]["balance"] == 150)
call("POST", TS, {"max_pending": 20}, at); server.throttle_clear()
n = 0
for i in range(30):
    r = top("HR-%04d" % i, cr2, 1)
    if r[0] == 429: break
    n += 1; call("POST", f"/admin/topups/{r[1]['id']}/review", {"status": "approved"}, at)
ok("hourly throttle stops flooding (<=10 attempts/hour)", r[0] == 429 and n <= 10)
ok("setting changes are audited", any(x["action"] == "settings.topup" for x in call("GET", "/admin/audit", None, at)[1]))
d = os.path.dirname(os.path.abspath(__file__)); rd = lambda *p: open(os.path.join(d, *p), encoding="utf-8").read()
ok("courier page shows instructions via esc()", "w.topup_instructions" in rd("static", "courier.html") and "esc(w.topup_instructions)" in rd("static", "courier.html"))
ok("admin topups tab has settings form", "/admin/topup-settings" in rd("static", "admin.html") and "esc(ts.instructions)" in rd("static", "admin.html"))
ok("service worker version >=v20", int(re.search(r"laqino-v(\d+)", rd("static", "sw.js")).group(1)) >= 20)
print("ALL OK")
