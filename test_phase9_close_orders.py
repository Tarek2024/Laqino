# البند 3: إغلاق الطلبات العالقة — اعتراض العميل، إكمال/إلغاء إداري، مهلة تأكيد تلقائي، عكس عمولة، ومنع تكرار الخصم.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import fare_ok
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8777), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8777/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
q = lambda sql, *a: sqlite3.connect(DB).execute(sql, a).fetchall()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cr, cu, cu2 = user("01011111111"), user("01012345678"), user("01033333333")
cid = call("GET", "/me", None, cr)[1]["id"]
apply_docs(call, cr); call("POST", f"/admin/couriers/{cid}/review", {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
call("POST", "/courier/topups", {"amount": 500, "transfer_ref": "REF0001"}, cr); call("POST", f"/admin/topups/{call('GET', '/admin/topups', None, at)[1][0]['id']}/review", {"status": "approved"}, at)
bal = lambda: call("GET", "/courier/wallet", None, cr)[1]["balance"]
def awaiting():
    o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cu)[1]["id"]
    assert call("POST", f"/courier/orders/{o}/accept", None, cr)[0] == 200
    fare_ok(o)
    for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): assert call("POST", f"/courier/orders/{o}/status", {"to": to}, cr)[0] == 200
    return o
status = lambda o: q("select status from delivery_orders where id=?", o)[0][0]
comm = lambda o, kind="commission": q("select count(*),coalesce(sum(amount),0) from wallet_entries where kind=? and ref_type='order' and ref_id=?", kind, o)[0]
def backdate(o, secs):
    c = sqlite3.connect(DB); c.execute("update delivery_orders set updated_at=updated_at-? where id=?", (secs, o)); c.commit(); c.close()

# --- إعداد المهلة
ok("auto-confirm setting: admin only", call("POST", "/admin/settings/auto-confirm", {"hours": 1}, cu)[0] == 403)
ok("auto-confirm setting rejects 0 / 1000 / text", all(call("POST", "/admin/settings/auto-confirm", {"hours": h}, at)[0] == 400 for h in (0, 1000, "x")))
ok("auto-confirm setting accepts 1", call("POST", "/admin/settings/auto-confirm", {"hours": 1}, at) == (200, {"hours": 1}))

# --- مهلة تلقائية
o1 = awaiting(); b0 = bal()
call("GET", "/admin/orders", None, at); ok("fresh awaiting order is NOT auto-confirmed", status(o1) == "awaiting_confirmation" and comm(o1) == (1, -5.0))  # المرحلة 28: العمولة تُخصم عند التسليم
backdate(o1, 7200); call("GET", "/admin/orders", None, at)
ok("expired order auto-completes on next request", status(o1) == "completed")
ok("auto-confirm charged exactly one commission (-5)", comm(o1) == (1, -5.0) and bal() == b0)  # b0 بعد الخصم المبكر
ok("auto-confirm logged in audit and events (actor NULL)", q("select count(*) from audit_log where action='order.auto_confirm' and target=?", str(o1))[0][0] == 1 and q("select count(*) from order_events where order_id=? and to_status='completed' and actor_id is null", o1)[0][0] == 1)
for _ in range(3): call("GET", "/admin/orders", None, at)
ok("repeated sweeps do not recharge", comm(o1) == (1, -5.0))
ok("customer confirm after auto-confirm -> 409, no recharge", call("POST", f"/delivery/orders/{o1}/confirm", None, cu)[0] == 409 and comm(o1) == (1, -5.0))

# --- اعتراض العميل
o2 = awaiting()
ok("dispute needs reason", call("POST", f"/delivery/orders/{o2}/dispute", {"reason": " "}, cu)[0] == 400)
ok("other customer cannot dispute (404)", call("POST", f"/delivery/orders/{o2}/dispute", {"reason": "السبب"}, cu2)[0] == 404)
ok("dispute from wrong status -> 409", call("POST", f"/delivery/orders/{o1}/dispute", {"reason": "السبب"}, cu)[0] == 409)
ok("customer disputes awaiting order", call("POST", f"/delivery/orders/{o2}/dispute", {"reason": "لم يصلني الطلب"}, cu) == (200, {"status": "disputed"}))
backdate(o2, 999999); call("GET", "/admin/orders", None, at)
ok("disputed order is NOT auto-confirmed even when old; no commission", status(o2) == "disputed" and comm(o2) == (1, -5.0))  # خُصمت عند التسليم؛ العكس يدوي من الإدارة
ok("customer cannot confirm a disputed order", call("POST", f"/delivery/orders/{o2}/confirm", None, cu)[0] == 409)
ok("courier cannot move a disputed order", call("POST", f"/courier/orders/{o2}/status", {"to": "completed"}, cr)[0] == 409)
lst = [x for x in call("GET", "/admin/orders?status=disputed", None, at)[1] if x["id"] == o2]
ok("admin list shows dispute reason", len(lst) == 1 and "لم يصلني" in (lst[0]["dispute"] or ""))
ok("admin complete: reason required, admin only", call("POST", f"/admin/orders/{o2}/complete", {}, at)[0] == 400 and call("POST", f"/admin/orders/{o2}/complete", {"reason": "تم التحقق"}, cu)[0] == 403)
b1 = bal()
ok("admin completes disputed order", call("POST", f"/admin/orders/{o2}/complete", {"reason": "تم التحقق من التسليم"}, at) == (200, {"status": "completed"}))
ok("commission charged once on admin complete", comm(o2) == (1, -5.0) and bal() == b1)  # خُصمت عند التسليم، الإكمال لا يكرر
ok("second admin complete -> 409, no recharge", call("POST", f"/admin/orders/{o2}/complete", {"reason": "مرة ثانية"}, at)[0] == 409 and comm(o2) == (1, -5.0))
ok("admin complete audited with reason", q("select count(*) from audit_log where action='order.admin_complete' and target=? and detail like '%التحقق%'", str(o2))[0][0] == 1)

# --- إكمال إداري مباشر من awaiting + رفض من حالات أخرى
o3 = awaiting()
ok("admin completes awaiting order directly", call("POST", f"/admin/orders/{o3}/complete", {"reason": "العميل لا يرد"}, at)[0] == 200 and comm(o3) == (1, -5.0))
o4 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cu)[1]["id"]
ok("admin complete on searching order -> 409", call("POST", f"/admin/orders/{o4}/complete", {"reason": "سبب"}, at)[0] == 409)
ok("admin complete on missing order -> 404", call("POST", "/admin/orders/99999/complete", {"reason": "سبب"}, at)[0] == 404)

# --- إلغاء إداري لطلب معترض عليه = لا عمولة
o5 = awaiting(); b2 = bal(); call("POST", f"/delivery/orders/{o5}/dispute", {"reason": "المنتج تالف"}, cu)
ok("admin cancels disputed order", call("POST", f"/admin/orders/{o5}/cancel", {}, at) == (200, {"status": "cancelled"}))
ok("cancelled disputed order: commission auto-reversed (phase 28), balance restored (b2 was taken after the early charge)", comm(o5, "reversal") == (1, 5.0) and bal() == b2 + 5)
ok("cancelled order cannot be completed afterwards", call("POST", f"/admin/orders/{o5}/complete", {"reason": "سبب"}, at)[0] == 409)

# --- عكس العمولة
b3 = bal()
ok("reverse: reason required, admin only", call("POST", f"/admin/orders/{o2}/reverse-commission", {}, at)[0] == 400 and call("POST", f"/admin/orders/{o2}/reverse-commission", {"reason": "سبب"}, cu)[0] == 403)
ok("reverse commission on completed order", call("POST", f"/admin/orders/{o2}/reverse-commission", {"reason": "خطأ في التقدير"}, at) == (200, {"reversed": 5.0}))
ok("reversal credits +5 once and restores balance", comm(o2, "reversal") == (1, 5.0) and bal() == b3 + 5)
ok("second reversal -> 409, no extra credit", call("POST", f"/admin/orders/{o2}/reverse-commission", {"reason": "مرة ثانية"}, at)[0] == 409 and comm(o2, "reversal") == (1, 5.0) and bal() == b3 + 5)
ok("reverse on cancelled / no-commission order -> 409", call("POST", f"/admin/orders/{o5}/reverse-commission", {"reason": "سبب"}, at)[0] == 409 and call("POST", f"/admin/orders/{o4}/reverse-commission", {"reason": "سبب"}, at)[0] == 409)
ok("reversal audited", q("select count(*) from audit_log where action='order.reverse_commission' and target=?", str(o2))[0][0] == 1)

# --- تزامن: تأكيد العميل + إكمال إداري + مهلة تلقائية في نفس اللحظة = عمولة واحدة
o6 = awaiting(); backdate(o6, 7200); res = []
def hit(f): res.append(f())
ts = [threading.Thread(target=hit, args=(f,)) for f in [lambda: call("POST", f"/delivery/orders/{o6}/confirm", None, cu)[0], lambda: call("POST", f"/admin/orders/{o6}/complete", {"reason": "سبب"}, at)[0]] + [lambda: call("GET", "/admin/orders", None, at)[0]] * 4]
[t.start() for t in ts]; [t.join() for t in ts]
ok("concurrent confirm/admin-complete/auto-sweep -> exactly one commission", status(o6) == "completed" and comm(o6) == (1, -5.0))
ok("no duplicate commission rows anywhere", q("select count(*) from (select ref_id from wallet_entries where kind='commission' group by ref_id having count(*)>1)")[0][0] == 0)

# --- الإحصاءات تحسب الطلبات المكتملة تلقائيًا/إداريًا
st = call("GET", "/courier/stats", None, cr)[1]
ok("courier stats count auto/admin completed orders", st["completed"] == 4)
print("ALL PASSED")
