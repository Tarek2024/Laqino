# الخطوة 1: صور الشات (chat.py) + تسجيل اطلاع الإدارة في audit_log. قاعدة ورفع مؤقتان، منفذ حر تلقائي.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, base64, socket
_DB = tempfile.mktemp(suffix=".db"); _UP = tempfile.mkdtemp()
os.environ["LAQINO_DB"] = _DB; os.environ["LAQINO_UPLOADS"] = _UP
import server, chat
from http.server import ThreadingHTTPServer
from phase16_imgutil import png_bytes, _chunk
assert os.path.realpath(server.DB if hasattr(server, "DB") else _DB).startswith(os.path.realpath(tempfile.gettempdir())), "ISOLATION BROKEN"
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % PORT; DB = _DB; HERE = os.path.dirname(os.path.abspath(__file__))
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def raw(p, t=None):
    r = urllib.request.Request(BASE + "/api" + p, headers={"Authorization": "Bearer " + t} if t else {})
    try: x = urllib.request.urlopen(r); return x.status, dict(x.headers), x.read()
    except urllib.error.HTTPError as e: return e.code, dict(e.headers), e.read()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
b64 = lambda b: base64.b64encode(b).decode()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
SELLER, B1, B2, OTHER, STAFF = "01066660001", "01066660002", "01066660003", "01066660004", "01066660005"
tk = {p: user(p) for p in (SELLER, B1, B2, OTHER)}
root = sql("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "أجهزة", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [x for x in call("GET", "/categories?section=souq")[1] if x["parent_id"]][0]["id"]
def listing(title):
    s, r = call("POST", "/listings", {"category_id": cat, "region_id": 3, "title": title}, tk[SELLER]); assert s == 201, (s, r)
    call("POST", f"/admin/listings/{r['id']}/review", {"status": "approved"}, at); return r["id"]
L = listing("جهاز للصور")
tid = call("POST", f"/listings/{L}/chat", None, tk[B1])[1]["thread_id"]

# ---------- المخطط
ok("chat_messages.file_id column exists", "file_id" in {r[1] for r in sql("PRAGMA table_info(chat_messages)")})
c0 = server.db(); chat.install(c0); chat.install(c0)
ok("chat.install idempotent with the new column", True)
try:
    c0.execute("ALTER TABLE chat_messages DROP COLUMN file_id"); c0.commit()
    chat.install(c0); ok("migration re-adds file_id on an old schema without losing rows", "file_id" in {r[1] for r in c0.execute("PRAGMA table_info(chat_messages)")})
except sqlite3.OperationalError:
    print("SKIP drop-column migration check (sqlite too old)")
c0.close()

# ---------- إرسال صورة
good = png_bytes(32, 32)
exif = good[:33] + _chunk(b"tEXt", b"Comment\x00SECRET-GPS-LOCATION") + good[33:]
s, r = call("POST", f"/chats/{tid}/images", {"data": b64(exif)}, tk[B1])
ok("buyer sends an image -> 201", s == 201 and r.get("image") is True)
mid = r["id"]
fid = sql("select file_id from chat_messages where id=?", (mid,))[0][0]
path = sql("select path from files where id=?", (fid,))[0][0]
stored = open(os.path.join(_UP, path), "rb").read()
ok("stored image has its metadata stripped (no tEXt / secret)", b"tEXt" not in stored and b"SECRET-GPS" not in stored and stored[:4] == b"\x89PNG")
ok("image-only message stores an empty body", sql("select body from chat_messages where id=?", (mid,))[0][0] == "")
s, r = call("GET", f"/chats/{tid}", None, tk[SELLER])
m0 = [x for x in r["messages"] if x["id"] == mid][0]
ok("seller sees the message flagged image (no file id / path leaked)", s == 200 and m0["image"] is True and "file_id" not in json.dumps(r) and path not in json.dumps(r))
st, hd, body = raw(f"/chats/{tid}/images/{mid}", tk[SELLER])
ok("seller downloads the image (png, private/no-store)", st == 200 and body == stored and hd.get("Content-Type", "").startswith("image/png") and "no-store" in hd.get("Cache-Control", ""))
ok("sender downloads own image", raw(f"/chats/{tid}/images/{mid}", tk[B1])[0] == 200)
ok("seller got a chat notification for the image", sql("select count(*) from notifications where user_id=? and ref_type='chat' and ref_id=?", (call("GET", "/me", None, tk[SELLER])[1]["id"], tid))[0][0] >= 1)

# ---------- صلاحيات الاطلاع
ok("another user cannot fetch the image (404)", raw(f"/chats/{tid}/images/{mid}", tk[B2])[0] == 404 and raw(f"/chats/{tid}/images/{mid}", tk[OTHER])[0] == 404)
ok("anonymous -> 401", raw(f"/chats/{tid}/images/{mid}")[0] == 401)
ok("wrong thread id with a valid message id -> 404", raw(f"/chats/{tid + 99}/images/{mid}", tk[B1])[0] == 404)
ok("unknown message id -> 404", raw(f"/chats/{tid}/images/99999", tk[B1])[0] == 404)
ok("text message id is not an image -> 404", (lambda m2: raw(f"/chats/{tid}/images/{m2}", tk[B1])[0] == 404)(call("POST", f"/chats/{tid}/messages", {"text": "مرحبا"}, tk[B1])[1]["id"]))
ok("non-participant cannot post an image (404)", call("POST", f"/chats/{tid}/images", {"data": b64(good)}, tk[B2])[0] == 404)
ok("anonymous cannot post an image (401)", call("POST", f"/chats/{tid}/images", {"data": b64(good)})[0] == 401)
st, _, _ = raw(f"/admin/chats/{tid}/images/{mid}", tk[B1])
ok("customer cannot use the admin image route (403)", st == 403)
ok("admin cannot open an image of a thread with no report (404)", raw(f"/admin/chats/{tid}/images/{mid}", at)[0] == 404)

# ---------- التحقق من الإدخال
ok("not base64 -> 400", call("POST", f"/chats/{tid}/images", {"data": "###"}, tk[B1])[0] == 400)
ok("not an image (text bytes) -> 400", call("POST", f"/chats/{tid}/images", {"data": b64(b"hello world")}, tk[B1])[0] == 400)
ok("corrupt png -> 400", call("POST", f"/chats/{tid}/images", {"data": b64(good[:40])}, tk[B1])[0] == 400)
ok("missing data -> 400", call("POST", f"/chats/{tid}/images", {}, tk[B1])[0] == 400)
ok("oversized image (>4MB) -> 413", call("POST", f"/chats/{tid}/images", {"data": b64(b"\x89PNG" + b"0" * 4_100_000)}, tk[B1])[0] == 413)
ok("caption longer than the limit -> 400", call("POST", f"/chats/{tid}/images", {"data": b64(good), "text": "x" * 1001}, tk[B1])[0] == 400)
s, r = call("POST", f"/chats/{tid}/images", {"data": b64(png_bytes()), "text": "  هذي الصورة  "}, tk[B1])
ok("caption is saved trimmed with the image", s == 201 and sql("select body from chat_messages where id=?", (r["id"],))[0][0] == "هذي الصورة")
cap_mid = r["id"]
nfiles_before = sql("select count(*) from files")[0][0]
call("POST", f"/chats/{tid}/images", {"data": "###"}, tk[B1]); call("POST", f"/chats/{tid}/images", {"data": b64(b"nope")}, tk[B1])
ok("rejected uploads leave no file row behind", sql("select count(*) from files")[0][0] == nfiles_before)

# ---------- القائمة والعدّاد
call("POST", f"/chats/{tid}/images", {"data": b64(png_bytes())}, tk[B1])
lst = [x for x in call("GET", "/chats", None, tk[SELLER])[1] if x["id"] == tid][0]
ok("last preview shows 📷 for an image-only message", lst["last"]["body"] == "📷 صورة" and lst["last"]["image"] is True)
ok("image messages count as unread for the other side", lst["unread"] >= 3)

# ---------- ملفات: السقف والحذف
cc = server.db(); uidb1 = call("GET", "/me", None, tk[B1])[1]["id"]
ok("chat images do not consume the customer's 20-file cap", cc.execute(server.COUNT_SQL["files"], (uidb1,)).fetchone()[0] == 0); cc.close()
ok("file delete route refuses a chat image (409)", call("POST", f"/files/{fid}/delete", {}, tk[B1])[0] == 409)
ok("the file survived the refused delete", os.path.exists(os.path.join(_UP, path)))

# ---------- الحد اليومي
chat.MAX_IMAGES_DAY = len(sql("select 1 from chat_messages where sender_id=? and file_id is not null", (uidb1,))) + 1
ok("image within the daily cap -> 201", call("POST", f"/chats/{tid}/images", {"data": b64(png_bytes())}, tk[B1])[0] == 201)
ok("image over the daily cap -> 429", call("POST", f"/chats/{tid}/images", {"data": b64(png_bytes())}, tk[B1])[0] == 429)
chat.MAX_IMAGES_DAY = 30

# ---------- حظر وحالة الإعلان
ok("block the thread", call("POST", f"/chats/{tid}/block", {"block": True}, tk[SELLER])[0] == 200)
ok("blocked thread refuses images (403)", call("POST", f"/chats/{tid}/images", {"data": b64(good)}, tk[B1])[0] == 403)
ok("blocked thread still lets participants read old images", raw(f"/chats/{tid}/images/{mid}", tk[B1])[0] == 200)
call("POST", f"/chats/{tid}/block", {"block": False}, tk[SELLER])
sql("update listings set status='hidden' where id=?", (L,)) if False else sql("update listings set status='rejected' where id=?", (L,))
ok("unavailable listing refuses images (409)", call("POST", f"/chats/{tid}/images", {"data": b64(good)}, tk[B1])[0] == 409)
sql("update listings set status='approved' where id=?", (L,))

# ---------- بلاغ + اطلاع الإدارة + السجل
ok("buyer reports the thread", call("POST", f"/chats/{tid}/report", {"reason": "صور مسيئة"}, tk[B1])[0] == 200)
a0 = sql("select count(*) from audit_log where action in('chat.admin_view','chat.admin_view_image')")[0][0]
s, r = call("GET", f"/admin/chats/{tid}", None, at)
ok("admin reads the reported thread; image messages are flagged", s == 200 and any(m["image"] for m in r["messages"]) and any(not m["image"] for m in r["messages"]))
ok("admin thread view is written to audit_log with the admin as actor", sql("select count(*) from audit_log where action='chat.admin_view' and target=? and actor_id=(select id from users where phone='01000000000')", (str(tid),))[0][0] == 1)
st, hd, body = raw(f"/admin/chats/{tid}/images/{mid}", at)
ok("admin downloads the image of a reported thread (private/no-store)", st == 200 and body == stored and "no-store" in hd.get("Cache-Control", ""))
ok("admin image view is audited with the message id", sql("select detail from audit_log where action='chat.admin_view_image' and target=?", (str(tid),))[0][0].find(str(mid)) >= 0)
ok("a thread without a report is still unreadable for admin (404) and not audited", call("GET", f"/admin/chats/{tid + 50}", None, at)[0] == 404 and sql("select count(*) from audit_log where action like 'chat.admin_view%'")[0][0] == a0 + 2)
ok("audit rows do not contain message text or image bytes", "مرحبا" not in json.dumps(sql("select detail from audit_log where action like 'chat.admin_view%'")))
ok("no phone number appears in any chat/admin chat payload", SELLER not in json.dumps(call("GET", f"/chats/{tid}", None, tk[B1])[1]) and B1 not in json.dumps(call("GET", f"/admin/chats/{tid}", None, at)[1]))

# ---------- الواجهة (فحص نصي) + الكاش + الحزمة
mk = open(os.path.join(HERE, "static/market.html"), encoding="utf-8").read(); ad = open(os.path.join(HERE, "static/admin.html"), encoding="utf-8").read(); sw = open(os.path.join(HERE, "static/sw.js"), encoding="utf-8").read()
ok("market chat has an image button + file input + shrink + authenticated blob fetch", all(k in mk for k in ("shrinkImg", "chatImg", 'type: "file"', "/images", "Authorization", "createObjectURL")))
ok("market chat never puts the token in an image URL", "images?token" not in mk and "token=" not in mk)
ok("admin chat view fetches images with the admin token and shows a button per image", "vci(" in ad and "/admin/chats/'+tid+'/images/" in ad)
import re as _re
ok("service worker cache is at least v41", int(_re.search(r'laqino-v(\d+)', sw).group(1)) >= 41)
ok("sw never caches /api/ responses (chat images stay private)", 'u.pathname.startsWith("/api/")) return' in sw)
ok("Dockerfile still copies chat.py", "chat.py" in open(os.path.join(HERE, "Dockerfile"), encoding="utf-8").read())
print("ALL PASSED")
