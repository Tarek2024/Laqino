# المرحلة 10: Web Push — إيقاظ المندوبين عند طلب جديد. يستخدم خادم push وهميًا محليًا ويتحقق من توقيع VAPID فعليًا.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, base64
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(); os.environ["LAQINO_TEST_PRESENCE"] = "1"; os.environ["LAQINO_PUSH_ALLOW_ANY"] = "1"
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8795), server.H).serve_forever, daemon=True).start()
HITS, GONE = [], set()
class P(BaseHTTPRequestHandler):
    def do_POST(self):
        HITS.append((self.path, {k.title(): v for k, v in self.headers.items()}, self.rfile.read(int(self.headers.get("Content-Length", 0)))))
        self.send_response(410 if self.path in GONE else 201); self.end_headers()
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8796), P).serve_forever, daemon=True).start(); time.sleep(.3)
DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8795/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def q(sql, *a):
    c = sqlite3.connect(DB); r = c.execute(sql, a).fetchall(); c.commit(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
def mk(ph, topup=100, approve=True):
    t = user(ph); i = call("GET", "/me", None, t)[1]["id"]; apply_docs(call, t)
    if approve: call("POST", f"/admin/couriers/{i}/review", {"status": "approved"}, at)
    if topup:
        call("POST", "/courier/topups", {"amount": topup, "transfer_ref": "R" + ph}, t)
        call("POST", f"/admin/topups/{[x for x in call('GET', '/admin/topups', None, at)[1] if x['transfer_ref'] == 'R' + ph][0]['id']}/review", {"status": "approved"}, at)
    return t, i
sub = lambda t, n: call("POST", "/courier/push/subscribe", {"endpoint": f"http://127.0.0.1:8796/{n}"}, t)[0]
A, ai = mk("01011111111"); B, bi = mk("01022222222"); C, ci = mk("01033333333"); D, di = mk("01044444444"); E, ei = mk("01055555555", topup=0); F, fi = mk("01066666666", topup=0, approve=False)
cust = user("01077777777")
for t in (A, B, C, D, E): call("POST", "/courier/online", {"online": True}, t)
call("POST", "/courier/online", {"online": False}, C)           # C chose offline
q("UPDATE couriers SET last_seen=? WHERE user_id=?", int(time.time()) - 3600, ai)  # A: app closed an hour ago (stale heartbeat) — must still be woken
q("UPDATE couriers SET last_seen=? WHERE user_id=?", int(time.time()) - 86400, di)  # D: last online yesterday — beyond reach window
# --- الاشتراك
ok("subscribe requires approved courier (customer 403)", call("POST", "/courier/push/subscribe", {"endpoint": "http://127.0.0.1:8796/x"}, cust)[0] == 403)
ok("unapproved courier cannot subscribe (403)", sub(F, "f") == 403)
ok("public key available to courier, 65-byte uncompressed P-256", len(base64.urlsafe_b64decode(call("GET", "/courier/push/key", None, A)[1]["key"] + "==")) == 65)
for t, n in ((A, "a"), (B, "b"), (C, "c"), (D, "d"), (E, "e")): assert sub(t, n) == 200
os.environ["LAQINO_PUSH_ALLOW_ANY"] = "0"
ok("SSRF guard: non-push-service / http / internal endpoints rejected", all(call("POST", "/courier/push/subscribe", {"endpoint": e}, A)[0] == 400 for e in ("http://127.0.0.1:8796/z", "https://evil.example.com/x", "https://169.254.169.254/latest", "ftp://fcm.googleapis.com/x", "")))
ok("real push-service endpoints accepted", all(call("POST", "/courier/push/subscribe", {"endpoint": e}, A)[0] == 200 for e in ("https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/abc", "https://web.push.apple.com/abc")))
for e in ("https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/abc", "https://web.push.apple.com/abc"): call("POST", "/courier/push/unsubscribe", {"endpoint": e}, A)
os.environ["LAQINO_PUSH_ALLOW_ANY"] = "1"
ok("max 5 devices per courier", [sub(A, "m%d" % i) for i in range(6)][-1] == 400)
for i in range(5): call("POST", "/courier/push/unsubscribe", {"endpoint": f"http://127.0.0.1:8796/m{i}"}, A)
# --- إرسال عند طلب جديد
def wait(n, t=4):
    e = time.time() + t
    while time.time() < e and len(HITS) < n: time.sleep(.05)
    time.sleep(.3)
st, o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cust); wait(2)
paths = sorted(h[0] for h in HITS)
ok("new order wakes eligible A (stale heartbeat) and B only", paths == ["/a", "/b"])
ok("not woken: C offline-by-choice, D beyond 12h, E no balance, F unapproved", not {"/c", "/d", "/e", "/f"} & set(paths))
h = [x for x in HITS if x[0] == "/a"][0]
ok("push has empty body (no order data) and TTL/urgency headers", h[2] == b"" and h[1]["Ttl"] == "300" and h[1]["Urgency"] == "high")
auth = h[1]["Authorization"]; tok, key = auth[len("vapid t="):].split(", k=")
hd, bd, sg = tok.split("."); pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pad(key)); sig = pad(sg)
try: pub.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")), (hd + "." + bd).encode(), ec.ECDSA(hashes.SHA256())); valid = True
except Exception: valid = False
claims = json.loads(pad(bd))
ok("VAPID JWT signature verifies with the advertised public key", valid and json.loads(pad(hd))["alg"] == "ES256")
ok("JWT aud = push origin, exp within 12h, key matches /push/key", claims["aud"] == "http://127.0.0.1:8796" and 0 < claims["exp"] - time.time() <= 12 * 3600 + 5 and key == call("GET", "/courier/push/key", None, A)[1]["key"])
ok("woken courier is NOT dispatch-eligible while heartbeat stale (no offer, 403 accept)", call("GET", "/courier/available", None, A)[1] == [] and call("POST", f"/courier/orders/{o['id']}/accept", None, A)[0] == 403)
ok("opening app (resume) with stale heartbeat but explicit online within 12h restores presence", call("POST", "/courier/heartbeat", {"resume": True}, A)[0] == 200 and call("GET", "/courier/status", None, A)[1]["online"] is True)
ok("resume does NOT connect a courier who never pressed connect (last_seen=0)", (q("UPDATE couriers SET last_seen=0 WHERE user_id=?", bi), call("POST", "/courier/heartbeat", {"resume": True}, B), call("GET", "/courier/status", None, B)[1]["online"])[2] is False)
ok("resume does NOT revive a courier last online >12h ago", (q("UPDATE couriers SET last_seen=? WHERE user_id=?", int(time.time()) - 86400, bi), call("POST", "/courier/heartbeat", {"resume": True}, B), call("GET", "/courier/status", None, B)[1]["online"])[2] is False)
call("POST", "/courier/online", {"online": True}, B)
ok("after the courier opens the app (heartbeat) the order is offered", o["id"] in [x["id"] for x in call("GET", "/courier/available", None, A)[1]])
ok("push audit recorded", q("SELECT COUNT(*) FROM audit_log WHERE action='push.order'")[0][0] == 1)
# --- رفض + إعادة البحث، 410 يحذف الاشتراك، العميل نفسه، منطقة أخرى
call("POST", f"/courier/orders/{o['id']}/reject", None, A); call("POST", "/courier/heartbeat", None, B)
HITS.clear(); GONE.add("/b"); call("POST", f"/delivery/orders/{o['id']}/retry", None, cust); wait(2)
ok("retry-search wakes again; 410 from push service removes dead subscription", "/b" in [x[0] for x in HITS] and not q("SELECT 1 FROM push_subs WHERE endpoint LIKE '%/b'"))
HITS.clear(); q("UPDATE order_offers SET status='rejected' WHERE order_id=? AND courier_id=?", o["id"], ai); q("DELETE FROM order_offers WHERE order_id=?", o["id"]); server.push_new_order(o["id"]); wait(1)
ok("courier without subscription/with removed sub is skipped; A woken again after offers cleared", [x[0] for x in HITS] == ["/a"])
q("UPDATE delivery_orders SET status='cancelled'"); HITS.clear(); server.push_new_order(o["id"]); time.sleep(.5)
ok("no push for an order that is no longer searching", HITS == [])
# courier who is also the customer is not pushed for own order
cu_c = A; call("POST", "/courier/push/subscribe", {"endpoint": "http://127.0.0.1:8796/a"}, A)
HITS.clear(); st, o2 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, A); wait(1)
ok("courier ordering for himself is not woken for own order", "/a" not in [x[0] for x in HITS])
ok("unsubscribe removes only own subscription", call("POST", "/courier/push/unsubscribe", {"endpoint": "http://127.0.0.1:8796/a"}, B)[0] == 200 and q("SELECT COUNT(*) FROM push_subs WHERE endpoint LIKE '%/a'")[0][0] == 1)
print("ALL OK")
