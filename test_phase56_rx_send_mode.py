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


def raw(pid, rid, items, **extra):
    d = {"items": items}; d.update(extra)
    return call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, d)

def line(n, price=10): return {"name": n, "qty": 1, "unit_price": price}   # بلا حالة: كل ما يُكتب = متاح

# ---- الاختيار هو اللي يحدد، لا حالة لكل صنف
r = new_rx(); rx.auto_forward(c, r); accept(P[0], r)
assert raw(P[0], r, [line("اموكسيسيللين")], send_mode="x")[0] == 400, "قيمة غير صالحة"
assert raw(P[0], r, [], send_mode="partial")[0] == 400, "لازم صنف واحد على الأقل"
assert raw(P[0], r, [dict(line("بنادول"), item_status="unavailable")], send_mode="partial")[0] == 400, "غير المتاح يُتجاهل فلا يبقى شيء"
code, out = raw(P[0], r, [line("اموكسيسيللين"), line("بنادول")], send_mode="partial")
assert code == 200 and out["status"] == "needs_confirmation" and out["send_mode"] == "partial", out
assert q1("SELECT COUNT(*) FROM rx_completed WHERE prescription_id=?", r) == 0, "المتاح فقط لا يكمّل الروشتة"
assert q1("SELECT COUNT(*) FROM rx_prescription_items WHERE prescription_id=?", r) == 0, "لا نستنتج أصنافًا متوقعة من رد الصيدلية"
assert q1("SELECT COUNT(*) FROM rx_quote_item_status WHERE prescription_id=? AND item_status!='available'", r) == 0

# ---- «الروشتة كاملة» تكفي لوحدها لإنهاء البحث (بدون فحص أصناف)
r2 = new_rx(); rx.auto_forward(c, r2); accept(P[1], r2)
code, out = raw(P[1], r2, [line("اموكسيسيللين")], send_mode="full")
assert code == 200 and out["status"] == "available" and rx.is_completed(c, r2), (code, out)

# ---- التوافق القديم: confirm_all = full، وبدون اختيار والكل متوفر مرفوض
r3 = new_rx(); rx.auto_forward(c, r3); accept(P[2], r3)
legacy = [{"name": "اموكسيسيللين", "qty": 1, "unit_price": 10, "item_status": "available"}]
assert raw(P[2], r3, legacy)[0] == 400, "الوضع القديم: لازم اختيار صريح"
assert raw(P[2], r3, legacy, confirm_all=True)[0] == 200

ph = open(os.path.join(os.path.dirname(__file__) or ".", "static", "pharmacy.html"), encoding="utf-8").read()
assert "send_mode:mode" in ph and "الروشتة كاملة ← إرسال" in ph and "تم إرسال المتاح وسيتم توفير الناقص" in ph
assert "item_status:r.querySelector" not in ph and "غير متوفر" not in ph.split("const qrow")[1].split("window.qadd")[0], "لا اختيار حالة لكل صنف في الفورم"
print("PASS الصيدلية تكتب المتاح فقط والاختيار (كاملة/المتاح) هو الذي يحدد، بلا حالة لكل صنف")

# ---- أفضل رد جزئي = الأكثر أصنافًا
r4 = new_rx(); rx.auto_forward(c, r4); accept(P[3], r4)
assert raw(P[3], r4, [line("اموكسيسيللين")], send_mode="partial")[0] == 200
accept(P[4], r4)
assert raw(P[4], r4, [line("اموكسيسيللين"), line("بنادول"), line("فولتارين")], send_mode="partial")[0] == 200
accept(P[5], r4)
assert raw(P[5], r4, [line("اموكسيسيللين"), line("بنادول")], send_mode="partial")[0] == 200
assert rx.best_partial(c, r4)["provider_id"] == P[4], "الأكثر أصنافًا هو الأفضل"
assert rx.best_partial(c, r4)["confirmed_count"] == 3
print("PASS عدد الأصناف هو مقياس أفضل رد جزئي")
print("TOTAL OK")
