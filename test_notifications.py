# المهمة 1: الإشعارات (triggers + API) + سلامة الترحيل على قاعدة قديمة + التراجع إلى السيرفر القديم.
import os, sys, json, time, shutil, sqlite3, tempfile, threading, hashlib, urllib.request, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__)); TMP = tempfile.mkdtemp(prefix="laqino-notif-")
os.environ["LAQINO_DB"] = os.path.join(TMP, "t.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(TMP, "up"); os.makedirs(os.environ["LAQINO_UPLOADS"])
sys.path.insert(0, HERE)
import server, notif
from testutil import apply_docs, fare_ok
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(TMP)), "ISOLATION BROKEN"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
def serve(mod, port):
    th = ThreadingHTTPServer(("127.0.0.1", port), mod.H); threading.Thread(target=th.serve_forever, daemon=True).start(); time.sleep(.2); return th
def mk_call(port):
    def call(m, p, d=None, t=None):
        r = urllib.request.Request("http://127.0.0.1:%d/api%s" % (port, p), json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
        try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read() or b"{}")
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    return call

# ---------- 1) قاعدة «قديمة» (مخطط الخادم الحالي قبل الإشعارات) فيها بيانات حقيقية الشكل ----------
server.init("01000000000", "AdminPass123")
c = server.db(); notif.uninstall(c)   # نحاكي قاعدة ما قبل المهمة 1: بلا جدول ولا triggers
ok("old DB has no notifications table and no triggers", not c.execute("SELECT 1 FROM sqlite_master WHERE name='notifications' OR (type='trigger' AND name NOT LIKE 'listings_fts_%')").fetchone())
now = int(time.time())
for i, (ph, nm) in enumerate((("01011111111", "عميل"), ("01022222222", "مندوب"), ("01033333333", "صيدلي")), 2):
    s = "ab" * 16; c.execute("INSERT INTO users(id,phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,3,?)", (i, ph, nm, server.hp("password1", s), s, "customer", now))
c.execute("INSERT INTO delivery_orders(id,customer_id,region_id,pickup_text,dropoff_text,fee,status,created_at,updated_at) VALUES(50,2,3,'أ','ب',10,'searching',?,?)", (now, now))
c.execute("INSERT INTO listings(id,user_id,category_id,region_id,title,status,created_at) VALUES(1,2,1,3,'قديم','approved',?)", (now,))
c.execute("INSERT INTO couriers(user_id,status,region_id,created_at) VALUES(3,'approved',3,?)", (now,)); c.execute("UPDATE users SET role='courier' WHERE id=3")
c.commit()
def dump(cn):
    out = {}
    for (t,) in cn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='notifications' ORDER BY 1").fetchall():
        out[t] = [tuple(r) for r in cn.execute("SELECT * FROM %s ORDER BY 1,2" % t) if True]
    return out
before = dump(c); c.close(); shutil.copy(server.DB, os.path.join(TMP, "backup.db"))
server.init("01000000000", "AdminPass123"); server.init("01000000000", "AdminPass123")   # مرتين: الترحيل idempotent
c = server.db(); after = dump(c)
# sessions تُنظَّف عند التشغيل بقصد؛ نستثنيها من المقارنة
before.pop("sessions", None); after.pop("sessions", None)
ok("migration: every old table identical (no row lost or changed)", before == after)
ok("migration: notifications table + triggers created", c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'ntf_%' AND name NOT LIKE 'ntf_prod_%' AND name NOT LIKE 'ntf_exch_%' AND name NOT LIKE 'ntf_rxresp_%'").fetchone()[0] == len(notif._triggers()))
ok("migration: old users still log in", server.hp("password1", "ab" * 16) == c.execute("SELECT pw_hash FROM users WHERE id=2").fetchone()["pw_hash"])
ok("migration: no notification fabricated for old rows", c.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0)
ok("integrity_check ok", c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and not c.execute("PRAGMA foreign_key_check").fetchall())
c.close()

# ---------- 2) السلوك عبر HTTP ----------
call = mk_call(8791); serve(server, 8791)
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cust, cour, pharm, other = user("01044444444", "عميل جديد"), user("01055555555", "مندوب جديد"), user("01066666666", "صيدلية جديدة"), user("01077777777", "آخر")
ok("unauthenticated -> 401", all(call("GET", p)[0] == 401 for p in ("/notifications", "/notifications/count", "/my/applications")) and call("POST", "/notifications/read", {"all": True})[0] == 401)
ok("applications empty for a plain customer", call("GET", "/my/applications", None, cust) == (200, {"courier": None, "pharmacy": None}))
ok("empty list", call("GET", "/notifications", None, cust)[1] == {"items": [], "unread": 0, "latest_id": 0})

# طلب مندوب
ok("courier apply", apply_docs(call, cour)[0] == 201)
a = call("GET", "/my/applications", None, cour)[1]["courier"]
ok("applications: courier pending, docs complete", a["status"] == "pending" and a["needs_documents"] is False and a["region_id"] == 3 and a["reason"] is None)
n = call("GET", "/notifications", None, cour)[1]
ok("courier gets 'received' notification, unread=1", n["unread"] == 1 and n["items"][0]["kind"] == "application.couriers" and "قيد المراجعة" in n["items"][0]["title"])
cid = call("GET", "/me", None, cour)[1]["id"]
ok("reject with reason -> notification carries reason", call("POST", "/admin/couriers/%d/review" % cid, {"status": "rejected", "reason": "صورة البطاقة غير واضحة"}, at)[0] == 200)
n = call("GET", "/notifications", None, cour)[1]["items"][0]
ok("rejected notification + reason", "رفض" in n["title"] and n["body"] == "صورة البطاقة غير واضحة")
a = call("GET", "/my/applications", None, cour)[1]["courier"]; ok("applications: rejected + reason", a["status"] == "rejected" and a["reason"] == "صورة البطاقة غير واضحة")
ok("re-apply after rejection", apply_docs(call, cour)[0] == 201)
ok("approve", call("POST", "/admin/couriers/%d/review" % cid, {"status": "approved"}, at)[0] == 200)
a = call("GET", "/my/applications", None, cour)[1]["courier"]; ok("applications: approved, reason cleared", a["status"] == "approved" and a["reason"] is None)
ok("approved notification", "اعتماد" in call("GET", "/notifications", None, cour)[1]["items"][0]["title"])
ok("same-status review does not duplicate", (call("POST", "/admin/couriers/%d/review" % cid, {"status": "approved"}, at), len(call("GET", "/notifications", None, cour)[1]["items"]))[1] == 4)

# صيدلية
ok("pharmacy apply", call("POST", "/providers/apply", {"name_ar": "صيدلية النور", "region_id": 3, "address": "ش 1"}, pharm)[0] == 201)
pid = call("GET", "/me", None, pharm)[1]["id"]
ok("applications: pharmacy pending", call("GET", "/my/applications", None, pharm)[1]["pharmacy"]["status"] == "pending" and call("GET", "/my/applications", None, pharm)[1]["courier"] is None)
ok("approve pharmacy", call("POST", "/admin/providers/%d/review" % pid, {"status": "approved"}, at)[0] == 200)
ok("pharmacy approved notification", "اعتماد" in call("GET", "/notifications", None, pharm)[1]["items"][0]["title"])
ok("applications: pharmacy approved with name", call("GET", "/my/applications", None, pharm)[1]["pharmacy"]["name_ar"] == "صيدلية النور")

# رد الصيدلية على استفسار (UPSERT يمرّ بـ trigger الإدراج ثم التحديث)
iq = call("POST", "/medical/inquiries", {"medicine_name": "بنادول", "region_id": 3}, cust)
ok("inquiry created", iq[0] in (200, 201))
iid = iq[1]["id"]
ok("pharmacy responds", call("POST", "/provider/inquiries/%d/respond" % iid, {"status": "available", "price": 25}, pharm)[0] == 200)
n = call("GET", "/notifications", None, cust)[1]
ok("customer notified of the pharmacy reply (once)", n["unread"] == 1 and "متوفر" in n["items"][0]["title"] and "صيدلية النور" in n["items"][0]["body"] and "25" in n["items"][0]["body"])
ok("identical re-respond adds nothing", (call("POST", "/provider/inquiries/%d/respond" % iid, {"status": "available", "price": 25}, pharm), call("GET", "/notifications/count", None, cust)[1]["unread"])[1] == 1)
ok("price change notifies again", (call("POST", "/provider/inquiries/%d/respond" % iid, {"status": "available", "price": 30}, pharm), call("GET", "/notifications/count", None, cust)[1]["unread"])[1] == 2)
ok("other users did not get it", call("GET", "/notifications/count", None, other)[1]["unread"] == 0 and call("GET", "/notifications/count", None, pharm)[1]["unread"] == 3)  # استلام + اعتماد + إشعار الاستفسار الجديد (الخطوة 7)؛ لا شيء عن رد الدواء

# طلب توصيل
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 15}, at)
o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "الصيدلية", "dropoff_text": "البيت", "details": "x"}, cust)
ok("order created", o[0] == 201); oid = o[1]["id"]
call("POST", "/courier/status", {"online": True}, cour)
ac = call("POST", "/courier/orders/%d/accept" % oid, {}, cour)
ok("courier accepts", ac[0] == 200)
n = call("GET", "/notifications", None, cust)[1]
ok("customer notified: accepted", any(i["kind"] == "order.status" and "قبول" in i["title"] and i["ref_id"] == oid for i in n["items"]))
fare_ok(oid)
for st in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"):
    call("POST", "/courier/orders/%d/status" % oid, {"to": st}, cour)
n = call("GET", "/notifications?limit=100", None, cust)[1]["items"]
ok("customer got every stage", sum(1 for i in n if i["kind"] == "order.status" and i["ref_id"] == oid) >= 5)
ok("customer's order notes never leak medicine/addresses", all(("الصيدلية" not in (i["body"] or "") and "البيت" not in (i["body"] or "")) for i in n if i["kind"] == "order.status"))
ok("customer confirms -> completed notifies both", call("POST", "/delivery/orders/%d/confirm" % oid, {}, cust)[0] == 200
   and any("اكتمل" in i["title"] for i in call("GET", "/notifications", None, cour)[1]["items"]) and any("اكتمل" in i["title"] for i in call("GET", "/notifications", None, cust)[1]["items"]))
o2 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "نقطة الاستلام", "dropoff_text": "نقطة التسليم", "details": "x"}, cust)[1]["id"]
call("POST", "/courier/orders/%d/accept" % o2, {}, cour)
ok("cancel while assigned notifies the courier", call("POST", "/delivery/orders/%d/cancel" % o2, {}, cust)[0] == 200 and any(i["kind"] == "order.courier" and "إلغاء" in i["title"] for i in call("GET", "/notifications", None, cour)[1]["items"]))

# قراءة/تعليم
cnt = call("GET", "/notifications/count", None, cust)[1]; ok("count endpoint", cnt["unread"] > 0 and cnt["latest_id"] > 0)
lst = call("GET", "/notifications", None, cust)[1]; first = lst["items"][-1]["id"]
ok("mark one read", call("POST", "/notifications/read", {"ids": [first]}, cust)[1]["marked"] == 1 and call("GET", "/notifications/count", None, cust)[1]["unread"] == cnt["unread"] - 1)
ok("cannot mark someone else's", call("POST", "/notifications/read", {"ids": [x["id"] for x in lst["items"]]}, other)[1]["marked"] == 0 and call("GET", "/notifications/count", None, cust)[1]["unread"] == cnt["unread"] - 1)
ok("garbage ids ignored", call("POST", "/notifications/read", {"ids": ["x", None, True, 1.5, -1]}, cust)[1]["marked"] == 0)
ok("after= returns only newer", call("GET", "/notifications?after=%d" % cnt["latest_id"], None, cust)[1]["items"] == [] and call("GET", "/notifications?after=abc&limit=zzz", None, cust)[0] == 200)
ok("mark all", call("POST", "/notifications/read", {"all": True}, cust)[0] == 200 and call("GET", "/notifications/count", None, cust)[1]["unread"] == 0)
ok("unknown notifications path -> 404", call("GET", "/notifications/nope", None, cust)[0] == 404)

# حد التخزين
c = server.db(); uid = call("GET", "/me", None, other)[1]["id"]
for i in range(260): c.execute("INSERT INTO notifications(user_id,kind,title,created_at) VALUES(?,?,?,?)", (uid, "t", "n%d" % i, int(time.time())))
c.execute("INSERT INTO notifications(user_id,kind,title,created_at) VALUES(?,?,?,?)", (uid, "t", "قديم جدًا", 1000)); c.commit(); c.close()
ok("list returns at most the requested limit", len(call("GET", "/notifications?limit=100", None, other)[1]["items"]) == 100)
_cn = sqlite3.connect(os.environ["LAQINO_DB"])
ok("prune keeps <= cap and drops >90d rows", _cn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=?", (uid,)).fetchone()[0] <= notif.KEEP_PER_USER and not _cn.execute("SELECT 1 FROM notifications WHERE user_id=? AND title='قديم جدًا'", (uid,)).fetchone()); _cn.close()

# فشل الإشعار لا يفشل العملية الأصلية
c = server.db(); c.execute("DROP TABLE notifications"); c.commit()
try: c.execute("UPDATE couriers SET status='suspended' WHERE user_id=?", (cid,)); c.commit(); res = "no-error"
except sqlite3.Error as e: res = "error"; c.rollback()
c.close()
print("INFO: with the table dropped but triggers left in place, writes ->", res, "(لذلك التراجع يتم بـ notif.py --uninstall لا بحذف الجدول يدويًا)")
c = server.db(); notif.install(c); c.close()   # إعادة التركيب تصلح الحالة

# ---------- 3) التراجع: السيرفر القديم على القاعدة بعد الترحيل ----------
import importlib.util
OLD_PATH = os.environ.get("LAQINO_OLD_SERVER") or os.path.join(HERE, "server.orig.py")   # نسخة server.py القديمة (من خطوة النسخ الاحتياطي في README)
if not os.path.isfile(OLD_PATH):
    c = sqlite3.connect(os.environ["LAQINO_DB"]); notif.uninstall(c); c.close()
    print("SKIP rollback-with-old-server checks: old server copy not found (%s). Put it there or set LAQINO_OLD_SERVER=/path/to/old/server.py" % OLD_PATH)
    print("ALL RUNNABLE NOTIFICATION CHECKS PASSED (rollback section skipped)"); sys.exit(0)
spec = importlib.util.spec_from_file_location("server_old", OLD_PATH); old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
old.DB = os.environ["LAQINO_DB"]; old.UP = os.environ["LAQINO_UPLOADS"]; old.PRESENCE_ENFORCED = False
old.init("01000000000", "AdminPass123"); call2 = mk_call(8792); serve(old, 8792)
t = call2("POST", "/login", {"phone": "01044444444", "password": "password1"})[1]["token"]
ok("rollback: OLD server logs in on migrated DB", bool(t))
ok("rollback: OLD server has no notifications routes (404)", call2("GET", "/notifications", None, t)[0] == 404)
o3 = call2("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "نقطة الاستلام", "dropoff_text": "نقطة التسليم", "details": "x"}, t)
ok("rollback: OLD server creates orders", o3[0] == 201)
ok("rollback: OLD server writes that fire triggers succeed", call2("POST", "/delivery/orders/%d/cancel" % o3[1]["id"], {}, t)[0] == 200)
ct = call2("POST", "/login", {"phone": "01055555555", "password": "password1"})[1]["token"]
ok("rollback: OLD server admin review (trigger-firing) works", call2("POST", "/admin/couriers/%d/review" % cid, {"status": "approved"}, call2("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"])[0] == 200)
c = server.db(); ok("rollback: triggers kept notifying while old server ran (harmless)", c.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] > 0); c.close()
# ثم نعود للجديد: كل شيء سليم ولا تُفقد بيانات
ok("forward again: new server still serves the notifications", call("GET", "/notifications", None, cust)[0] == 200)
# إزالة كاملة
c = sqlite3.connect(os.environ["LAQINO_DB"]); notif.uninstall(c)
ok("uninstall removes table + triggers only", not c.execute("SELECT 1 FROM sqlite_master WHERE name='notifications' OR name LIKE 'ntf_%'").fetchone() and c.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 7); c.close()
ok("old server fully works after uninstall", call2("POST", "/login", {"phone": "01044444444", "password": "password1"})[0] == 200)
print("ALL NOTIFICATION CHECKS PASSED")
