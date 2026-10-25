"""phase-64: لما يوصل رد كامل، الردود الجزئية ما تظهرش للعميل (إلا لو مرتبطة بطلب توصيل). قاعدة SQLite مؤقتة؛ rx.handle مباشرة."""
import os, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(prefix="laqino-p64-", suffix=".db")
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(prefix="laqino-p64-up-")
import server
rx = server.rx
server.init("01000000000", "AdminPass123")
now = int(time.time()); c = server.db()
class H:
    def __init__(s, b=None): s.b = b or {}; s.out = None
    def body(s): return s.b
    def send(s, code, obj): s.out = (code, obj)
def call(user, method, path, body=None):
    cc = server.db()
    try:
        h = H(body); assert rx.handle(h, cc, user, method, path, {}), path; return h.out
    finally: cc.close()
region = int((c.execute("SELECT id FROM regions WHERE level='markaz' ORDER BY id LIMIT 1").fetchone() or c.execute("SELECT id FROM regions ORDER BY id LIMIT 1").fetchone())["id"])
def add_user(phone, name, role):
    salt = "ab" * 8
    return c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,?)", (phone, name, server.hp("password1", salt), salt, role, region, now)).lastrowid
ADMIN = {"id": c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()["id"], "role": "admin"}
cust = add_user("01090640000", "عميل", "customer"); CUST = {"id": cust, "role": "customer"}
P = []
for i in range(3):
    pid = add_user("0109064%04d" % (i + 1), "ص%d" % i, "medical_provider")
    c.execute("INSERT INTO providers(user_id,name_ar,kind,region_id,address,status,created_at,distribution_enabled) VALUES(?,?,'pharmacy',?,?,'approved',?,1)", (pid, "صيدلية %d" % i, region, "ع", now)); P.append(pid)
c.commit()
U = lambda p: {"id": p, "role": "medical_provider"}
def new_rx():
    fid = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (cust, "f%d.png" % time.time_ns(), "image/png", 1, now)).lastrowid
    r = c.execute("INSERT INTO prescriptions(customer_id,region_id,file_id,note,status,created_at,kind) VALUES(?,?,?,'','pending',?,'rx')", (cust, region, fid, now - 60)).lastrowid
    c.commit(); return r
it = lambda n, st: {"name": n, "qty": 1, "unit_price": 10 if st == "available" else None, "item_status": st}
def quote(pid, rid, items, mode):
    code, out = call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, {"items": items, "send_mode": mode}); assert code == 200, out
def quotes(rid):
    code, out = call(CUST, "GET", "/api/medical/prescriptions/%d/quotes" % rid); assert code == 200, out; return out
part = [it("بنادول", "available"), it("فولتارين", "unavailable")]
full = [it("بنادول", "available"), it("فولتارين", "available")]
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "auto"})[0] == 200
r = new_rx(); rx.auto_forward(c, r); c.commit()
for pid in P[:2]:
    assert call(U(pid), "POST", "/api/provider/prescriptions/%d/accept" % r)[0] == 200
    quote(pid, r, part, "partial")
    q = quotes(r); assert q["quotes"] == [] and q["search_state"] == "searching", q
assert call(U(P[2]), "POST", "/api/provider/prescriptions/%d/accept" % r)[0] == 200
quote(P[2], r, full, "full")
q = quotes(r)
assert q["search_state"] == "complete", q["search_state"]
assert [x["provider_id"] for x in q["quotes"]] == [P[2]], [(x["provider_id"], x["complete"]) for x in q["quotes"]]
assert all(x["complete"] for x in q["quotes"])
hid = rx.hidden_provider_ids(c, r)  # قائمة «طلباتك» تصفّي ردودها بنفس الدالة
assert hid == {P[0], P[1]}, hid
print("PASS: بعد رد كامل يظهر الكامل فقط (الجزئيان مخفيان في /quotes وفي قائمة الروشتات)")

# جزئي بعد نهاية البحث بلا كامل: أفضل جزئي فقط (السلوك القديم لم يتغير)
r2 = new_rx(); rx.auto_forward(c, r2); c.commit()
for pid, items in ((P[0], part), (P[1], part + [it("اموكسيسيللين", "available")]), (P[2], part)):
    assert call(U(pid), "POST", "/api/provider/prescriptions/%d/accept" % r2)[0] == 200
    quote(pid, r2, items, "partial")
q = quotes(r2)
assert q["search_state"] == "ended_partial" and [x["provider_id"] for x in q["quotes"]] == [P[1]], q
print("PASS: بلا رد كامل بعد انتهاء البحث يظهر أعلى رد جزئي فقط")
