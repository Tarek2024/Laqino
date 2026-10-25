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
def line(n, price=10, qty=1): return {"name": n, "qty": qty, "unit_price": price}
def quote(pid, rid, items, **kw): return call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, dict(items=items, **kw))
def photo():
    fid = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (cust, "m%d.png" % time.time_ns(), "image/png", 1, now)).lastrowid
    c.commit(); return fid
def ms(rid, body): return call(CUST, "POST", "/api/medical/prescriptions/%d/missing-search" % rid, body)

# روشتة أصلية: صيدلية ردّت بالمتاح فقط، وباقي الصيدليات رفضوا/خلصوا → البحث انتهى
r = new_rx(); rx.auto_forward(c, r); accept(P[0], r)
assert quote(P[0], r, [line("اموكسيسيللين")], send_mode="partial")[0] == 200
for pid in P[1:]:
    assert call(U(pid), "POST", "/api/provider/prescriptions/%d/decline" % r)[0] == 200
assert rx.search_state(c, r) == "ended_partial"

# بدون اسم ولا صورة: مرفوض
assert ms(r, {})[0] == 400
assert ms(r, {"items": []})[0] == 400

# 1) صنف مكتوب بإيد العميل (أي اسم، مش مربوط بقايمة الصيدلية) → نفس نظام التوزيع (عروض لكل الصيدليات)
code, out = ms(r, {"items": [{"name": "فيتامين د", "qty": 2}], "note": "50000 وحدة"})
assert code == 201 and out["search_kind"] == "typed_items", out
child = out["id"]
assert {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (child,))} == set(P)
accept(P[3], child)
assert q1("SELECT COUNT(*) FROM rx_claims WHERE prescription_id=? AND status='active'", child) == 1, "حجز 10 دقايق للي قبل"
claim = c.execute("SELECT claimed_at,expires_at FROM rx_claims WHERE prescription_id=? AND status='active'", (child,)).fetchone()
assert claim["expires_at"] - claim["claimed_at"] == 600
assert {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (child,))} == set(), "اختفى عن الباقي"
# الصيدلية «كاملة» على الصنف المكتوب → البحث الفرعي يكتمل ويكمّل الأصل كمان
code, out = quote(P[3], child, [line("فيتامين د", qty=2)], send_mode="full")
assert code == 200, out
assert rx.is_completed(c, child) and rx.aggregate_status(c, r) == "complete" and rx.is_completed(c, r), "اكتمال الفرعي يكمّل الأصل"
print("PASS صنف مكتوب: يتوزّع ويتحجز 10 دقايق ورد «كاملة» يكمّل الأصل")

# 2) بصورة فقط (بلا اسم) → نفس التوزيع، وبلا نطاق أصناف
r2 = new_rx(); rx.auto_forward(c, r2); accept(P[0], r2)
assert quote(P[0], r2, [line("اموكسيسيللين")], send_mode="partial")[0] == 200
for pid in P[1:]:
    assert call(U(pid), "POST", "/api/provider/prescriptions/%d/decline" % r2)[0] == 200
fid = photo()
code, out = ms(r2, {"file_ids": [fid]})
assert code == 201 and out["search_kind"] == "item_photo" and out["items"] == [], out
child2 = out["id"]
assert {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (child2,))} == set(P), "صورة فقط تتوزع كمان"
assert rx.requested_items(c, child2, P[4]) == []
accept(P[4], child2)
assert quote(P[4], child2, [line("الصنف اللي في الصورة")], send_mode="partial")[0] == 200
assert not rx.is_completed(c, r2), "المتاح لا يكمّل الأصل"
print("PASS صورة صنف فقط: نفس التوزيع والحجز بلا نطاق")

# 3) مفيش بحث تاني على روشتة اتكمّلت
assert ms(r, {"items": [{"name": "اسبرين", "qty": 1}]})[0] == 409
print("TOTAL OK")
