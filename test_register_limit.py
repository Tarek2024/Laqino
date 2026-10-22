# حد التسجيل (لكل عنوان + سقف عام) وحفظ الحدود في SQLite عبر إعادة التشغيل
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8790), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(p, d, xff=None):
    h = {"Content-Type": "application/json"}
    if xff: h["X-Forwarded-For"] = xff
    r = urllib.request.Request("http://127.0.0.1:8790/api" + p, json.dumps(d).encode(), h)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
n = [0]
def reg(xff=None):
    n[0] += 1; return call("/register", {"phone": "0111%07d" % n[0], "name": "u", "password": "password1"}, xff)[0]
def rows(k): return sqlite3.connect(server.DB).execute("SELECT COUNT(*) FROM throttle WHERE k=?", (k,)).fetchone()[0]

ok("direct loopback (no proxy header) is not limited", [reg() for _ in range(8)] == [201] * 8)
ok("behind proxy: 5 registrations per client IP, then 429", [reg("8.8.8.8") for _ in range(6)] == [201] * 5 + [429])
ok("another client IP unaffected", reg("8.8.4.4") == 201)
ok("spoofed leftmost XFF entry ignored (rightmost counts)", reg("1.2.3.4, 8.8.8.8") == 429)
ok("limit stored in SQLite", rows("reg|8.8.8.8") == 5)
server.init("01000000000", "AdminPass123")
ok("limit survives restart (init again)", reg("8.8.8.8") == 429)
server.REG_GLOBAL = rows("reg|*") + 1
ok("global cap: next new IP allowed once", reg("9.9.9.1") == 201)
ok("global cap: then everyone gets 429", reg("9.9.9.2") == 429)
server.REG_GLOBAL = 200
ok("invalid phone does not consume the quota", call("/register", {"phone": "bad", "name": "u", "password": "password1"}, "7.7.7.7")[0] == 400 and rows("reg|7.7.7.7") == 0)
# login throttle persists across restart
codes = [call("/login", {"phone": "01011112222", "password": "bad%d" % i})[0] for i in range(6)]
ok("5 wrong logins -> 401 then 429", codes == [401] * 5 + [429])
server.init("01000000000", "AdminPass123")
ok("login block survives restart", call("/login", {"phone": "01011112222", "password": "x"})[0] == 429)
# pruning of old rows
c = sqlite3.connect(server.DB); c.execute("INSERT INTO throttle VALUES('old|x', ?)", (int(time.time()) - 200000,)); c.commit(); c.close()
cc = server.db(); server.note_fail(cc, "reg|prune"); cc.close()
ok("rows older than 24h are pruned", rows("old|x") == 0)
server.throttle_clear()
ok("throttle_clear empties table", rows("reg|8.8.8.8") == 0 and reg("8.8.8.8") == 201)
print("ALL PASSED")
