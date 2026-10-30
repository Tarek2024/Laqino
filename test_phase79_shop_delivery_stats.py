# المرحلة 79: إحصائيات ولوحات دليفري المحلات + مطابقة «المحل يطلب مندوب» لمسار الصيدلية (4 مراحل، تفاصيل اختيارية، تأكيد التسليم، لوحة المحل، لوحة الإدارة، CSV).
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8979; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
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
SD = lambda s, p: "/owner/shops/%d/delivery-%s" % (s, p)
def run4(oid, t):
    for to in ("heading_pickup", "picked_up", "heading_customer", "completed"):
        if call("POST", f"/courier/orders/{oid}/status", {"to": to}, t)[0] != 200: return False
    return True
def pk2(s, tk=None, **x): return call("POST", "/owner/shops/%d/delivery-request" % s, x, tk or own)

# ---- 1) تفاصيل اختيارية مثل الصيدلية
ok("bad phone / bad price rejected", pk2(S1, customer_phone="12")[0] == 400 and pk2(S1, price="abc")[0] == 400 and pk2(S1, price=-5)[0] == 400 and pk2(S1, price="nan")[0] == 400)
s, r = pk2(S1, customer_phone="٠١٠٠١٢٣٤٥٦٧", price="45.5", note="كيسين دفع عند الاستلام", dropoff_text="شارع 9"); a1 = r["id"]
row = sql("SELECT pd_cust_phone,pd_cust_norm,pd_price,pd_note FROM delivery_orders WHERE id=?", a1)[0]
ok("details stored (arabic digits normalized)", s == 201 and row == ("01001234567", "01001234567", 45.5, "كيسين دفع عند الاستلام"))
call("POST", f"/courier/orders/{a1}/accept", {}, c1); co = cord(c1, a1)
ok("courier sees customer phone/price/note while active", co["pd_cust_phone"] == "01001234567" and co["pd_price"] == 45.5 and co["pd_note"])
ok("the full 4-stage run to the customer", run4(a1, c1))
ok("after completion the courier no longer sees details", cord(c1, a1).get("pd_cust_phone") is None)
# طلب ثانٍ: المحل نفسه يؤكد التسليم يدويًا
s, r = pk2(S1, customer_phone="01001234567", price=30); a2 = r["id"]; call("POST", f"/courier/orders/{a2}/accept", {}, c1)
call("POST", f"/courier/orders/{a2}/status", {"to": "heading_pickup"}, c1); call("POST", f"/courier/orders/{a2}/status", {"to": "picked_up"}, c1)
DN = "/owner/shops/%d/delivery-requests/%d/delivered"
ok("only the owner can confirm; wrong shop/order is 404", call("POST", DN % (S1, a2), {}, own2)[0] == 404 and call("POST", DN % (S2, a2), {}, own2)[0] == 404 and call("POST", DN % (S1, 999999), {}, own)[0] == 404 and call("POST", DN % (S1, a2), {})[0] == 401)
ok("owner confirms delivery after pickup", call("POST", DN % (S1, a2), {}, own)[1] == {"id": a2, "status": "completed"} and call("POST", DN % (S1, a2), {}, own)[0] == 409)
ok("delivered_by=shop and event actor recorded", [x for x in call("GET", "/owner/shops/%d/delivery-requests" % S1, None, own)[1]["items"] if x["id"] == a2][0]["delivered_by"] == "shop")
s, r = pk2(S1); a3 = r["id"]
ok("cannot confirm before pickup (searching)", call("POST", DN % (S1, a3), {}, own)[0] == 409)
call("POST", f"/delivery/orders/{a3}/cancel", {}, own)  # ملغي

# ---- 2) لوحة المحل
D = call("GET", SD(S1, "dashboard") + "?range=all", None, own)[1]
ok("dashboard summary: 3 orders, 2 completed, 1 cancelled, price sum 75.5", D["summary"]["total"] == 3 and D["summary"]["completed"] == 2 and D["summary"]["cancelled"] == 1 and D["summary"]["price_sum"] == 75.5 and D["late_minutes"] == 45)
ok("dashboard hides courier ids/phones, keeps names", all("courier_id" not in x and "pd_cust_norm" not in x and "courier_phone" not in x for x in D["items"]) and any(x["courier_name"] for x in D["items"]))
ok("repeat customer detected today (2 orders by the same phone)", D["repeat_today"] == [{"phone": "01001234567", "count": 2}])
ok("range today / bad date / custom", call("GET", SD(S1, "dashboard"), None, own)[1]["summary"]["total"] == 3 and call("GET", SD(S1, "dashboard") + "?from=2020-02-31", None, own)[0] == 400 and call("GET", SD(S1, "dashboard") + "?from=2000-01-01&to=2000-01-02", None, own)[1]["summary"]["total"] == 0)
ok("per-shop isolation: other shop sees nothing, outsider 404, anonymous 401", call("GET", SD(S2, "dashboard") + "?range=all", None, own2)[1]["summary"]["total"] == 0 and call("GET", SD(S1, "dashboard"), None, own2)[0] == 404 and call("GET", SD(S1, "dashboard"))[0] == 401 and call("GET", SD(S1, "dashboard"), None, cust)[0] == 404 and call("GET", SD(SP, "dashboard"), None, cust2)[0] == 403)
ok("read only: POST not handled", call("POST", SD(S1, "dashboard"), {}, own)[0] in (404, 405))
O = call("GET", SD(S1, "order") + "?id=%d" % a2, None, own)[1]
ok("order detail: events with shop/courier actors, no courier ids", [e["by"] for e in O["events"]][-1] == "shop" and "courier" in [e["by"] for e in O["events"]] and "courier_id" not in O and O["pd_price"] == 30 and O["courier_phone"] is None)
ok("order detail: other shop's order 404 / bad id 400", call("GET", SD(S2, "order") + "?id=%d" % a2, None, own2)[0] == 404 and call("GET", SD(S1, "order") + "?id=x", None, own)[0] == 400)
ok("search by phone counts without cancelled", call("GET", SD(S1, "search") + "?phone=01001234567", None, own)[1]["total"] == 2 and call("GET", SD(S1, "search") + "?phone=1", None, own)[0] == 400 and call("GET", SD(S1, "search"), None, own)[0] == 400)
nm = call("GET", "/courier/orders", None, c1)[1][0]["customer_name"]
cr = sql("SELECT name FROM users WHERE id=?", u1)[0][0]
ok("search by courier name (partial) and by full phone only", call("GET", SD(S1, "search") + "?courier=" + cr[:3] + "&range=all", None, own)[1]["summary"]["total"] == 2 and call("GET", SD(S1, "search") + "?courier=zz&range=all", None, own)[1]["items"] == [])
E = call("GET", SD(S1, "export") + "?range=all", None, own)[1]
ok("csv export has bom, 3 rows, no formulas", E["count"] == 3 and E["csv"].startswith("\ufeff") and E["csv"].count("\n") == 4)
s, r = pk2(S1, note="=HYPERLINK(1)"); call("POST", f"/delivery/orders/{r['id']}/cancel", {}, own)
ok("csv escapes formula injection", "'=HYPERLINK" in call("GET", SD(S1, "export") + "?range=all", None, own)[1]["csv"])

# ---- 3) لوحة الإدارة (admin فقط)
s2, r = pk2(S2, tk=own2, customer_phone="01001234567", price=10); b1 = r["id"]; call("POST", f"/courier/orders/{b1}/accept", {}, c2); run4(b1, c2)
ADM = "/admin/shop-delivery/dashboard"
ok("admin only: staff/user/anonymous refused", call("GET", ADM, None, stf)[0] == 403 and call("GET", ADM, None, cust)[0] == 403 and call("GET", ADM)[0] == 401 and call("GET", "/admin/shop-delivery/export", None, stf)[0] == 403)
A = call("GET", ADM + "?range=all", None, at)[1]
ok("admin summary across shops incl. commission", A["summary"]["total"] == 5 and A["summary"]["shops"] == 2 and A["summary"]["completed"] == 3 and A["summary"]["commission"] == 6.0)
ok("shops ranked by orders and couriers listed", [x["name"] for x in A["shops"]][0] == "مطعم الأمل" and len(A["shops"]) == 2 and len(A["couriers"]) == 2 and A["shops"][0]["commission"] == 4.0)
ok("cross-shop phone alert", A["alerts"]["cross_shop_phones"] and A["alerts"]["cross_shop_phones"][0]["phone"] == "01001234567" and sorted(A["alerts"]["cross_shop_phones"][0]["shops"]) == ["سوبر ماركت النور", "مطعم الأمل"])
ok("sorts and invalid sort", all(call("GET", ADM + "?range=all&sort=" + k, None, at)[0] == 200 for k in ("orders", "cancel", "late", "commission")) and call("GET", ADM + "?sort=zzz", None, at)[0] == 400 and call("GET", ADM + "?from=bad", None, at)[0] == 400)
AE = call("GET", "/admin/shop-delivery/export?range=all", None, at)[1]
ok("admin csv has shop names and commission column", AE["count"] == 5 and "مطعم الأمل" in AE["csv"] and "العمولة المحصّلة" in AE["csv"])

# ---- 4) حد التأخير: مفتاح مستقل عن الصيدلية
ok("late minutes validation", call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 2, "late_minutes": -1}, at)[0] == 400 and call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 2, "late_minutes": "x"}, at)[0] == 400 and call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 2, "late_minutes": 1441}, at)[0] == 400)
ok("late minutes saved under its own key; pharmacy key untouched", call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 2, "late_minutes": 30}, at)[1]["late_minutes"] == 30 and sql("SELECT value FROM settings WHERE key='shop_delivery_late_minutes'")[0][0] == "30" and not sql("SELECT 1 FROM settings WHERE key='provider_delivery_late_minutes'"))
ok("omitting late_minutes keeps it", call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 3}, at)[1]["late_minutes"] == 30)
sql("UPDATE order_events SET at=at-7200 WHERE order_id=? AND to_status='picked_up'", a1)  # الاستلام قبل ساعتين ← تسليم بعد أكثر من 30 دقيقة = متأخر
D = call("GET", SD(S1, "dashboard") + "?range=all", None, own)[1]
ok("late flag computed from the shop threshold", D["summary"]["late"] >= 1 and any(x["late"] for x in D["items"]))

# ---- 5) الصيدلية لم تتأثر: مساراتها وبياناتها منفصلة
ok("pharmacy endpoints untouched by shop orders (no leakage)", call("GET", "/provider/delivery-dashboard", None, own)[0] in (403, 404) and sql("SELECT COUNT(*) FROM delivery_orders WHERE origin_type='provider_pickup'")[0][0] == 0)
print("ALL PASSED")
