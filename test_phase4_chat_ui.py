# المرحلة 4 (واجهة): تشغيل سكربت market.html الحقيقي في fake-DOM ضد خادم حي. ليس متصفحًا حقيقيًا (لا تخطيط/CSS).
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8795), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8795"; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__)); HAR = os.path.join(HERE, "test_market_dom_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def ui(token, hash_, steps=()):
    r = subprocess.run(["node", HAR, BASE, token or "-", hash_, json.dumps(list(steps))], capture_output=True, text=True, timeout=90)
    if r.returncode: print(r.stderr[:800])
    return json.loads(r.stdout)
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
SELLER, BUYER = "01066660001", "01066660002"; ts, tb = user(SELLER), user(BUYER)
root = sql("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "أجهزة", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [x for x in call("GET", "/categories?section=souq")[1] if x["parent_id"]][0]["id"]
def listing(title, mode):
    lid = call("POST", "/listings", {"category_id": cat, "region_id": 3, "title": title, "contact_mode": mode}, ts)[1]["id"]; call("POST", f"/admin/listings/{lid}/review", {"status": "approved"}, at); return lid
Lb, Lc, Lp = listing("إعلان الاثنين", "both"), listing("إعلان محادثة", "chat"), listing("إعلان رقم", "phone")

r = ui(tb, f"#/l/{Lb}"); ok("buyer sees both actions on 'both' listing", "راسل البائع" in r["snaps"][0] and "إظهار رقم البائع" in r["snaps"][0] and not r["errs"])
r = ui(tb, f"#/l/{Lc}"); ok("chat-only listing: chat button, no phone button", "راسل البائع" in r["snaps"][0] and "إظهار رقم البائع" not in r["snaps"][0])
r = ui(tb, f"#/l/{Lp}"); ok("phone-only listing: phone button, no chat button", "إظهار رقم البائع" in r["snaps"][0] and "راسل البائع" not in r["snaps"][0])
r = ui(tb, f"#/l/{Lb}", [{"js": "$$click('إظهار رقم البائع')"}]); ok("phone button reveals seller phone", SELLER in r["snaps"][1] and not r["errs"])
r = ui("", f"#/l/{Lb}", [{"js": "$$click('راسل البائع')"}]); ok("anonymous: chat button asks to log in (no request)", "سجّل الدخول" in r["snaps"][1] and not r["errs"])
r = ui(ts, f"#/l/{Lb}"); ok("owner sees contact-mode chooser, not buyer buttons", "طريقة تواصل المشترين" in r["snaps"][0] and "راسل البائع" not in r["snaps"][0])
r = ui(ts, f"#/l/{Lb}", [{"js": "$$tags('select').filter(function(s){return s.attrs['aria-label']==='طريقة تواصل المشترين'})[0].value='chat'; $$click('حفظ')"}])
ok("owner saves mode=chat from the UI", "تم الحفظ" in r["snaps"][1] and call("GET", f"/listings/{Lb}", None, ts)[1]["contact_mode"] == "chat" and not r["errs"])
call("POST", f"/listings/{Lb}/contact-mode", {"mode": "both"}, ts)
steps = [{"js": "$$click('راسل البائع')", "wait": 900},
         {"js": "var t=$$tags('textarea')[0]; t.value='<b>مرحبا</b> هل متاح؟'; $$click('إرسال')", "wait": 900}]
r = ui(tb, f"#/l/{Lc}", steps)
ok("buyer opens chat from listing (hash -> #/chat/<id>) and sends", r["hash"].startswith("#/chat/") and not r["errs"] and sql("select body from chat_messages")[0][0] == "<b>مرحبا</b> هل متاح؟")
ok("message rendered as literal text (no HTML injection)", "<b>مرحبا</b> هل متاح؟" in r["snaps"][2])
r = ui(ts, "#/chats"); ok("seller chats list shows listing, buyer name, unread count", "إعلان محادثة" in r["snaps"][0] and "u02" in r["snaps"][0] and "1 جديدة" in r["snaps"][0] and not r["errs"])
ok("chats list shows the notifications card (unsupported-browser note in the fake DOM)", "لا يدعم الإشعارات" in r["snaps"][0])
tid = sql("select id from chat_threads")[0][0]
r = ui(ts, f"#/chat/{tid}", [{"js": "var t=$$tags('textarea')[0]; t.value='نعم متاح'; $$click('إرسال')", "wait": 900}])
ok("seller replies from the UI", "نعم متاح" in r["snaps"][1] and not r["errs"] and sql("select count(*) from chat_messages")[0][0] == 2)
r = ui(ts, f"#/chat/{tid}", [{"js": "$$click('حظر')", "wait": 700}]); ok("block from UI blocks the thread", sql("select blocked_by from chat_threads")[0][0] is not None and not r["errs"])
r = ui(tb, f"#/chat/{tid}"); ok("blocked thread shows stopped notice to the other side", "المحادثة موقوفة" in r["snaps"][0])
r = ui("", f"#/chat/{tid}"); ok("anonymous opening chat route asks to log in", "سجّل الدخول" in r["snaps"][0])
print("ALL PASSED")
