# واجهات التحقق عبر واتساب: سكربتات الصفحات الحقيقية في node على DOM وهمي ضد الخادم الفعلي (ليست اختبار متصفح ولا عرضًا بصريًا).
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, re, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(); os.environ["LAQINO_WA_VERIFY"] = "1"
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8792), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8792"; H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def page(pg, tok, steps):
    o = subprocess.run(["node", H, pg, BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); assert o.returncode == 0, o.stderr
    return json.loads(o.stdout)
# تأكيد يدوي من الإدارة بنفس كود الصفحة (VF.code) — يغطي مسار الإدارة دون الحاجة لـ webhook
ADMIN_CONFIRM = "(async()=>{const L=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:'01000000000',password:'AdminPass123'})})).json();const r=await fetch('/api/admin/verifications/confirm',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+L.token},body:JSON.stringify({phone:VF.phone,purpose:VF.purpose,code:VF.code})});if(r.status!==200)throw 'confirm '+r.status})()"
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]

# --- تسجيل جديد: صار في register.html (auth() في index.html تسجيل دخول فقط)؛ نختبر عقد الـAPI الذي تستخدمه الصفحة ثم سكربت الصفحة نفسه
rv = call("POST", "/verify/start", {"phone": "01155550000", "purpose": "register"})[1]
ok("register start returns code, Laqino number and wa.me link (what register.html renders)", rv["code"] and rv["wa_number"] == "01017011170" and rv["wa_link"].startswith("https://wa.me/201017011170?text="))
ok("account NOT created before verification", sqlite3.connect(server.DB).execute("SELECT COUNT(*) FROM users WHERE phone='01155550000'").fetchone()[0] == 0 and call("POST", "/verify/status", {"phone": "01155550000", "purpose": "register"})[1]["verified"] is False)
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
ok("admin confirms the code", call("POST", "/admin/verifications/confirm", {"phone": "01155550000", "purpose": "register", "code": rv["code"]}, at)[0] == 200)
ok("status becomes verified", call("POST", "/verify/status", {"phone": "01155550000", "purpose": "register"})[1]["verified"] is True)
ok("register then login succeed after verification", call("POST", "/register", {"phone": "01155550000", "name": "سارة", "password": "password1"})[0] == 201 and call("POST", "/login", {"phone": "01155550000", "password": "password1"})[0] == 200)
ok("verification consumed", sqlite3.connect(server.DB).execute("SELECT COUNT(*) FROM phone_verifications WHERE phone='01155550000'").fetchone()[0] == 0)
# register.html: لا TypeError لو أُلغي التحقق أثناء طلب poll قيد التنفيذ
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "register.html"), encoding="utf-8").read()
ok("register.html poll re-checks verification after the await (no null deref on cancel)", "const v0=verification" in src and "verification!==v0" in src)

# --- استعادة كلمة المرور عبر واتساب
call("POST", "/verify/start", {"phone": "01166660000"}); server.wa_ingest(server.db(), "201166660000", sqlite3.connect(server.DB).execute("SELECT code FROM phone_verifications WHERE phone='01166660000' AND purpose='register'").fetchone()[0])
ok("setup: second customer registered", call("POST", "/register", {"phone": "01166660000", "name": "علي", "password": "password1"})[0] == 201)
r = page("index", "", [
    {"js": "go(0)", "wait": 600}, {"js": "FG=1;go(0)", "wait": 600},
    {"js": "$('fph').value='01166660000';$('fpw').value='newpass999';rstw()", "snap": "v", "wait": 1200},
    {"js": ADMIN_CONFIRM, "wait": 300},
    {"js": "vfp()", "wait": 1800},
])
ok("reset via WhatsApp: alert shown, new password works, old does not", not r["errs"] and any("تم تغيير كلمة المرور" in a for a in r["alerts"]) and call("POST", "/login", {"phone": "01166660000", "password": "newpass999"})[0] == 200 and call("POST", "/login", {"phone": "01166660000", "password": "password1"})[0] == 401)
r = page("index", "", [{"js": "go(0)", "wait": 600}, {"js": "FG=1;go(0)", "wait": 600}, {"js": "$('fph').value='123';$('fpw').value='newpass999';rstw()", "snap": "v", "wait": 800}])
ok("reset with invalid phone shows an error, no WhatsApp step", "رقم الهاتف غير صحيح" in r["v"] and "تأكيد رقم الهاتف" not in r["v"])

# --- لوحة الإدارة: قائمة الانتظار والتأكيد اليدوي
call("POST", "/verify/start", {"phone": "01177770000"})
r = page("admin", at, [{"js": "tab='wa';shell()", "snap": "v", "wait": 1200}])
ok("admin tab lists pending phones with a code box, never the code", not r["errs"] and "01177770000" in r["v"] and "الكود من الرسالة" in r["v"] and "تأكيد" in r["v"] and sqlite3.connect(server.DB).execute("SELECT code FROM phone_verifications WHERE phone='01177770000'").fetchone()[0] not in r["v"])
code = sqlite3.connect(server.DB).execute("SELECT code FROM phone_verifications WHERE phone='01177770000'").fetchone()[0]
r = page("admin", at, [{"js": "tab='wa';shell()", "wait": 1000}, {"js": "document.getElementById('wc01177770000register').value='%s';wac('01177770000','register')" % code, "snap": "v", "wait": 1200}])
ok("admin confirms with the code from the message; it leaves the pending list", not r["errs"] and "01177770000" not in r["v"] and call("POST", "/verify/status", {"phone": "01177770000"})[1]["verified"] is True)
print("ALL PASSED")
