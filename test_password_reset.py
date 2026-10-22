# استعادة كلمة المرور بكود يصدره الأدمن + تغيير كلمة المرور للمستخدم المسجّل (لا يوجد مزوّد SMS: الهوية تُتحقق خارج النظام).
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8798), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8798"; DB = os.environ["LAQINO_DB"]; HN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def q(sql, *a):
    c = sqlite3.connect(DB); r = c.execute(sql, a).fetchall(); c.commit(); return r
def reg(ph, pw="password1"):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": pw}); return call("POST", "/login", {"phone": ph, "password": pw})[1]["token"]
def login(ph, pw): return call("POST", "/login", {"phone": ph, "password": pw})
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
t1 = reg("01011111111"); t1b = call("POST", "/login", {"phone": "01011111111", "password": "password1"})[1]["token"]; uid = call("GET", "/me", None, t1)[1]["id"]
other = reg("01022222222"); adm_id = call("GET", "/me", None, at)[1]["id"]
# --- إصدار الكود
ok("customer cannot issue reset codes (403)", call("POST", f"/admin/users/{uid}/reset-code", {}, other)[0] == 403)
ok("no auth cannot issue (401)", call("POST", f"/admin/users/{uid}/reset-code", {})[0] == 401)
ok("cannot issue for an admin account (409)", call("POST", f"/admin/users/{adm_id}/reset-code", {}, at)[0] == 409)
ok("unknown user 404", call("POST", "/admin/users/99999/reset-code", {}, at)[0] == 404)
st, r = call("POST", f"/admin/users/{uid}/reset-code", {}, at); code = r["code"]
ok("admin gets 8-digit code, 30 min expiry, shown once", st == 200 and len(code) == 8 and code.isdigit() and r["expires_in"] == 1800)
ok("code is stored hashed, never in plaintext; audit has no code", code not in str(q("SELECT * FROM password_resets")) and code not in str(q("SELECT * FROM audit_log")) and q("SELECT COUNT(*) FROM audit_log WHERE action='password.reset_code'")[0][0] == 1)
# --- الاستعادة: أخطاء
ok("short new password rejected (400)", call("POST", "/password/reset", {"phone": "01011111111", "code": code, "new_password": "short"})[0] == 400)
bad = call("POST", "/password/reset", {"phone": "01011111111", "code": "00000000" if code != "00000000" else "11111111", "new_password": "newpass123"})
nophone = call("POST", "/password/reset", {"phone": "01099999999", "code": "12345678", "new_password": "newpass123"})
nocode = call("POST", "/password/reset", {"phone": "01022222222", "code": "12345678", "new_password": "newpass123"})
ok("wrong code / unknown phone / no code give the SAME generic 400 (no account enumeration)", bad[0] == nophone[0] == nocode[0] == 400 and bad[1] == nophone[1] == nocode[1])
ok("old password still works after failed attempts", login("01011111111", "password1")[0] == 200)
# --- نجاح
st, _ = call("POST", "/password/reset", {"phone": "01011111111", "code": code, "new_password": "newpass123"}); ok("correct code resets password", st == 200)
ok("old password rejected, new works", login("01011111111", "password1")[0] == 401 and login("01011111111", "newpass123")[0] == 200)
ok("all old sessions revoked after reset", call("GET", "/me", None, t1)[0] == 401 and call("GET", "/me", None, t1b)[0] == 401)
ok("code is one-time (reuse fails)", call("POST", "/password/reset", {"phone": "01011111111", "code": code, "new_password": "another123"})[0] == 400 and login("01011111111", "newpass123")[0] == 200)
ok("reset audited", q("SELECT COUNT(*) FROM audit_log WHERE action='password.reset'")[0][0] == 1)
# --- 5 محاولات تُبطل الكود
code2 = call("POST", f"/admin/users/{uid}/reset-code", {}, at)[1]["code"]; wrong = "00000000" if code2 != "00000000" else "11111111"
for _ in range(5): call("POST", "/password/reset", {"phone": "01011111111", "code": wrong, "new_password": "newpass123"})
st = call("POST", "/password/reset", {"phone": "01011111111", "code": code2, "new_password": "viaGuess1"})[0]
ok("after 5 wrong attempts even the right code is refused (brute force blocked)", st in (400, 429) and login("01011111111", "viaGuess1")[0] == 401)
q("DELETE FROM throttle")
ok("admin can issue a fresh code afterwards and it works", (lambda c3: call("POST", "/password/reset", {"phone": "01011111111", "code": c3, "new_password": "fresh12345"})[0] == 200)(call("POST", f"/admin/users/{uid}/reset-code", {}, at)[1]["code"]) and login("01011111111", "fresh12345")[0] == 200)
# --- انتهاء الصلاحية
code3 = call("POST", f"/admin/users/{uid}/reset-code", {}, at)[1]["code"]; q("UPDATE password_resets SET expires=? WHERE user_id=?", int(time.time()) - 1, uid)
ok("expired code refused and removed", call("POST", "/password/reset", {"phone": "01011111111", "code": code3, "new_password": "late12345"})[0] == 400 and not q("SELECT 1 FROM password_resets WHERE user_id=?", uid))
# --- كود لمستخدم لا يعمل لغيره
cA = call("POST", f"/admin/users/{uid}/reset-code", {}, at)[1]["code"]
ok("code of user A cannot reset user B", call("POST", "/password/reset", {"phone": "01022222222", "code": cA, "new_password": "hijack123"})[0] == 400 and login("01022222222", "password1")[0] == 200)
# --- تغيير كلمة المرور من الحساب
q("DELETE FROM throttle"); a1 = login("01022222222", "password1")[1]["token"]; a2 = login("01022222222", "password1")[1]["token"]
ok("change requires login (401)", call("POST", "/me/password", {"old_password": "password1", "new_password": "x12345678"})[0] == 401)
ok("wrong current password refused (403)", call("POST", "/me/password", {"old_password": "nope", "new_password": "x12345678"}, a1)[0] == 403)
ok("short / same password refused (400)", call("POST", "/me/password", {"old_password": "password1", "new_password": "short"}, a1)[0] == 400 and call("POST", "/me/password", {"old_password": "password1", "new_password": "password1"}, a1)[0] == 400)
ok("change succeeds", call("POST", "/me/password", {"old_password": "password1", "new_password": "changed12345"}, a1)[0] == 200)
ok("current session stays, other devices logged out", call("GET", "/me", None, a1)[0] == 200 and call("GET", "/me", None, a2)[0] == 401)
ok("old password dead, new works", login("01022222222", "password1")[0] == 401 and login("01022222222", "changed12345")[0] == 200)
q("DELETE FROM throttle")
for _ in range(5): call("POST", "/me/password", {"old_password": "bad", "new_password": "x12345678"}, a1)
ok("change-password brute force throttled (429)", call("POST", "/me/password", {"old_password": "changed12345", "new_password": "x12345678"}, a1)[0] == 429)
# --- واجهات
def page(pg, tok, steps):
    o = subprocess.run(["node", HN, pg, BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); assert o.returncode == 0, o.stderr
    return json.loads(o.stdout)
r = page("index", "", [{"js": "FG=1;go(tab)", "snap": "v", "wait": 800}])
ok("index shows forgot-password form (phone, code, new password)", not r["errs"] and "استعادة كلمة المرور" in r["v"] and 'id="fco"' in r["v"] and 'id="fpw"' in r["v"])
r = page("index", "", [{"js": "go(tab)", "snap": "v", "wait": 800}]); ok("login card has 'forgot password' link", "نسيت كلمة المرور" in r["v"])
q("DELETE FROM throttle"); cu = call("POST", "/login", {"phone": "01011111111", "password": "fresh12345"})[1]["token"]
r = page("index", cu, [{"js": "CP=1;go(3)", "snap": "v", "wait": 900}]); ok("logged-in account tab has change-password form", not r["errs"] and 'id="cpo"' in r["v"] and 'id="cpn"' in r["v"])
r = page("admin", at, [{"js": "go('/admin/users')", "wait": 300}]) if False else None
adm = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "admin.html"), encoding="utf-8").read()
ok("admin users list has reset-code button (not for admin accounts)", "كود استعادة كلمة المرور" in adm and "x.role=='admin'?''" in adm and "/reset-code" in adm)
# --- تدفق كامل عبر دوال الصفحة الفعلية (rst / chp)
q("DELETE FROM throttle"); c4 = call("POST", f"/admin/users/{uid}/reset-code", {}, at)[1]["code"]
r = page("index", "", [{"js": "FG=1;go(tab)", "wait": 600}, {"js": f"$('fph').value='01011111111';$('fco').value='{c4}';$('fpw').value='viaUI12345';rst()", "wait": 1500}])
ok("UI rst(): reset through the real page script", not r["errs"] and any("تم تغيير كلمة المرور" in a for a in r["alerts"]) and login("01011111111", "viaUI12345")[0] == 200)
tk = login("01011111111", "viaUI12345")[1]["token"]
r = page("index", tk, [{"js": "CP=1;go(3)", "wait": 800}, {"js": "$('cpo').value='viaUI12345';$('cpn').value='viaUI99999';chp()", "wait": 1500}])
ok("UI chp(): change password through the real page script", not r["errs"] and any("تم تغيير كلمة المرور" in a for a in r["alerts"]) and login("01011111111", "viaUI99999")[0] == 200)
r = page("index", "", [{"js": "FG=1;go(tab)", "wait": 600}, {"js": "$('fph').value='01011111111';$('fco').value='00000000';$('fpw').value='whatever123';rst()", "snap": "v", "wait": 1200}])
ok("UI shows server error message for a bad code", "الكود غير صحيح" in r["v"])
print("ALL OK")
