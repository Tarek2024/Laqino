"""Phase 53: التوزيع المتزامن + القبول الذري + الوضعان + أفضل عرض جزئي وقبوله + البحث الفرعي.
قاعدة بيانات SQLite مؤقتة حقيقية؛ يستدعي rx.handle مباشرة (نفس المسارات التي يستخدمها الخادم)."""
import json, os, tempfile, threading, time

DB = tempfile.mktemp(prefix="laqino-p53-", suffix=".db")
os.environ["LAQINO_DB"] = DB
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(prefix="laqino-p53-up-")
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

# ---- 1) الوضع محفوظ في قاعدة البيانات، والافتراضي يدوي ولا يوزّع
assert call(ADMIN, "GET", "/api/admin/rx/distribution-mode")[1]["mode"] == "manual"
assert call(CUST, "POST", "/api/admin/rx/distribution-mode", {"mode": "auto"})[0] in (401, 403)
r0 = new_rx(); assert rx.auto_forward(c, r0) == 0 and q1("SELECT COUNT(*) FROM rx_offers") == 0
assert call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "bad"})[0] == 400
code, info = call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "auto"})
assert code == 200 and info["mode"] == "auto" and info["eligible_pharmacies"] == 10, info
assert rx.distribution_mode(server.db()) == "auto"
print("PASS الوضع التلقائي/اليدوي محفوظ في قاعدة البيانات، والافتراضي يدوي")

# ---- 2) بث متزامن لكل المؤهلات (10 > 8) دون المعطّلة/غير المعتمدة، بلا حجز مسبق
r1 = new_rx(); assert rx.auto_forward(c, r1) == 1
offers = {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (r1,))}
assert offers == set(P), offers
assert {x[0] for x in c.execute("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (r1,))} == set(P)
assert q1("SELECT COUNT(*) FROM rx_claims WHERE prescription_id=?", r1) == 0
assert q1("SELECT COUNT(*) FROM notifications WHERE kind='rx.offer' AND ref_id=?", r1) == 10
rx.auto_forward(c, r1)
assert q1("SELECT COUNT(*) FROM notifications WHERE kind='rx.offer' AND ref_id=?", r1) == 10, "no duplicate offer notices"
print("PASS الطلب يُعرض على كل الصيدليات المؤهلة معًا (10) بلا سقف 8، وبلا تكرار إشعارات")

# ---- 3) قبول ذري: أول صيدلية فقط
res = []; bar = threading.Barrier(4)
def go(pid):
    bar.wait(); res.append((pid, call(U(pid), "POST", "/api/provider/prescriptions/%d/accept" % r1)[0]))
ts = [threading.Thread(target=go, args=(pid,)) for pid in P[:4]]
[t.start() for t in ts]; [t.join() for t in ts]
wins = [p for p, code in res if code == 200]
assert len(wins) == 1 and all(code == 409 for p, code in res if p not in wins), res
W = wins[0]
assert q1("SELECT COUNT(*) FROM rx_claims WHERE prescription_id=? AND status='active'", r1) == 1
exp = q1("SELECT expires_at-claimed_at FROM rx_claims WHERE prescription_id=? AND status='active'", r1); assert exp == 600, exp
assert {x[0] for x in c.execute("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (r1,))} == {W}, "الطلب اختفى عن الباقي"
assert call(U(P[9]), "POST", "/api/provider/prescriptions/%d/accept" % r1)[0] == 409
assert call(U(P[9]), "POST", "/api/provider/prescriptions/%d/quote" % r1, {"items": [{"name": "دواء", "qty": 1, "unit_price": 5, "item_status": "available"}], "confirm_all": True})[0] == 404
print("PASS أول قبول يربح الحجز (10 دقائق من القبول) ويختفي الطلب عن الباقين")

# ---- 4) انتهاء المهلة: إعادة بث لمن لم يجرّب، وسجل الحجز محفوظ
c.execute("UPDATE rx_claims SET expires_at=? WHERE prescription_id=? AND status='active'", (now - 1, r1)); c.commit()
rx.refresh_claims(c, now)
assert q1("SELECT COUNT(*) FROM rx_claims WHERE prescription_id=? AND status='expired'", r1) == 1
op = {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (r1,))}
assert op == set(P) - {W} and q1("SELECT COUNT(*) FROM rx_claim_attempts WHERE prescription_id=?", r1) == 1, op
print("PASS انتهاء مهلة الحجز يعيد العرض على باقي الصيدليات ولا يعيده على من أخذه")

# ---- 5) ردود جزئية + إعادة بث للنواقص + قبول/اعتذار + نهاية البحث
r2 = new_rx(); rx.auto_forward(c, r2)
def accept(pid, rid): assert call(U(pid), "POST", "/api/provider/prescriptions/%d/accept" % rid)[0] == 200
def quote(pid, rid, items):
    code, out = call(U(pid), "POST", "/api/provider/prescriptions/%d/quote" % rid, {"items": items})
    assert code == 200, (code, out);
    assert call(ADMIN, "POST", "/api/admin/rx/responses/%d/%d/review" % (rid, pid), {"decision": "approve"})[0] == 200
it = lambda n, st: {"name": n, "qty": 1, "unit_price": 10 if st == "available" else None, "item_status": st}
accept(P[0], r2); quote(P[0], r2, [it("اموكسيسيللين", "available"), it("بنادول", "unavailable"), it("فيتامين")] if False else [it("اموكسيسيللين", "available"), it("بنادول", "unavailable"), it("فولتارين", "needs_confirmation")])
op = {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (r2,))}
assert op == set(P[1:]), "إعادة البث بعد الرد الجزئي لمن لم يجرّب"
assert [i["name"] for i in rx.requested_items(c, r2, P[1])] == ["بنادول", "فولتارين"]
assert rx.search_state(c, r2) == "searching"
accept(P[1], r2); quote(P[1], r2, [it("بنادول", "available"), it("فولتارين", "unavailable")])
accept(P[2], r2); quote(P[2], r2, [it("فولتارين", "unavailable")])
for pid in P[3:9]:
    assert rx.search_state(c, r2) == "searching"
    assert call(U(pid), "POST", "/api/provider/prescriptions/%d/decline" % r2)[0] == 200
assert call(U(P[3]), "POST", "/api/provider/prescriptions/%d/decline" % r2)[0] in (404, 409)
assert rx.search_state(c, r2) == "searching", "لم يُجَب أحد الصيدليات بعد: الوقت وحده/الرد الجزئي لا ينهي البحث"
assert call(U(P[9]), "POST", "/api/provider/prescriptions/%d/decline" % r2)[0] == 200
assert rx.search_state(c, r2) == "ended_partial"
assert q1("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.search_ended' AND ref_id=?", cust, r2) == 1
assert q1("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=?", r2) == 3, "كل الردود محفوظة"
print("PASS الاعتذار والردود الجزئية وإعادة البث؛ البحث لا ينتهي إلا باكتمال كل الدورات، وإشعار واحد للعميل")

# ---- 6) أفضل عرض جزئي ثم قبوله
code, qs = call(CUST, "GET", "/api/medical/prescriptions/%d/quotes" % r2)
bp = qs["best_partial"]
assert code == 200 and qs["search_state"] == "ended_partial" and bp["provider_id"] == P[1], bp
assert [x["name"] for x in bp["confirmed"]] == ["بنادول"] and [x["name"] for x in bp["unavailable"]] == ["فولتارين"] and bp["undecided"] == []
c0 = [d for d in rx.quotes_for(c, r2) if d["provider_id"] == P[0]][0]
v0 = rx._partial_view(c0); assert [x["name"] for x in v0["undecided"]] == ["فولتارين"] and v0["unavailable"] != v0["undecided"], "المجهول لا يُعرض كغير متوفر"
assert call(CUST, "POST", "/api/medical/prescriptions/%d/accept-partial" % r2, {"provider_id": P[0]})[0] == 409
code, out = call(CUST, "POST", "/api/medical/prescriptions/%d/accept-partial" % r2, {"provider_id": P[1]})
assert code == 200 and "لا يعني شراء" in out["message"], out
assert call(CUST, "POST", "/api/medical/prescriptions/%d/accept-partial" % r2, {"provider_id": P[1]})[0] == 200
assert call(CUST, "POST", "/api/medical/prescriptions/%d/accept-partial" % r2, {"provider_id": P[0]})[0] == 409
assert rx.search_state(c, r2) == "partial_accepted" and q1("SELECT status FROM prescriptions WHERE id=?", r2) != "closed"
assert q1("SELECT COUNT(*) FROM delivery_orders") == 0, "القبول الجزئي ليس شراءً تلقائيًا"
print("PASS أفضل عرض جزئي (الأكثر تأكيدًا ثم الأقل مجهولًا)، المجهول لا يظهر كغير متوفر، والقبول لا ينشئ شراء ولا يغلق الطلب")

# ---- 7) بحث فرعي عن النواقص فقط بعد انتهاء البحث، والتاريخ محفوظ
code, out = call(CUST, "POST", "/api/medical/prescriptions/%d/missing-search" % r2, {"items": [{"name": "فولتارين", "qty": 1}], "note": "التركيز 50 مجم"})
assert code == 201, out
child = out["id"]
assert q1("SELECT parent_prescription_id FROM rx_search_links WHERE child_prescription_id=?", child) == r2
assert {x[0] for x in c.execute("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (child,))} == set(P)
assert [i["name"] for i in rx.requested_items(c, child, P[5])] == ["فولتارين"]
assert q1("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=?", r2) == 3
assert "التركيز 50 مجم" in q1("SELECT note FROM prescriptions WHERE id=?", child)
print("PASS البحث الفرعي للنواقص وحدها يُبثّ على الصيدليات ويحفظ التاريخ وتفاصيل العميل")

# ---- 7b) عروض بلا قبول تُغلق عند سقف الأمان ويُبلَّغ العميل مرة واحدة
r5 = new_rx(); rx.auto_forward(c, r5)
assert q1("SELECT COUNT(*) FROM rx_offers WHERE prescription_id=? AND state='open'", r5) == 10
c.execute("UPDATE prescriptions SET created_at=? WHERE id=?", (now - 61 * 60, r5)); c.commit()
rx.refresh_claims(c, now); rx.refresh_claims(c, now)
assert q1("SELECT COUNT(*) FROM rx_offers WHERE prescription_id=? AND state='open'", r5) == 0
assert q1("SELECT COUNT(*) FROM prescription_access WHERE prescription_id=?", r5) == 0
assert q1("SELECT COUNT(*) FROM notifications WHERE user_id=? AND ref_id=? AND kind IN('rx.claim_timeout','rx.no_pharmacy')", cust, r5) == 1
assert rx.search_state(c, r5, now) == "ended_none"
print("PASS سقف الأمان يغلق العروض غير المقبولة ويُبلغ العميل مرة واحدة")

# ---- 8) التبديل لليدوي لا يلغي شيئًا
before = (q1("SELECT COUNT(*) FROM rx_offers WHERE state='open'"), q1("SELECT COUNT(*) FROM prescription_responses"), q1("SELECT COUNT(*) FROM prescriptions"))
code, info = call(ADMIN, "POST", "/api/admin/rx/distribution-mode", {"mode": "manual"})
assert info["mode"] == "manual" and not info["claim_mode"]
after = (q1("SELECT COUNT(*) FROM rx_offers WHERE state='open'"), q1("SELECT COUNT(*) FROM prescription_responses"), q1("SELECT COUNT(*) FROM prescriptions"))
assert before == after, (before, after)
r3 = new_rx(); assert rx.auto_forward(c, r3) == 0 and q1("SELECT COUNT(*) FROM rx_offers WHERE prescription_id=?", r3) == 0
assert q1("SELECT COUNT(*) FROM audit_log WHERE action='rx.distribution_mode'") == 2
print("PASS التحويل لليدوي يحفظ الطلبات والردود والعروض ولا يوزّع الجديد تلقائيًا، ويُسجَّل في التدقيق")
c.close()
