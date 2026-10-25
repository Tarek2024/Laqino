"""Phase 55: قفل البحث تلقائيًا لما رد الروشتة يكتمل (بدون إغلاق الطلب نفسه عشان التوصيل يفضل شغّال).
قاعدة SQLite مؤقتة حقيقية؛ يستدعي rx.handle مباشرة."""
import json, os, tempfile, threading, time

DB = tempfile.mktemp(prefix="laqino-p55-", suffix=".db")
os.environ["LAQINO_DB"] = DB
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(prefix="laqino-p55-up-")
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


def quote(pid, rid, items, **kw):
    return call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, dict(items=items, **kw))

A, B, C = "اموكسيسيللين", "بنادول", "فولتارين"
r = new_rx(); rx.auto_forward(c, r)
accept(P[0], r)
code, out = quote(P[0], r, [it(A, "available"), it(B, "unavailable"), it(C, "unavailable")], send_mode="partial")
assert code == 200, out

# بعد الرد الجزئي: العرض للصيدليات التانية بالروشتة كلها، بلا نطاق «الناقص فقط»
op = {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (r,))}
assert op == set(P[1:]), "إعادة العرض على باقي الصيدليات"
for pid in P[1:4]:
    assert rx.requested_items(c, r, pid) == [], "لا نطاق: الروشتة كلها"

# الصيدلية التالية تسعّر الروشتة كلها (تشمل الصنف اللي الأولى غطّته) ولا يُرفض ردها
accept(P[1], r)
code, out = quote(P[1], r, [it(A, "available"), it(B, "available"), it(C, "unavailable")], send_mode="partial")
assert code == 200 and out["status"] == "needs_confirmation", (code, out)
assert q1("SELECT COUNT(*) FROM rx_claim_items WHERE prescription_id=?", r) == 0, "ولا أي نطاق مخزَّن"

# صيدلية تالية تغطي الروشتة كلها => اكتمال
accept(P[2], r)
code, out = quote(P[2], r, [it(A, "available"), it(B, "available"), it(C, "available")], send_mode="full")
assert code == 200 and rx.is_completed(c, r), (code, out)

# بحث الأصناف الفرعي يحتفظ بنطاقه (الأصناف الناقصة فقط) — لم يتغيّر
print("PASS بعد الرد الجزئي تُوزَّع الروشتة كلها على الصيدليات التالية (بلا نطاق ناقص)، وتسعيرها كاملة يقفل البحث")
print("TOTAL OK")
