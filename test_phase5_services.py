# المرحلة 5: طلبات الخدمات المحلية (svc.py). قاعدة مؤقتة. اختبار API + فحص نصي للواجهة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8797), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8797"; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__))
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
U1, U2 = user("01066660001"), user("01066660002")
rid = 3
tid = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
tid2 = call("POST", "/admin/service-types", {"name_ar": "كهرباء"}, at)[1]["id"]
pid = call("POST", "/admin/services", {"name_ar": "المعلم سمير", "type_id": tid, "region_id": rid, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
call("POST", f"/admin/services/{pid}/publish", {"published": True}, at)
body = {"type_id": tid, "region_id": rid, "description": "محتاج سباك لإصلاح تسريب في الحمام"}

ok("anonymous cannot create a request (401)", call("POST", "/service-requests", body)[0] == 401)
ok("anonymous cannot list (401)", call("GET", "/service-requests")[0] == 401)
s, r = call("POST", "/service-requests", body, U1); ok("create request -> 201 open", s == 201 and r["status"] == "open"); r1 = r["id"]
ok("short description rejected", call("POST", "/service-requests", {**body, "description": "قصير"}, U1)[0] == 400)
ok("too long description rejected", call("POST", "/service-requests", {**body, "description": "ا" * 501}, U1)[0] == 400)
ok("unknown type rejected", call("POST", "/service-requests", {**body, "type_id": 9999}, U1)[0] == 400)
ok("unknown region rejected", call("POST", "/service-requests", {**body, "region_id": 9999}, U1)[0] == 400)
ok("missing fields rejected", call("POST", "/service-requests", {"description": body["description"]}, U1)[0] == 400)
mine = call("GET", "/service-requests", None, U1)[1]
ok("my list has the request with type, region and matching provider name", len(mine) == 1 and mine[0]["type"] == "سباكة" and mine[0]["providers"] == [{"id": pid, "name_ar": "المعلم سمير"}])
ok("customer responses never contain a phone number", "01099990000" not in json.dumps(mine, ensure_ascii=False) and "phone" not in json.dumps(mine))
ok("other user sees none of it", call("GET", "/service-requests", None, U2)[1] == [])
ok("other user cannot cancel it (404)", call("POST", f"/service-requests/{r1}/cancel", {}, U2)[0] == 404)
ok("customer cannot use admin routes (403)", call("GET", "/admin/service-requests", None, U1)[0] == 403 and call("POST", f"/admin/service-requests/{r1}", {"status": "done"}, U1)[0] == 403)
n = sql("select count(*), min(link) from notifications where kind='service_request.new'")[0]
ok("admin got a bell notification linking to the admin section", n[0] >= 1 and n[1] == "admin:svcreq")
al = call("GET", "/admin/service-requests", None, at)[1]
ok("admin list shows requester name and phone", len(al) == 1 and al[0]["user_phone"] == "01066660001" and al[0]["status"] == "open")
ok("admin status filter works and rejects junk", len(call("GET", "/admin/service-requests?status=done", None, at)[1]) == 0 and call("GET", "/admin/service-requests?status=zz", None, at)[0] == 400)
ok("admin invalid status rejected", call("POST", f"/admin/service-requests/{r1}", {"status": "open"}, at)[0] == 400)
ok("admin unknown request 404", call("POST", "/admin/service-requests/9999", {"status": "done"}, at)[0] == 404)
ok("admin moves to in_progress with a note", call("POST", f"/admin/service-requests/{r1}", {"status": "in_progress", "note": "تواصلنا مع السباك"}, at)[0] == 200)
m2 = call("GET", "/service-requests", None, U1)[1][0]
ok("customer sees status and note", m2["status"] == "in_progress" and m2["admin_note"] == "تواصلنا مع السباك")
ok("customer got a notification about it", sql("select count(*) from notifications where kind='service_request.in_progress' and link='svc'")[0][0] == 1)
ok("admin action is audited", sql("select count(*) from audit_log where action='service_request.in_progress'")[0][0] == 1)
ok("admin finishes it", call("POST", f"/admin/service-requests/{r1}", {"status": "done"}, at)[0] == 200)
ok("finished request cannot change again (409)", call("POST", f"/admin/service-requests/{r1}", {"status": "cancelled"}, at)[0] == 409)
ok("customer cannot cancel a finished request (409)", call("POST", f"/service-requests/{r1}/cancel", {}, U1)[0] == 409)
ok("finished request no longer lists providers", call("GET", "/service-requests", None, U1)[1][0]["providers"] == [])
# limits
ids = [call("POST", "/service-requests", body, U2)[1]["id"] for _ in range(3)]
ok("4th concurrent open request is limited (429)", call("POST", "/service-requests", body, U2)[0] == 429)
ok("customer cancels one", call("POST", f"/service-requests/{ids[0]}/cancel", {}, U2)[0] == 200)
ok("cancelling frees a slot", call("POST", "/service-requests", body, U2)[0] == 201)
ok("inactive service type rejected", (call("POST", f"/admin/service-types/{tid2}", {"name_ar": "كهرباء", "is_active": False}, at), call("POST", "/service-requests", {**body, "type_id": tid2}, U1)[0] == 400)[1])
sql("update service_requests set created_at=? where user_id=(select id from users where phone='01066660001')", (int(time.time()),))
U3 = user("01066660003")
for _ in range(10):
    sql("insert into service_requests(user_id,type_id,region_id,description,status,created_at,updated_at) select id,?,?,'وصف طويل كفاية للطلب','done',?,? from users where phone='01066660003'", (tid, rid, int(time.time()), int(time.time())))
ok("daily cap (10/day) enforced (429)", call("POST", "/service-requests", body, U3)[0] == 429)
# UI / wiring (text checks)
rd = lambda p: open(os.path.join(HERE, p), encoding="utf8").read()
ix, ad, nf, sw, dk = rd("static/index.html"), rd("static/admin.html"), rd("static/notif.js"), rd("static/sw.js"), rd("Dockerfile")
ok("customer UI: request form, my requests, cancel; all text through esc()", "srbox" in ix and "/service-requests" in ix and "esc(x.description)" in ix and "esc(x.admin_note)" in ix)
ok("admin UI: svcreq tab declared and rendered with esc()", "svcreq:'طلبات الخدمات'" in ad and "async svcreq()" in ad and "esc(x.description)" in ad and "esc(x.user_phone)" in ad)
ok("notification link 'svc' is routed", "svc: ['/'" in nf)
ok("svc.py copied by Dockerfile and service worker bumped", "svc.py" in dk and int(__import__("re").search(r"laqino-v(\d+)", sw).group(1)) >= 36)
print("ALL PASSED")
