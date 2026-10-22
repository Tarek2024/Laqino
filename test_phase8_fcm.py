# المرحلة 8 (دفعة 1): إشعارات أندرويد عبر FCM — fcm.py + ربطها بالسيرفر. خادم Google وهمي محلي يتحقق من توقيع RS256 فعليًا.
import os, json, threading, urllib.request, urllib.error, urllib.parse, tempfile, time, sqlite3, base64, re
_TMP = tempfile.mkdtemp(prefix="laqino-p8-")
os.environ["LAQINO_DB"] = os.path.join(_TMP, "test.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "up"); os.makedirs(os.environ["LAQINO_UPLOADS"])
os.environ["LAQINO_TEST_PRESENCE"] = "1"; os.environ["LAQINO_PUSH_ALLOW_ANY"] = "1"; os.environ.pop("LAQINO_FCM_SERVICE_ACCOUNT", None)
import server, fcm
from testutil import apply_docs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8811), server.H).serve_forever, daemon=True).start()
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
TOKENS, MSGS, BAD = [], [], []
class G(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/token":
            jwt = urllib.parse.parse_qs(body.decode())["assertion"][0]; h, b, s = jwt.split("."); pad = lambda x: base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))
            try: KEY.public_key().verify(pad(s), (h + "." + b).encode(), padding.PKCS1v15(), hashes.SHA256()); good = json.loads(pad(h))["alg"] == "RS256"
            except Exception: good = False
            cl = json.loads(pad(b)); TOKENS.append(cl)
            if not good: BAD.append("sig"); self.send_response(400); self.end_headers(); return
            out = json.dumps({"access_token": "AT%d" % len(TOKENS), "expires_in": 3600}).encode(); self.send_response(200); self.end_headers(); self.wfile.write(out); return
        if self.headers.get("Authorization", "") != "Bearer AT%d" % len(TOKENS): BAD.append("auth"); self.send_response(401); self.end_headers(); return
        m = json.loads(body); MSGS.append((self.path, m["message"]))
        if "DEAD" in m["message"]["token"]: self.send_response(404); self.end_headers(); self.wfile.write(b'{"error":{"details":[{"errorCode":"UNREGISTERED"}]}}'); return
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8812), G).serve_forever, daemon=True).start(); time.sleep(.3)
SA = os.path.join(_TMP, "sa.json"); json.dump({"client_email": "svc@laqino-test.iam.gserviceaccount.com", "private_key": PEM, "project_id": "laqino-test", "token_uri": "http://127.0.0.1:8812/token"}, open(SA, "w"))
DB = server.DB
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8811/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def q(sql, *a):
    c = sqlite3.connect(DB); r = c.execute(sql, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def wait(cond, t=5):
    e = time.time() + t
    while time.time() < e and not cond(): time.sleep(.05)
    time.sleep(.2)
tk = lambda n: ("tok%s_" % n).ljust(40, "x")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cu = user("01088880001")

# ---- مقفول افتراضيًا
ok("anonymous register -> 401", call("POST", "/fcm/register", {"token": tk(1)})[0] == 401)
ok("disabled server: register -> 503 and nothing stored", call("POST", "/fcm/register", {"token": tk(1)}, cu)[0] == 503 and q("select count(*) from fcm_tokens")[0][0] == 0)
ok("status: customer 403, admin enabled=false", call("GET", "/admin/fcm/status", None, cu)[0] == 403 and call("GET", "/admin/fcm/status", None, at)[1] == {"enabled": False, "devices": 0})
ok("disabled: send() is a no-op returning 0 and touches no network", fcm.send(server.db(), [1], 60, "order") == 0 and not TOKENS and not MSGS)

# ---- تفعيل
os.environ["LAQINO_FCM_SERVICE_ACCOUNT"] = SA; os.environ["LAQINO_FCM_ALLOW_ANY"] = "1"; os.environ["LAQINO_FCM_BASE"] = "http://127.0.0.1:8812"
ok("status enabled=true after setting the env var", call("GET", "/admin/fcm/status", None, at)[1]["enabled"] is True)
ok("invalid tokens rejected (empty, short, spaces, <script>)", all(call("POST", "/fcm/register", {"token": x}, cu)[0] == 400 for x in ("", "abc", "a b" * 20, "<script>" + "x" * 30)))
ok("register 200 stores token for the user", call("POST", "/fcm/register", {"token": tk(1)}, cu)[0] == 200 and q("select user_id from fcm_tokens where token=?", tk(1)) == [(call("GET", "/me", None, cu)[1]["id"],)])
other = user("01088880002"); oid_ = call("GET", "/me", None, other)[1]["id"]
call("POST", "/fcm/register", {"token": tk(1)}, other)
ok("same device token re-registered by another account moves to it (shared phone)", q("select user_id from fcm_tokens where token=?", tk(1)) == [(oid_,)] and q("select count(*) from fcm_tokens")[0][0] == 1)
ok("unregister by a non-owner does nothing", (call("POST", "/fcm/unregister", {"token": tk(1)}, cu)[0], q("select count(*) from fcm_tokens")[0][0]) == (200, 1))
ok("unregister by owner removes it", call("POST", "/fcm/unregister", {"token": tk(1)}, other)[0] == 200 and q("select count(*) from fcm_tokens")[0][0] == 0)
for i in range(7): call("POST", "/fcm/register", {"token": tk(10 + i)}, cu); time.sleep(.01)
rows = [r[0] for r in q("select token from fcm_tokens where user_id=? order by updated_at, rowid", call("GET", "/me", None, cu)[1]["id"])]
ok("max 5 per user: oldest evicted, newest kept (no rejection on reinstall)", len(rows) == 5 and tk(16) in rows and tk(10) not in rows)
ok("GET/other methods on register -> 404", call("GET", "/fcm/register", None, cu)[0] == 404)
ok("status counts devices (admin sees a number only)", call("GET", "/admin/fcm/status", None, at)[1] == {"enabled": True, "devices": 5})

# ---- الإرسال الفعلي
q("delete from fcm_tokens"); cuid = call("GET", "/me", None, cu)[1]["id"]
call("POST", "/fcm/register", {"token": tk(20)}, cu)
db = server.db(); n = fcm.send(db, [cuid], 300, "order"); n2 = fcm.send(db, [cuid], 300, "chat"); db.close()
ok("send accepted twice", n == 1 and n2 == 1 and len(MSGS) == 2)
ok("RS256 JWT verified by the fake Google; claims: iss/scope/aud/exp<=1h", not BAD and TOKENS[0]["iss"].startswith("svc@") and TOKENS[0]["scope"].endswith("firebase.messaging") and TOKENS[0]["aud"] == "http://127.0.0.1:8812/token" and 0 < TOKENS[0]["exp"] - time.time() <= 3605)
ok("access token cached: 2 sends, 1 token request", len(TOKENS) == 1)
path, msg = MSGS[0]
ok("FCM v1 path with project id; HIGH priority; ttl 300s; collapse key/tag; channel", path == "/v1/projects/laqino-test/messages:send" and msg["android"]["priority"] == "HIGH" and msg["android"]["ttl"] == "300s" and msg["android"]["collapse_key"] == "order" and msg["android"]["notification"] == {"tag": "order", "channel_id": "laqino_alerts"})
blob = json.dumps(MSGS, ensure_ascii=False)
ok("message is generic: fixed title/text per kind, no phone/name/ids", msg["notification"] == {"title": "لاقينو", "body": "طلب توصيل جديد في منطقتك"} and MSGS[1][1]["notification"]["body"] == "عندك رسالة جديدة" and msg["data"] == {"kind": "order"} and "0108888" not in blob and "u01" not in blob)
ok("ttl clamped to [30, 3600]s", fcm.build_message("x" * 30, "order", 5)["message"]["android"]["ttl"] == "30s" and fcm.build_message("x" * 30, "order", 99999)["message"]["android"]["ttl"] == "3600s")
ok("unknown kind falls back to the generic order text (no injection of arbitrary text)", fcm.build_message("x" * 30, "<b>evil</b>", 60)["message"]["notification"]["body"] == fcm.TEXTS["order"])
# توكن ميت (UNREGISTERED) يُحذف
call("POST", "/fcm/register", {"token": ("DEAD_").ljust(40, "d")}, cu); MSGS.clear()
db = server.db(); n = fcm.send(db, [cuid], 60, "order"); db.close()
ok("404/UNREGISTERED token is deleted, live token still counted", n == 1 and q("select count(*) from fcm_tokens")[0][0] == 1)
# مفتاح خاطئ في الملف: لا استثناء ولا إرسال
bad = os.path.join(_TMP, "bad.json"); open(bad, "w").write("{not json")
os.environ["LAQINO_FCM_SERVICE_ACCOUNT"] = bad
ok("broken service-account file: disabled safely (no crash)", fcm.enabled() is False and fcm.send(server.db(), [cuid]) == 0)
os.environ["LAQINO_FCM_ALLOW_ANY"] = "0"; evil = os.path.join(_TMP, "evil.json"); json.dump({"client_email": "a@b", "private_key": PEM, "project_id": "p", "token_uri": "http://169.254.169.254/token"}, open(evil, "w"))
os.environ["LAQINO_FCM_SERVICE_ACCOUNT"] = evil
ok("SSRF guard: token_uri must be https on googleapis.com in production", fcm.enabled() is False)
os.environ["LAQINO_FCM_SERVICE_ACCOUNT"] = SA; os.environ["LAQINO_FCM_ALLOW_ANY"] = "1"
ok("test overrides (ALLOW_ANY) are what enabled the local fake", fcm.enabled() is True)
os.environ["LAQINO_FCM_ALLOW_ANY"] = "0"
ok("without ALLOW_ANY the FCM base cannot be redirected by env", fcm._base() == "https://fcm.googleapis.com")
os.environ["LAQINO_FCM_ALLOW_ANY"] = "1"

# ---- التكامل مع السيرفر: طلب توصيل + محادثة
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
def mk(ph):
    t = user(ph); i = call("GET", "/me", None, t)[1]["id"]; apply_docs(call, t); call("POST", f"/admin/couriers/{i}/review", {"status": "approved"}, at)
    call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "R" + ph}, t)
    call("POST", f"/admin/topups/{[x for x in call('GET', '/admin/topups', None, at)[1] if x['transfer_ref'] == 'R' + ph][0]['id']}/review", {"status": "approved"}, at)
    call("POST", "/courier/online", {"online": True}, t); return t, i
A, ai = mk("01099990001"); B, bi = mk("01099990002"); Cc, ci = mk("01099990003")
call("POST", "/fcm/register", {"token": tk(31)}, A)                                   # A: Android فقط (بلا Web Push)
HITS = []
class W(BaseHTTPRequestHandler):
    def do_POST(self): HITS.append(self.path); self.send_response(201); self.end_headers()
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8813), W).serve_forever, daemon=True).start()
call("POST", "/courier/push/subscribe", {"endpoint": "http://127.0.0.1:8813/b"}, B)   # B: Web Push فقط  | C: لا شيء
MSGS.clear(); cust = user("01099990009")
st, o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cust)
wait(lambda: MSGS and HITS)
ok("new order: FCM-only courier A woken via FCM, Web-Push-only B via Web Push, neither-token C not woken", {m[1]["token"] for m in MSGS} == {tk(31)} and set(HITS) == {"/b"})
ok("order wake text is the order one", MSGS[0][1]["notification"]["body"] == fcm.TEXTS["order"] and MSGS[0][1]["data"]["kind"] == "order")
n_before = len(MSGS); time.sleep(0)
call("POST", f"/delivery/orders/{o['id']}/cancel", {}, cust); time.sleep(1.5)
ok("final sweep (order cancelled) does NOT send a native notification (it cannot be withdrawn)", len(MSGS) == n_before)
# محادثة: push_hook -> FCM kind=chat
MSGS.clear(); server.chat_push(ai); wait(lambda: MSGS)
ok("chat wake: FCM-only user gets the generic chat text", len(MSGS) == 1 and MSGS[0][1]["data"]["kind"] == "chat" and MSGS[0][1]["notification"]["body"] == "عندك رسالة جديدة")
MSGS.clear(); server.chat_push(ci); time.sleep(.8)
ok("chat wake: user with no device -> nothing sent", not MSGS)
# ---- ملفات
here = os.path.dirname(os.path.abspath(__file__)); rd = lambda p: open(os.path.join(here, p), encoding="utf8").read()
ok("Dockerfile copies fcm.py", "fcm.py" in rd("Dockerfile"))
sw = rd("static/sw.js"); ok("sw.js: cache >= v40 and native.js in SHELL", int(re.search(r"laqino-v(\d+)", sw).group(1)) >= 40 and '"/native.js"' in sw)
ok("native.js loaded by index.html and courier.html", all('/native.js' in rd("static/" + f) for f in ("index.html", "courier.html")))
cfgj = json.loads(rd("android/capacitor.config.json")); ok("android skeleton: appId, https server.url, cleartext off", cfgj["appId"] == "com.laqino.app" and cfgj["server"]["url"].startswith("https://") and cfgj["server"]["cleartext"] is False)
ok("no secrets shipped (google-services.json / service account)", not any(f in os.listdir(here) or f in os.listdir(os.path.join(here, "android")) for f in ("google-services.json", "sa.json")))
print("ALL PASSED")
