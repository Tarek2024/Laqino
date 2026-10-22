# المرحلة 10: التوزيع على المندوبين المتصلين — Heartbeat، عروض، رفض، مهلة، قبول ذري متزامن، رمز التسليم، العمولة مرة واحدة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(); os.environ["LAQINO_TEST_PRESENCE"] = "1"
import server
from testutil import apply_docs, fare_ok
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8778), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8778/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def q(sql, *a):
    c = sqlite3.connect(DB); r = c.execute(sql, a).fetchall(); c.commit(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
def mk_courier(ph, topup=200, approve=True):
    t = user(ph); i = call("GET", "/me", None, t)[1]["id"]; apply_docs(call, t)
    if approve: call("POST", f"/admin/couriers/{i}/review", {"status": "approved"}, at)
    if topup:
        call("POST", "/courier/topups", {"amount": topup, "transfer_ref": "REF" + ph}, t)
        call("POST", f"/admin/topups/{[x for x in call('GET', '/admin/topups', None, at)[1] if x['transfer_ref'] == 'REF' + ph][0]['id']}/review", {"status": "approved"}, at)
    return t, i
A, ai = mk_courier("01011111111"); B, bi = mk_courier("01022222222"); C, ci = mk_courier("01033333333"); D, di = mk_courier("01044444444", topup=0, approve=False); E0, ei = mk_courier("01055555555", topup=0)
cu = user("01066666666")
order = lambda **k: call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb", **k}, cu)
ids = lambda t: [x["id"] for x in call("GET", "/courier/available", None, t)[1] if not x["taken"]]

# --- حضور المندوب
o1 = order()[1]["id"]
q("UPDATE couriers SET last_seen=0,is_available=0"); ok("courier in offline mode: available list empty", call("GET", "/courier/available", None, A)[1] == [])
q("UPDATE couriers SET last_seen=0,is_available=1")  # available flag on but heartbeat stale
st, _ = call("POST", f"/courier/orders/{o1}/accept", None, A); ok("accept refused when no recent heartbeat (403)", st == 403)
ok("status endpoint explains offline reason", "لا توجد إشارة اتصال حديثة" in " ".join(call("GET", "/courier/status", None, A)[1]["reasons"]))
for t in (A, B, E0): call("POST", "/courier/online", {"online": True}, t)
ok("online toggle sets heartbeat; status online", call("GET", "/courier/status", None, A)[1]["online"] is True)
ok("order reaches online eligible couriers A and B", o1 in ids(A) and o1 in ids(B))
ok("offline (never connected) courier C gets no offer", ids(C) == [] and not q("SELECT 1 FROM order_offers WHERE courier_id=?", ci))
ok("unapproved courier D blocked (403)", call("GET", "/courier/available", None, D)[0] == 403 and call("POST", f"/courier/orders/{o1}/accept", None, D)[0] == 403)
ok("zero-balance courier gets no offer and 402 on accept", ids(E0) == [] and call("POST", f"/courier/orders/{o1}/accept", None, E0)[0] == 402)
ok("insufficient balance reason shown", "رصيدك غير كافٍ" in " ".join(call("GET", "/courier/status", None, E0)[1]["reasons"]))
ok("offer carries countdown, no address/customer data", all(set(x) == {"id", "region_id", "region_name", "offer_fee", "created_at", "expires_in", "taken"} and 0 < x["expires_in"] <= 30 for x in call("GET", "/courier/available", None, A)[1]))

# --- قبول متزامن: واحد فقط
res = []
def go(t): res.append(call("POST", f"/courier/orders/{o1}/accept", None, t)[0])
th = [threading.Thread(target=go, args=(t,)) for t in (A, B)]; [x.start() for x in th]; [x.join() for x in th]
ok("two simultaneous accepts: exactly one 200 and one 409", sorted(res) == [200, 409])
win = q("SELECT courier_id FROM delivery_orders WHERE id=?", o1)[0][0]; lose = B if win == ai else A; loseid = bi if win == ai else ai
ok("order has a single courier; offers marked accepted/lost", sorted(r[0] for r in q("SELECT status FROM order_offers WHERE order_id=?", o1)) == ["accepted", "lost"])
av = call("GET", "/courier/available", None, lose)[1]
ok("losing courier sees 'taken by another courier' marker, not an actionable offer", [x for x in av if x["id"] == o1 and x["taken"] == 1] and o1 not in ids(lose))
ok("losing courier cannot accept later (409)", call("POST", f"/courier/orders/{o1}/accept", None, lose)[0] == 409)
winT = A if win == ai else B

# --- رفض، مهلة، إعادة البحث
o2 = order()[1]["id"]
ok("both see new order", o2 in ids(A) and o2 in ids(B))
ok("reject accepted", call("POST", f"/courier/orders/{o2}/reject", None, A)[0] == 200)
ok("rejecting courier no longer sees it; order still searching for the other", o2 not in ids(A) and o2 in ids(B) and q("SELECT status FROM delivery_orders WHERE id=?", o2)[0][0] == "searching")
ok("rejected courier cannot accept it (409)", call("POST", f"/courier/orders/{o2}/accept", None, A)[0] == 409)
q("UPDATE order_offers SET offered_at=offered_at-100 WHERE order_id=? AND courier_id=?", o2, bi)
ids(B)  # poll: expires then re-offers within the search window
r = q("SELECT status,rounds FROM order_offers WHERE order_id=? AND courier_id=?", o2, bi)[0]
ok("unanswered offer expired then re-offered (round 2)", r == ("offered", 2))
q("UPDATE delivery_orders SET search_started_at=search_started_at-1000,created_at=created_at-1000 WHERE id=?", o2)
q("UPDATE order_offers SET offered_at=offered_at-100 WHERE order_id=?", o2); ok("after search window ends, no more offers (customer sees old search_started_at)", o2 not in ids(B) and call("GET", "/delivery/orders", None, cu)[1][0]["search_started_at"] < int(time.time()) - 900)
ok("customer retry search clears offers and re-opens", call("POST", f"/delivery/orders/{o2}/retry", None, cu)[0] == 200 and o2 in ids(B) and o2 in ids(A))
ok("another customer cannot retry my order", call("POST", f"/delivery/orders/{o2}/retry", None, user("01077777777"))[0] == 409)

# --- خروج من الاتصال
call("POST", "/courier/online", {"online": False}, B); o3 = order()[1]["id"]
ok("courier who went offline gets no new offers", ids(B) == [] and not q("SELECT 1 FROM order_offers WHERE order_id=? AND courier_id=?", o3, bi) and call("POST", f"/courier/orders/{o3}/accept", None, B)[0] == 403)
call("POST", "/courier/online", {"online": True}, B)
call("POST", "/courier/online", {"online": True}, C); call("POST", "/admin/couriers/%d/review" % ci, {"status": "suspended"}, at)
ok("suspended courier gets 403 and cannot accept", call("GET", "/courier/available", None, C)[0] == 403 and call("POST", f"/courier/orders/{o3}/accept", None, C)[0] == 403)
ok("suspended courier status shows reason", "موقوف" in " ".join(call("GET", "/courier/status", None, C)[1]["reasons"]))

# --- تنفيذ الطلب + رمز التسليم + عمولة مرة واحدة (o1 مع الفائز)
fare_ok(o1)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): assert call("POST", f"/courier/orders/{o1}/status", {"to": to}, winT)[0] == 200
code = [x for x in call("GET", "/delivery/orders", None, cu)[1] if x["id"] == o1][0]["delivery_code"]
ok("customer sees 6-digit delivery code", code and len(code) == 6)
ok("courier endpoints never expose the code", code not in json.dumps(call("GET", "/courier/orders", None, winT)[1]) and code not in json.dumps(call("GET", "/courier/available", None, winT)[1]))
ok("wrong handover code rejected, still awaiting", call("POST", f"/courier/orders/{o1}/handover", {"code": "000000" if code != "000000" else "111111"}, winT)[0] == 403 and q("SELECT status FROM delivery_orders WHERE id=?", o1)[0][0] == "awaiting_confirmation")
ok("other courier cannot hand over this order (404)", call("POST", f"/courier/orders/{o1}/handover", {"code": code}, C)[0] in (403, 404))
ok("correct code completes order", call("POST", f"/courier/orders/{o1}/handover", {"code": code}, winT)[0] == 200 and q("SELECT status FROM delivery_orders WHERE id=?", o1)[0][0] == "completed")
ok("replay handover and customer confirm after completion are 409", call("POST", f"/courier/orders/{o1}/handover", {"code": code}, winT)[0] == 409 and call("POST", f"/delivery/orders/{o1}/confirm", None, cu)[0] == 409)
ok("commission charged exactly once", q("SELECT COUNT(*),SUM(amount) FROM wallet_entries WHERE kind='commission' AND ref_id=?", o1)[0] == (1, -5.0))
o4 = order()[1]["id"]; call("POST", f"/courier/orders/{o4}/accept", None, A) if A != winT else call("POST", f"/courier/orders/{o4}/accept", None, A)
fare_ok(o4)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{o4}/status", {"to": to}, A)
codes = [call("POST", f"/courier/orders/{o4}/handover", {"code": "%06d" % n}, A)[0] for n in range(7)]
ok("brute-force: wrong codes 403 then 429, order not completed", 429 in codes and q("SELECT status FROM delivery_orders WHERE id=?", o4)[0][0] == "awaiting_confirmation")
ok("customer confirm closes it; commission once", call("POST", f"/delivery/orders/{o4}/confirm", None, cu)[0] == 200 and q("SELECT COUNT(*) FROM wallet_entries WHERE kind='commission' AND ref_id=?", o4)[0][0] == 1)

# --- منع التكرار
k1 = order(request_key="abc123")[1]; k2 = order(request_key="abc123")
ok("same request_key returns the same order (no duplicate)", k2[0] == 200 and k2[1]["id"] == k1["id"] and k2[1]["duplicate"] and q("SELECT COUNT(*) FROM delivery_orders WHERE request_key='abc123'")[0][0] == 1)

# --- صلاحيات الإدارة
for t, n in ((cu, "customer"), (A, "courier")):
    ok(n + " cannot use admin delivery endpoints", all(call(m, p, d, t)[0] == 403 for m, p, d in (("GET", "/admin/delivery-settings", None), ("POST", "/admin/delivery-settings", {"offer_timeout": 20}), ("GET", "/admin/couriers/online", None), ("GET", f"/admin/orders/{o1}/offers", None))))
ok("admin sees online couriers incl. real presence", {x["user_id"]: x["online"] for x in call("GET", "/admin/couriers/online", None, at)[1]}[ai] is True)
ok("admin sees offer log for order (accepted + lost)", sorted(x["status"] for x in call("GET", f"/admin/orders/{o1}/offers", None, at)[1]) == ["accepted", "lost"])
ok("admin settings validated and applied", call("POST", "/admin/delivery-settings", {"offer_timeout": 5}, at)[0] == 400 and call("POST", "/admin/delivery-settings", {"offer_timeout": 20, "heartbeat_ttl": 60}, at)[0] == 200 and call("GET", "/admin/delivery-settings", None, at)[1]["offer_timeout"] == 20)
ok("heartbeat endpoint keeps courier online", call("POST", "/courier/heartbeat", None, A)[0] == 200)
print("ALL OK")
