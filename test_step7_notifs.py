# الخطوة 7: إشعارات ناقصة — استفسارات (للصيدليات)، روشتات جديدة (للإدارة)، اعتراضات على الطلبات (للإدارة والصيدلية). قاعدة مؤقتة + خادم حقيقي.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, notif
from http.server import ThreadingHTTPServer
from imgutil import png
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
nt = lambda uid, kind: sql("SELECT title,body,link,ref_type,ref_id FROM notifications WHERE user_id=? AND kind=? ORDER BY id", (uid, kind))
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
staff, sid = user("01055550001", "موظف"); assert call("POST", "/admin/users/%d/role" % sid, {"role": "staff"}, at)[0] == 200
cust, cid = user("01055550002", "عميل"); pa, a = user("01055550003", "صيدلي أ"); pb, b = user("01055550004", "صيدلي ب"); pc, c_ = user("01055550005", "صيدلي ج"); pd, d_ = user("01055550006", "صيدلي د")
sql("INSERT INTO regions(id,parent_id,name_ar,slug,level,is_active) VALUES(94,2,'مركز شقيق','sibling',(SELECT level FROM regions WHERE id=3),1)")   # شقيق المنطقة 3: غير متداخل معها
for t, uid, reg, st in ((pa, a, 3, "approved"), (pb, b, 2, "approved"), (pc, c_, 94, "approved"), (pd, d_, 3, "pending")):
    call("POST", "/providers/apply", {"name_ar": "صيدلية %d" % uid, "region_id": reg, "address": "x"}, t)
    if st == "approved": assert call("POST", "/admin/providers/%d/review" % uid, {"status": "approved"}, at)[0] == 200
# ---- استفسار دواء جديد -> الصيدليات المعتمدة في مناطق متداخلة فقط
s_, r = call("POST", "/medical/inquiries", {"medicine_name": "بنادول", "region_id": 3}, cust); I = r["id"]; ok("inquiry created", s_ == 201)
for who, uid in (("pharmacy in same region", a), ("pharmacy in parent region", b)):
    r = nt(uid, "provider.inquiry"); ok(who + " notified", len(r) == 1 and r[0][0] == "استفسار دواء جديد في منطقتك" and r[0][1] == "بنادول" and r[0][2] == "pharmacy" and r[0][3:] == ("inquiry", I))
ok("pharmacy in unrelated region not notified", not nt(c_, "provider.inquiry"))
ok("pending (unapproved) pharmacy not notified", not nt(d_, "provider.inquiry"))
ok("customer / admin / staff get no provider.inquiry", not any(nt(x, "provider.inquiry") for x in (cid, 1, sid)))
ok("notified pharmacy actually sees the inquiry in its panel API", any(x["id"] == I for x in call("GET", "/provider/inquiries", None, pa)[1]))
ok("invalid inquiry creates no notifications", call("POST", "/medical/inquiries", {"medicine_name": "x", "region_id": 3}, cust)[0] == 400 and len(nt(a, "provider.inquiry")) == 1)
ok("notification API shows it to the pharmacy", any(i["kind"] == "provider.inquiry" for i in call("GET", "/notifications", None, pa)[1]["items"]))
# ---- المرحلة: نفس الصيدلي يملك استفسارًا خاصًا به -> لا يُشعَر بنفسه
call("POST", "/medical/inquiries", {"medicine_name": "ذاتي", "region_id": 3}, pa)
ok("a pharmacy owner's own inquiry does not notify itself", len(nt(a, "provider.inquiry")) == 1 and len(nt(b, "provider.inquiry")) == 2)
# ---- روشتة جديدة بلا توجيه تلقائي -> الإدارة والموظفون
f = call("POST", "/files", {"data": png()}, cust)[1]["id"]
s_, r = call("POST", "/medical/prescriptions", {"file_ids": [f], "region_id": 3}, cust); R = r["id"]; ok("prescription created", s_ == 201)
for who, uid in (("admin", 1), ("staff", sid)):
    r = nt(uid, "admin.rx_new"); ok(who + " notified of pending prescription", len(r) == 1 and r[0][2] == "admin:rx" and r[0][4] == R and "#%d" % R in r[0][1])
ok("customer and pharmacies get no admin.rx_new", not any(nt(x, "admin.rx_new") for x in (cid, a, b)))
# ---- مع التوجيه التلقائي: الصيدلية تُشعَر (trigger الموجود) والإدارة لا تُزعَج
assert call("POST", "/admin/rx/auto-forward", {"enabled": True}, at)[0] == 200
f2 = call("POST", "/files", {"data": png()}, cust)[1]["id"]
s_, r = call("POST", "/medical/prescriptions", {"file_ids": [f2], "region_id": 3}, cust); R2 = r["id"]
ok("auto-forward: pharmacies notified of the prescription", any(x[4] == R2 for x in nt(a, "provider.prescription")))
ok("auto-forward: admin NOT notified (nothing to forward)", not any(x[4] == R2 for x in nt(1, "admin.rx_new")))
# ---- اعتراض على طلب توصيل: الإدارة + الصيدلية صاحبة الطلب الطبي
now = int(time.time())
def order(link_provider=None):
    sql("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,fee,status,created_at,updated_at) VALUES(?,3,'p','d',10,'awaiting_confirmation',?,?)", (cid, now, now))
    o = sql("SELECT MAX(id) FROM delivery_orders")[0][0]
    if link_provider: sql("INSERT INTO medical_delivery_links(order_id,source_type,source_id,provider_id,created_at) VALUES(?,'inquiry',?,?,?)", (o, I, link_provider, now))
    return o
o1 = order(a); sql("UPDATE delivery_orders SET status='disputed' WHERE id=?", (o1,))
for who, uid in (("admin", 1), ("staff", sid)):
    r = nt(uid, "admin.order_dispute"); ok(who + " notified of order dispute", len(r) == 1 and r[0][2] == "admin:orders" and r[0][4] == o1 and str(o1) in r[0][1])
r = nt(a, "provider.order_dispute"); ok("pharmacy of the medical order notified", len(r) == 1 and r[0][2] == "pharmacy" and r[0][4] == o1)
ok("other pharmacies not notified", not nt(b, "provider.order_dispute") and not nt(c_, "provider.order_dispute"))
sql("UPDATE delivery_orders SET status='disputed',updated_at=updated_at+1 WHERE id=?", (o1,))
ok("re-setting same status does not duplicate", len(nt(1, "admin.order_dispute")) == 1 and len(nt(a, "provider.order_dispute")) == 1)
o2 = order(); sql("UPDATE delivery_orders SET status='disputed' WHERE id=?", (o2,))
ok("non-medical order: admin notified, no pharmacy", len(nt(1, "admin.order_dispute")) == 2 and len(nt(a, "provider.order_dispute")) == 1)
o3 = order(a); sql("UPDATE delivery_orders SET status='completed' WHERE id=?", (o3,))
ok("non-dispute status change sends no dispute notice", len(nt(1, "admin.order_dispute")) == 2)
# ---- عبر الـAPI الحقيقي: اعتراض العميل
sql("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,fee,status,created_at,updated_at) VALUES(?,3,'p','d',10,'awaiting_confirmation',?,?)", (cid, now, now))
o4 = sql("SELECT MAX(id) FROM delivery_orders")[0][0]; sql("INSERT INTO medical_delivery_links(order_id,source_type,source_id,provider_id,created_at) VALUES(?,'inquiry',?,?,?)", (o4, I, b, now))
s_, r = call("POST", "/delivery/orders/%d/dispute" % o4, {"reason": "لم أستلم الطلب فعليا"}, cust)
ok("customer dispute via API succeeds", s_ == 200 and r.get("status") == "disputed")
ok("API dispute notified admin and the order's pharmacy", any(x[4] == o4 for x in nt(1, "admin.order_dispute")) and any(x[4] == o4 for x in nt(b, "provider.order_dispute")))
# ---- أمان: فشل الإشعار لا يُفشل العملية
c = sqlite3.connect(DB); c.execute("DROP TABLE notifications"); c.commit(); c.close()
s_, r = call("POST", "/medical/inquiries", {"medicine_name": "بلا جدول", "region_id": 3}, cust)
ok("inquiry still created when notifications table is gone", s_ == 201 or s_ == 500 and False)
print("ALL PASS")
