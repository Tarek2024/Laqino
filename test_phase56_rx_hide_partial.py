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


def quotes(rid):
    code, out = call(CUST, "GET", "/api/medical/prescriptions/%d/quotes" % rid); assert code == 200, out; return out
def cust_notes():
    return q1("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.quote'", cust)

full_items = [it("اموكسيسيللين", "available"), it("بنادول", "available")]
p3 = [it("اموكسيسيللين", "available"), it("بنادول", "available"), it("فولتارين", "unavailable")]
p2 = [it("اموكسيسيللين", "available"), it("بنادول", "unavailable"), it("فولتارين", "unavailable")]

# ---- أثناء البحث: الجزئي يتحفظ ولا يظهر ولا إشعار
r = new_rx(); rx.auto_forward(c, r)
accept(P[0], r)
n0 = cust_notes()
out = call(U(P[0]), "POST", "/api/provider/prescriptions/%d/quote" % r, {"items": p2, "send_mode": "partial"})[1]
assert out["review"] == "approved"
assert cust_notes() == n0, "لا إشعار للعميل على رد جزئي"
q = quotes(r)
assert q["search_state"] == "searching" and q["quotes"] == [], q["quotes"]
assert q["best_partial"] is None
assert q1("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=? AND provider_id=?", r, P[0]) == 1, "الرد محفوظ"

# ---- صيدلية ثانية بردّ أفضل (أصناف أكتر)؛ لسه مخفي
accept(P[1], r)
assert call(U(P[1]), "POST", "/api/provider/prescriptions/%d/quote" % r, {"items": [it("بنادول", "available"), it("فولتارين", "unavailable")], "send_mode": "partial"})[0] == 200  # (الروشتة كلها بعد البند 3؛ هنا مجرد رد جزئي ثاني)
assert quotes(r)["quotes"] == [] and cust_notes() == n0

# ---- نهاية البحث بمهلة كلية: يظهر أفضل رد جزئي فقط
c.execute("UPDATE prescriptions SET created_at=? WHERE id=?", (now - 7200, r)); c.commit()
rx.refresh_claims(c); c.commit()
q = quotes(r)
assert q["search_state"] in ("ended_partial", "partial_accepted"), q["search_state"]
assert len(q["quotes"]) == 1 and q["quotes"][0]["provider_id"] == q["best_partial"]["provider_id"], "أفضل رد جزئي بس"
assert q1("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=?", r) == 2, "الردين محفوظين"

# ---- الرد الكامل يظهر فورًا ويبعت إشعار
r2 = new_rx(); rx.auto_forward(c, r2); accept(P[2], r2)
n1 = cust_notes()
assert call(U(P[2]), "POST", "/api/provider/prescriptions/%d/quote" % r2, {"items": full_items, "send_mode": "full"})[0] == 200
assert cust_notes() == n1 + 1, "إشعار واحد للرد الكامل"
q = quotes(r2)
assert len(q["quotes"]) == 1 and q["quotes"][0]["complete"] is True
print("PASS الجزئي يتحفظ بلا إشعار ولا ظهور أثناء البحث، وأفضل رد جزئي بس يظهر في النهاية، والكامل يظهر ويُشعر فورًا")
print("TOTAL OK")
