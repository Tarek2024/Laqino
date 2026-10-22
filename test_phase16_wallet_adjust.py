# المرحلة 16 / المهمة 5: تعديل رصيد المندوب يدويًا من الإدارة (جدول wallet_adjustments المنفصل؛ wallet_entries لم يُمس).
import os, json, threading, urllib.request, urllib.error, tempfile, time, re, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from testutil import fare_ok
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8778), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8778/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
cust, cr, cr2 = user("01012345678"), user("01011111111"), user("01022222222")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
me = lambda t: call("GET", "/me", None, t)[1]["id"]; cid, cid2 = me(cr), me(cr2)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 8}, at)
for t in (cr, cr2): apply_docs(call, t); call("POST", f"/admin/couriers/{me(t)}/review", {"status": "approved"}, at)
q = lambda sql, *a: sqlite3.connect(os.environ["LAQINO_DB"]).execute(sql, a).fetchall()
A = lambda i: f"/admin/couriers/{i}/wallet-adjust"; adj = lambda amt, why="تسوية يدوية", i=cid, t=at, **k: call("POST", A(i), {"amount": amt, "reason": why, **k}, t)
W = lambda i=cid: call("GET", f"/admin/couriers/{i}/wallet", None, at)[1]
cw = lambda: call("GET", "/courier/wallet", None, cr)[1]
ok("table exists, wallet_entries CHECK untouched", q("select count(*) from sqlite_master where name='wallet_adjustments'")[0][0] == 1 and "'topup','commission','reversal'" in q("select sql from sqlite_master where name='wallet_entries'")[0][0])
ok("credit +50 => balance 50, in both ledgers with reason", adj(50, "هدية")[0] == 201 and W()["balance"] == 50 and cw()["balance"] == 50 and cw()["entries"][0] == {"kind": "adjustment", "amount": 50.0, "ref_type": "adjustment", "ref_id": 1, "created_at": cw()["entries"][0]["created_at"], "reason": "هدية"} and W()["entries"][0]["reason"] == "هدية")
ok("debit -20 => 30", adj(-20, "تصحيح خطأ")[0] == 201 and W()["balance"] == 30 and cw()["balance"] == 30)
ok("debit beyond available => 409, nothing written", adj(-31)[0] == 409 and W()["balance"] == 30 and q("select count(*) from wallet_adjustments")[0][0] == 2)
ok("debit exactly to zero allowed", adj(-30, "سحب كامل")[0] == 201 and W()["balance"] == 0)
for bad, why in ((0, "سبب"), ("x", "سبب"), (None, "سبب"), (100001, "سبب"), (5, ""), (5, "ab"), (5, "x" * 301), (float("nan"), "سبب")):
    r = call("POST", A(cid), {"amount": bad if bad == bad else "nan", "reason": why}, at); ok("rejected 400: amount=%r reason_len=%d" % (bad, len(why)), r[0] == 400)
ok("unknown courier => 404; plain user => 404", adj(5, i=99999)[0] == 404 and adj(5, i=me(cust))[0] == 404)
ok("customer/courier/anonymous blocked", adj(5, t=cust)[0] == 403 and adj(5, t=cr)[0] == 403 and call("POST", A(cid), {"amount": 5, "reason": "abc"})[0] == 401)
ok("no stray rows after all rejections", q("select count(*) from wallet_adjustments")[0][0] == 3)
# interaction with real flow: topup + held commission + completed order
k = call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "AJ-0001"}, cr)[1]["id"]; call("POST", f"/admin/topups/{k}/review", {"status": "approved"}, at)
oid = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cust)[1]["id"]
ok("courier accepts; 8 held", call("POST", f"/courier/orders/{oid}/accept", None, cr)[0] == 200 and W()["held"] == 8 and W()["available_balance"] == 92)
ok("cannot debit into the held commission (-93 blocked, -92 ok)", adj(-93)[0] == 409 and adj(-92, "خصم")[0] == 201 and W()["balance"] == 8 and W()["available_balance"] == 0)
ok("courier at 0 available can no longer take another order", call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "ccc", "dropoff_text": "ddd"}, cust)[0] == 201 and call("GET", "/courier/available", None, cr)[1] == [])
adj(10, "إعادة")
fare_ok(oid)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{oid}/status", {"to": to}, cr)
call("POST", f"/delivery/orders/{oid}/confirm", None, cust)
ok("commission still charged exactly once; balance = topup100 + adj(50-20-30-92+10) - 8", len(q("select 1 from wallet_entries where kind='commission'")) == 1 and cw()["balance"] == 100 + (50 - 20 - 30 - 92 + 10) - 8)
ok("admin sees the same balance as the courier", W()["balance"] == cw()["balance"])
ok("idempotent request_key: same key twice => one row, duplicate flag", (lambda a, b: a[0] == 201 and b[0] == 200 and b[1].get("duplicate") and q("select count(*) from wallet_adjustments where request_key='k1'")[0][0] == 1)(adj(5, "مرة", request_key="k1"), adj(5, "مرة", request_key="k1")))
ok("other courier unaffected", W(cid2)["balance"] == 0)
ok("adjustments audited with reason and amount", any(x["action"] == "wallet.adjust" and "هدية" in x["detail"] and '"amount": 50.0' in x["detail"] for x in call("GET", "/admin/audit", None, at)[1]))
ok("report: topups_credited excludes adjustments (still 100)", call("GET", "/admin/reports", None, at)[1]["topups_credited"] == 100)
net = q("select sum(amount) from wallet_adjustments")[0][0]; ok("report adjustments_net equals the table sum", abs(call("GET", "/admin/reports", None, at)[1]["adjustments_net"] - net) < 1e-9)
r = adj(10.126, "تقريب"); ok("amount rounded to 2 decimals", r[0] == 201 and r[1]["amount"] == 10.13)
d = os.path.dirname(os.path.abspath(__file__)); rd = lambda *p: open(os.path.join(d, *p), encoding="utf-8").read()
ok("admin UI: adjust form, confirm dialog, esc() for reason", all(x in rd("static", "admin.html") for x in ("window.cwa=", "wallet-adjust", "تنفيذ التعديل", "esc(e.reason")))
ok("courier UI shows adjustment with escaped reason", "adjustment:'تعديل من الإدارة'" in rd("static", "courier.html") and "esc(e.reason)" in rd("static", "courier.html"))
ok("service worker version >=v21", int(re.search(r"laqino-v(\d+)", rd("static", "sw.js")).group(1)) >= 21)
print("ALL OK")
