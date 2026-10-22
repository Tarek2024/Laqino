# المرحلة 16 / نظام حسابات المندوبين: دخول وتسجيل وتقديم طلب ومتابعة حالته من courier.html وحدها، وسبب الرفض/الإيقاف.
# واجهة المندوب تُختبر في node بـ DOM وهمي على خادم حقيقي (ليس متصفحًا).
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs, png
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8779; BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph, nm="u"):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def ui(token, steps):
    r = subprocess.run(["node", H, "courier", BASE, token, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    if r.returncode: print(r.stderr[:600])
    return json.loads(r.stdout)
q = lambda sql, *a: sqlite3.connect(os.environ["LAQINO_DB"]).execute(sql, a).fetchall()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 8}, at)
me = lambda t: call("GET", "/me", None, t)[1]["id"]; ST = lambda t: call("GET", "/courier/status", None, t)
rv = lambda t, st, **k: call("POST", f"/admin/couriers/{me(t)}/review", {"status": st, **k}, at)
# ---------- API ----------
a = user("01011111111")
ok("no application yet => 404 'لا يوجد طلب انضمام' (the page keys on this)", ST(a) == (404, {"error": "لا يوجد طلب انضمام"}))
ok("apply with documents => pending, has_documents, no reason", apply_docs(call, a)[0] == 201 and (lambda s: s["status"] == "pending" and s["has_documents"] is True and s["review_reason"] is None)(ST(a)[1]))
ok("reject WITH reason => shown to the courier", rv(a, "rejected", reason="  صورة البطاقة غير واضحة ")[0] == 200 and ST(a)[1]["status"] == "rejected" and ST(a)[1]["review_reason"] == "صورة البطاقة غير واضحة")
ok("reason is audited", any(x["action"] == "courier.rejected" and "غير واضحة" in x["detail"] for x in call("GET", "/admin/audit", None, at)[1]))
ok("re-apply after rejection clears the reason and returns to pending", apply_docs(call, a)[0] == 201 and ST(a)[1]["status"] == "pending" and ST(a)[1]["review_reason"] is None)
ok("approve ignores/clears any reason", rv(a, "approved", reason="تجاهل")[0] == 200 and ST(a)[1]["review_reason"] is None and q("select review_reason from couriers")[0][0] is None)
ok("suspend with reason => shown; reinstate clears it", rv(a, "suspended", reason="شكاوى")[0] == 200 and ST(a)[1]["review_reason"] == "شكاوى" and rv(a, "approved")[0] == 200 and ST(a)[1]["review_reason"] is None)
ok("reason is optional (old clients unaffected) and capped at 300", rv(a, "suspended")[0] == 200 and ST(a)[1]["review_reason"] is None and rv(a, "suspended", reason="x" * 400)[0] == 200 and len(ST(a)[1]["review_reason"]) == 300)
rv(a, "approved")
ok("non-admin cannot review", call("POST", f"/admin/couriers/{me(a)}/review", {"status": "suspended"}, a)[0] == 403)
# ---------- standalone page ----------
FR = "FileReader=class{readAsDataURL(f){this.result='data:image/png;base64,'+f.b64;setTimeout(()=>this.onload(),0)}}"
fl = lambda i, n=10: f"document.getElementById('{i}').files=[{{size:{n},b64:'{png()}'}}]"
setv = lambda i, v: {"js": f"document.getElementById('{i}').value={json.dumps(v)}"}
r = ui("", [{"snap": "m"}])
ok("logged out: courier page has its own login form (no 'go to home page' dead end)", all(x in r["m"] for x in ('id="x_ph"', 'id="x_pw"', "تسجيل دخول المندوب")) and not r["errs"])
r = ui("", [{"js": "authView(1)", "snap": "m"}])
ok("register form available on the courier page", 'id="x_nm"' in r["m"] and "إنشاء الحساب" in r["m"])
r = ui("", [setv("x_ph", "01011111111"), setv("x_pw", "wrongpass1"), {"js": "doAuth(0)"}, {"snap": "x_err"}])
ok("wrong password => error shown, stays on login", "غير صحيحة" in r["x_err"] and not r["errs"])
r = ui("", [setv("x_nm", "مندوب جديد"), setv("x_ph", "01055555555"), setv("x_pw", "password1"), {"js": "doAuth(1)", "wait": 1500}, {"snap": "m"}])
ok("register on the courier page => straight to the application form", q("select count(*) from users where phone='01055555555'")[0][0] == 1 and 'id="x_f1"' in r["m"] and 'id="x_f2"' in r["m"] and not r["errs"])
ok("register with a bad phone shows the server error", "رقم الهاتف" in ui("", [setv("x_nm", "x"), setv("x_ph", "123"), setv("x_pw", "password1"), {"js": "doAuth(1)"}, {"snap": "x_err"}])["x_err"])
b = user("01066666666")
NOF = "for(const i of ['x_f1','x_f2','x_f3'])document.getElementById(i).files=[]"  # a real <input type=file> always has .files; the fake DOM does not
ST_STUB = {"js": "document.getElementById('x_rg').querySelectorAll=()=>[{value:'3'}];" + NOF}  # the fake DOM has no <select> cascade
r = ui(b, [{"snap": "m"}])
ok("logged-in user without an application sees the apply form", 'id="x_f1"' in r["m"] and not r["errs"])
r = ui(b, [{"js": FR}, ST_STUB, {"js": "sendApply()", "snap": "x_err"}])
ok("no photos => asks for ID, nothing created", "ارفع صورة البطاقة" in r["x_err"] and not q("select * from couriers where user_id=?", me(b)))
r = ui(b, [{"js": FR}, ST_STUB, {"js": fl("x_f1", 5_000_000)}, {"js": fl("x_f2")}, {"js": "sendApply()", "snap": "x_err"}])
ok("oversize photo rejected client-side", "كبيرة" in r["x_err"] and not q("select * from couriers where user_id=?", me(b)))
r = ui(b, [{"js": FR}, {"js": "document.getElementById('x_rg').querySelectorAll=()=>[];" + NOF}, {"js": fl("x_f1")}, {"js": fl("x_f2")}, {"js": "sendApply()", "snap": "x_err"}])
ok("no region chosen => asked to choose, nothing created", "منطقة" in r["x_err"] and not q("select * from couriers where user_id=?", me(b)))
r = ui(b, [{"js": FR}, ST_STUB, {"js": fl("x_f1")}, {"js": fl("x_f2")}, {"js": "sendApply()", "wait": 1500}, {"snap": "m"}])
ok("apply from the page => pending + 2 documents + waiting screen", q("select status,region_id from couriers where user_id=?", me(b)) == [("pending", 3)] and q("select count(*) from courier_documents where courier_id=?", me(b))[0][0] == 2 and "قيد مراجعة" in r["m"] and not r["errs"])
rv(b, "rejected", reason="<img src=x onerror=alert(1)>")
r = ui(b, [{"snap": "m"}])
ok("rejected screen: reason escaped (no raw HTML), re-apply button", "&lt;img" in r["m"] and "<img src=x" not in r["m"] and "تقديم طلب جديد" in r["m"] and "تم رفض" in r["m"])
rv(b, "suspended", reason="مخالفة")  # (not approved yet: still allowed by the API; page must show suspended text)
r = ui(b, [{"snap": "m"}])
ok("suspended screen: reason shown, no re-apply button, sign-out present", "مخالفة" in r["m"] and "موقوف" in r["m"] and "تقديم طلب جديد" not in r["m"] and "signOut()" in r["m"])
rv(b, "approved")
r = ui(b, [{"snap": "m"}])
ok("approved => dashboard + sign-out button", "الرصيد" in r["m"] and "signOut()" in r["m"] and not r["errs"])
r = ui(b, [{"js": "signOut()", "wait": 800}, {"snap": "m"}])
ok("sign-out returns to the login form", 'id="x_ph"' in r["m"] and not r["errs"])
ok("sign-out revoked the server session", call("GET", "/me", None, b)[0] == 401)
d = os.path.dirname(os.path.abspath(__file__)); rd = lambda *p: open(os.path.join(d, *p), encoding="utf-8").read()
ok("auto-refresh pauses while a form is open (HOLD) so typed data/files are not wiped", "!HOLD&&" in rd("static", "courier.html") and "let T=" in rd("static", "courier.html"))
ok("admin asks for a reason on reject/suspend", "window.crv=" in rd("static", "admin.html") and "crv(${c.user_id},'rejected')" in rd("static", "admin.html"))
ok("service worker version >=v22", int(re.search(r"laqino-v(\d+)", rd("static", "sw.js")).group(1)) >= 22)
print("ALL OK")
