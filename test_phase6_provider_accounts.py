# المرحلة 6: مقدم الخدمة كحساب (svc.py). قاعدة مؤقتة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8798), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8798"; DB = os.environ["LAQINO_DB"]
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
CU, PV, PV2, OT = user("01077770001"), user("01077770002"), user("01077770003"), user("01077770004")
rid = 3
tid = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
tid2 = call("POST", "/admin/service-types", {"name_ar": "كهرباء"}, at)[1]["id"]
def prov(name, t, r=rid):
    p = call("POST", "/admin/services", {"name_ar": name, "type_id": t, "region_id": r, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
    call("POST", f"/admin/services/{p}/publish", {"published": True}, at); return p
p1, p2 = prov("المعلم سمير", tid), prov("المعلم كمال", tid2)
body = {"type_id": tid, "region_id": rid, "description": "محتاج سباك لإصلاح تسريب في الحمام"}

ok("migration columns exist", {"owner_user_id"} <= {r[1] for r in sql("PRAGMA table_info(service_providers)")} and {"provider_id", "accepted_at"} <= {r[1] for r in sql("PRAGMA table_info(service_requests)")})
ok("unlinked account: list is empty 200, actions 403", call("GET", "/my/service-jobs", None, PV) == (200, {"providers": [], "jobs": []}) and call("POST", "/my/service-jobs/1/accept", {}, PV)[0] == 403)
ok("anonymous gets 401", call("GET", "/my/service-jobs")[0] == 401)
ok("customer cannot link owners (403)", call("POST", "/admin/service-owners", {"provider_id": p1, "phone": "01077770002"}, CU)[0] == 403)
ok("link unknown phone -> 404", call("POST", "/admin/service-owners", {"provider_id": p1, "phone": "01012345678"}, at)[0] == 404)
ok("link unknown provider -> 404", call("POST", "/admin/service-owners", {"provider_id": 9999, "phone": "01077770002"}, at)[0] == 404)
ok("cannot link admin account", call("POST", "/admin/service-owners", {"provider_id": p1, "phone": "01000000000"}, at)[0] == 400)
ok("admin links provider1 -> PV", call("POST", "/admin/service-owners", {"provider_id": p1, "phone": "01077770002"}, at)[0] == 200)
ok("admin links provider2 -> PV2", call("POST", "/admin/service-owners", {"provider_id": p2, "phone": "01077770003"}, at)[0] == 200)
lst = call("GET", "/admin/service-owners", None, at)[1]
ok("admin owners list shows owner phone", any(x["id"] == p1 and x["owner_phone"] == "01077770002" for x in lst))
ok("linked user got notification", sql("SELECT COUNT(*) FROM notifications WHERE kind='service_provider.linked'")[0][0] == 2)

s, r = call("POST", "/service-requests", body, CU); ok("customer creates request", s == 201); r1 = r["id"]
ok("matching owner notified, non-matching not", sql("SELECT COUNT(*) FROM notifications WHERE kind='service_request.job'")[0][0] == 1)
jobs = call("GET", "/my/service-jobs", None, PV)[1]
ok("provider sees matching open job without phone", [j["id"] for j in jobs["jobs"]] == [r1] and "phone" not in json.dumps(jobs["jobs"]) and "customer_name" not in json.dumps(jobs["jobs"]))
ok("non-matching provider sees nothing", call("GET", "/my/service-jobs", None, PV2)[1]["jobs"] == [])
ok("non-matching provider cannot accept (403)", call("POST", f"/my/service-jobs/{r1}/accept", {}, PV2)[0] == 403)
ok("other user cannot accept (403)", call("POST", f"/my/service-jobs/{r1}/accept", {}, OT)[0] == 403)
s, a = call("POST", f"/my/service-jobs/{r1}/accept", {}, PV)
ok("provider accepts -> accepted and gets customer phone", s == 200 and a["status"] == "accepted" and a["customer_phone"] == "01077770001")
ok("second accept -> 409", call("POST", f"/my/service-jobs/{r1}/accept", {}, PV)[0] == 409)
mine = call("GET", "/service-requests", None, CU)[1]
ok("customer sees provider name, no phone", mine[0]["status"] == "accepted" and mine[0]["accepted_by"] == "المعلم سمير" and "01099990000" not in json.dumps(mine) and "phone" not in json.dumps(mine))
ok("customer notified of acceptance", sql("SELECT COUNT(*) FROM notifications WHERE kind='service_request.accepted' AND user_id=(SELECT id FROM users WHERE phone='01077770001')")[0][0] == 1)
pj = call("GET", "/my/service-jobs", None, PV)[1]["jobs"]
ok("accepted job listed as mine with customer info", len(pj) == 1 and pj[0]["mine"] and pj[0]["customer_phone"] == "01077770001")
ok("other provider cannot finish it (404)", call("POST", f"/my/service-jobs/{r1}/done", {}, PV2)[0] == 404)
ok("release returns job to open", call("POST", f"/my/service-jobs/{r1}/release", {}, PV)[1]["status"] == "open" and sql("SELECT provider_id FROM service_requests WHERE id=?", (r1,))[0][0] is None)
ok("released job visible again, no phone", "customer_phone" not in json.dumps(call("GET", "/my/service-jobs", None, PV)[1]["jobs"]))
call("POST", f"/my/service-jobs/{r1}/accept", {}, PV)
ok("done -> done", call("POST", f"/my/service-jobs/{r1}/done", {}, PV)[1]["status"] == "done")
ok("done job cannot be released (409)", call("POST", f"/my/service-jobs/{r1}/release", {}, PV)[0] == 409)
ok("customer notified of done", sql("SELECT COUNT(*) FROM notifications WHERE kind='service_request.done'")[0][0] == 1)

# atomic claim race: two providers of the same type/region
p3 = prov("المعلم نبيل", tid); call("POST", "/admin/service-owners", {"provider_id": p3, "phone": "01077770004"}, at)
s, r = call("POST", "/service-requests", body, CU); r2 = r["id"]
res = []
def go(t): res.append(call("POST", f"/my/service-jobs/{r2}/accept", {}, t)[0])
th = [threading.Thread(target=go, args=(t,)) for t in (PV, OT)]; [x.start() for x in th]; [x.join() for x in th]
ok("race: exactly one accepts", sorted(res) == [200, 409])
_winner = sql("SELECT provider_id FROM service_requests WHERE id=?", (r2,))[0][0]
ok("unlink returns in-progress job to open", call("POST", "/admin/service-owners", {"provider_id": sql("SELECT provider_id FROM service_requests WHERE id=?", (r2,))[0][0]}, at)[0] == 200 and sql("SELECT status,provider_id FROM service_requests WHERE id=?", (r2,))[0] == ("open", None))
call("POST", "/admin/service-owners", {"provider_id": p1, "phone": "01077770002"}, at); call("POST", "/admin/service-owners", {"provider_id": p3, "phone": "01077770004"}, at)  # الفائز بالسباق متغيّر: أعد الربط صراحةً
# unpublished provider loses access to new jobs
call("POST", f"/admin/services/{p1}/publish", {"published": False}, at)
ok("unpublished provider sees no open jobs and cannot accept", call("GET", "/my/service-jobs", None, PV)[1]["jobs"] == [] or all(j["mine"] for j in call("GET", "/my/service-jobs", None, PV)[1]["jobs"]))
ok("unpublished provider accept -> 403", call("POST", f"/my/service-jobs/{r2}/accept", {}, PV)[0] == 403)
# job cap
call("POST", f"/admin/services/{p1}/publish", {"published": True}, at)
sql("UPDATE service_requests SET status='done' WHERE status IN('open','accepted','on_the_way','in_progress')")
ids = []
for i in range(11):
    sql("INSERT INTO service_requests(user_id,type_id,region_id,description,created_at,updated_at) VALUES(1,?,?,?,?,?)", (tid, rid, "طلب رقم %d لاختبار الحد" % i, int(time.time()), int(time.time())))
ids = [x[0] for x in sql("SELECT id FROM service_requests WHERE status='open' ORDER BY id")]
codes = [call("POST", f"/my/service-jobs/{i}/accept", {}, PV)[0] for i in ids]
ok("job cap: 10 accepted then 429", codes.count(200) == 10 and codes[-1] == 429)
ok("no raw phone of provider leaks via customer API", "01099990000" not in json.dumps(call("GET", "/service-requests", None, CU)[1]))
HERE = os.path.dirname(os.path.abspath(__file__)); rd = lambda f: open(os.path.join(HERE, f), encoding="utf8").read()
ix, ad, nf, sw = rd("static/index.html"), rd("static/admin.html"), rd("static/notif.js"), rd("static/sw.js")
ok("UI: provider jobs panel + accept/done/release wired in index", all(k in ix for k in ("/my/service-jobs", "window.sjp=", "window.sja=", "accepted_by")))
ok("UI: provider panel escapes values with esc()", "esc(j.description)" in ix and "esc(j.customer_name)" in ix)
ok("UI: admin owner-link control wired", all(k in ad for k in ("/admin/service-owners", "window.sol=", "window.own=")))
import re
ok("UI: notification link svcjob + cache >= v37", "svcjob" in nf and int(re.search(r"laqino-v(\d+)", sw).group(1)) >= 37)
print("ALL PASS")
