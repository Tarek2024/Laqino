"""المرحلة 22 (الموقع الموحد) — السيرفر: ترحيل قاعدة قديمة، تحويل الإحداثيات لمنطقة، إحداثيات الإدارة، موقع التسليم وخصوصيته.
قاعدة مؤقتة فقط (لا يلمس أي قاعدة حقيقية)."""
import os, sys, json, sqlite3, threading, urllib.request, urllib.error, tempfile, time
_T = tempfile.mkdtemp(prefix="lq22-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
if os.environ["LAQINO_DB"].startswith(os.getcwd() + "/laqino.db"): print("ISOLATION BROKEN"); sys.exit(1)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server, testutil
from testutil import fare_ok
from http.server import ThreadingHTTPServer
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))

# ---- 1) ترحيل قاعدة قديمة (بلا أعمدة الإحداثيات) مع بيانات حقيقية الشكل ----
server.init("01000000000", "AdminPass123")
c = sqlite3.connect(os.environ["LAQINO_DB"])
c.execute("PRAGMA foreign_keys=OFF")
# نبني قاعدة «قبل التحديث» بحذف الأعمدة الجديدة (الصفوف تبقى)
for tbl, col in (("regions", "lat"), ("regions", "lng"), ("delivery_orders", "dropoff_lat"), ("delivery_orders", "dropoff_lng")):
    c.execute("ALTER TABLE %s DROP COLUMN %s" % (tbl, col))
c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES('01099990000','قديم','x','y','customer',3,1)")
c.commit(); before = c.execute("SELECT COUNT(*) FROM regions").fetchone()[0], c.execute("SELECT COUNT(*) FROM users").fetchone()[0]; c.close()
ok("old-schema DB really lacks the new columns", "lat" not in [r[1] for r in sqlite3.connect(os.environ["LAQINO_DB"]).execute("PRAGMA table_info(regions)")])
server.init(); server.init()   # مرتان: idempotent
c = sqlite3.connect(os.environ["LAQINO_DB"])
ok("migration adds regions.lat/lng and delivery_orders.dropoff_lat/lng", {"lat", "lng"} <= {r[1] for r in c.execute("PRAGMA table_info(regions)")} and {"dropoff_lat", "dropoff_lng"} <= {r[1] for r in c.execute("PRAGMA table_info(delivery_orders)")})
ok("migration loses no rows", (c.execute("SELECT COUNT(*) FROM regions").fetchone()[0], c.execute("SELECT COUNT(*) FROM users").fetchone()[0]) == before)
c.close()

srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d/api" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]

# ---- 2) تحويل الإحداثيات لمنطقة ----
ok("fresh install seeds Riyad markaz coordinates → a GPS point there resolves to it", (lambda r: r.get("region") and r["region"]["id"] == 3 and r["distance_km"] == 0.0)(call("POST", "/location/resolve", {"lat": 31.314810, "lng": 30.928087})[1]))
call("POST", "/admin/regions/3/coords", {"lat": None, "lng": None}, at)
r = call("POST", "/location/resolve", {"lat": 31.1, "lng": 30.9})[1]
ok("resolve with no coordinates configured → unspecified/manual selection", r.get("region") is None and r.get("distance_km") is None and r.get("state") == "unspecified")
ok("admin can set coordinates on a markaz", call("POST", "/admin/regions/3/coords", {"lat": 31.05, "lng": 30.95}, at)[0] == 200)
v1 = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "v1", "name_ar": "قرية أ", "is_active": True, "lat": 31.06, "lng": 30.96}, at)[1]["id"]
v2 = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "v2", "name_ar": "قرية ب", "is_active": True, "lat": 31.20, "lng": 31.10}, at)[1]["id"]
vx = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "vx", "name_ar": "قرية موقوفة", "is_active": False, "lat": 31.0501, "lng": 30.9501}, at)[1]["id"]
st, r = call("POST", "/location/resolve", {"lat": 31.0601, "lng": 30.9601})
ok("Riyad child villages resolve to the unified markaz scope", st == 200 and r["region"]["id"] == 3 and r["region"]["name_ar"] == "مركز الرياض")
ok("resolve returns the unified markaz path, never the country", r["region"]["path"][-1] == "مركز الرياض" and "مصر" not in r["region"]["path"])
ok("inactive regions are never matched", call("POST", "/location/resolve", {"lat": 31.0501, "lng": 30.9501})[1]["region"]["id"] != vx)
st, r = call("POST", "/location/resolve", {"lat": 31.25, "lng": 30.95})
ok("outside every village radius but inside the markaz radius → the markaz", r["region"]["id"] == 3)
ok("far from everything (Cairo) → null, no wrong region", call("POST", "/location/resolve", {"lat": 30.04, "lng": 31.23})[1]["region"] is None)
ok("governorate level is never auto-selected", call("POST", "/admin/regions/2/coords", {"lat": 30.04, "lng": 31.23}, at)[0] == 200 and call("POST", "/location/resolve", {"lat": 30.04, "lng": 31.23})[1]["region"] is None)
for bad in ({}, {"lat": "x", "lng": 1}, {"lat": 95, "lng": 10}, {"lat": 10, "lng": 190}, {"lat": 10}, {"lat": None, "lng": None}, {"lat": float("nan"), "lng": 1}):
    st, _ = call("POST", "/location/resolve", bad)
    if st != 400: ok("invalid coordinates rejected (%r → %s)" % (bad, st), False)
ok("invalid coordinates rejected (7 shapes)", True)
ok("resolve stores nothing: audit_log has no location entry", not [1 for r in sqlite3.connect(os.environ["LAQINO_DB"]).execute("SELECT action,detail FROM audit_log") if "location" in (r[0] or "") or "31.0601" in (r[1] or "")])

# ---- 3) صلاحيات الإدارة وواجهة المناطق ----
cu = user("01022222222", "عميل")
ok("customer cannot set region coordinates", call("POST", "/admin/regions/3/coords", {"lat": 1, "lng": 1}, cu)[0] in (401, 403))
ok("coords endpoint: unknown region → 404, bad value → 400", call("POST", "/admin/regions/9999/coords", {"lat": 1, "lng": 1}, at)[0] == 404 and call("POST", "/admin/regions/3/coords", {"lat": "a", "lng": 1}, at)[0] == 400)
ok("admin can clear coordinates", call("POST", "/admin/regions/%d/coords" % v2, {"lat": None, "lng": None}, at)[0] == 200 and [x for x in call("GET", "/regions?parent_id=3&all=1", None, at)[1] if x["id"] == v2][0]["lat"] is None)
lst = call("GET", "/regions?parent_id=2")[1]
ok("GET /regions keeps every old field and adds lat/lng", lst and {"id", "parent_id", "level", "slug", "name_ar", "is_active", "lat", "lng"} <= set(lst[0]))
ok("region create still works without coordinates", call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "v3", "name_ar": "ج", "is_active": True}, at)[0] == 201)

# ---- 4) طلب التوصيل: الموقع اختياري، ويراه المندوب بعد القبول فقط ----
ok("fee set for the markaz", call("POST", "/admin/region-fees", {"region_id": 3, "fee": 20}, at)[0] == 200)
st, r0 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "سوبرماركت", "dropoff_text": "بيتي"}, cu)
ok("order WITHOUT a pin still works exactly as before", st == 201 and r0["status"] == "searching")
for bad in ({"dropoff_lat": 31.2}, {"dropoff_lat": "x", "dropoff_lng": 1}, {"dropoff_lat": 99, "dropoff_lng": 1}):
    st, _ = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "سوبرماركت", "dropoff_text": "بيتي", **bad}, cu)
    if st != 400: ok("bad pin rejected %r" % bad, False)
ok("a half/invalid pin is rejected with 400", True)
st, r1 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "سوبرماركت", "dropoff_text": "موقعي الحالي (GPS)", "dropoff_lat": 31.0612345678, "dropoff_lng": 30.9612345678, "request_key": "k-pin-1"}, cu)
ok("order WITH a pin is created", st == 201)
st, rd = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "سوبرماركت", "dropoff_text": "موقعي الحالي (GPS)", "dropoff_lat": 31.0612345678, "dropoff_lng": 30.9612345678, "request_key": "k-pin-1"}, cu)
ok("retry with the same request_key returns the same order (idempotency kept)", rd.get("duplicate") and rd["id"] == r1["id"])
row = sqlite3.connect(os.environ["LAQINO_DB"]).execute("SELECT dropoff_lat,dropoff_lng FROM delivery_orders WHERE id=?", (r1["id"],)).fetchone()
ok("pin stored rounded to 6 decimals (~0.1 m)", row == (31.061235, 30.961235))
ok("customer's own order list is unchanged in shape (no coordinates leak into it)", all("dropoff_lat" not in x for x in call("GET", "/delivery/orders", None, cu)[1]))

co = user("01033333333", "مندوب"); testutil.apply_docs(call, co, 3)
cuid = call("GET", "/me", None, co)[1]["id"]; call("POST", "/admin/couriers/%d/review" % cuid, {"status": "approved"}, at)
call("POST", "/courier/online", {"online": True}, co)
st, a = call("POST", "/courier/orders/%d/accept" % r1["id"], None, co); ok("courier accepts the order (%s)" % st, st == 200)
ok("pin withheld from courier until the customer approves the fare", {x["id"]: x for x in call("GET", "/courier/orders", None, co)[1]}[r1["id"]]["dropoff_lat"] is None); fare_ok(r1["id"])
mine = {x["id"]: x for x in call("GET", "/courier/orders", None, co)[1]}
ok("after acceptance the courier receives the drop-off pin", mine[r1["id"]]["dropoff_lat"] == 31.061235 and mine[r1["id"]]["dropoff_lng"] == 30.961235)
c2 = sqlite3.connect(os.environ["LAQINO_DB"]); c2.execute("UPDATE delivery_orders SET status='completed' WHERE id=?", (r1["id"],)); c2.commit(); c2.close()
ok("once the order is finished the pin is no longer shown to the courier", call("GET", "/courier/orders", None, co)[1][0]["dropoff_lat"] is None)

# ---- 5) التوصيل الطبي يقبل الموقع بنفس القواعد (التحقق فقط، بلا تغيير سلوكه) ----
st, _ = call("POST", "/medical/delivery", {"source_type": "inquiry", "source_id": 1, "provider_id": 1, "dropoff_text": "عنوان", "dropoff_lat": 99, "dropoff_lng": 1}, cu)
ok("medical delivery rejects a bad pin before anything else", st == 400)
print("ALL PASSED")
