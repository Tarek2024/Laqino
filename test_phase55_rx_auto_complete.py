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

# ---- 1) رد كامل من أول صيدلية => البحث يتقفل
r1 = new_rx(); rx.auto_forward(c, r1)
assert open_offers(r1) == 10 and rx.stage_of(c, r1, "forwarded") == "at_pharmacies"
accept(P[0], r1); quote(P[0], r1, [it("اموكسيسيللين", "available"), it("بنادول", "available")], ca=True)
assert q1("SELECT COUNT(*) FROM rx_completed WHERE prescription_id=?", r1) == 1
assert q1("SELECT provider_id FROM rx_completed WHERE prescription_id=?", r1) == P[0]
assert open_offers(r1) == 0, "لا عروض مفتوحة بعد الاكتمال"
assert access(r1) == {P[0]}, "الطلب اختفى عن الباقي وفضل مع صاحب الرد الكامل"
assert q1("SELECT COUNT(*) FROM rx_claims WHERE prescription_id=? AND status='active'", r1) == 0
assert q1("SELECT status FROM prescriptions WHERE id=?", r1) != "closed", "الطلب مش closed عشان التوصيل"
assert rx.stage_of(c, r1, "forwarded") == "completed" and rx.search_state(c, r1) == "complete"
assert q1("SELECT COUNT(*) FROM audit_log WHERE action='rx.completed' AND target=?", str(r1)) == 1
code, qs = call(CUST, "GET", "/api/medical/prescriptions/%d/quotes" % r1)
assert code == 200 and qs["completed"] is True and qs["stage"] == "completed" and qs["quotes"][0]["complete"] is True
assert call(U(P[5]), "POST", "/api/provider/prescriptions/%d/accept" % r1)[0] in (404, 409)
assert rx.monitor_row(c, r1)["stage"] == "completed"
print("PASS الرد الكامل يقفل البحث: عروض مقفولة، الطلب مع صاحب الرد بس، مرحلة «اكتملت»، والطلب نفسه مش closed")

# ---- 2) لا إعادة توزيع بعد الاكتمال (العامل الدوري + _claim_next)
c.execute("UPDATE rx_offers SET state='open' WHERE prescription_id=? AND provider_id=?", (r1, P[7])); c.commit()
assert rx._claim_next(c, r1, now) is None and rx.refresh_claims(c, now + 4000) >= 0
assert rx.mark_completed(c, r1, P[0]) is False, "التكرار آمن"
assert q1("SELECT COUNT(*) FROM rx_completed WHERE prescription_id=?", r1) == 1
print("PASS مفيش توزيع تاني بعد الاكتمال والتكرار آمن")

# ---- 3) اكتمال بعد رد ناقص: الصيدلية التانية تكمّل الناقص => يتقفل
r2 = new_rx(); rx.auto_forward(c, r2)
accept(P[1], r2); quote(P[1], r2, [it("اموكسيسيللين", "available"), it("بنادول", "unavailable")])
assert q1("SELECT COUNT(*) FROM rx_completed WHERE prescription_id=?", r2) == 0, "الرد الناقص لا يقفل"
assert rx.stage_of(c, r2, "forwarded") == "quoted" and open_offers(r2) == 9
accept(P[2], r2); quote(P[2], r2, [it("بنادول", "available")], ca=True)
assert q1("SELECT provider_id FROM rx_completed WHERE prescription_id=?", r2) == P[2]
assert open_offers(r2) == 0 and access(r2) == {P[2]} and rx.stage_of(c, r2, "forwarded") == "completed"
print("PASS الرد الناقص لا يقفل، وتكملة الناقص تقفل البحث")

# ---- 4) حد الطلبات المفتوحة (5): المكتملة لا تُحتسب
r3 = new_rx(); rx.auto_forward(c, r3)
total_not_closed = q1("SELECT COUNT(*) FROM prescriptions WHERE customer_id=? AND status!='closed'", cust)
assert total_not_closed == 3 and rx.open_prescription_count(c, cust) == 1
assert c.execute(server.COUNT_SQL["prescriptions"], (cust,)).fetchone()[0] == 1
print("PASS المكتملة لا تُحتسب ضمن حد الروشتات المفتوحة")

# ---- 5) بحث النواقص الفرعي يكتمل => الأصل يتقفل
accept(P[0], r3); quote(P[0], r3, [it("اموكسيسيللين", "available"), it("بنادول", "unavailable")])
for pid in P[1:]: assert call(U(pid), "POST", "/api/provider/prescriptions/%d/decline" % r3)[0] == 200
assert rx.search_state(c, r3) == "ended_partial" and q1("SELECT COUNT(*) FROM rx_completed WHERE prescription_id=?", r3) == 0
code, ch = call(CUST, "POST", "/api/medical/prescriptions/%d/missing-search" % r3, {"items": [{"name": "بنادول", "qty": 1}]})
assert code == 201, (code, ch); child = ch["id"]
accept(P[3], child); quote(P[3], child, [it("بنادول", "available")], ca=True)
assert q1("SELECT COUNT(*) FROM rx_completed WHERE prescription_id=?", child) == 1
assert q1("SELECT COUNT(*) FROM rx_completed WHERE prescription_id=?", r3) == 1, "الأصل اتقفل بالتبعية"
assert rx.stage_of(c, r3, "forwarded") == "completed"
print("PASS اكتمال بحث النواقص الفرعي يقفل الأصل أيضًا")

# ---- 6) لو الاكتمال اتراجع (رد اتغيّر) البحث يتفتح تاني بدل ما يفضل مقفول بالغلط
r4 = new_rx(); rx.auto_forward(c, r4)
accept(P[0], r4); quote(P[0], r4, [it("اموكسيسيللين", "available"), it("بنادول", "unavailable")])
c.execute("INSERT INTO rx_completed(prescription_id,provider_id,completed_at) VALUES(?,?,?)", (r4, P[0], now)); c.commit()
assert rx.aggregate_status(c, r4) != "complete"
rx._claim_next(c, r4, now); c.commit()
assert q1("SELECT COUNT(*) FROM rx_completed WHERE prescription_id=?", r4) == 0, "الحارس لا يقفل روشتة ناقصة"
print("PASS الحارس لا يقفل روشتة مش مكتملة فعلًا")

# ---- 7) الواجهات والإصدار
idx = open("static/index.html", encoding="utf-8").read(); adm = open("static/admin.html", encoding="utf-8").read()
assert "completed:'اكتمل" in idx and "completed:'اكتملت" in adm
assert open("VERSION").read().split()[0] in ("release=phase-55", "release=phase-56", "release=phase-57", "release=phase-59", "release=phase-61", "release=phase-62", "release=phase-63")
print("PASS تسميات «اكتمل» في العميل والإدارة والإصدار phase-55")
print("TOTAL OK")
