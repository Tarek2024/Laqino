"""Phase 59 (بند 2): الرد الجزئي المخفي أثناء البحث ما يتسرّبش للعميل: لا إشعار «صيدلية تطلب تأكيدًا» ولا مرحلة «وصلت ردود» ولا «توافر جزئي».
قاعدة SQLite مؤقتة حقيقية + سيرفر HTTP حقيقي لقائمة العميل."""
import json, os, tempfile, threading, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer

DB = tempfile.mktemp(prefix="laqino-p59-", suffix=".db")
os.environ["LAQINO_DB"] = DB
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(prefix="laqino-p59-up-")
import server
rx = server.rx
server.init("01000000000", "AdminPass123")
now = int(time.time())
c = server.db()

class H:
    def __init__(s, b=None): s.b = b or {}; s.out = None
    def body(s): return s.b
    def send(s, code, obj): s.out = (code, obj)

def call(user, method, path, body=None):
    cc = server.db()
    try:
        h = H(body); handled = rx.handle(h, cc, user, method, path, {})
        assert handled, path
        return h.out
    finally: cc.close()

region = int((c.execute("SELECT id FROM regions WHERE level='markaz' ORDER BY id LIMIT 1").fetchone() or c.execute("SELECT id FROM regions ORDER BY id LIMIT 1").fetchone())["id"])
def add_user(phone, name, role):
    salt = "ab" * 8
    return c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,?)", (phone, name, server.hp("password1", salt), salt, role, region, now)).lastrowid
admin_id = c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()["id"]
ADMIN = {"id": admin_id, "role": "admin"}
cust = add_user("01090530000", "عميل", "customer"); CUST = {"id": cust, "role": "customer"}
P = []
for i in range(10):
    pid = add_user("0109053%04d" % (i + 1), "ص%d" % i, "medical_provider")
    c.execute("INSERT INTO providers(user_id,name_ar,kind,region_id,address,status,created_at,distribution_enabled) VALUES(?,?,'pharmacy',?,?,'approved',?,1)", (pid, "صيدلية %d" % i, region, "ع", now))
    P.append(pid)
pend = add_user("01090539001", "معلقة", "medical_provider")
c.execute("INSERT INTO providers(user_id,name_ar,kind,region_id,address,status,created_at,distribution_enabled) VALUES(?,?,'pharmacy',?,?,'pending',?,1)", (pend, "غير معتمدة", region, "ع", now))
noopt = add_user("01090539002", "غير مشاركة", "medical_provider")
c.execute("INSERT INTO providers(user_id,name_ar,kind,region_id,address,status,created_at,distribution_enabled) VALUES(?,?,'pharmacy',?,?,'approved',?,0)", (noopt, "غير مشاركة", region, "ع", now))
U = lambda pid: {"id": pid, "role": "medical_provider"}
def new_rx():
    fid = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (cust, "f%d.png" % time.time_ns(), "image/png", 1, now)).lastrowid
    r = c.execute("INSERT INTO prescriptions(customer_id,region_id,file_id,note,status,created_at,kind) VALUES(?,?,?,'','pending',?,'rx')", (cust, region, fid, now - 60)).lastrowid
    c.commit(); return r
q1 = lambda sql, *a: c.execute(sql, a).fetchone()[0]

c.commit()
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "auto"})[0] == 200
U = lambda pid: {"id": pid, "role": "medical_provider"}
def accept(pid, rid): assert call(U(pid), "POST", "/api/provider/prescriptions/%d/accept" % rid)[0] == 200, (pid, rid)
def quote(pid, rid, items, ca=False):
    code, out = call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, {"items": items, "confirm_all": ca})
    assert code == 200, (code, out); return out
it = lambda n, st: {"name": n, "qty": 1, "unit_price": 10 if st == "available" else None, "item_status": st}
def open_offers(rid): return q1("SELECT COUNT(*) FROM rx_offers WHERE prescription_id=? AND state='open'", rid)
def access(rid): return {x[0] for x in c.execute("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (rid,))}


def quotes(rid):
    code, out = call(CUST, "GET", "/api/medical/prescriptions/%d/quotes" % rid); assert code == 200, out; return out
def cust_notes():
    return q1("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.quote'", cust)

full_items = [it("اموكسيسيللين", "available"), it("بنادول", "available")]
p3 = [it("اموكسيسيللين", "available"), it("بنادول", "available"), it("فولتارين", "unavailable")]
p2 = [it("اموكسيسيللين", "available"), it("بنادول", "unavailable"), it("فولتارين", "unavailable")]


BASE = "http://127.0.0.1:8861"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8861), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def http(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
tok = http("POST", "/login", {"phone": "01090530000", "password": "password1"})[1]["token"]
def mine(rid): return next(x for x in http("GET", "/medical/prescriptions", None, tok)[1] if x["id"] == rid)
def all_notes(): return [dict(x) for x in c.execute("SELECT kind,title FROM notifications WHERE user_id=? ORDER BY id", (cust,))]
def ok(msg): print("PASS " + msg)

c.commit()
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "auto"})[0] == 200
def accept(pid, rid): assert call(U(pid), "POST", "/api/provider/prescriptions/%d/accept" % rid)[0] == 200
def quote(pid, rid, items, mode):
    out = call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, {"items": items, "send_mode": mode}); assert out[0] == 200, out; return out[1]
it = lambda n, st: {"name": n, "qty": 1, "unit_price": 10 if st == "available" else None, "item_status": st}
def quotes(rid): code, out = call(CUST, "GET", "/api/medical/prescriptions/%d/quotes" % rid); assert code == 200; return out
partial = [it("اموكسيسيللين", "available"), it("بنادول", "unavailable"), it("فولتارين", "unavailable")]
full = [it("اموكسيسيللين", "available"), it("بنادول", "available")]
BAD = ("صيدلية تطلب تأكيدًا منك", "صيدلية ردّت: الدواء متوفر", "صيدلية ردّت: غير متوفر")

# 1) أثناء البحث: رد جزئي -> صفر إشعارات من أي نوع، المرحلة «عند الصيدليات»، والتوافر «بانتظار»
r = new_rx(); rx.auto_forward(c, r); accept(P[0], r)
before = all_notes()
quote(P[0], r, partial, "partial")
assert all_notes() == before, ("تسريب إشعار أثناء البحث", all_notes()[len(before):])
q = quotes(r)
assert q["search_state"] == "searching" and q["quotes"] == []
assert q["stage"] == "at_pharmacies", q["stage"]
assert not any(x["quoted"] for x in q["pharmacies"]), ("phase-61: عدّاد ردّت يعدّ رد مخفي", q["pharmacies"])
assert q["aggregate_status"] == "unknown", q["aggregate_status"]
m = mine(r)
assert m["stage"] == "at_pharmacies" and m["aggregate_status"] == "unknown", (m["stage"], m["aggregate_status"])
assert m["responses"] == [], ("phase-61: الرد الجزئي المخفي ما يظهرش في responses (عدّاد ردّت N)", m["responses"])
assert q1("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=?", r) == 1, "الرد محفوظ"
ok("أثناء البحث: الرد الجزئي بلا إشعار، والمرحلة «عند الصيدليات»، والتوافر «بانتظار» (في /quotes وفي قائمة العميل)")

# 2) المراجعة الداخلية للإدارة ما اتغيرتش (الإدارة لسه شايفة الرد)
assert q1("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=? AND review='approved'", r) == 1
assert rx.stage_of(c, r, "forwarded") == "quoted", "الحالة الداخلية (للإدارة) زي ما هي"
ok("الحالة الداخلية للإدارة لم تتغير")

# 3) نهاية البحث بالمهلة الكلية: أفضل رد جزئي يظهر + إشعار نهاية واحد، وما فيش ولا «تطلب تأكيدًا»
c.execute("UPDATE prescriptions SET created_at=? WHERE id=?", (now - 7200, r)); c.commit()
rx.refresh_claims(c, now); c.commit()
q = quotes(r)
assert q["search_state"] in ("ended_partial", "partial_accepted") and len(q["quotes"]) == 1
assert q["stage"] == "quoted" and q["aggregate_status"] == "partial", (q["stage"], q["aggregate_status"])
m = mine(r); assert m["stage"] == "quoted" and m["aggregate_status"] == "partial"
ended = [n for n in all_notes() if n["kind"] == "rx.search_ended"]
assert len(ended) == 1, ended
assert not [n for n in all_notes() if n["title"] in BAD], "لا إشعار تسريب"
ok("بعد انتهاء البحث: يظهر أفضل رد جزئي و«وصلت ردود»، وإشعار نهاية واحد فقط")

# 4) رد كامل: يظهر فورًا بإشعار واحد (rx.quote) ومن غير الإشعار العام القديم
r2 = new_rx(); rx.auto_forward(c, r2); accept(P[1], r2)
b = all_notes()
quote(P[1], r2, full, "full")
new = all_notes()[len(b):]
assert [n["kind"] for n in new] == ["rx.quote"], new
assert not [n for n in new if n["title"] in BAD]
q = quotes(r2); assert q["stage"] == "completed" and q["aggregate_status"] == "complete"
ok("الرد الكامل: إشعار واحد «وصلك رد» فقط، والمرحلة «اكتمل»")

# 5) الوضع اليدوي (القديم): الرد يظهر ويُشعر مرة واحدة بدون الإشعار العام
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "manual"})[0] == 200
r3 = new_rx(); c.execute("UPDATE prescriptions SET status='forwarded' WHERE id=?", (r3,)); c.execute("INSERT OR IGNORE INTO prescription_access VALUES(?,?)", (r3, P[2])); c.commit()
b = all_notes()
out = call(U(P[2]), "POST", "/api/provider/prescriptions/%d/quote" % r3, {"items": partial, "confirm_all": True})
assert out[0] == 200, out
new = all_notes()[len(b):]
assert not [n for n in new if n["title"] in BAD], new
assert len([n for n in new if n["kind"] == "rx.quote"]) == 1, new
q = quotes(r3); assert q["stage"] == "quoted" and len(q["quotes"]) == 1
ok("الوضع اليدوي: إشعار «وصلك رد» مرة واحدة والرد ظاهر، بدون الإشعار العام")

# 6) استفسارات الدواء (غير الروشتات) لسه بتتشعِر زي ما كانت
trig = {x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'ntf_%'")}
assert "ntf_inquiry_responses_ins" in trig and "ntf_prescription_responses_ins" not in trig, sorted(trig)
ok("trigger ردود الاستفسارات باقي، وtrigger ردود الروشتات العام اتشال")
print("TOTAL OK")
