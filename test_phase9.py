import base64, os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8774), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request("http://127.0.0.1:8774/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); b = x.read(); return x.status, (b if raw else json.loads(b))
    except urllib.error.HTTPError as e: b = e.read(); return e.code, (b if raw else json.loads(b))
import sqlite3 as _sq3
_call = call
def call(m, p, *a, **k):  # الخطوة 4: رد الصيدلية يلزمه اعتماد الإدارة قبل أن يراه العميل؛ هذا الاختبار يفترض أن الإدارة اعتمدت كل الردود (الاعتماد نفسه في test_step4_rx.py)
    if (m == "GET" and p.startswith("/medical/prescriptions")) or p == "/medical/delivery":
        _c = _sq3.connect(os.environ["LAQINO_DB"]); _c.execute("UPDATE prescription_responses SET review='approved' WHERE review='pending'"); _c.commit(); _c.close()
    return _call(m, p, *a, **k)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cust, other, ph1, ph2, ph3 = user("01012345678"), user("01099999999"), user("01011111111"), user("01022222222"), user("01033333333")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
uid = lambda t: call("GET", "/me", None, t)[1]["id"]
for t, n in ((ph1, "صيدلية الأمل"), (ph2, "صيدلية النور")):
    call("POST", "/providers/apply", {"name_ar": n, "region_id": 3, "address": "الرياض"}, t); call("POST", f"/admin/providers/{uid(t)}/review", {"status": "approved"}, at)
call("POST", "/providers/apply", {"name_ar": "صيدلية معلقة", "region_id": 3}, ph3)
ok("customer cannot approve providers", call("POST", f"/admin/providers/{uid(ph3)}/review", {"status": "approved"}, other)[0] == 403)
ok("unapproved pharmacy blocked", call("GET", "/provider/inquiries", None, ph3)[0] == 403)
# stock + search
ok("search before any confirmation: empty, not 'unavailable'", call("GET", "/medical/search?q=panadol&region_id=3")[1] == [])
ok("stock needs price when available", call("POST", "/provider/stock", {"medicine_name": "Panadol", "available": True}, ph1)[0] == 400)
call("POST", "/provider/stock", {"medicine_name": "Panadol", "available": True, "price": 55}, ph1); call("POST", "/provider/stock", {"medicine_name": "Panadol", "available": False}, ph2)
r = call("GET", "/medical/search?q=panadol&region_id=3")[1]
ok("only confirmed-available pharmacy shown with price + time", len(r) == 1 and r[0]["pharmacy"] == "صيدلية الأمل" and r[0]["price"] == 55 and r[0]["confirmed_at"])
server_db = server.db(); server_db.execute("UPDATE provider_stock SET confirmed_at=confirmed_at-200000"); server_db.commit()
ok("stale confirmation not shown as available", call("GET", "/medical/search?q=panadol&region_id=3")[1] == [])
# inquiries
st, i = call("POST", "/medical/inquiries", {"medicine_name": "دواء غير موجود", "region_id": 3}, cust)
ok("inquiry created waiting", st == 201 and i["status"] == "waiting" and call("GET", "/medical/inquiries", None, cust)[1][0]["responses"] == [])
ok("pharmacy sees inquiry without customer identity", (lambda l: len(l) == 1 and "customer" not in json.dumps(l))(call("GET", "/provider/inquiries", None, ph1)[1]))
ok("available needs price", call("POST", f"/provider/inquiries/{i['id']}/respond", {"status": "available"}, ph1)[0] == 400)
ok("pharmacy1 confirms with price", call("POST", f"/provider/inquiries/{i['id']}/respond", {"status": "available", "price": 80}, ph1)[0] == 200)
ok("pharmacy2 says unavailable", call("POST", f"/provider/inquiries/{i['id']}/respond", {"status": "unavailable"}, ph2)[0] == 200)
rs = call("GET", "/medical/inquiries", None, cust)[1][0]["responses"]
ok("customer sees per-pharmacy statuses", {x["pharmacy"]: x["status"] for x in rs} == {"صيدلية الأمل": "available", "صيدلية النور": "unavailable"})
call("POST", f"/provider/inquiries/{i['id']}/respond", {"status": "needs_confirmation", "note": "نتأكد"}, ph1)
ok("pharmacy can update its own answer (one row)", len([x for x in call("GET", "/medical/inquiries", None, cust)[1][0]["responses"] if x["pharmacy"] == "صيدلية الأمل"]) == 1)
ok("other customer sees none of my inquiries", call("GET", "/medical/inquiries", None, other)[1] == [])
ok("cancelled inquiry leaves pharmacy queue", call("POST", f"/medical/inquiries/{i['id']}/cancel", None, cust)[0] == 200 and call("GET", "/provider/inquiries", None, ph1)[1] == [])
# files + prescriptions
png = __import__("imgutil").png()
ok("non-image rejected", call("POST", "/files", {"data": base64.b64encode(b"hello world").decode()}, cust)[0] == 400)
ok("anonymous upload blocked", call("POST", "/files", {"data": png})[0] == 401)
fid = call("POST", "/files", {"data": png}, cust)[1]["id"]
ok("owner reads file", call("GET", f"/files/{fid}", None, cust, raw=True)[0] == 200)
ok("stranger cannot read file", call("GET", f"/files/{fid}", None, other, raw=True)[0] == 404)
ok("pharmacy cannot read file before forward", call("GET", f"/files/{fid}", None, ph1, raw=True)[0] == 404)
ok("cannot attach someone else's file", call("POST", "/medical/prescriptions", {"file_id": fid, "region_id": 3}, other)[0] == 400)
pid = call("POST", "/medical/prescriptions", {"file_id": fid, "region_id": 3}, cust)[1]["id"]
ok("pharmacy sees no unforwarded prescriptions", call("GET", "/provider/prescriptions", None, ph1)[1] == [])
ok("admin can read file", call("GET", f"/files/{fid}", None, at, raw=True)[0] == 200)
ok("customer cannot forward", call("POST", f"/admin/prescriptions/{pid}/forward", {"provider_id": uid(ph1)}, cust)[0] == 403)
ok("cannot forward to unapproved pharmacy", call("POST", f"/admin/prescriptions/{pid}/forward", {"provider_id": uid(ph3)}, at)[0] == 400)
ok("admin forwards to pharmacy1", call("POST", f"/admin/prescriptions/{pid}/forward", {"provider_id": uid(ph1)}, at)[0] == 200)
ok("pharmacy1 sees and reads it", len(call("GET", "/provider/prescriptions", None, ph1)[1]) == 1 and call("GET", f"/files/{fid}", None, ph1, raw=True)[0] == 200)
ok("pharmacy2 still blocked", call("GET", "/provider/prescriptions", None, ph2)[1] == [] and call("GET", f"/files/{fid}", None, ph2, raw=True)[0] == 404 and call("POST", f"/provider/prescriptions/{pid}/respond", {"status": "unavailable"}, ph2)[0] == 404)
ok("pharmacy1 answers prescription", call("POST", f"/provider/prescriptions/{pid}/respond", {"status": "available", "price": 210, "note": "الأصناف كاملة"}, ph1)[0] == 200)
ok("customer sees prescription answer", call("GET", "/medical/prescriptions", None, cust)[1][0]["responses"][0]["price"] == 210)
ok("other user cannot delete file", call("POST", f"/files/{fid}/delete", {}, other)[0] == 404)
ok("owner deletes image; request closed, pharmacy loses access", call("POST", f"/files/{fid}/delete", {}, cust)[0] == 200 and call("GET", "/provider/prescriptions", None, ph1)[1] == [] and call("GET", f"/files/{fid}", None, cust, raw=True)[0] == 404 and call("GET", "/medical/prescriptions", None, cust)[1][0]["status"] == "closed")
print("ALL PASSED")
