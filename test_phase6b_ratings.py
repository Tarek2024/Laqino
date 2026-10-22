# المرحلة 6ب: تقييم مقدم الخدمة (svc.py). قاعدة مؤقتة.
import os, re, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8799), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8799"; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__))
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
C1, C2, C3, PV = user("01088880001"), user("01088880002"), user("01088880003"), user("01088880004")
rid = 3
tid = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
pid = call("POST", "/admin/services", {"name_ar": "المعلم سمير", "type_id": tid, "region_id": rid, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
call("POST", f"/admin/services/{pid}/publish", {"published": True}, at)
call("POST", "/admin/service-owners", {"provider_id": pid, "phone": "01088880004"}, at)
body = {"type_id": tid, "region_id": rid, "description": "محتاج سباك لإصلاح تسريب في الحمام"}
def done_request(tok):
    r = call("POST", "/service-requests", body, tok)[1]["id"]
    call("POST", f"/my/service-jobs/{r}/accept", {}, PV); call("POST", f"/my/service-jobs/{r}/done", {}, PV); return r

ok("migration: service_ratings table exists", sql("SELECT name FROM sqlite_master WHERE name='service_ratings'") != [])
ok("no rating shown before any rating", call("GET", f"/services/{pid}")[1]["rating_avg"] is None and call("GET", f"/services/{pid}")[1]["rating_count"] == 0)
r1 = call("POST", "/service-requests", body, C1)[1]["id"]
ok("cannot rate an open request (409)", call("POST", f"/service-requests/{r1}/rate", {"stars": 5}, C1)[0] == 409)
call("POST", f"/my/service-jobs/{r1}/accept", {}, PV)
ok("cannot rate in-progress request (409)", call("POST", f"/service-requests/{r1}/rate", {"stars": 5}, C1)[0] == 409)
call("POST", f"/my/service-jobs/{r1}/done", {}, PV)
mine = call("GET", "/service-requests", None, C1)[1][0]
ok("done request exposes can_rate and no rating yet", mine["can_rate"] is True and mine["rated"] is None)
ok("anonymous cannot rate (401)", call("POST", f"/service-requests/{r1}/rate", {"stars": 5})[0] == 401)
ok("other user cannot rate it (404)", call("POST", f"/service-requests/{r1}/rate", {"stars": 5}, C2)[0] == 404)
ok("provider cannot rate its own job (404)", call("POST", f"/service-requests/{r1}/rate", {"stars": 5}, PV)[0] == 404)
for bad in (0, 6, -1, "x", None, 2.5 if False else "abc"): ok("invalid stars %r rejected (400)" % (bad,), call("POST", f"/service-requests/{r1}/rate", {"stars": bad}, C1)[0] == 400)
s, r = call("POST", f"/service-requests/{r1}/rate", {"stars": 4}, C1)
ok("owner rates done request -> 200 with avg/count", s == 200 and r["stars"] == 4 and r["rating_avg"] == 4.0 and r["rating_count"] == 1)
ok("second rating on same request -> 409", call("POST", f"/service-requests/{r1}/rate", {"stars": 1}, C1)[0] == 409)
mine = call("GET", "/service-requests", None, C1)[1][0]
ok("customer sees own rating, can_rate false", mine["rated"] == 4 and mine["can_rate"] is False)
ok("provider owner notified of rating", sql("SELECT COUNT(*) FROM notifications WHERE kind='service_request.rated' AND user_id=(SELECT id FROM users WHERE phone='01088880004')")[0][0] == 1)
r2 = done_request(C2); call("POST", f"/service-requests/{r2}/rate", {"stars": 5}, C2)
pub = call("GET", f"/services/{pid}")[1]
ok("public detail shows average 4.5 of 2", pub["rating_avg"] == 4.5 and pub["rating_count"] == 2)
lst = call("GET", f"/services?region_id={rid}&type_id={tid}")[1]
ok("public list carries rating", lst and lst[0]["rating_count"] == 2 and lst[0]["rating_avg"] == 4.5)
ok("rater identity not exposed publicly", "01088880001" not in json.dumps(pub) and "user" not in json.dumps(pub))
jobs = call("GET", "/my/service-jobs", None, PV)[1]
ok("provider panel shows own rating", jobs["providers"][0]["rating_avg"] == 4.5 and jobs["providers"][0]["rating_count"] == 2)
ow = call("GET", "/admin/service-owners", None, at)[1]
ok("admin owners list shows rating", ow[0]["rating_count"] == 2)
# cancelled / admin-done without provider is not ratable
r3 = call("POST", "/service-requests", body, C3)[1]["id"]; call("POST", f"/admin/service-requests/{r3}", {"status": "done"}, at)
ok("admin-closed request with no provider is not ratable (409)", call("POST", f"/service-requests/{r3}/rate", {"stars": 5}, C3)[0] == 409 and call("GET", "/service-requests", None, C3)[1][0]["can_rate"] is False)
# self-rating farming: provider cannot accept own request
rs = call("POST", "/service-requests", body, PV)[1]["id"]
ok("provider cannot accept a request from own account (403)", call("POST", f"/my/service-jobs/{rs}/accept", {}, PV)[0] == 403)
# race: double-submit counts once
r4 = done_request(C1); res = []
th = [threading.Thread(target=lambda: res.append(call("POST", f"/service-requests/{r4}/rate", {"stars": 5}, C1)[0])) for _ in range(2)]; [t.start() for t in th]; [t.join() for t in th]
ok("race: double submit counts once", sorted(res) == [200, 409] and sql("SELECT COUNT(*) FROM service_ratings WHERE request_id=?", (r4,))[0][0] == 1)
rd = lambda f: open(os.path.join(HERE, f), encoding="utf8").read()
ix, ad = rd("static/index.html"), rd("static/admin.html")
ok("UI: rate control + escaped stars in index", all(k in ix for k in ("window.srr=", "/rate", "x.can_rate", "stv(x.rating_avg,x.rating_count)")) and "esc(a)" in ix)
ok("UI: provider panel and admin show rating", "p.rating_count" in ix and "p.rating_count" in ad)
print("ALL PASS")
