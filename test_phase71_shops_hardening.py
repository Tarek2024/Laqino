# المرحلة 71 (م6 المحلات): تفعيل تدريجي بالمناطق، سقف الطلبات بالساعة، سباق مفتاح الطلب، صلاحيات الإعدادات، تماسك الإيقاف.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8974; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
o1, o2, cu = user("01090000001"), user("01090000002"), user("01090000003")
call("POST", "/admin/shops-settings", {"enabled": True}, at); call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 0}, at)
for r in (3, 4): call("POST", "/admin/region-fees", {"region_id": r, "fee": 30}, at)
mk = lambda t, rid, nm: (lambda s: (call("POST", "/admin/shops/%d/review" % s, {"status": "approved"}, at), call("POST", "/owner/shops/%d/open" % s, {}, t), call("POST", "/owner/shops/%d/items" % s, {"name_ar": "صنف", "price": 10}, t), s)[3])(call("POST", "/shops/apply", {"type_id": 1, "name_ar": nm, "address": "شارع النصر", "phone": "01012345678", "region_id": rid}, t)[1]["id"])
S3, S4 = mk(o1, 3, "محل ثلاثة"), mk(o2, 4, "محل أربعة")
IT = {s: call("GET", "/shops/%d/menu" % s)[1]["items"][0]["id"] for s in (S3, S4)}
iid = lambda s: IT[s]
GOOD = lambda s, **k: {"items": [{"item_id": iid(s), "qty": 1}], "dropoff_text": "شارع الجمهورية 5", **k}
ordr = lambda s, **k: call("POST", "/shops/%d/order" % s, GOOD(s, **k), cu)

# 1) الإعدادات
ok("settings GET shows regions []", call("GET", "/admin/shops-settings", None, at)[1] == {"enabled": True, "regions": []})
ok("only admin may write regions", call("POST", "/admin/shops-settings", {"regions": [3]}, cu)[0] in (401, 403))
for bad in ("x", [0], [True], ["3"], [99999], [3] * 0 + list(range(1, 202))): ok("bad regions rejected %r" % (bad if not isinstance(bad, list) or len(bad) < 5 else "long"), call("POST", "/admin/shops-settings", {"regions": bad}, at)[0] == 400)
ok("empty body rejected", call("POST", "/admin/shops-settings", {}, at)[0] == 400)
ok("regions only (no enabled) keeps the switch on", call("POST", "/admin/shops-settings", {"regions": [3]}, at)[1] == {"enabled": True, "regions": [3]})

# 2) التفعيل التدريجي: منطقة 3 فقط
ok("list only shows region 3", [x["id"] for x in call("GET", "/shops")[1]["items"]] == [S3])
ok("menu of an out-of-region shop is 404", call("GET", "/shops/%d/menu" % S4)[0] == 404 and call("GET", "/shops/%d/menu" % S3)[0] == 200)
ok("order from an out-of-region shop is 404", call("POST", "/shops/%d/order" % S4, {"items": [{"item_id": 1, "qty": 1}], "dropoff_text": "شارع الجمهورية 5"}, cu)[0] == 404)
call("POST", "/admin/shops-settings", {"regions": []}, at)
ok("empty list = all regions again", len(call("GET", "/shops")[1]["items"]) == 2 and call("GET", "/shops/%d/menu" % S4)[0] == 200)

# 3) الطلب: سباق المفتاح المتكرر (8 خيوط بنفس المفتاح) → طلب واحد فقط
res = []
def go(): res.append(ordr(S3, request_key="race-1"))
th = [threading.Thread(target=go) for _ in range(8)]; [t.start() for t in th]; [t.join() for t in th]
ids = {r[1].get("id") for r in res}
ok("race: no 500s, one order id", all(r[0] in (200, 201) for r in res) and len(ids) == 1 and sql("SELECT COUNT(*) FROM delivery_orders WHERE request_key='race-1'")[0][0] == 1)

# 4) سقف 10 طلبات/ساعة (نقفز فوق سقف الطلبات المفتوحة بإكمالها يدويًا)
sql("UPDATE delivery_orders SET status='completed'")
cnt = sql("SELECT COUNT(*) FROM shop_delivery_links")[0][0]
for i in range(10 - cnt): ordr(S3, request_key="k%d" % i); sql("UPDATE delivery_orders SET status='completed'")
c, r = ordr(S3, request_key="over"); ok("11th order within an hour is 429", c == 429)
sql("UPDATE shop_delivery_links SET created_at=created_at-7200")
sql("UPDATE delivery_orders SET status='completed'")
ok("window expires: allowed again", ordr(S3, request_key="again")[0] == 201)

# 5) إيقاف المحل/المفتاح يوقف الطلب فورًا
call("POST", "/admin/shops/%d/review" % S3, {"status": "suspended", "reason": "اختبار الإيقاف"}, at)
sql("UPDATE delivery_orders SET status='completed'"); ok("suspended shop: menu 404 and order 404", call("GET", "/shops/%d/menu" % S3)[0] == 404 and ordr(S3, request_key="s")[0] == 404)
print("ALL PASS")
