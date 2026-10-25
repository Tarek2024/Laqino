"""Phase 57: جولات الرد الجزئي المتتالية وأفضل رد جزئي.
قاعدة SQLite مؤقتة حقيقية؛ يستدعي rx.handle مباشرة."""
import json, os, tempfile, threading, time

DB = tempfile.mktemp(prefix="laqino-p57r-", suffix=".db")
os.environ["LAQINO_DB"] = DB
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(prefix="laqino-p57r-up-")
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
c.commit()
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "auto"})[0] == 200
def accept(pid, rid):
    code, out = call(U(pid), "POST", "/api/provider/prescriptions/%d/accept" % rid); return code
def quote(pid, rid, items, mode):
    return call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, {"items": items, "send_mode": mode})
it = lambda n, st: {"name": n, "qty": 1, "unit_price": 10 if st == "available" else None, "item_status": st}
q1 = lambda sql, *a: c.execute(sql, a).fetchone()[0]
def open_for(rid): return {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (rid,))}
def active_claim(rid): return c.execute("SELECT provider_id,claimed_at,expires_at FROM rx_claims WHERE prescription_id=? AND status='active'", (rid,)).fetchone()
def new_rx():
    fid = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (cust, "f%d.png" % time.time_ns(), "image/png", 1, now)).lastrowid
    r = c.execute("INSERT INTO prescriptions(customer_id,region_id,file_id,note,status,created_at,kind) VALUES(?,?,?,'','pending',?,'rx')", (cust, region, fid, now - 60)).lastrowid
    c.commit(); return r
N = ["دواء أ", "دواء ب", "دواء ج", "دواء د", "دواء هـ"]
r = new_rx(); rx.auto_forward(c, r)
assert open_for(r) == set(P), "الجولة 1: معروضة على الكل"
# جولة 1: P0 يقبل -> يختفي عن الباقي، حجز 10 د
assert accept(P[0], r) == 200
assert open_for(r) == set() and active_claim(r)["provider_id"] == P[0]
assert active_claim(r)["expires_at"] - active_claim(r)["claimed_at"] == 600
assert accept(P[1], r) != 200, "الباقي ما يقدرش يقبل"
code, out = quote(P[0], r, [it(N[0], "available")], "partial"); assert code == 200, out
# جولة 2: نفس المسار — معروضة على الكل ما عدا اللي جرّب
assert open_for(r) == set(P) - {P[0]}, open_for(r)
assert accept(P[1], r) == 200
assert open_for(r) == set() and active_claim(r)["provider_id"] == P[1]
assert active_claim(r)["expires_at"] - active_claim(r)["claimed_at"] == 600
assert accept(P[2], r) != 200
# P1 جزئي 3 أصناف
code, out = quote(P[1], r, [it(N[0], "available"), it(N[1], "available"), it(N[2], "available"), it(N[3], "unavailable"), it(N[4], "unavailable")], "partial"); assert code == 200, out
assert open_for(r) == set(P) - {P[0], P[1]}
# جولة 3: P2 يقبل ثم تنتهي مهلته بدون رد -> يرجع العرض للباقي
assert accept(P[2], r) == 200
c.execute("UPDATE rx_claims SET expires_at=? WHERE prescription_id=? AND status='active'", (int(time.time()) - 5, r)); c.commit()
cc = server.db(); rx.refresh_claims(cc); cc.commit(); cc.close()
assert active_claim(r) is None and P[2] not in open_for(r) and open_for(r) == set(P) - {P[0], P[1], P[2]}, open_for(r)
# P3 جزئي بصنفين
assert accept(P[3], r) == 200
code, out = quote(P[3], r, [it(N[0], "available"), it(N[1], "available")], "partial"); assert code == 200, out
bp = rx.best_partial(c, r)
assert bp["provider_id"] == P[1] and bp["confirmed_count"] == 3, bp
# باقي الصيدليات تعتذر -> نهاية البحث وأفضل جزئي
for pid in P[4:]:
    assert call(U(pid), "POST", "/api/provider/prescriptions/%d/decline" % r)[0] == 200
cc = server.db(); st = rx.search_state(cc, r); cc.close()
assert st == "ended_partial", st
code, out = call(CUST, "GET", "/api/medical/prescriptions/%d/quotes" % r)
assert code == 200 and out["search_state"] == "ended_partial" and out["best_partial"]["provider_id"] == P[1], out
assert q1("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.search_ended'", cust) == 1
print("PASS جولات جزئية متتالية: بث للكل، أول قابل يحجز 10 د ويختفي عن الباقي، المهلة تعيد العرض، وأفضل جزئي بعدد الأصناف")
print("TOTAL OK")
