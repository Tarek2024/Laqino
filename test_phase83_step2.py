# المرحلة 83 / خطوة 2: بيانات المندوب لعميل طلب المحل من القبول (مأخوذ إعداده من اختبار م69). المرحلة 69 (م4 من خطة المحلات): الدليفري للمحلات — المحل يطلب مندوب (مثل الصيدلية) + العميل يطلب من المحل ويوصله المندوب. قاعدة مؤقتة معزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8983; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
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
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at); call("POST", "/admin/region-fees", {"region_id": Z2, "fee": 25}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
own, oid_ = user("01090000001"); own2, _ = user("01090000002"); cust, cid = user("01090000003"); cust2, _ = user("01090000004"); stf, sid_ = user("01090000007"); c1, u1 = user("01090000005"); c2, u2 = user("01090000006")
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
call("POST", "/admin/shops-settings", {"enabled": True}, at)
def mkshop(t, tid, nm, approve=True):
    r = call("POST", "/shops/apply", {"type_id": tid, "name_ar": nm, "address": "شارع النصر", "phone": "01012345678", "region_id": Z2}, t)[1]["id"]
    if approve: call("POST", "/admin/shops/%d/review" % r, {"status": "approved"}, at)
    return r
S1 = mkshop(own, 1, "مطعم الأمل"); S2 = mkshop(own2, 2, "سوبر ماركت النور"); SP = mkshop(cust2, 3, "حلويات معلقة", approve=False)
call("POST", "/owner/shops/%d/open" % S1, {}, own)
I = lambda s: "/owner/shops/%d/items" % s
i1 = call("POST", I(S1), {"name_ar": "كشري", "price": 35.5}, own)[1]["id"]; i2 = call("POST", I(S1), {"name_ar": "فول", "price": 10}, own)[1]["id"]
i3 = call("POST", I(S1), {"name_ar": "طعمية", "price": 8, "is_available": False}, own)[1]["id"]; ix = call("POST", I(S2), {"name_ar": "أرز", "price": 20}, own2)[1]["id"]
def pk(s, **x): return call("POST", "/owner/shops/%d/delivery-request" % s, x, own)
def ordr(**x): return call("POST", "/shops/%d/order" % S1, x, cust)
def cord(t, oid): return [o for o in call("GET", "/courier/orders", None, t)[1] if o["id"] == oid][0]
def notifs(t): return call("GET", "/notifications", None, t)[1]
GOOD = {"items": [{"item_id": i1, "qty": 2}, {"item_id": i2, "qty": 1}], "dropoff_text": "عمارة 5 شقة 3"}

call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 2}, at)
def mine(t, oid): return [o for o in call("GET", "/delivery/orders", None, t)[1] if o["id"] == oid][0]
oo = ordr(**GOOD)[1]["id"]
m = mine(cust, oo)
ok("searching: no courier data", m["status"] == "searching" and m["courier_name"] is None and m["courier_phone"] is None and m["courier_id"] is None)
ok("accept goes to fare draft (fare cycle untouched)", call("POST", f"/courier/orders/{oo}/accept", {}, c1) == (200, {"ok": True, "fee": 25, "fare_status": "draft"}))
m = mine(cust, oo); ph1 = sql("SELECT phone FROM users WHERE id=?", u1)[0][0]
ok("draft: customer already sees courier name, phone, id", m["fare_status"] == "draft" and m["courier_name"] and m["courier_phone"] == ph1 and m["courier_id"] == u1)
ok("draft: fee still hidden from customer (fare cycle unchanged)", m["fee"] is None)
ok("draft: customer can open the courier profile card", call("GET", f"/couriers/{u1}/profile", None, cust)[0] == 200)
ok("courier still cannot see customer data before approval", cord(c1, oo)["customer_phone"] is None)
ok("courier cannot start before fare approval", call("POST", f"/courier/orders/{oo}/status", {"to": "heading_pickup"}, c1)[0] == 409)
ok("propose + approve still works", call("POST", f"/courier/orders/{oo}/fare", {"fee": 35}, c1)[0] == 200 and call("POST", f"/delivery/orders/{oo}/fare/approve", {"fee": 35}, cust)[0] == 200)
m = mine(cust, oo); ok("approved: data + fee shown", m["courier_phone"] == ph1 and m["fee"] == 35)
# رفض الأجرة: يرجع للبحث ويختفي المندوب
o2 = ordr(**GOOD)[1]["id"]; call("POST", f"/courier/orders/{o2}/accept", {}, c2); call("POST", f"/courier/orders/{o2}/fare", {"fee": 90}, c2)
call("POST", f"/delivery/orders/{o2}/fare/reject", {}, cust); m = mine(cust, o2)
ok("after fare rejection: back to searching, courier data hidden again", m["status"] == "searching" and m["courier_name"] is None and m["courier_phone"] is None and m["courier_id"] is None)
# طلب عادي (غير محل) في draft لا يكشف شيئًا: السلوك القديم
rg = Z2; r0 = call("POST", "/delivery/orders", {"pickup_text": "شارع أ", "dropoff_text": "شارع ب", "region_id": rg}, cust)
n = r0[1]["id"]; call("POST", f"/courier/orders/{n}/accept", {}, c1); m = mine(cust, n)
ok("regular (non-shop) order in draft: still hidden", r0[0] == 201 and m["fare_status"] == "draft" and m["courier_name"] is None and m["courier_phone"] is None)
ok("another customer never sees the courier", all(o["id"] != oo for o in call("GET", "/delivery/orders", None, cust2)[1]))
ok("stranger cannot open the courier profile", call("GET", f"/couriers/{u1}/profile", None, cust2)[0] == 404)
print("ALL PASS")
