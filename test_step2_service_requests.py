# الخطوة 2: توسيع طلب الخدمة (عنوان/وقت/ميزانية/صور) + الحالات الـ11 وخريطة الانتقالات + ترحيل الجدول القديم. قاعدة ورفع مؤقتان، منفذ حر.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, base64
_DB = tempfile.mktemp(suffix=".db"); _UP = tempfile.mkdtemp()
os.environ["LAQINO_DB"] = _DB; os.environ["LAQINO_UPLOADS"] = _UP
import server, svc
from http.server import ThreadingHTTPServer
from phase16_imgutil import png_bytes, _chunk
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % PORT; DB = _DB
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
CU, PV, PV2, OT = user("01088880001"), user("01088880002"), user("01088880003"), user("01088880004")
rid = 3; now = int(time.time())
tid = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
def prov(name, t, r=rid):
    p = call("POST", "/admin/services", {"name_ar": name, "type_id": t, "region_id": r, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
    call("POST", f"/admin/services/{p}/publish", {"published": True}, at); return p
p1, p2 = prov("المعلم سمير", tid), prov("المعلم كمال", tid)
call("POST", "/admin/service-owners", {"provider_id": p1, "phone": "01088880002"}, at)
call("POST", "/admin/service-owners", {"provider_id": p2, "phone": "01088880003"}, at)
body = {"type_id": tid, "region_id": rid, "description": "محتاج سباك لإصلاح تسريب في الحمام"}

# ---------- المخطط والحالات
cols = {r[1] for r in sql("PRAGMA table_info(service_requests)")}
ok("new columns exist", {"address", "preferred_at", "budget_min", "budget_max", "cancelled_by"} <= cols)
ok("11 statuses defined", len(svc.STATUSES) == 11 and len(set(svc.STATUSES)) == 11)
ok("every status has a label and a NEXT entry", all(s in svc.LABELS and s in svc.NEXT for s in svc.STATUSES))
ok("NEXT only points at valid statuses", all(t in svc.STATUSES for v in svc.NEXT.values() for t in v))
ok("tables for images and events exist", sql("select count(*) from sqlite_master where name in('service_request_images','service_request_events')")[0][0] == 2)

# ---------- إنشاء طلب بالحقول الجديدة + التحقق
full = {**body, "address": "شارع النصر، عمارة 5، شقة 3", "preferred_at": now + 86400, "budget_min": 100, "budget_max": 300}
s, r = call("POST", "/service-requests", full, CU); ok("create with address/time/budget -> 201", s == 201); R1 = r["id"]
d = call("GET", f"/service-requests/{R1}", None, CU)[1]
ok("detail returns the new fields", d["address"] == full["address"] and d["preferred_at"] == now + 86400 and d["budget_min"] == 100 and d["budget_max"] == 300 and d["images"] == [])
ok("detail history starts with open by customer", d["history"] and d["history"][0]["to"] == "open" and d["history"][0]["by"] == "customer")
ok("plain request (old payload) still works", call("POST", "/service-requests", body, CU)[0] == 201)
R2 = call("GET", "/service-requests", None, CU)[1][0]["id"]
m2 = call("GET", f"/service-requests/{R2}", None, CU)[1]
ok("omitted fields are null", m2["address"] is None and m2["preferred_at"] is None and m2["budget_min"] is None and m2["budget_max"] is None)
for name, extra in (("short address", {"address": "abc"}), ("long address", {"address": "ع" * 201}), ("past time", {"preferred_at": now - 3600}),
                    ("far future", {"preferred_at": now + 200 * 86400}), ("text time", {"preferred_at": "غدًا"}), ("negative budget", {"budget_min": -5}),
                    ("zero budget", {"budget_max": 0}), ("huge budget", {"budget_max": 10 ** 9}), ("text budget", {"budget_min": "كتير"}), ("bool budget", {"budget_min": True}),
                    ("min > max", {"budget_min": 500, "budget_max": 100})):
    ok("rejects " + name, call("POST", "/service-requests", {**body, **extra}, OT)[0] == 400)
ok("rejected requests created nothing", sql("select count(*) from service_requests")[0][0] == 2)
ok("only max budget is fine", call("POST", "/service-requests", {**body, "budget_max": 250}, OT)[0] == 201)
call("POST", f"/service-requests/{call('GET', '/service-requests', None, OT)[1][0]['id']}/cancel", {}, OT)
ok("other user cannot read my detail (404)", call("GET", f"/service-requests/{R1}", None, OT)[0] == 404)
ok("anonymous gets 401 on detail", call("GET", f"/service-requests/{R1}")[0] == 401)

# ---------- صور الطلب
good = png_bytes(32, 32)
exif = good[:33] + _chunk(b"tEXt", b"Comment\x00SECRET-GPS-LOCATION") + good[33:]
s, r = call("POST", f"/service-requests/{R1}/images", {"data": b64(exif)}, CU); ok("owner uploads an image -> 201", s == 201 and len(r["images"]) == 1); F1 = r["id"]
path = sql("select path from files where id=?", (F1,))[0][0]; stored = open(os.path.join(_UP, path), "rb").read()
ok("stored image has metadata stripped", b"tEXt" not in stored and b"SECRET-GPS" not in stored and stored[:4] == b"\x89PNG")
ok("bad image bytes -> 400", call("POST", f"/service-requests/{R1}/images", {"data": b64(b"not an image")}, CU)[0] == 400)
ok("other user cannot upload to my request (404)", call("POST", f"/service-requests/{R1}/images", {"data": b64(good)}, OT)[0] == 404)
ok("anonymous upload -> 401", call("POST", f"/service-requests/{R1}/images", {"data": b64(good)})[0] == 401)
call("POST", f"/service-requests/{R1}/images", {"data": b64(png_bytes(20, 20))}, CU); s, r = call("POST", f"/service-requests/{R1}/images", {"data": b64(png_bytes(21, 21))}, CU)
F3 = r["id"]; ok("third image accepted", s == 201 and len(r["images"]) == 3)
ok("fourth image rejected (409)", call("POST", f"/service-requests/{R1}/images", {"data": b64(png_bytes(22, 22))}, CU)[0] == 409)
s, h, b = raw(f"/service-requests/{R1}/images/{F1}", CU)
ok("owner reads image: png + private/no-store", s == 200 and h.get("Cache-Control") == "private, no-store" and b[:4] == b"\x89PNG")
ok("admin reads image", raw(f"/service-requests/{R1}/images/{F1}", at)[0] == 200)
ok("anonymous image read -> 401", raw(f"/service-requests/{R1}/images/{F1}")[0] == 401)
ok("other user image read -> 404", raw(f"/service-requests/{R1}/images/{F1}", OT)[0] == 404)
ok("matching provider cannot read images BEFORE accepting (404)", raw(f"/service-requests/{R1}/images/{F1}", PV)[0] == 404)
ok("image id of another request does not leak (404)", raw(f"/service-requests/{R2}/images/{F1}", CU)[0] == 404)
CUID = sql("select id from users where phone='01088880001'")[0][0]
_c = server.db(); _n = _c.execute(server.COUNT_SQL["files"], (CUID,)).fetchone()[0]; _c.close()
ok("image files do not count toward the 20-file quota", _n == 0 and sql("select count(*) from files where owner_id=?", (CUID,))[0][0] == 3)
s, r = call("POST", f"/files/{F1}/delete", {}, CU); ok("generic file delete refuses a request image (409)", s == 409)
F3PATH = os.path.join(_UP, sql("select path from files where id=?", (F3,))[0][0])
s, r = call("POST", f"/service-requests/{R1}/images/{F3}/delete", {}, CU); ok("owner deletes one image", s == 200 and F3 not in r["images"] and len(r["images"]) == 2)
ok("deleted image row and file are gone", sql("select count(*) from files where id=?", (F3,))[0][0] == 0 and not os.path.exists(F3PATH))
ok("other user cannot delete my image (404)", call("POST", f"/service-requests/{R1}/images/{F1}/delete", {}, OT)[0] == 404)

# ---------- ما يراه المقدم قبل القبول وبعده
jobs = call("GET", "/my/service-jobs", None, PV)[1]["jobs"]; j = [x for x in jobs if x["id"] == R1][0]
ok("provider sees budget/time/image_count before accept", j["budget_min"] == 100 and j["budget_max"] == 300 and j["preferred_at"] == now + 86400 and j["image_count"] == 2)
ok("provider sees NO address/images/phone before accept", all(k not in j for k in ("address", "images", "customer_phone", "customer_name")) and "شارع النصر" not in json.dumps(jobs))
s, a = call("POST", f"/my/service-jobs/{R1}/accept", {}, PV)
ok("accept -> accepted, reveals phone+address+images", s == 200 and a["status"] == "accepted" and a["customer_phone"] == "01088880001" and a["address"] == full["address"] and len(a["images"]) == 2)
ok("second provider cannot accept the same request (409/403)", call("POST", f"/my/service-jobs/{R1}/accept", {}, PV2)[0] in (403, 409))
ok("accepting provider reads the images", raw(f"/service-requests/{R1}/images/{F1}", PV)[0] == 200)
ok("the other matching provider still cannot (404)", raw(f"/service-requests/{R1}/images/{F1}", PV2)[0] == 404)
mj = [x for x in call("GET", "/my/service-jobs", None, PV)[1]["jobs"] if x["id"] == R1][0]
ok("accepted job lists address and images", mj["address"] == full["address"] and mj["images"] and mj["status"] == "accepted" and mj["status_label"] == "قبله المقدم")
ok("customer sees accepted + provider name, no phone", call("GET", "/service-requests", None, CU)[1][-1]["status"] in ("accepted", "open") and "01088880002" not in json.dumps(call("GET", "/service-requests", None, CU)[1]))

# ---------- تقدّم العمل
P = lambda st, t=PV, i=R1: call("POST", f"/my/service-jobs/{i}/progress", {"status": st}, t)
ok("progress with a bad status -> 400", P("open")[0] == 400 and P("cancelled")[0] == 400 and P("zzz")[0] == 400)
ok("other provider cannot progress it (404)", P("on_the_way", PV2)[0] == 404)
ok("customer cannot progress it (403)", P("on_the_way", CU)[0] == 403)
ok("accepted -> on_the_way", P("on_the_way") == (200, {"ok": True, "status": "on_the_way"}))
ok("same status again -> 409", P("on_the_way")[0] == 409)
ok("customer notified: on_the_way", sql("select count(*) from notifications where kind='service_request.on_the_way'")[0][0] == 1)
ok("on_the_way -> in_progress", P("in_progress")[0] == 200)
ok("in_progress cannot go back to on_the_way (409)", P("on_the_way")[0] == 409)
ok("customer can still read images while in progress", raw(f"/service-requests/{R1}/images/{F1}", CU)[0] == 200)
ok("in_progress -> done", P("done")[0] == 200)
ok("done is final for the provider (409)", P("in_progress")[0] == 409)
d = call("GET", f"/service-requests/{R1}", None, CU)[1]
ok("history shows the full path with actors", [h["to"] for h in d["history"]] == ["open", "accepted", "on_the_way", "in_progress", "done"] and [h["by"] for h in d["history"]][1:] == ["provider"] * 4)
ok("history hides user ids and phones", "01088880002" not in json.dumps(d) and "actor_id" not in json.dumps(d))
ok("done request can be rated", d["can_rate"] is True and call("POST", f"/service-requests/{R1}/rate", {"stars": 5}, CU)[0] == 200)
ok("done request: no more uploads/deletes (409)", call("POST", f"/service-requests/{R1}/images/{F1}/delete", {}, CU)[0] == 409 and call("POST", f"/service-requests/{R1}/images", {"data": b64(good)}, CU)[0] == 409)
ok("provider keeps image access after done", raw(f"/service-requests/{R1}/images/{F1}", PV)[0] == 200)

# ---------- legacy /done من accepted + release + إلغاء العميل
s, r = call("POST", "/service-requests", {**body, "address": "شارع السلام 10"}, CU); R3 = r["id"]
call("POST", f"/my/service-jobs/{R3}/accept", {}, PV)
ok("legacy /done works straight from accepted", call("POST", f"/my/service-jobs/{R3}/done", {}, PV) == (200, {"ok": True, "status": "done"}))
s, r = call("POST", "/service-requests", body, CU); R4 = r["id"]; call("POST", f"/my/service-jobs/{R4}/accept", {}, PV); P("on_the_way", PV, R4)
ok("provider releases from on_the_way -> open, provider cleared", call("POST", f"/my/service-jobs/{R4}/release", {}, PV)[1]["status"] == "open" and sql("select provider_id from service_requests where id=?", (R4,))[0][0] is None)
ok("released request is visible to matching providers again", R4 in [x["id"] for x in call("GET", "/my/service-jobs", None, PV2)[1]["jobs"]])
call("POST", f"/my/service-jobs/{R4}/accept", {}, PV2)
s, r = call("POST", f"/service-requests/{R4}/cancel", {}, CU)
ok("customer cancels an accepted request -> cancelled_by=customer", s == 200 and sql("select status,cancelled_by from service_requests where id=?", (R4,))[0] == ("cancelled", "customer"))
ok("provider was told about the cancellation", sql("select count(*) from notifications where kind='service_request.cancelled'")[0][0] == 1)
ok("cancelling twice -> 409", call("POST", f"/service-requests/{R4}/cancel", {}, CU)[0] == 409)
ok("provider cannot progress a cancelled request (409)", P("in_progress", PV2, R4)[0] == 409)

# ---------- الإدارة
s, r = call("POST", "/service-requests", body, CU); R5 = r["id"]
ok("admin list filters by each of the 11 statuses without error", all(call("GET", "/admin/service-requests?status=" + st, None, at)[0] == 200 for st in svc.STATUSES))
ok("admin list rejects an unknown status", call("GET", "/admin/service-requests?status=bogus", None, at)[0] == 400)
ok("admin list exposes status_label and new fields", all(k in call("GET", "/admin/service-requests?status=open", None, at)[1][0] for k in ("status_label", "address", "budget_min", "images")))
ok("admin rejects non-admin statuses (accepted/expired)", call("POST", f"/admin/service-requests/{R5}", {"status": "accepted"}, at)[0] == 400 and call("POST", f"/admin/service-requests/{R5}", {"status": "expired"}, at)[0] == 400)
ok("admin: open -> in_progress with note", call("POST", f"/admin/service-requests/{R5}", {"status": "in_progress", "note": "قيد المتابعة"}, at)[0] == 200)
ok("admin: cancel -> cancelled_by=admin", call("POST", f"/admin/service-requests/{R5}", {"status": "cancelled", "note": "مكرر"}, at)[0] == 200 and sql("select cancelled_by from service_requests where id=?", (R5,))[0][0] == "admin")
ok("admin cannot change a cancelled request (409)", call("POST", f"/admin/service-requests/{R5}", {"status": "done"}, at)[0] == 409)
ok("customer cannot use admin routes (403)", call("POST", f"/admin/service-requests/{R5}", {"status": "done"}, CU)[0] == 403 and call("GET", "/admin/service-requests", None, CU)[0] == 403)

# ---------- حد الطلبات الحيّة والانتهاء التلقائي
U2 = user("01088880005")
ids = [call("POST", "/service-requests", body, U2)[1]["id"] for _ in range(3)]
ok("3 live requests reached the cap -> 4th is 429", call("POST", "/service-requests", body, U2)[0] == 429)
call("POST", f"/my/service-jobs/{ids[0]}/accept", {}, PV); P("on_the_way", PV, ids[0])
ok("an on_the_way request still counts as live", call("POST", "/service-requests", body, U2)[0] == 429)
sql("UPDATE service_requests SET created_at=? WHERE id=?", (now - (svc.EXPIRE_DAYS + 1) * 86400, ids[1]))
sql("UPDATE service_requests SET created_at=? WHERE id=?", (now - (svc.EXPIRE_DAYS + 1) * 86400, ids[0]))
call("GET", "/service-requests", None, U2)
st = {r[0]: r[1] for r in sql("select id,status from service_requests where id in(?,?,?)", tuple(ids))}
ok("old unaccepted request -> expired", st[ids[1]] == "expired")
ok("old but ACCEPTED request is not expired", st[ids[0]] == "on_the_way")
ok("a recent open request is untouched", st[ids[2]] == "open")
ok("expiry wrote an event and notified the owner", sql("select count(*) from service_request_events where to_status='expired' and request_id=?", (ids[1],))[0][0] == 1 and sql("select count(*) from notifications where kind='service_request.expired'")[0][0] == 1)
ok("expired frees a slot for a new request", call("POST", "/service-requests", body, U2)[0] == 201)
ok("expired request cannot be cancelled or accepted", call("POST", f"/service-requests/{ids[1]}/cancel", {}, U2)[0] == 409 and call("POST", f"/my/service-jobs/{ids[1]}/accept", {}, PV)[0] == 409)
ok("expiry is idempotent", svc._expire(server.db(), int(time.time())) == 0)

# ---------- ترحيل قاعدة قديمة (4 حالات) إلى الجديدة بلا فقد بيانات
c = server.db(); c.execute("PRAGMA foreign_keys=OFF")
c.executescript("""BEGIN; DROP TABLE service_request_images; DROP TABLE service_request_events;
CREATE TABLE sr_old(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), type_id INTEGER NOT NULL REFERENCES service_types(id), region_id INTEGER NOT NULL REFERENCES regions(id),
 description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','in_progress','done','cancelled')), admin_note TEXT, handled_by INTEGER REFERENCES users(id),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, provider_id INTEGER REFERENCES service_providers(id), accepted_at INTEGER);
INSERT INTO sr_old SELECT id,user_id,type_id,region_id,description,CASE WHEN status IN('open','in_progress','done','cancelled') THEN status ELSE 'open' END,admin_note,handled_by,created_at,updated_at,provider_id,accepted_at FROM service_requests;
DROP TABLE service_requests; ALTER TABLE sr_old RENAME TO service_requests; COMMIT;""")
c.execute("PRAGMA foreign_keys=ON"); before = c.execute("select id,user_id,description,status,provider_id from service_requests order by id").fetchall()
ratings_before = c.execute("select count(*) from service_ratings").fetchone()[0]
ok("simulated old schema really rejects new statuses", "on_the_way" not in c.execute("select sql from sqlite_master where name='service_requests'").fetchone()[0])
svc.install(c); svc.install(c)
ok("install migrates the old schema (idempotent)", "on_the_way" in c.execute("select sql from sqlite_master where name='service_requests'").fetchone()[0])
after = c.execute("select id,user_id,description,status,provider_id from service_requests order by id").fetchall()
ok("migration keeps every row unchanged", before == after and len(after) > 5)
ok("migration keeps ratings and their foreign keys valid", c.execute("select count(*) from service_ratings").fetchone()[0] == ratings_before and c.execute("PRAGMA foreign_key_check").fetchall() == [])
ok("new columns are NULL on migrated rows", c.execute("select count(*) from service_requests where address is not null or preferred_at is not null or budget_min is not null").fetchone()[0] == 0)
c.execute("UPDATE service_requests SET status='on_the_way' WHERE id=?", (ids[0],)); c.commit()
try: c.execute("UPDATE service_requests SET status='bogus' WHERE id=?", (ids[0],)); bad = False
except sqlite3.IntegrityError: bad = True
ok("migrated table accepts new statuses and still rejects junk", bad)
ok("foreign keys are ON again after the migration", c.execute("PRAGMA foreign_keys").fetchone()[0] == 1)
ok("indexes were recreated", {"ix_service_requests_user", "ix_service_requests_status", "ix_service_requests_provider"} <= {r[0] for r in c.execute("select name from sqlite_master where type='index'")})
c.close()
ok("API works on the migrated table", call("POST", "/service-requests", {**body, "address": "بعد الترحيل 123"}, user("01088880006"))[0] == 201 and call("GET", "/admin/service-requests", None, at)[0] == 200)
print("ALL OK")
