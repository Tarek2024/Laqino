# اختبار النشر: PWA، ترويسات الأمان، مسار الملفات، healthz، التخزين المؤقت.
import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8766), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def get(p):
    try: x = urllib.request.urlopen("http://127.0.0.1:8766" + p); return x.status, x.headers, x.read()
    except urllib.error.HTTPError as e: return e.code, e.headers, e.read()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
st, h, b = get("/healthz"); ok("healthz", st == 200 and json.loads(b)["ok"])
st, h, b = get("/manifest.webmanifest"); m = json.loads(b); ok("manifest served with proper type", st == 200 and "manifest+json" in h["Content-Type"] and m["display"] == "standalone")
ok("manifest icons exist", all(get(i["src"])[0] == 200 for i in m["icons"]) and any(i.get("purpose") == "maskable" for i in m["icons"]))
st, h, b = get("/sw.js"); ok("sw.js is javascript and never cached", st == 200 and "javascript" in h["Content-Type"] and h["Cache-Control"] == "no-cache" and b"/api/" in b)
ok("offline page", get("/offline.html")[0] == 200)
for p in ("/", "/admin.html", "/courier.html", "/pharmacy.html"):
    b = get(p)[2].decode(); ok("pwa tags in " + p, "manifest.webmanifest" in b and "serviceWorker" in b)
h = get("/")[1]; ok("security headers", h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff" and h["Referrer-Policy"] == "same-origin")
ok("assets cacheable", "max-age" in get("/assets/logo.jpg")[1]["Cache-Control"])
ok("traversal blocked", all(get(p)[0] == 404 for p in ("/../server.py", "/..%2fserver.py", "/%2e%2e/server.py", "/assets/../../server.py")))
os.makedirs(os.path.join(os.path.dirname(server.ROOT), "static_evil"), exist_ok=True); open(os.path.join(os.path.dirname(server.ROOT), "static_evil", "x.txt"), "w").write("secret")
ok("sibling-prefix dir blocked", get("/../static_evil/x.txt")[0] == 404)
import shutil; shutil.rmtree(os.path.join(os.path.dirname(server.ROOT), "static_evil"))
c = server.db(); ok("WAL enabled", c.execute("PRAGMA journal_mode").fetchone()[0] == "wal")
c.execute("INSERT INTO users(phone,name,pw_hash,salt,created_at) VALUES('01011111111','t','x','y',1)"); c.execute("INSERT INTO sessions VALUES('old',(SELECT id FROM users WHERE phone='01011111111'),5)"); c.commit(); c.close()
server.init(); c = server.db(); ok("expired sessions purged", c.execute("SELECT COUNT(*) FROM sessions WHERE token_hash='old'").fetchone()[0] == 0)
print("ALL PASSED")
