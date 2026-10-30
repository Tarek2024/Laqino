# phase-76 / م3 «دفتر الصيدلية»: لوحة الدليفري (ملخص، بحث برقم عميل/مندوب، تفاصيل، تصدير CSV) — قراءة فقط ولطلبات الصيدلية نفسها
import os, json, urllib.parse, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, provider_delivery
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8976; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}; Z2 = Z["المجد 55"]
cust, cid = user("01070000001"); ph, pid = user("01070000002"); ph2, pid2 = user("01070000003"); c1, u1 = user("01070000004"); c2, u2 = user("01070000005")
for t, i, n in ((ph, pid, "صيدلية النور"), (ph2, pid2, "صيدلية الأمل")):
    call("POST", "/providers/apply", {"name_ar": n, "region_id": Z2, "address": "شارع البحر"}, t); call("POST", f"/admin/providers/{i}/review", {"status": "approved"}, at)
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 0}, at)
mk = lambda t=ph, **x: call("POST", "/provider/delivery-request", x, t)
cord = lambda t, oid: ([o for o in call("GET", "/courier/orders", None, t)[1] if o["id"] == oid] or [None])[0]
mine = lambda oid, t=ph: ([o for o in call("GET", "/provider/delivery-requests", None, t)[1]["items"] if o["id"] == oid] or [None])[0]



cs = lambda t, oid, to: call("POST", f"/courier/orders/{oid}/status", {"to": to}, t)
def run(t, **x):
    oid = mk(**x)[1]["id"]; call("POST", f"/courier/orders/{oid}/accept", {}, t)
    for st in ("heading_pickup", "picked_up", "heading_customer", "completed"): cs(t, oid, st)
    return oid
dash = lambda t=ph, q="range=today": call("GET", "/provider/delivery-dashboard?" + q, None, t)
o1 = run(c1, request_key="d1", customer_phone="01001230001", price=40, note="كيس")
o2 = run(c1, request_key="d2", customer_phone="+20 100 123 0001", price=60)
o3 = run(c2, request_key="d3", customer_phone="01001230002", price=25)
mk(request_key="d4", customer_phone="01001230003")  # يظل بانتظار مندوب
s, d = dash()
ok("dashboard summary", s == 200 and d["summary"]["total"] == 4 and d["summary"]["completed"] == 3 and d["summary"]["open"] == 1 and d["summary"]["price_sum"] == 125)
ok("repeat customer today", d["repeat_today"] == [{"phone": "01001230001", "count": 2}])
ok("items have no courier id / norm / phone", all("courier_id" not in i and "pd_cust_norm" not in i and "courier_phone" not in i for i in d["items"]))
ok("other pharmacy sees nothing of it", dash(ph2)[1]["summary"]["total"] == 0)
ok("non-pharmacy user refused", dash(cust)[0] == 403)
ok("bad dates 400", dash(q="from=oops")[0] == 400 and dash(q="from=2026-02-01&to=2026-01-01")[0] == 400)
s, x = call("GET", "/provider/delivery-search?phone=0100%20123%200001", None, ph)
ok("customer search: normalised, counts", s == 200 and x["today"] == 2 and x["total"] == 2 and len(x["items"]) == 2)
ok("customer search: other pharmacy isolated", call("GET", "/provider/delivery-search?phone=01001230001", None, ph2)[1]["total"] == 0)
nm = sql("SELECT name FROM users WHERE id=?", u1)[0][0]
s, x = call("GET", "/provider/delivery-search?courier=" + urllib.parse.quote(nm) + "&range=all", None, ph)
ok("courier search by name", s == 200 and x["summary"]["completed"] >= 2 and all(i["courier_name"] == nm for i in x["items"]))
ok("courier partial phone does not match", call("GET", "/provider/delivery-search?courier=0107000&range=all", None, ph)[1]["couriers"] == [])
ok("search needs exactly one key", call("GET", "/provider/delivery-search", None, ph)[0] == 400)
s, x = call("GET", f"/provider/delivery-order?id={o1}", None, ph)
ok("order detail with timeline", s == 200 and x["pd_note"] == "كيس" and [e["to"] for e in x["events"]][-1] == "completed" and x["courier_phone"] is None)
ok("detail of another pharmacy's order 404", call("GET", f"/provider/delivery-order?id={o1}", None, ph2)[0] == 404)
s, x = call("GET", "/provider/delivery-export?range=today", None, ph)
ok("csv export", s == 200 and x["count"] == 4 and x["csv"].startswith("\ufeff") and "01001230001" in x["csv"])
call("POST", "/admin/provider-delivery", {"enabled": False}, at)
ok("history still readable while feature is off", dash()[0] == 200)
print("ALL PASS")
