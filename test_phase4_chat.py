# المرحلة 4: محادثة سوق لاقينو (chat.py) + اختيار البائع لطريقة التواصل. قاعدة مؤقتة. اختبار API + فحص نصي للواجهة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8794), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8794"; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__))
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
SELLER, B1, B2, B3, OTHER = "01055550001", "01055550002", "01055550003", "01055550004", "01055550005"
tk = {p: user(p) for p in (SELLER, B1, B2, B3, OTHER)}; uid = {p: call("GET", "/me", None, t)[1]["id"] for p, t in tk.items()}
root = sql("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "أجهزة", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [x for x in call("GET", "/categories?section=souq")[1] if x["parent_id"]][0]["id"]
def listing(title, mode=None, approve=True, anonymous=False):
    body = {"category_id": cat, "region_id": 3, "title": title}
    if mode: body["contact_mode"] = mode
    if anonymous: body["anonymous"] = True
    s, r = call("POST", "/listings", body, tk[SELLER]); assert s == 201, (s, r)
    if approve: call("POST", f"/admin/listings/{r['id']}/review", {"status": "approved"}, at)
    return r["id"]

# ---------- المخطط والوضع الافتراضي
cols = {r[1] for r in sql("PRAGMA table_info(listings)")}
ok("listings.contact_mode column + chat tables exist", "contact_mode" in cols and {"chat_threads", "chat_messages", "chat_reports"} <= {r[0] for r in sql("select name from sqlite_master where type='table'")})
import chat
c0 = server.db(); chat.install(c0); chat.install(c0); c0.close(); ok("chat.install is idempotent", True)
Ld = listing("افتراضي"); Lc = listing("محادثة فقط", "chat"); Lp = listing("رقم فقط", "phone"); Lb = listing("الاثنان", "both"); Lpend = listing("معلّق", "chat", approve=False)
ok("default contact_mode is 'both' (keeps current behaviour)", call("GET", f"/listings/{Ld}")[1]["contact_mode"] == "both")
ok("listing created with contact_mode=chat", call("GET", f"/listings/{Lc}")[1]["contact_mode"] == "chat")
ok("invalid contact_mode on create -> 400", call("POST", "/listings", {"category_id": cat, "region_id": 3, "title": "خطأ", "contact_mode": "x"}, tk[SELLER])[0] == 400)

# ---------- اختيار البائع / رقم البائع
ok("phone endpoint refused (403) when seller chose chat only", call("GET", f"/listings/{Lc}/contact", None, tk[B1])[0] == 403)
ok("phone still given for phone/both/default", all(call("GET", f"/listings/{i}/contact", None, tk[B1])[1].get("phone") == SELLER for i in (Lp, Lb, Ld)))
ok("owner still reads own contact on chat-only listing", call("GET", f"/listings/{Lc}/contact", None, tk[SELLER])[0] == 200)
ok("contact anon still 401", call("GET", f"/listings/{Lc}/contact")[0] == 401)
ok("only owner can set mode (others 404, anon 401)", call("POST", f"/listings/{Lb}/contact-mode", {"mode": "chat"}, tk[B1])[0] == 404 and call("POST", f"/listings/{Lb}/contact-mode", {"mode": "chat"})[0] == 401)
ok("invalid mode -> 400", call("POST", f"/listings/{Lb}/contact-mode", {"mode": "sms"}, tk[SELLER])[0] == 400 and call("POST", f"/listings/{Lb}/contact-mode", {}, tk[SELLER])[0] == 400)
ok("owner switches both -> chat hides number", call("POST", f"/listings/{Lb}/contact-mode", {"mode": "chat"}, tk[SELLER])[0] == 200 and call("GET", f"/listings/{Lb}/contact", None, tk[B1])[0] == 403)
call("POST", f"/listings/{Lb}/contact-mode", {"mode": "both"}, tk[SELLER])
ok("public listing payloads never contain a phone", SELLER not in json.dumps(call("GET", "/listings")[1]) and SELLER not in json.dumps(call("GET", f"/listings/{Lc}")[1]))

# ---------- فتح محادثة
ok("open chat requires login", call("POST", f"/listings/{Lc}/chat")[0] == 401)
ok("cannot chat on own listing", call("POST", f"/listings/{Lc}/chat", None, tk[SELLER])[0] == 400)
ok("pending / missing listing -> 404", call("POST", f"/listings/{Lpend}/chat", None, tk[B1])[0] == 404 and call("POST", "/listings/99999/chat", None, tk[B1])[0] == 404)
ok("phone-only listing refuses chat (403)", call("POST", f"/listings/{Lp}/chat", None, tk[B1])[0] == 403)
s, r = call("POST", f"/listings/{Lc}/chat", None, tk[B1]); T1 = r["thread_id"]
ok("buyer opens chat (201) and gets same thread again (200)", s == 201 and call("POST", f"/listings/{Lc}/chat", None, tk[B1]) == (200, {"thread_id": T1}))
T2 = call("POST", f"/listings/{Lc}/chat", None, tk[B2])[1]["thread_id"]; ok("each buyer has an own thread per listing", T2 != T1)
ok("both/default listings accept chat", call("POST", f"/listings/{Lb}/chat", None, tk[B3])[0] == 201 and call("POST", f"/listings/{Ld}/chat", None, tk[B3])[0] == 201)

# ---------- خصوصية الإعلان مجهول الهوية
Lan = listing("إعلان مجهول الهوية", "chat", anonymous=True)
Tan = call("POST", f"/listings/{Lan}/chat", None, tk[B2])[1]["thread_id"]
buyer_threads = call("GET", "/chats", None, tk[B2])[1]
anon_buyer_row = [x for x in buyer_threads if x["id"] == Tan][0]
seller_threads = call("GET", "/chats", None, tk[SELLER])[1]
anon_seller_row = [x for x in seller_threads if x["id"] == Tan][0]
anon_buyer_thread = call("GET", f"/chats/{Tan}", None, tk[B2])[1]["thread"]
anon_seller_thread = call("GET", f"/chats/{Tan}", None, tk[SELLER])[1]["thread"]
ok("anonymous seller identity hidden in buyer chat list and thread API", anon_buyer_row["other_name"] == "مستخدم مجهول" and anon_buyer_thread["other_name"] == "مستخدم مجهول")
ok("anonymous seller name remains available to listing owner; buyer identity not changed", anon_seller_row["other_name"] == "u02" and anon_seller_thread["other_name"] == "u02")

# ---------- الرسائل والصلاحيات
ok("non-participant cannot read / write (404)", call("GET", f"/chats/{T1}", None, tk[OTHER])[0] == 404 and call("POST", f"/chats/{T1}/messages", {"text": "x"}, tk[OTHER])[0] == 404 and call("GET", f"/chats/{T1}", None, tk[B2])[0] == 404)
ok("anon cannot read chats", call("GET", "/chats")[0] == 401 and call("GET", f"/chats/{T1}")[0] == 401)
ok("empty / whitespace / too-long message -> 400", all(call("POST", f"/chats/{T1}/messages", {"text": t}, tk[B1])[0] == 400 for t in ("", "   ", "ا" * 1001)) and call("POST", f"/chats/{T1}/messages", {})[0] == 401)
ok("buyer sends message", call("POST", f"/chats/{T1}/messages", {"text": "<b>هل ما زالت متاحة؟</b>"}, tk[B1])[0] == 201)
ok("seller reply", call("POST", f"/chats/{T1}/messages", {"text": "نعم متاحة"}, tk[SELLER])[0] == 201)
r = call("GET", "/chats", None, tk[SELLER])[1]; row = [x for x in r if x["id"] == T1][0]
ok("seller list: unread=1 from buyer, role seller, other_name set", row["unread"] == 1 and row["role"] == "seller" and row["other_name"] == "u02" and row["last"]["mine"] is True)
s, g = call("GET", f"/chats/{T1}", None, tk[SELLER])
ok("thread payload: messages in order, mine flags, body kept as plain text", [m["mine"] for m in g["messages"]] == [False, True] and g["messages"][0]["body"] == "<b>هل ما زالت متاحة؟</b>" and g["thread"]["role"] == "seller")
ok("reading marks as read (unread 0)", [x for x in call("GET", "/chats", None, tk[SELLER])[1] if x["id"] == T1][0]["unread"] == 0)
ok("after= returns only newer messages", call("GET", f"/chats/{T1}?after={g['messages'][0]['id']}", None, tk[B1])[1]["messages"][0]["body"] == "نعم متاحة" and len(call("GET", f"/chats/{T1}?after=abc", None, tk[B1])[1]["messages"]) == 2)
ok("no phone number appears in any chat payload", all(p not in json.dumps([call("GET", "/chats", None, tk[x])[1], call("GET", f"/chats/{T1}", None, tk[x])[1]]) for x in (SELLER, B1) for p in (SELLER, B1, B2)))

# ---------- الإشعارات
for _ in range(3): call("POST", f"/chats/{T1}/messages", {"text": "تفاصيل"}, tk[B1])
n = sql("select count(*),min(kind),min(link) from notifications where user_id=? and ref_type='chat' and ref_id=? and read_at is null", (uid[SELLER], T1))[0]
ok("seller notified once per thread (deduped), kind chat", n == (1, "chat", "chat"))
ok("sender gets no chat notification", sql("select count(*) from notifications where user_id=? and ref_type='chat'", (uid[B1],))[0][0] == 1)  # the one from seller's reply
ok("notif.js knows the chat link", "chat:" in open(os.path.join(HERE, "static", "notif.js"), encoding="utf8").read().split("LINKS =")[1][:600])

# ---------- الحد من الإرسال
Tr = call("POST", f"/listings/{Ld}/chat", None, tk[B3])[1]["thread_id"]; codes = [call("POST", f"/chats/{Tr}/messages", {"text": "م" + str(i)}, tk[B3])[0] for i in range(22)]
ok("rate limit: 20 messages/min then 429", codes[:20] == [201] * 20 and codes[20] == 429)

# ---------- الحظر
ok("block: stops messages for both sides", call("POST", f"/chats/{T1}/block", {"block": True}, tk[SELLER])[1]["blocked"] is True and call("POST", f"/chats/{T1}/messages", {"text": "x"}, tk[B1])[0] == 403 and call("POST", f"/chats/{T1}/messages", {"text": "x"}, tk[SELLER])[0] == 403)
ok("other side cannot lift a block; blocker can", call("POST", f"/chats/{T1}/block", {"block": False}, tk[B1])[0] == 403 and call("POST", f"/chats/{T1}/block", {"block": False}, tk[SELLER])[1]["blocked"] is False and call("POST", f"/chats/{T1}/messages", {"text": "عدنا"}, tk[B1])[0] == 201)

# ---------- بلاغ وإدارة
ok("admin endpoints: anon 401, user 403", call("GET", "/admin/chats/reports")[0] == 401 and call("GET", "/admin/chats/reports", None, tk[B1])[0] == 403 and call("GET", f"/admin/chats/{T1}", None, tk[B1])[0] == 403)
ok("admin cannot read an unreported chat", call("GET", f"/admin/chats/{T1}", None, at)[0] == 404)
ok("report validation + non-participant 404", call("POST", f"/chats/{T1}/report", {"reason": "x"}, tk[B1])[0] == 400 and call("POST", f"/chats/{T1}/report", {"reason": "إساءة"}, tk[OTHER])[0] == 404)
ok("participant reports", call("POST", f"/chats/{T1}/report", {"reason": "ألفاظ مسيئة"}, tk[SELLER])[0] == 200 and call("POST", f"/chats/{T1}/report", {"reason": "ألفاظ مسيئة"}, tk[SELLER])[0] == 200)
rp = call("GET", "/admin/chats/reports", None, at)[1]; ok("admin sees one open report (duplicate ignored)", len(rp) == 1 and rp[0]["thread_id"] == T1 and rp[0]["reporter"] == "u01")
a = call("GET", f"/admin/chats/{T1}", None, at)[1]; ok("admin reads reported chat, no phones", len(a["messages"]) >= 5 and a["messages"][0]["from"] == "buyer" and SELLER not in json.dumps(a) and B1 not in json.dumps(a))
ok("resolve report", call("POST", f"/admin/chats/reports/{rp[0]['id']}/resolve", {"status": "bad"}, at)[0] == 400 and call("POST", f"/admin/chats/reports/{rp[0]['id']}/resolve", {"status": "resolved"}, at)[0] == 200 and call("GET", "/admin/chats/reports", None, at)[1] == [] and call("POST", f"/admin/chats/reports/{rp[0]['id']}/resolve", {"status": "resolved"}, at)[0] == 404)

# ---------- إعلان لم يعد متاحًا
call("POST", f"/listings/{Lc}/delete", {}, tk[SELLER])
ok("deleted listing: new chats 404, existing thread messages 409, history still readable", call("POST", f"/listings/{Lc}/chat", None, tk[OTHER])[0] == 404 and call("POST", f"/chats/{T1}/messages", {"text": "x"}, tk[B1])[0] == 409 and call("GET", f"/chats/{T1}", None, tk[B1])[0] == 200)

# ---------- حد فتح المحادثات يوميًا
c1 = sqlite3.connect(DB)
for i in range(30): c1.execute("insert into chat_threads(listing_id,buyer_id,seller_id,created_at,last_message_at) values(?,?,?,?,?)", (100000 + i, uid[OTHER], uid[SELLER], int(time.time()), 0))
c1.commit(); c1.close()
ok("daily new-thread cap (30) -> 429", call("POST", f"/listings/{Ld}/chat", None, tk[OTHER])[0] == 429)

# ---------- الواجهة (نصي)
M = open(os.path.join(HERE, "static", "market.html"), encoding="utf8").read()
ok("market.html: chat + phone actions, contact-mode chooser, chats routes", all(k in M for k in ("/chat", "/contact", "contact-mode", "#/chats", "#/chat/")))
ok("market.html: messages inserted with textContent (no innerHTML)", ".innerHTML" not in M and "innerHTML =" not in M)


# ---------- إيقاظ الأجهزة (Web Push) للمحادثة + مسارات الاشتراك العامة
os.environ["LAQINO_PUSH_ALLOW_ANY"] = "1"
from http.server import BaseHTTPRequestHandler
HITS = []
class Cap(BaseHTTPRequestHandler):
    def do_POST(self):
        HITS.append((self.path, self.headers.get("Authorization", ""), self.headers.get("Content-Length"))); self.send_response(201); self.end_headers()
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8796), Cap).serve_forever, daemon=True).start()
EP = lambda n: f"http://127.0.0.1:8796/p/{n}"
ok("push key/subscribe need login", call("GET", "/push/key")[0] == 401 and call("POST", "/push/subscribe", {"endpoint": EP("x")})[0] == 401 and call("POST", "/push/unsubscribe", {"endpoint": EP("x")})[0] == 401)
ok("any logged-in user gets the VAPID key", len(call("GET", "/push/key", None, tk[B1])[1]["key"]) > 20)
ok("invalid endpoint -> 400", call("POST", "/push/subscribe", {"endpoint": "ftp://x"}, tk[B1])[0] == 400 and call("POST", "/push/subscribe", {}, tk[B1])[0] == 400)
Lq = listing("للإيقاظ", "chat"); Tq = call("POST", f"/listings/{Lq}/chat", None, tk[B1])[1]["thread_id"]
ok("subscribe seller + buyer devices", call("POST", "/push/subscribe", {"endpoint": EP("seller")}, tk[SELLER])[0] == 200 and call("POST", "/push/subscribe", {"endpoint": EP("buyer")}, tk[B1])[0] == 200)
chat.PUSH_GAP = 30; HITS.clear(); call("POST", f"/chats/{Tq}/messages", {"text": "مرحبا"}, tk[B1]); time.sleep(1.2)
ok("new message wakes ONLY the recipient's device (empty data-less push, VAPID auth)", [h[0] for h in HITS] == ["/p/seller"] and HITS[0][1].startswith("vapid ") and HITS[0][2] == "0")
call("POST", f"/chats/{Tq}/messages", {"text": "تاني"}, tk[B1]); time.sleep(1.0)
ok("second message within the gap is throttled (no extra push)", len(HITS) == 1)
chat.PUSH_GAP = 0; call("POST", f"/chats/{Tq}/messages", {"text": "ثالث"}, tk[B1]); time.sleep(1.2)
ok("push again once the gap allows", len(HITS) == 2)
st = call("POST", "/push/state", {"endpoint": EP("seller")})[1]
ok("push state returns counts/flags only (chat unread, medical unread, pending, courier)", set(st) == {"pending", "chat", "medical", "courier"} and st["pending"] == 0 and st["medical"] >= 0 and st["courier"] is False and st["chat"] >= 3)
call("GET", f"/chats/{Tq}", None, tk[SELLER])
ok("reading the thread lowers the unread count by its 3 messages", call("POST", "/push/state", {"endpoint": EP("seller")})[1]["chat"] == st["chat"] - 3)
ok("unknown endpoint -> zeros (no information leak)", call("POST", "/push/state", {"endpoint": EP("nobody")})[1] == {"pending": 0, "chat": 0, "medical": 0, "courier": False})
call("POST", "/push/unsubscribe", {"endpoint": EP("seller")}, tk[SELLER]); HITS.clear(); chat.PUSH_GAP = 0
call("POST", f"/chats/{Tq}/messages", {"text": "بعد الإيقاف"}, tk[B1]); time.sleep(1.0)
ok("after unsubscribe no push is sent; the message still succeeds", HITS == [])
for i in range(5): call("POST", "/push/subscribe", {"endpoint": EP("m%d" % i)}, tk[B3])
ok("device cap per user (5) -> 400", call("POST", "/push/subscribe", {"endpoint": EP("m6")}, tk[B3])[0] == 400)
chat.PUSH_GAP = 30

# ---------- إعلاناتي (index) / بلاغات الإدارة (admin) / زر الإشعارات (market)
ok("/my/listings returns contact_mode", all("contact_mode" in x for x in call("GET", "/my/listings", None, tk[SELLER])[1]))
I2 = open(os.path.join(HERE, "static", "index.html"), encoding="utf8").read(); A = open(os.path.join(HERE, "static", "admin.html"), encoding="utf8").read(); M2 = open(os.path.join(HERE, "static", "market.html"), encoding="utf8").read()
ok("index.html: my listings can change contact mode (select + sm handler -> contact-mode)", "window.sm=run" in I2 and "/contact-mode" in I2 and 'id="cm${x.id}"' in I2)
ok("admin.html: chat reports tab (list, view thread, resolve/dismiss)", "chats:'بلاغات المحادثات'" in A and "/admin/chats/reports" in A and "window.vc=" in A and "'/admin/chats/'+tid" in A and "status:'resolved'" in A and "status:'dismissed'" in A)
ok("admin.html: chat text is escaped", "${esc(m.body)}" in A and "${esc(x.reason)}" in A)
ok("market.html: push on/off wired to /api/push/*, SW registered", all(k in M2 for k in ("/api/push/key", "/api/push/subscribe", "/api/push/unsubscribe", 'register("/sw.js")', "pushBox()")))

# ---------- index.html (التطبيق الرئيسي): خيار الطريقة في نموذج الإنشاء + أزرار البطاقة
I = open(os.path.join(HERE, "static", "index.html"), encoding="utf8").read()
ok("index.html: creation form has contact-mode chooser and sends contact_mode", 'id="lcm"' in I and "contact_mode:$('lcm').value" in I and all(v in I for v in ('value="both"', 'value="chat"', 'value="phone"')))
ok("index.html: card shows chat button unless phone-only, phone button unless chat-only", "onclick=\"cm(${l.id})\"" in I and "l.contact_mode=='phone'?''" in I and "l.contact_mode=='chat'?''" in I and "window.cm=run" in I)
ok("public list payload carries contact_mode (no phone)", all("contact_mode" in x and "phone" not in x for x in call("GET", "/listings")[1]))
print("ALL PASSED")
