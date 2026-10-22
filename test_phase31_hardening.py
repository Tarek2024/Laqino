# المرحلة 31: body() يرفض غير الكائن بـ400، والنسخة الاحتياطية التلقائية قبل التشغيل. قاعدة مؤقتة، منفذ ديناميكي.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, glob
d0 = tempfile.mkdtemp(); os.environ["LAQINO_DB"] = os.path.join(d0, "t.db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
# أول تشغيل: لا قاعدة => لا نسخة
server.init("01000000000", "Xk9-vQ2m-Lp7zRt")
ok("no backup when db did not exist", not glob.glob(os.path.join(d0, "backups", "*")))
# ثاني تشغيل: قاعدة موجودة => نسخة سليمة
b = server.auto_backup(); ok("backup created", b and os.path.isfile(b))
c = sqlite3.connect(b); ok("backup integrity ok and has tables", c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] > 10); c.close()
# التقليم: نُنشئ نسخًا قديمة ثم نتأكد أن العدد لا يتجاوز keep
bd = os.path.join(d0, "backups")
for i in range(8): open(os.path.join(bd, "pre-start-2000010%d-000000.db" % i), "wb").write(b"x")
server.auto_backup(keep=3); ok("pruned to 3", len(glob.glob(os.path.join(bd, "pre-start-*.db"))) == 3)
os.environ["LAQINO_AUTO_BACKUP"] = "0"; n = len(os.listdir(bd)); time.sleep(1.1); ok("disabled by env", server.auto_backup() is None and len(os.listdir(bd)) == n); os.environ.pop("LAQINO_AUTO_BACKUP")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def raw(m, p, data, tok=None):
    r = urllib.request.Request(BASE + p, data.encode(), {"Content-Type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
tok = raw("POST", "/api/login", json.dumps({"phone": "01000000000", "password": "Xk9-vQ2m-Lp7zRt"}))[1]["token"]
for bad in ("[1,2]", '"abc"', "null", "123", "true"):
    for p in ("/api/register", "/api/login", "/api/password/change", "/api/files", "/api/verify/start"):
        code, _ = raw("POST", p, bad, tok); ok("%s %s -> 400/401/403/404 not 500" % (p, bad), code in (400, 401, 403, 404, 429))
code, _ = raw("POST", "/api/login", json.dumps({"phone": "01000000000", "password": "Xk9-vQ2m-Lp7zRt"})); ok("valid login still works", code == 200)
code, _ = raw("POST", "/api/login", ""); ok("empty body still handled", code in (400, 401))
print("ALL PASSED")
