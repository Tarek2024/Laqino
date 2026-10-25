"""Phase 58: التوصيل اختياري لأي رد ظاهر للعميل (كامل / جزئي / أصناف ناقصة)، والروشتة تفضل مفتوحة؛ والرد الجزئي المخفي أثناء البحث ما يتوصّلش.
"""
import json, os, tempfile, threading, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer

DB = tempfile.mktemp(prefix="laqino-p58-", suffix=".db")
os.environ["LAQINO_DB"] = DB
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(prefix="laqino-p58-up-")
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


BASE = "http://127.0.0.1:8862"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8862), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
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


c.execute("INSERT INTO region_fees(region_id,fee) VALUES(?,20) ON CONFLICT(region_id) DO UPDATE SET fee=excluded.fee", (region,)); c.commit()
def deliver(rid, pid): return http("POST", "/medical/delivery", {"source_type": "prescription", "source_id": rid, "provider_id": pid, "dropoff_text": "شارع النيل"}, tok)
def rx_status(rid): return q1("SELECT status FROM prescriptions WHERE id=?", rid)

# 1) رد جزئي مخفي أثناء البحث: مفيش توصيل
r = new_rx(); rx.auto_forward(c, r); accept(P[0], r); quote(P[0], r, partial, "partial")
assert quotes(r)["quotes"] == []
code, out = deliver(r, P[0]); assert code == 409, (code, out)
ok("الرد الجزئي المخفي أثناء البحث لا يُطلب له توصيل")

# 2) رد كامل ظاهر: توصيل اختياري والروشتة مفتوحة
r2 = new_rx(); rx.auto_forward(c, r2); accept(P[1], r2); quote(P[1], r2, full, "full")
code, out = deliver(r2, P[1]); assert code == 201, (code, out)
assert rx_status(r2) != "closed"
assert deliver(r2, P[1])[0] == 409, "لا طلب توصيل مكرر لنفس الرد"
ok("الرد الكامل: توصيل اختياري والروشتة تفضل مفتوحة، ولا تكرار")

# 3) الوضع اليدوي: الرد الجزئي ظاهر فورًا، والتوصيل اختياري له برضه
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "manual"})[0] == 200
r3 = new_rx(); c.execute("INSERT OR IGNORE INTO prescription_access(prescription_id,provider_id) VALUES(?,?)", (r3, P[2])); c.commit()
quote(P[2], r3, partial, "partial")
vis = quotes(r3)["quotes"]; assert [x["provider_id"] for x in vis] == [P[2]] and vis[0]["partial"], vis
code, out = deliver(r3, P[2]); assert code == 201, (code, out); assert rx_status(r3) != "closed"
ok("الرد الجزئي الظاهر: توصيل اختياري والروشتة مفتوحة")

print("TOTAL OK")
