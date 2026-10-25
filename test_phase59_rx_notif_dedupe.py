"""Phase 59 (بند 3): إشعار واحد للصيدلية لكل روشتة، وإشعار واحد للعميل لكل رد (بلا تكرار)."""
import json, os, tempfile, threading, time

DB = tempfile.mktemp(prefix="laqino-p59b-", suffix=".db")
os.environ["LAQINO_DB"] = DB
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(prefix="laqino-p59b-up-")
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
def ok(msg): print("PASS " + msg)
it = lambda n, st: {"name": n, "qty": 1, "unit_price": 10 if st == "available" else None, "item_status": st}
partial = [it("بنادول", "available"), it("فولتارين", "unavailable")]
full = [it("بنادول", "available"), it("فولتارين", "available")]
def accept(pid, rid): assert call(U(pid), "POST", "/api/provider/prescriptions/%d/accept" % rid)[0] == 200
def quote(pid, rid, items, **kw):
    out = call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, {"items": items, **kw}); assert out[0] == 200, out
NEWRX = "('provider.prescription','rx.offer')"
def pharm_new(pid, rid): return q1("SELECT COUNT(*) FROM notifications WHERE user_id=? AND ref_type='prescription' AND ref_id=? AND kind IN " + NEWRX, pid, rid)
def cust_n(kind=None, rid=None):
    return q1("SELECT COUNT(*) FROM notifications WHERE user_id=?" + (" AND kind='%s'" % kind if kind else "") + (" AND ref_id=%d" % rid if rid else ""), cust)

# A) بث تلقائي: كل صيدلية إشعار واحد للروشتة، حتى بعد رد جزئي وإعادة توزيع (جولة تانية) ورد كامل
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "auto"})[0] == 200
r = new_rx(); rx.auto_forward(c, r); c.commit()
assert all(pharm_new(p, r) == 1 for p in P), [pharm_new(p, r) for p in P]
accept(P[0], r); quote(P[0], r, partial, send_mode="partial")
c.execute("UPDATE rx_claims SET expires_at=1 WHERE prescription_id=?", (r,)); c.commit(); rx.refresh_claims(c); c.commit()
accept(P[1], r); quote(P[1], r, full, send_mode="full")
assert all(pharm_new(p, r) == 1 for p in P), [pharm_new(p, r) for p in P]
assert cust_n("rx.quote", r) == 1, "الرد الكامل = إشعار واحد للعميل"
ok("بث تلقائي: كل صيدلية إشعار واحد للروشتة عبر الجولات، والعميل إشعار واحد للرد الكامل")

# B) توجيه يدوي: forward-many مرتين + حذف الصلاحية وإضافتها = إشعار واحد
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "manual"})[0] == 200
r2 = new_rx(); c.commit()
for _ in range(2): assert call(ADMIN, "POST", "/api/admin/prescriptions/%d/forward-many" % r2, {"provider_ids": [P[3], P[4]]})[0] == 200
c.execute("DELETE FROM prescription_access WHERE prescription_id=? AND provider_id=?", (r2, P[3])); c.commit()
assert call(ADMIN, "POST", "/api/admin/prescriptions/%d/forward-many" % r2, {"provider_ids": [P[3]]})[0] == 200
assert pharm_new(P[3], r2) == 1 and pharm_new(P[4], r2) == 1, (pharm_new(P[3], r2), pharm_new(P[4], r2))
assert q1("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='provider.prescription'", P[3]) == 1
ok("توجيه يدوي: إشعار واحد للصيدلية حتى مع تكرار التوجيه وإعادة الصلاحية")

# C) ردّين من صيدليتين في الوضع اليدوي = إشعارين للعميل (واحد لكل رد)، ما فيش تكرار
quote(P[3], r2, full, confirm_all=True); quote(P[4], r2, partial, confirm_all=True)
assert cust_n("rx.quote", r2) == 2, cust_n("rx.quote", r2)
ok("الوضع اليدوي: ردّين = إشعارين، واحد لكل رد")

# D) اعتماد الإدارة اليدوي: لا إشعار للعميل عند وصول الرد، وإشعار واحد عند الاعتماد
assert call(ADMIN, "POST", "/api/admin/rx/manual-review", {"enabled": True})[0] == 200
r3 = new_rx(); c.commit()
assert call(ADMIN, "POST", "/api/admin/prescriptions/%d/forward-many" % r3, {"provider_ids": [P[5]]})[0] == 200
quote(P[5], r3, full, confirm_all=True)
assert cust_n("rx.quote", r3) == 0, "ما يوصلش قبل الاعتماد"
assert call(ADMIN, "POST", "/api/admin/rx/responses/%d/%d/review" % (r3, P[5]), {"decision": "approve"})[0] == 200
assert cust_n("rx.quote", r3) == 1 and q1("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.approved' AND ref_id=?", P[5], r3) == 1
assert call(ADMIN, "POST", "/api/admin/rx/manual-review", {"enabled": False})[0] == 200
ok("اعتماد الإدارة: صفر قبل الاعتماد، وإشعار واحد للعميل وواحد للصيدلية بعده")

# E) نهاية البحث بالمهلة: استدعاء refresh_claims أكتر من مرة = إشعار نهاية واحد بس
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "auto"})[0] == 200
r4 = new_rx(); rx.auto_forward(c, r4); c.commit(); accept(P[6], r4); quote(P[6], r4, partial, send_mode="partial")
c.execute("UPDATE prescriptions SET created_at=? WHERE id=?", (now - 7200, r4)); c.commit()
for _ in range(3): rx.refresh_claims(c, now); c.commit()
assert cust_n("rx.search_ended", r4) == 1 and cust_n(None, r4) == 1, (cust_n("rx.search_ended", r4), cust_n(None, r4))
ok("نهاية البحث: إشعار واحد للعميل مهما اتكرر الفحص الدوري")
print("TOTAL OK")
