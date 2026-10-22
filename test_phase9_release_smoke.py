# المرحلة 9: فحص إصدار «من الصندوق» — يشغّل server.py كعملية مستقلة (كما على Termux/Docker) على قاعدة مؤقتة،
# ثم يمرّ على الصفحات والأصول والترويسات والدخول والنسخ الاحتياطي وإعادة التشغيل. لا يستورد server.py داخل الاختبار.
import os, re, sys, json, socket, subprocess, tempfile, time, urllib.request, urllib.error, tarfile, sqlite3, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); TMP = tempfile.mkdtemp(prefix="laqino-p9-")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or (_stop() or exit(1)))
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
ENV = {**{k: v for k, v in os.environ.items() if not k.startswith("LAQINO_")}, "LAQINO_DB": os.path.join(TMP, "l.db"), "LAQINO_UPLOADS": os.path.join(TMP, "up"),
       "LAQINO_ADMIN_PHONE": "01000000000", "LAQINO_ADMIN_PASSWORD": "Str0ng-Release-Pass-9", "HOST": "127.0.0.1", "PYTHONDONTWRITEBYTECODE": "1"}
PROC = [None]
def _stop():
    if PROC[0] and PROC[0].poll() is None: PROC[0].terminate(); PROC[0].wait(10)
def start(env=None):
    port = free_port(); e = {**(env or ENV), "PORT": str(port)}
    PROC[0] = subprocess.Popen([sys.executable, "server.py"], cwd=HERE, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    for _ in range(100):
        try:
            if urllib.request.urlopen(base + "/healthz", timeout=1).status == 200: return base
        except Exception: time.sleep(.1)
    return None
def get(base, path, tok=None, data=None):
    r = urllib.request.Request(base + path, json.dumps(data).encode() if data is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})})
    try: x = urllib.request.urlopen(r, timeout=10); return x.status, x.headers, x.read()
    except urllib.error.HTTPError as e: return e.code, e.headers, e.read()
J = lambda t: json.loads(t[2])
base = start(); ok("server.py starts as its own process and answers /healthz", base is not None)
st, h, b = get(base, "/healthz"); ok("healthz -> {ok:true}", st == 200 and json.loads(b) == {"ok": True})
sw = open(os.path.join(HERE, "static/sw.js"), encoding="utf8").read()
shell = re.findall(r'"(/[^"]*)"', re.search(r"SHELL\s*=\s*\[(.*?)\]", sw, re.S).group(1))
bad = [p for p in shell + ["/sw.js", "/admin.html", "/pharmacy.html", "/courier.html", "/native.js", "/assets/icon-512.png", "/assets/apple-touch-icon.png"] if get(base, p)[0] != 200]
ok("every page/asset in the service-worker SHELL (+ sw.js, panels, icons, native.js) is served 200 (bad: %s)" % (bad or "none"), not bad)
man = json.loads(get(base, "/manifest.webmanifest")[2])
ok("manifest: name, start_url, standalone, every icon file is served", man.get("name") and man.get("display") in ("standalone", "fullscreen") and all(get(base, i["src"])[0] == 200 for i in man["icons"]))
hd = get(base, "/")[1]
ok("security headers on pages: CSP (frame-ancestors none, object-src none), nosniff, X-Frame DENY", "frame-ancestors 'none'" in hd["Content-Security-Policy"] and "object-src 'none'" in hd["Content-Security-Policy"] and hd["X-Content-Type-Options"] == "nosniff" and hd["X-Frame-Options"] == "DENY")
ok("path traversal / source / db are not served", all(get(base, p)[0] == 404 for p in ("/../server.py", "/%2e%2e/server.py", "/server.py", "/laqino.db", "/..%2fserver.py", "/static/../server.py")))
ok("unknown API path -> JSON error, not a crash", get(base, "/api/nope")[0] in (401, 404))
st, _, b = get(base, "/api/login", data={"phone": "01000000000", "password": "Str0ng-Release-Pass-9"}); at = json.loads(b)["token"]
ok("admin created from env on first start and can log in", st == 200 and at)
ok("admin overview + FCM status (disabled by default) answer", get(base, "/api/admin/overview", at)[0] == 200 and J(get(base, "/api/admin/fcm/status", at)) == {"enabled": False, "devices": 0})
get(base, "/api/register", data={"phone": "01066660001", "name": "ali", "password": "password1"}); ut = J(get(base, "/api/login", data={"phone": "01066660001", "password": "password1"}))["token"]
ok("customer registers/logs in; bell count, applications, push key work; admin API is 403", J(get(base, "/api/notifications/count", ut)).keys() >= {"unread", "latest_id"} and get(base, "/api/my/applications", ut)[0] == 200 and get(base, "/api/admin/overview", ut)[0] == 403)
ok("anonymous gets 401 on protected APIs", all(get(base, p)[0] == 401 for p in ("/api/me", "/api/notifications/count", "/api/admin/overview")))
# نسخة احتياطية والخادم يعمل
bk = os.path.join(TMP, "bk"); r = subprocess.run([sys.executable, "backup_restore.py", "backup", "--out", bk, "--keep", "3"], cwd=HERE, env=ENV, capture_output=True, text=True)
tg = [f for f in os.listdir(bk)] if os.path.isdir(bk) else []
ok("backup while the server is running produces one laqino-*.tgz", r.returncode == 0 and len(tg) == 1 and re.match(r"laqino-\d{8}-\d{6}\.tgz$", tg[0]))
with tarfile.open(os.path.join(bk, tg[0])) as t: names = t.getnames()
ok("archive holds the database and no secrets", any(n.endswith("laqino.db") for n in names) and not any(".env" in n or "google-services" in n for n in names))
# إعادة تشغيل: البيانات باقية
_stop(); base = start(); ok("restart works on the existing database", base is not None)
ok("data survives restart (same users can log in)", get(base, "/api/login", data={"phone": "01066660001", "password": "password1"})[0] == 200 and get(base, "/api/login", data={"phone": "01000000000", "password": "Str0ng-Release-Pass-9"})[0] == 200)
_stop()
# أمان الإقلاع: كلمة مرور ضعيفة للمدير ترفض الإقلاع على قاعدة جديدة
weak = {**ENV, "LAQINO_DB": os.path.join(TMP, "w.db"), "LAQINO_ADMIN_PASSWORD": "12345678", "PORT": str(free_port())}
p = subprocess.run([sys.executable, "server.py"], cwd=HERE, env=weak, capture_output=True, text=True, timeout=30)
ok("weak admin password refuses to start on a fresh database (exit != 0)", p.returncode != 0 and "كلمة مرور المدير" in (p.stdout + p.stderr))
shutil.rmtree(TMP, ignore_errors=True)
print("ALL PASSED")
