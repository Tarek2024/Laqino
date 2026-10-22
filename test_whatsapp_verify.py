# التحقق العكسي عبر واتساب: العميل يبعت الكود لرقم لاقينو، والخادم يطابق رقم المُرسِل.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, hmac, hashlib
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
os.environ["LAQINO_WA_VERIFY_TOKEN"] = "hook-token"; os.environ["LAQINO_WA_APP_SECRET"] = "app-secret"
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8791), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
B = "http://127.0.0.1:8791"
def call(m, p, d=None, tok=None, raw=None, hdr=None):
    h = {"Content-Type": "application/json", **(hdr or {})}
    if tok: h["Authorization"] = "Bearer " + tok
    r = urllib.request.Request(B + p, raw if raw is not None else (json.dumps(d).encode() if d is not None else None), h, method=m)
    try: x = urllib.request.urlopen(r); b = x.read(); return x.status, (json.loads(b) if b[:1] in b"{[" else b.decode())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def db(): c = server.db(); return c
def ingest(frm, text):
    c = db(); r = server.wa_ingest(c, frm, text); c.close(); return r
def start(ph, purpose="register"): return call("POST", "/api/verify/start", {"phone": ph, "purpose": purpose})
def status(ph, purpose="register"): return call("POST", "/api/verify/status", {"phone": ph, "purpose": purpose})[1]["verified"]
def reg(ph): return call("POST", "/api/register", {"phone": ph, "name": "عميل", "password": "password1"})[0]
def admin(): return call("POST", "/api/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]

# --- دوال مساعدة
ok("wa id -> local phone", server.wa_to_local("201012345678") == "01012345678" and server.wa_to_local("+20 101 234 5678") == "01012345678")
ok("non-Egyptian/invalid sender ignored", server.wa_to_local("966501234567") is None and server.wa_to_local("") is None and server.wa_to_local(None) is None)
ok("codes extracted incl. Arabic-Indic digits", server.wa_codes("كود التحقق من لاقينو: ١٢٣٤٥٦") == ["123456"] and server.wa_codes("1234567 12345") == [])
ok("wa link targets Laqino's number", server.wa_link("123456").startswith("https://wa.me/201017011170?text="))

# --- متوقف افتراضيًا: التسجيل يعمل بدون تحقق
os.environ.pop("LAQINO_WA_VERIFY", None)
ok("default: verification not required", reg("01111111101") == 201)

# --- مفعّل
os.environ["LAQINO_WA_VERIFY"] = "1"
ok("required: register without verification -> 403", reg("01111111102") == 403)
st, r = start("01111111102")
ok("start returns code, Laqino number and link", st == 200 and len(r["code"]) == 6 and r["wa_number"] == "01017011170" and "201017011170" in r["wa_link"] and r["expires_in"] == 600)
code = r["code"]
ok("not verified before the message", status("01111111102") is False and reg("01111111102") == 403)
ok("message from ANOTHER number with the right code does not verify", ingest("201222222222", code) is False and status("01111111102") is False)
ok("wrong code from the right number does not verify", ingest("201111111102", "999999" if code != "999999" else "888888") is False and status("01111111102") is False)
ok("right sender + right code (Arabic digits, extra text) verifies", ingest("201111111102", "السلام عليكم " + code.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))) is True and status("01111111102") is True)
ok("verified phone can register", reg("01111111102") == 201)
ok("verification consumed after register", status("01111111102") is False)
ok("registered phone cannot start register verification again", start("01111111102")[0] == 409)
ok("invalid phone / purpose rejected", start("123")[0] == 400 and call("POST", "/api/verify/start", {"phone": "01111111103", "purpose": "x"})[0] == 400)

# --- محاولات خاطئة تُبطل الكود
code = start("01111111103")[1]["code"]
bad = "000000" if code != "000000" else "111111"
[ingest("201111111103", bad) for _ in range(5)]
ok("5 wrong codes lock the request", ingest("201111111103", code) is False and status("01111111103") is False)
code = start("01111111103")[1]["code"]
ok("a fresh start resets attempts", ingest("201111111103", code) is True)

# --- انتهاء الصلاحية
code = start("01111111104")[1]["code"]
c = db(); c.execute("UPDATE phone_verifications SET expires=? WHERE phone='01111111104'", (int(time.time()) - 1,)); c.commit(); c.close()
ok("expired code rejected", ingest("201111111104", code) is False)
code = start("01111111105")[1]["code"]; ingest("201111111105", code)
c = db(); c.execute("UPDATE phone_verifications SET verified_at=? WHERE phone='01111111105'", (int(time.time()) - 4000,)); c.commit(); c.close()
ok("verified status expires after 30 min", status("01111111105") is False and reg("01111111105") == 403)

# --- حد طلب الكود لكل رقم
codes = [start("01111111106")[0] for _ in range(6)]
ok("start limited to 5/hour per phone", codes == [200] * 5 + [429])

# --- Webhook (Meta Cloud API)
ok("webhook handshake with right token", call("GET", "/api/wa/webhook?hub.mode=subscribe&hub.verify_token=hook-token&hub.challenge=555") == (200, "555"))
ok("webhook handshake with wrong token -> 403", call("GET", "/api/wa/webhook?hub.mode=subscribe&hub.verify_token=nope&hub.challenge=555")[0] == 403)
code = start("01111111107")[1]["code"]
payload = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": "201111111107", "type": "text", "text": {"body": "كود التحقق من لاقينو: " + code}}]}}]}]}).encode()
sig = lambda sec, b: "sha256=" + hmac.new(sec.encode(), b, hashlib.sha256).hexdigest()
ok("unsigned webhook rejected", call("POST", "/api/wa/webhook", raw=payload)[0] == 403 and status("01111111107") is False)
ok("badly signed webhook rejected", call("POST", "/api/wa/webhook", raw=payload, hdr={"X-Hub-Signature-256": sig("wrong", payload)})[0] == 403 and status("01111111107") is False)
ok("signed webhook verifies the sender", call("POST", "/api/wa/webhook", raw=payload, hdr={"X-Hub-Signature-256": sig("app-secret", payload)})[0] == 200 and status("01111111107") is True)
junk = b'{"entry":[{"changes":[{"value":{"messages":[1,"x",{"type":"image"}]}}]}, 5]}'
ok("malformed/non-text webhook payload tolerated", call("POST", "/api/wa/webhook", raw=junk, hdr={"X-Hub-Signature-256": sig("app-secret", junk)})[0] == 200)
os.environ["LAQINO_WA_APP_SECRET"] = ""
ok("no app secret configured -> webhook refuses everything", call("POST", "/api/wa/webhook", raw=payload, hdr={"X-Hub-Signature-256": sig("", payload)})[0] == 403)
os.environ["LAQINO_WA_APP_SECRET"] = "app-secret"

# --- استعادة كلمة المرور عبر واتساب
reg_phone = "01111111108"; ingest("201111111108", start(reg_phone)[1]["code"]); reg(reg_phone)
tok = call("POST", "/api/login", {"phone": reg_phone, "password": "password1"})[1]["token"]
ok("reset without verification -> 400", call("POST", "/api/password/reset", {"phone": reg_phone, "wa": True, "new_password": "newpass999"})[0] == 400)
ghost = start("01199999999", "reset")
ok("reset start for unknown phone answers like a known one (no enumeration)", ghost[0] == 200 and set(ghost[1]) == set(start(reg_phone, "reset")[1]))
rc = start(reg_phone, "reset")[1]["code"]
ok("reset: other sender cannot verify", ingest("201333333333", rc) is False)
ok("reset: owner verifies", ingest("201111111108", rc) is True)
ok("reset via WhatsApp changes the password", call("POST", "/api/password/reset", {"phone": reg_phone, "wa": True, "new_password": "newpass999"})[0] == 200
   and call("POST", "/api/login", {"phone": reg_phone, "password": "newpass999"})[0] == 200 and call("POST", "/api/login", {"phone": reg_phone, "password": "password1"})[0] == 401)
ok("old sessions revoked", call("GET", "/api/me", tok=tok)[0] == 401)
ok("verification is one-time", call("POST", "/api/password/reset", {"phone": reg_phone, "wa": True, "new_password": "another1234"})[0] == 400)
c = db(); c.execute("INSERT OR REPLACE INTO phone_verifications(phone,purpose,code,expires,attempts,verified_at,created_at) VALUES(?,?,?,?,0,?,?)", (reg_phone, "register", "123456", int(time.time()) + 600, int(time.time()), int(time.time()))); c.commit(); c.close()
ok("a register-verification cannot be used to reset", call("POST", "/api/password/reset", {"phone": reg_phone, "wa": True, "new_password": "another1234"})[0] == 400)
ac = start("01000000000", "reset")[1]["code"]; ingest("201000000000", ac)
ok("admin account cannot be reset via WhatsApp", call("POST", "/api/password/reset", {"phone": "01000000000", "wa": True, "new_password": "hacked12345"})[0] == 400 and call("POST", "/api/login", {"phone": "01000000000", "password": "AdminPass123"})[0] == 200)

# --- التأكيد اليدوي من الإدارة (رقم واتساب عادي بدون API)
code = start("01111111109")[1]["code"]; at = admin(); tok = call("POST", "/api/login", {"phone": reg_phone, "password": "newpass999"})[1]["token"]
lst = call("GET", "/api/admin/verifications", tok=at)[1]
ok("admin sees pending phone but NOT the code", any(x["phone"] == "01111111109" for x in lst) and all("code" not in x for x in lst))
ok("customer cannot use admin endpoints", call("GET", "/api/admin/verifications", tok=tok)[0] == 403 and call("POST", "/api/admin/verifications/confirm", {"phone": "01111111109", "code": code}, tok=tok)[0] == 403)
ok("admin confirm with wrong code -> 400", call("POST", "/api/admin/verifications/confirm", {"phone": "01111111109", "code": "000000" if code != "000000" else "111111"}, tok=at)[0] == 400 and status("01111111109") is False)
ok("admin confirm with the code from the message -> verified", call("POST", "/api/admin/verifications/confirm", {"phone": "01111111109", "code": code}, tok=at)[0] == 200 and status("01111111109") is True)
ok("manual confirmation audited", sqlite3.connect(server.DB).execute("SELECT COUNT(*) FROM audit_log WHERE action='phone.verified' AND target='01111111109'").fetchone()[0] == 1)
ok("then the customer registers", reg("01111111109") == 201)
os.environ.pop("LAQINO_WA_VERIFY", None)
print("ALL PASSED")
