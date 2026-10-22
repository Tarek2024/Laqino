# الخطوة 5: التقييم — تعليق، تعديل، حذف، بلاغ المقدم، اعتماد الإدارة، الصفحة العامة، ترحيل قاعدة قديمة. قاعدة مؤقتة.
import os, re, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8851), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8851"; DB = os.environ["LAQINO_DB"]
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
C1, C2, C3, PV, OT = user("01077770001"), user("01077770002"), user("01077770003"), user("01077770004"), user("01077770005")
tid = call("POST", "/admin/service-types", {"name_ar": "كهرباء"}, at)[1]["id"]
pid = call("POST", "/admin/services", {"name_ar": "المعلم كريم", "type_id": tid, "region_id": 3, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
call("POST", f"/admin/services/{pid}/publish", {"published": True}, at)
call("POST", "/admin/service-owners", {"provider_id": pid, "phone": "01077770004"}, at)
body = {"type_id": tid, "region_id": 3, "description": "محتاج كهربائي لتغيير مفاتيح الصالة"}
def done(tok):
    r = call("POST", "/service-requests", body, tok)[1]["id"]
    call("POST", f"/my/service-jobs/{r}/accept", {}, PV); call("POST", f"/my/service-jobs/{r}/done", {}, PV); return r
RT = lambda r, d, t, a="": call("POST", f"/service-requests/{r}/rate" + a, d, t)
cnt = lambda: sql("SELECT COUNT(*) FROM service_notifications_dummy")[0][0] if False else None
myreq = lambda tok, rid: [x for x in call("GET", "/service-requests", None, tok)[1] if x["id"] == rid][0]
nt = lambda kind: sql("SELECT COUNT(*) FROM notifications WHERE kind=?", (kind,))[0][0]

ok("migration: new columns + reports table", {"comment", "updated_at", "hidden"} <= {r[1] for r in sql("PRAGMA table_info(service_ratings)")} and sql("SELECT name FROM sqlite_master WHERE name='service_rating_reports'") != [])
r1, r2, r3 = done(C1), done(C2), done(C3)
for bad in ("x" * 301, "كلمني على 01234567890"): ok("bad comment rejected (400)", RT(r1, {"stars": 4, "comment": bad}, C1)[0] == 400)
ok("rating with comment accepted", RT(r1, {"stars": 4, "comment": "  شغل نضيف وسريع  "}, C1)[0] == 200)
mine = call("GET", "/service-requests", None, C1)[1][0]
ok("customer sees own rating object (stars, trimmed comment, not hidden)", mine["rating"] == {"stars": 4, "comment": "شغل نضيف وسريع", "hidden": False} and mine["rated"] == 4)
ok("second POST /rate still 409 (use update)", RT(r1, {"stars": 1}, C1)[0] == 409)
RT(r2, {"stars": 2}, C2); RT(r3, {"stars": 5, "comment": "ممتاز"}, C3)
ok("stars-only rating allowed", sql("SELECT comment FROM service_ratings WHERE request_id=?", (r2,))[0][0] is None)

# ---- update ----
ok("update: anonymous 401", RT(r1, {"stars": 3}, None, "/update")[0] == 401)
ok("update: other user 404", RT(r1, {"stars": 3}, C2, "/update")[0] == 404)
ok("update: provider 404", RT(r1, {"stars": 3}, PV, "/update")[0] == 404)
ok("update: invalid stars 400", RT(r1, {"stars": 9}, C1, "/update")[0] == 400)
ok("update: phone in comment 400", RT(r1, {"stars": 3, "comment": "01234567890"}, C1, "/update")[0] == 400)
ok("update: request with no rating 404", call("POST", f"/service-requests/{call('POST','/service-requests',body,C1)[1]['id']}/rate/update", {"stars": 3}, C1)[0] == 404)
before = nt("service_request.rating_updated")
s, r = RT(r1, {"stars": 2, "comment": "اتغير رأيي"}, C1, "/update")
ok("update: 200 and average recomputed ((2+2+5)/3=3.0)", s == 200 and r["rating_avg"] == 3.0 and r["rating_count"] == 3)
row = sql("SELECT stars,comment,updated_at FROM service_ratings WHERE request_id=?", (r1,))[0]
ok("update stored with updated_at", row[0] == 2 and row[1] == "اتغير رأيي" and row[2])
ok("provider notified of edit", nt("service_request.rating_updated") == before + 1)
RT(r1, {"stars": 3}, C1, "/update")
ok("update without comment key keeps the comment", sql("SELECT comment FROM service_ratings WHERE request_id=?", (r1,))[0][0] == "اتغير رأيي")
RT(r1, {"stars": 3, "comment": ""}, C1, "/update")
ok("update with empty comment clears it", sql("SELECT comment FROM service_ratings WHERE request_id=?", (r1,))[0][0] == "")
RT(r1, {"stars": 4, "comment": "رجعت وقيّمت تاني، شغل كويس"}, C1, "/update")

# ---- public page ----
s, pg = call("GET", f"/services/{pid}/ratings")
ok("public ratings: no login needed, 200", s == 200 and pg["rating_count"] == 3 and pg["rating_avg"] == 3.7)
ok("public ratings: distribution", pg["distribution"] == {"1": 0, "2": 1, "3": 0, "4": 1, "5": 1})
ok("public ratings: newest first, comment + stars only", [i["stars"] for i in pg["items"]] == [5, 2, 4] and set(pg["items"][0]) == {"stars", "comment", "at", "edited"})
ok("public ratings: edited flag", pg["items"][2]["edited"] is True and pg["items"][0]["edited"] is False)
ok("public ratings: no identity leaked", not re.search(r"0\d{10}|u0\d|user", json.dumps(pg, ensure_ascii=False)))
ok("public ratings: unpublished/unknown provider 404", call("GET", "/services/99999/ratings")[0] == 404)
for i in range(25): sql("INSERT INTO service_ratings(request_id,provider_id,user_id,stars,created_at,hidden) VALUES(?,?,?,?,?,0)", (1000 + i, pid, 1, 5, 1 + i))
s, p1 = call("GET", f"/services/{pid}/ratings"); s, p2 = call("GET", f"/services/{pid}/ratings?offset=20")
ok("public ratings: paging (20 + rest, has_more)", len(p1["items"]) == 20 and p1["has_more"] is True and len(p2["items"]) == 8 and p2["has_more"] is False)
ok("public ratings: junk offset tolerated", call("GET", f"/services/{pid}/ratings?offset=abc")[0] == 200)
sql("DELETE FROM service_ratings WHERE request_id>=1000")

# ---- provider list + report ----
s, mr = call("GET", "/my/service-ratings", None, PV)
ok("provider sees own ratings (no identity)", s == 200 and len(mr) == 3 and not re.search(r"0\d{10}|user_id|u0\d", json.dumps(mr, ensure_ascii=False)))
ok("non-owner sees none", call("GET", "/my/service-ratings", None, OT)[1] == [])
gid = [x["id"] for x in mr if x["stars"] == 4][0]
ok("report: anonymous 401", call("POST", f"/my/service-ratings/{gid}/report", {"reason": "تقييم كاذب"})[0] == 401)
ok("report: non-owner 404", call("POST", f"/my/service-ratings/{gid}/report", {"reason": "تقييم كاذب"}, OT)[0] == 404)
ok("report: customer cannot report 404", call("POST", f"/my/service-ratings/{gid}/report", {"reason": "تقييم كاذب"}, C1)[0] == 404)
ok("report: short reason 400", call("POST", f"/my/service-ratings/{gid}/report", {"reason": "ab"}, PV)[0] == 400)
ok("report: unknown rating 404", call("POST", "/my/service-ratings/9999/report", {"reason": "تقييم كاذب"}, PV)[0] == 404)
na = nt("service_rating.reported")
ok("report: 201", call("POST", f"/my/service-ratings/{gid}/report", {"reason": "العميل ده مش بتاعي أصلًا"}, PV)[0] == 201)
ok("report: admins notified", nt("service_rating.reported") == na + 1)
ok("report: duplicate 409", call("POST", f"/my/service-ratings/{gid}/report", {"reason": "تقييم كاذب تاني"}, PV)[0] == 409)
ok("provider list marks my_report=pending", [x for x in call("GET", "/my/service-ratings", None, PV)[1] if x["id"] == gid][0]["my_report"] == "pending")
ok("report written to audit_log", sql("SELECT COUNT(*) FROM audit_log WHERE action='service_rating.report'")[0][0] == 1)

# ---- admin ----
ok("admin list: customer 403", call("GET", "/admin/service-rating-reports", None, C1)[0] == 403)
ok("admin list: provider 403", call("GET", "/admin/service-rating-reports", None, PV)[0] == 403)
s, lst = call("GET", "/admin/service-rating-reports", None, at); rid_ = lst[0]["id"]
ok("admin list: pending with snapshot + names", s == 200 and len(lst) == 1 and lst[0]["stars"] == 4 and lst[0]["provider_name"] == "المعلم كريم" and lst[0]["customer_name"] and lst[0]["status"] == "pending")
ok("admin list: bad status 400", call("GET", "/admin/service-rating-reports?status=x", None, at)[0] == 400)
ok("overview counts the pending report", call("GET", "/admin/overview", None, at)[1]["pending"]["rating_reports"] == 1)
ok("decide: customer 403", call("POST", f"/admin/service-rating-reports/{rid_}", {"action": "hide", "note": "مخالف للشروط"}, C1)[0] == 403)
ok("decide: invalid action 400", call("POST", f"/admin/service-rating-reports/{rid_}", {"action": "x", "note": "مخالف للشروط"}, at)[0] == 400)
ok("decide: note required 400", call("POST", f"/admin/service-rating-reports/{rid_}", {"action": "hide", "note": "x"}, at)[0] == 400)
ok("decide: unknown report 404", call("POST", "/admin/service-rating-reports/9999", {"action": "hide", "note": "مخالف للشروط"}, at)[0] == 404)
ok("restore on pending 409", call("POST", f"/admin/service-rating-reports/{rid_}", {"action": "restore", "note": "مخالف للشروط"}, at)[0] == 409)
ok("hide: 200", call("POST", f"/admin/service-rating-reports/{rid_}", {"action": "hide", "note": "التعليق مسيء للمقدم"}, at)[0] == 200)
pg = call("GET", f"/services/{pid}/ratings")[1]
ok("hidden rating leaves average, count, list", pg["rating_count"] == 2 and pg["rating_avg"] == 3.5 and 4 not in [i["stars"] for i in pg["items"]] and pg["distribution"]["4"] == 0)
ok("public service card count/avg exclude hidden", call("GET", f"/services/{pid}")[1]["rating_count"] == 2)
ok("customer sees rating hidden", myreq(C1, r1)["rating"]["hidden"] is True)
ok("customer cannot edit hidden rating 409", RT(r1, {"stars": 5}, C1, "/update")[0] == 409)
ok("provider list marks hidden + upheld", [x for x in call("GET", "/my/service-ratings", None, PV)[1] if x["id"] == gid][0]["hidden"] is True)
ok("customer + provider notified of hide", nt("service_rating.hide") == 2)
ok("hide logged in audit", sql("SELECT COUNT(*) FROM audit_log WHERE action='service_rating.hide'")[0][0] == 1)
ok("decide again on decided report 409", call("POST", f"/admin/service-rating-reports/{rid_}", {"action": "dismiss", "note": "مخالف للشروط"}, at)[0] == 409)
ok("report on hidden rating 409", call("POST", f"/my/service-ratings/{gid}/report", {"reason": "تقييم كاذب"}, PV)[0] == 409)
ok("overview: no pending left", call("GET", "/admin/overview", None, at)[1]["pending"]["rating_reports"] == 0)
ok("admin upheld list has it", len(call("GET", "/admin/service-rating-reports?status=upheld", None, at)[1]) == 1)
ok("restore: 200", call("POST", f"/admin/service-rating-reports/{rid_}", {"action": "restore", "note": "تمت المراجعة وهو مقبول"}, at)[0] == 200)
ok("restored rating counts again", call("GET", f"/services/{pid}/ratings")[1]["rating_count"] == 3)
ok("customer can edit again after restore", RT(r1, {"stars": 5}, C1, "/update")[0] == 200)

# dismiss path
g2 = [x["id"] for x in call("GET", "/my/service-ratings", None, PV)[1] if x["stars"] == 5 and x["comment"] == "ممتاز"][0]
call("POST", f"/my/service-ratings/{g2}/report", {"reason": "أشك إنه تقييم صديق"}, PV)
rid2 = call("GET", "/admin/service-rating-reports", None, at)[1][0]["id"]
ok("dismiss: 200, rating stays visible", call("POST", f"/admin/service-rating-reports/{rid2}", {"action": "dismiss", "note": "لا مخالفة واضحة"}, at)[0] == 200 and call("GET", f"/services/{pid}/ratings")[1]["rating_count"] == 3)
ok("provider notified of dismissal", nt("service_rating.dismiss") == 1)

# ---- delete ----
ok("delete: other user 404", RT(r2, {}, C1, "/delete")[0] == 404)
ok("delete: request with no rating 404", RT(call("POST", "/service-requests", body, C1)[1]["id"], {}, C1, "/delete")[0] == 404)
call("POST", f"/my/service-ratings/{[x['id'] for x in call('GET','/my/service-ratings',None,PV)[1] if x['stars']==2][0]}/report", {"reason": "تقييم مبالغ فيه"}, PV)
s, r = RT(r2, {}, C2, "/delete")
ok("delete: 200 and average recomputed", s == 200 and r["rating_count"] == 2)
ok("delete: pending report on it auto-dismissed", sql("SELECT status FROM service_rating_reports WHERE request_id=?", (r2,))[0][0] == "dismissed")
ok("deleted: can_rate true again, rated None", (lambda x: x["can_rate"] is True and x["rated"] is None and x["rating"] is None)(myreq(C2, r2)))
ok("re-rate after delete works", RT(r2, {"stars": 3}, C2)[0] == 200)
sql("UPDATE service_ratings SET hidden=1 WHERE request_id=?", (r2,))
ok("hidden rating can still be deleted by owner", RT(r2, {}, C2, "/delete")[0] == 200)
ok("delete logged in audit", sql("SELECT COUNT(*) FROM audit_log WHERE action='service_rating.delete'")[0][0] == 2)

# ---- migration from a pre-step-5 DB ----
old = tempfile.mktemp(suffix=".db"); c = sqlite3.connect(old); c.executescript("""
CREATE TABLE users(id INTEGER PRIMARY KEY); CREATE TABLE files(id INTEGER PRIMARY KEY); CREATE TABLE regions(id INTEGER PRIMARY KEY); CREATE TABLE service_types(id INTEGER PRIMARY KEY);
CREATE TABLE service_providers(id INTEGER PRIMARY KEY, owner_user_id INTEGER);
CREATE TABLE service_requests(id INTEGER PRIMARY KEY, user_id INTEGER, type_id INTEGER, region_id INTEGER, description TEXT, status TEXT, admin_note TEXT, handled_by INTEGER, created_at INTEGER, updated_at INTEGER, provider_id INTEGER, accepted_at INTEGER, address TEXT, preferred_at INTEGER, budget_min INTEGER, budget_max INTEGER, cancelled_by TEXT, dispute_reason TEXT, disputed_by TEXT, disputed_at INTEGER);
CREATE TABLE service_ratings(id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL UNIQUE, provider_id INTEGER NOT NULL, user_id INTEGER NOT NULL, stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5), created_at INTEGER NOT NULL);
INSERT INTO service_ratings VALUES(1,1,1,1,4,100);
""")
import svc; svc.install(c); svc.install(c)
ok("migration: old rows kept, hidden defaults 0, columns added, idempotent", c.execute("SELECT stars,hidden,comment,updated_at FROM service_ratings").fetchall() == [(4, 0, None, None)] and svc.rating_of(c, 1)["rating_count"] == 1)

# ---- UI wiring (static) ----
HERE = os.path.dirname(os.path.abspath(__file__)); rd = lambda f: open(os.path.join(HERE, f), encoding="utf8").read()
ix, ad, sw = rd("static/index.html"), rd("static/admin.html"), rd("static/sw.js")
ok("UI: index has comment box, edit/delete, public ratings, provider report", all(k in ix for k in ("rcm", "srEdit", "srDel", "svrs", "spR", "/my/service-ratings", "/ratings")))
ok("UI: admin has rating reports section", all(k in ad for k in ("service-rating-reports", "rrd(")))
ok("UI: cache bumped to >= v45", int(__import__("re").search(r"laqino-v(\d+)", sw).group(1)) >= 45 and int(__import__("re").search(r"release=phase-(\d+)", rd("VERSION")).group(1)) >= 9)
print("ALL PASS")
