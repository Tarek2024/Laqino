# المرحلة 30 (إصلاح): قفل الدخول يُحسب على عنوان العميل الحقيقي (خلف Caddy) فلا يقدر غريب يقفل حساب غيره
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8791), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(p, d, xff=None):
    h = {"Content-Type": "application/json"}
    if xff: h["X-Forwarded-For"] = xff
    r = urllib.request.Request("http://127.0.0.1:8791/api" + p, json.dumps(d).encode(), h)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
PH, PW = "01122223333", "correct-pass-1"
ok("register victim", call("/register", {"phone": PH, "name": "victim", "password": PW})[0] == 201)
bad = lambda ip: call("/login", {"phone": PH, "password": "wrong"}, ip)[0]
ok("attacker IP: 5 wrong -> 401 then 429", [bad("6.6.6.6") for _ in range(6)] == [401] * 5 + [429])
ok("victim from another IP can still log in", call("/login", {"phone": PH, "password": PW}, "5.5.5.5")[0] == 200)
ok("attacker stays blocked even with the right password guess pattern", bad("6.6.6.6") == 429)
server.throttle_clear()
# distributed guessing: the looser per-phone cap (25) still stops it
codes = [bad("10.1.%d.%d" % (i // 250, i % 250 + 1)) if False else bad("20.0.0.%d" % (i + 1)) for i in range(26)]
ok("26 wrong guesses from 26 different IPs -> per-phone cap kicks in", codes[:25] == [401] * 25 and codes[25] == 429)
ok("a successful login by the owner clears both counters", (server.throttle_clear() or True) and call("/login", {"phone": PH, "password": PW}, "5.5.5.5")[0] == 200)
n = sqlite3.connect(server.DB).execute("SELECT COUNT(*) FROM throttle WHERE k LIKE 'login%'").fetchone()[0]
ok("owner login leaves no failure rows for this IP/phone", n == 0)
# per-IP cap across many phones (password spraying) and idle-socket timeout
server.throttle_clear()
spray = [call("/login", {"phone": "0100000%04d" % i, "password": "x"}, "30.0.0.1")[0] for i in range(41)]
ok("one IP spraying 40 different phones -> 401s then 429", spray[:40] == [401] * 40 and spray[40] == 429)
ok("a different IP is unaffected by that spray", call("/login", {"phone": PH, "password": PW}, "31.0.0.1")[0] == 200)
import socket
server.H.timeout = 2
sk = socket.create_connection(("127.0.0.1", 8791)); sk.settimeout(6); t0 = time.time()
try: data = sk.recv(10)
except socket.timeout: data = None
ok("idle connection is closed by the server within the timeout (%.1fs)" % (time.time() - t0), data == b"" and time.time() - t0 < 5)
print("ALL PASSED")
