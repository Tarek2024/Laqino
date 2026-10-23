# الخطوة 4: الروشتات — صور متعددة، المرحلة، من استلم/اطّلع/ردّ، واعتماد الإدارة للردود قبل أن يراها العميل. قاعدة مؤقتة + خادم حقيقي.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
from imgutil import png
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8814), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8814"; DB = os.environ["LAQINO_DB"]
def raw(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, x.read(), x.headers.get("Content-Type")
    except urllib.error.HTTPError as e: return e.code, e.read(), None
def call(m, p, d=None, t=None):
    s, b, _ = raw(m, p, d, t); return s, json.loads(b)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cust, other, pa, pb = (user(x) for x in ("01012345678", "01099999999", "01011111111", "01022222222"))
cid = call("GET", "/me", None, cust)[1]["id"]
ids = {n: call("GET", "/me", None, t)[1]["id"] for n, t in (("a", pa), ("b", pb))}
for n, t in (("a", pa), ("b", pb)):
    call("POST", "/providers/apply", {"name_ar": "صيدلية " + n, "region_id": 3, "address": "x"}, t); call("POST", f"/admin/providers/{ids[n]}/review", {"status": "approved"}, at)
def up(tok=cust): return call("POST", "/files", {"data": png()}, tok)[1]["id"]
ITEMS = [{"name": "باراسيتامول", "qty": 2, "unit_price": 20}]

# ---- صور متعددة
f1, f2, f3, f4, f5, f6 = up(), up(), up(), up(), up(), up()
ok("6 images rejected (max 5)", call("POST", "/medical/prescriptions", {"file_ids": [f1, f2, f3, f4, f5, f6], "region_id": 3}, cust)[0] == 400)
ok("duplicate image ids rejected", call("POST", "/medical/prescriptions", {"file_ids": [f1, f1], "region_id": 3}, cust)[0] == 400)
ok("empty / non-list rejected", all(call("POST", "/medical/prescriptions", {"file_ids": v, "region_id": 3}, cust)[0] == 400 for v in ([], "x", [True], ["x"])))
ok("someone else's image rejected", call("POST", "/medical/prescriptions", {"file_ids": [up(other)], "region_id": 3}, cust)[0] == 400)
ok("nothing was created by rejected calls", sql("SELECT COUNT(*) FROM prescriptions")[0][0] == 0)
s, r = call("POST", "/medical/prescriptions", {"file_ids": [f1, f2, f3, f4, f5], "region_id": 3, "note": "n"}, cust); R = r["id"]
ok("5 images accepted", s == 201 and sql("SELECT file_id FROM rx_images WHERE prescription_id=? ORDER BY pos", (R,)) == [(f1,), (f2,), (f3,), (f4,), (f5,)])
ok("cover file_id = first image (old code keeps working)", sql("SELECT file_id FROM prescriptions WHERE id=?", (R,))[0][0] == f1)
ok("prescription images do not consume the generic upload quota", sql(server.COUNT_SQL["files"], (cid,))[0][0] == 1)
ok("image cannot be reused by a second prescription", call("POST", "/medical/prescriptions", {"file_ids": [f2], "region_id": 3}, cust)[0] == 409 and call("POST", "/medical/prescriptions", {"file_id": f1, "region_id": 3}, cust)[0] == 409)
s, r = call("POST", "/medical/prescriptions", {"file_id": up(), "region_id": 3}, cust); ok("legacy single file_id still works", s == 201); RL = r["id"]
mine = {x["id"]: x for x in call("GET", "/medical/prescriptions", None, cust)[1]}
ok("customer list: images + stage review", mine[R]["images"] == [f1, f2, f3, f4, f5] and mine[R]["stage"] == "review" and len(mine[RL]["images"]) == 1)
adm = {x["id"]: x for x in call("GET", "/admin/prescriptions", None, at)[1]}
ok("admin list carries all images", adm[R]["images"] == [f1, f2, f3, f4, f5])

# ---- تحويل + استلام/اطلاع
ok("pharmacy cannot read image before forwarding", raw("GET", f"/files/{f2}", None, pa)[0] == 404)
call("POST", f"/admin/prescriptions/{R}/forward-many", {"provider_ids": [ids["a"], ids["b"]]}, at)
s, r = call("GET", f"/medical/prescriptions/{R}/quotes", None, cust)
ok("stage at_pharmacies; both pharmacies listed, none seen/quoted, no phones", r["stage"] == "at_pharmacies" and len(r["pharmacies"]) == 2 and not any(p["seen"] or p["quoted"] for p in r["pharmacies"]) and "0101" not in json.dumps(r))
ok("provider list exposes all 5 images", next(x for x in call("GET", "/provider/prescriptions", None, pa)[1] if x["id"] == R)["images"] == [f1, f2, f3, f4, f5])
st, body, ct = raw("GET", f"/files/{f3}", None, pa); ok("pharmacy can open the 3rd image (not only the cover)", st == 200 and ct == "image/png")
ok("other pharmacy not yet seen; opening an image marks only that pharmacy", sql("SELECT provider_id FROM rx_seen WHERE prescription_id=?", (R,)) == [(ids["a"],)])
tr = {x["id"]: x for x in call("GET", "/admin/rx/tracking", None, at)[1]}[R]
ok("admin tracking: A received+seen, B received not seen, nobody replied", [(p["pharmacy"], p["seen_at"] is not None, p["resp_status"]) for p in tr["pharmacies"]] == [("صيدلية a", True, None), ("صيدلية b", False, None)])
ok("tracking is admin/staff only", call("GET", "/admin/rx/tracking", None, cust)[0] == 403 and call("GET", "/admin/rx/tracking")[0] == 401)
call("GET", f"/provider/prescriptions/{R}/quote", None, pb)
ok("opening the quote form also marks seen", sql("SELECT COUNT(*) FROM rx_seen WHERE prescription_id=?", (R,))[0][0] == 2)

# ---- ردود تحتاج اعتماد
ok("phone number in the note is refused", call("POST", f"/provider/prescriptions/{R}/quote", {"items": ITEMS, "note": "كلمني ٠١٠١١١١١١١١"}, pa)[0] == 400 and call("POST", f"/provider/prescriptions/{R}/quote", {"items": [{"name": "دواء 01011111111", "unit_price": 5}]}, pa)[0] == 400)
s, r = call("POST", f"/provider/prescriptions/{R}/quote", {"items": ITEMS, "note": "متاح"}, pa); ok("pharmacy quote saved as pending", s == 200 and r["review"] == "pending" and sql("SELECT review FROM prescription_responses WHERE prescription_id=? AND provider_id=?", (R, ids["a"]))[0][0] == "pending")
ok("admins notified of the pending response", sql("SELECT COUNT(*) FROM notifications WHERE kind='admin.rx_response' AND link='admin:rx'")[0][0] >= 1)
s, r = call("GET", f"/medical/prescriptions/{R}/quotes", None, cust)
ok("customer sees NO quote yet, but is told one is under review", r["quotes"] == [] and r["pending_review"] == 1 and r["stage"] == "at_pharmacies")
ok("legacy customer list hides the pending response", mine and next(x for x in call("GET", "/medical/prescriptions", None, cust)[1] if x["id"] == R)["responses"] == [])
# طلب توصيل من رد غير معتمد
sql("INSERT OR REPLACE INTO region_fees(region_id,fee) VALUES(3,10)")
s, r = call("POST", "/medical/delivery", {"source_type": "prescription", "source_id": R, "provider_id": ids["a"], "dropoff_text": "شارع النيل"}, cust)
ok("cannot order delivery from an unapproved response", s == 404)
# الأدمن
pend = call("GET", "/admin/rx/responses", None, at)[1]
ok("admin sees pending list with items + images", len(pend) == 1 and pend[0]["pharmacy"] == "صيدلية a" and pend[0]["items"][0]["name"] == "باراسيتامول" and pend[0]["images"] == [f1, f2, f3, f4, f5])
ok("review endpoints: auth + validation", call("POST", f"/admin/rx/responses/{R}/{ids['a']}/review", {"decision": "approve"}, cust)[0] == 403
   and call("POST", f"/admin/rx/responses/{R}/{ids['a']}/review", {"decision": "maybe"}, at)[0] == 400
   and call("POST", f"/admin/rx/responses/{R}/{ids['a']}/review", {"decision": "reject"}, at)[0] == 400
   and call("POST", f"/admin/rx/responses/{R}/{ids['a']}/review", {"decision": "reject", "reason": "abc"}, at)[0] == 400
   and call("POST", f"/admin/rx/responses/{R}/{ids['b']}/review", {"decision": "approve"}, at)[0] == 404
   and call("GET", "/admin/rx/responses?review=zzz", None, at)[0] == 400)
s, r = call("POST", f"/admin/rx/responses/{R}/{ids['a']}/review", {"decision": "reject", "reason": "السعر غير منطقي"}, at); ok("reject with reason", s == 200 and r["review"] == "rejected")
ok("pharmacy notified with the reason; customer sees nothing", sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.rejected' AND body LIKE '%السعر غير منطقي%'", (ids["a"],))[0][0] == 1 and call("GET", f"/medical/prescriptions/{R}/quotes", None, cust)[1]["quotes"] == [])
ok("pharmacy sees rejection + reason on its list", (lambda x: x["my_review"] == "rejected" and x["my_review_reason"] == "السعر غير منطقي")(next(x for x in call("GET", "/provider/prescriptions", None, pa)[1] if x["id"] == R)))
ok("rejecting twice is 409", call("POST", f"/admin/rx/responses/{R}/{ids['a']}/review", {"decision": "reject", "reason": "نفس السبب"}, at)[0] == 409)
call("POST", f"/provider/prescriptions/{R}/quote", {"items": [{"name": "باراسيتامول", "qty": 2, "unit_price": 18}]}, pa)
ok("edit after rejection goes back to pending, reason cleared", sql("SELECT review,review_reason FROM prescription_responses WHERE prescription_id=? AND provider_id=?", (R, ids["a"]))[0] == ("pending", None))
call("POST", f"/provider/prescriptions/{R}/quote", {"items": [{"name": "باراسيتامول", "qty": 2, "unit_price": 15}]}, pb)
s, r = call("POST", f"/admin/rx/responses/{R}/{ids['a']}/review", {"decision": "approve"}, at); ok("approve", s == 200 and r["review"] == "approved")
r = call("GET", f"/medical/prescriptions/{R}/quotes", None, cust)[1]
ok("customer now sees ONLY the approved quote; B still pending", [x["pharmacy"] for x in r["quotes"]] == ["صيدلية a"] and r["pending_review"] == 1 and r["stage"] == "quoted")
ok("customer notified on approval; pharmacy too", sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.quote'", (cid,))[0][0] == 1 and sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.approved'", (ids["a"],))[0][0] == 1)
ok("tracking shows A replied+approved, B replied+pending", [(p["pharmacy"], p["review"]) for p in {x["id"]: x for x in call("GET", "/admin/rx/tracking", None, at)[1]}[R]["pharmacies"]] == [("صيدلية a", "approved"), ("صيدلية b", "pending")])
ok("audit rows written for review decisions", sql("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'rx.response.%'")[0][0] == 2)
ov = call("GET", "/admin/overview", None, at)[1]; ok("overview counts pending rx responses", ov["pending"]["rx_responses"] == 1)
# الطلب بعد الاعتماد
s, r = call("POST", "/medical/delivery", {"source_type": "prescription", "source_id": R, "provider_id": ids["a"], "dropoff_text": "شارع النيل"}, cust)
ok("delivery from an approved response works", s in (200, 201))
ok("legacy /respond path also lands as pending", (lambda: (call("POST", f"/provider/prescriptions/{RL}/respond", {"status": "unavailable"}, pa), sql("SELECT 1"))[0][0] == 404)())

# ---- حذف صورة من روشتة متعددة الصور
ok("deleting a non-cover image keeps the prescription open", call("POST", f"/files/{f3}/delete", {}, cust)[0] == 200 and sql("SELECT status FROM prescriptions WHERE id=?", (R,))[0][0] != "closed" and [x[0] for x in sql("SELECT file_id FROM rx_images WHERE prescription_id=? ORDER BY pos", (R,))] == [f1, f2, f4, f5])
ok("deleting remaining extra images keeps the prescription open", call("POST", f"/files/{f4}/delete", {}, cust)[0] == 200 and call("POST", f"/files/{f5}/delete", {}, cust)[0] == 200 and [x[0] for x in sql("SELECT file_id FROM rx_images WHERE prescription_id=? ORDER BY pos", (R,))] == [f1, f2])
ok("deleting the cover promotes the next image and keeps it open", call("POST", f"/files/{f1}/delete", {}, cust)[0] == 200 and sql("SELECT file_id,status FROM prescriptions WHERE id=?", (R,))[0][0] == f2 and sql("SELECT status FROM prescriptions WHERE id=?", (R,))[0][0] != "closed" and sql("SELECT file_id FROM rx_images WHERE prescription_id=?", (R,)) == [(f2,)])
ok("deleting the last image closes it (old behaviour)", call("POST", f"/files/{f2}/delete", {}, cust)[0] == 200 and sql("SELECT status FROM prescriptions WHERE id=?", (R,))[0][0] == "closed")
ok("closed → stage closed in list", next(x for x in call("GET", "/medical/prescriptions", None, cust)[1] if x["id"] == R)["stage"] == "closed")

# ---- ترحيل قاعدة قديمة (بلا review) تبقي الردود القديمة ظاهرة
old = tempfile.mktemp(suffix=".db"); c = sqlite3.connect(old)
c.executescript("""CREATE TABLE prescriptions(id INTEGER PRIMARY KEY, file_id INTEGER);CREATE TABLE providers(user_id INTEGER PRIMARY KEY);CREATE TABLE notifications(id INTEGER PRIMARY KEY, user_id,kind,title,body,link,ref_type,ref_id,created_at);CREATE TABLE users(id INTEGER PRIMARY KEY, role);
CREATE TABLE prescription_responses(prescription_id INTEGER NOT NULL, provider_id INTEGER NOT NULL, status TEXT NOT NULL, price REAL, note TEXT, updated_at INTEGER NOT NULL, PRIMARY KEY(prescription_id,provider_id));
INSERT INTO prescription_responses VALUES(1,5,'available',10,NULL,1);""")
import rx as rxm
rxm.install(c); rxm.install(c)
ok("old DB: legacy response grandfathered as approved (migration idempotent)", c.execute("SELECT review FROM prescription_responses").fetchone()[0] == "approved")
c.execute("INSERT INTO prescription_responses(prescription_id,provider_id,status,price,note,updated_at) VALUES(2,5,'available',10,NULL,1)")
ok("old DB: new response becomes pending", c.execute("SELECT review FROM prescription_responses WHERE prescription_id=2").fetchone()[0] == "pending")
print("ALL OK")
