# البند 5: ربط الطبي بالدليفري — طلب توصيل من رد صيدلية (استعلام أو روشتة) بدون كشف اسم الدواء/الروشتة للمندوب.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, base64, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import fare_ok
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8780; BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
import sqlite3 as _sq3
_call = call
def call(m, p, *a, **k):  # الخطوة 4: رد الصيدلية يلزمه اعتماد الإدارة قبل أن يراه العميل؛ هذا الاختبار يفترض أن الإدارة اعتمدت كل الردود (الاعتماد نفسه في test_step4_rx.py)
    if (m == "GET" and p.startswith("/medical/prescriptions")) or p == "/medical/delivery":
        _c = _sq3.connect(os.environ["LAQINO_DB"]); _c.execute("UPDATE prescription_responses SET review='approved' WHERE review='pending'"); _c.commit(); _c.close()
    return _call(m, p, *a, **k)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def ui(page, token, steps):
    r = subprocess.run(["node", H, page, BASE, token, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    if r.returncode: print(r.stderr[:600])
    return json.loads(r.stdout)
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
P1, P2, CU, CU2, CR = "01011110001", "01011110002", "01011110003", "01011110004", "01011110005"
tk = {p: user(p) for p in (P1, P2, CU, CU2, CR)}; uid = lambda p: call("GET", "/me", None, tk[p])[1]["id"]
for p, n, a in ((P1, "صيدلية الأمل", "شارع النيل 5"), (P2, "صيدلية النور", None)):
    call("POST", "/providers/apply", {"name_ar": n, "region_id": 3, "address": a}, tk[p]); call("POST", f"/admin/providers/{uid(p)}/review", {"status": "approved"}, at)
apply_docs(call, tk[CR]); call("POST", f"/admin/couriers/{uid(CR)}/review", {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF0001"}, tk[CR]); call("POST", f"/admin/topups/{call('GET', '/admin/topups', None, at)[1][0]['id']}/review", {"status": "approved"}, at)
MED = "دواءحساس123"; NOTE = "ملاحظةسرية456"
inq = call("POST", "/medical/inquiries", {"medicine_name": MED, "note": NOTE, "region_id": 3}, tk[CU])[1]["id"]
resp = lambda i, p, st, pr=None: call("POST", f"/provider/inquiries/{i}/respond", {"status": st, **({"price": pr} if pr else {})}, tk[p])
call("POST", "/medical/inquiries", {"medicine_name": "x" * 5, "region_id": 3}, tk[CU])
dl = lambda src, sid, pid, to="شارع الجمهورية 10", t=None, st="inquiry": call("POST", "/medical/delivery", {"source_type": st, "source_id": sid, "provider_id": pid, "dropoff_text": to}, tk[t or CU])
rows = lambda: call("GET", "/medical/inquiries", None, tk[CU])[1]
# ---------- التحقق والصلاحيات
resp(inq, P1, "needs_confirmation"); resp(inq, P2, "unavailable")
ok("customer sees provider_id and no delivery yet", all("provider_id" in x and x["delivery_order_id"] is None for x in rows()[-1]["responses"]) if False else all("provider_id" in x and x["delivery_order_id"] is None for x in [r for r in rows() if r["id"] == inq][0]["responses"]))
ok("requires login", call("POST", "/medical/delivery", {})[0] == 401)
ok("bad source type / missing address / non-numeric ids -> 400", dl("x", inq, uid(P1), st="x")[0] == 400 and dl(0, inq, uid(P1), to="a")[0] == 400 and dl(0, "abc", uid(P1))[0] == 400)
ok("another customer cannot order from my inquiry (404)", dl(0, inq, uid(P1), t=CU2)[0] == 404)
ok("no response from that pharmacy -> 404", call("POST", "/medical/delivery", {"source_type": "inquiry", "source_id": inq, "provider_id": 99999, "dropoff_text": "عنوان طويل"}, tk[CU])[0] in (404, 409))
ok("needs_confirmation answer -> 409", dl(0, inq, uid(P1))[0] == 409)
ok("unavailable answer -> 409", dl(0, inq, uid(P2))[0] == 409)
resp(inq, P1, "available", 77)
# ---------- طلب ناجح + خصوصية المندوب
st, o = dl(0, inq, uid(P1)); oid = o["id"]
ok("available + fresh answer -> order created with reference, no price exposed", st == 201 and "fee" not in o and o["reference"] == f"M{inq}" and o["status"] == "searching")
order = [x for x in call("GET", "/delivery/orders", None, tk[CU])[1] if x["id"] == oid][0]
ok("order pickup = pharmacy name + address, dropoff = customer address", "صيدلية الأمل" in order["pickup_text"] and "شارع النيل 5" in order["pickup_text"] and order["dropoff_text"] == "شارع الجمهورية 10")
call("POST", f"/courier/orders/{oid}/accept", None, tk[CR])
courier_view = json.dumps([call("GET", "/courier/available", None, tk[CR])[1], call("GET", "/courier/orders", None, tk[CR])[1]], ensure_ascii=False)
ok("courier sees the reference but NEVER the medicine name or customer note", f"المرجع M{inq}" in courier_view and MED not in courier_view and NOTE not in courier_view)
ok("customer response row now shows the live delivery order", [x for x in [r for r in rows() if r["id"] == inq][0]["responses"] if x["provider_id"] == uid(P1)][0]["delivery_order_id"] == oid)
ok("duplicate request for same answer -> 409", dl(0, inq, uid(P1))[0] == 409)
# ---------- صيدلية: ترى الطلب بدون هوية العميل
pd = call("GET", "/provider/deliveries", None, tk[P1])[1]
ok("pharmacy sees reference, medicine, status, courier name (active); no customer identity", len(pd) == 1 and pd[0]["source_id"] == inq and pd[0]["medicine_name"] == MED and pd[0]["courier_name"] == "u05" and "u03" not in json.dumps(pd) and CU not in json.dumps(pd))
ok("other pharmacy sees nothing; customer/courier are forbidden", call("GET", "/provider/deliveries", None, tk[P2])[1] == [] and call("GET", "/provider/deliveries", None, tk[CU])[0] == 403 and call("GET", "/provider/deliveries", None, tk[CR])[0] == 403)
# ---------- دورة كاملة: عمولة واحدة
fare_ok(oid)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{oid}/status", {"to": to}, tk[CR])
call("POST", f"/delivery/orders/{oid}/confirm", None, tk[CU]); call("POST", f"/delivery/orders/{oid}/confirm", None, tk[CU])
ok("medical order completes with exactly one commission (-4)", sql("select count(*),sum(amount) from wallet_entries where kind='commission' and ref_id=?", oid)[0] == (1, -4.0))
ok("pharmacy sees completed, courier name hidden after end", call("GET", "/provider/deliveries", None, tk[P1])[1][0]["status"] == "completed" and call("GET", "/provider/deliveries", None, tk[P1])[1][0]["courier_name"] is None)
ok("completed delivery still blocks a second order for same answer", dl(0, inq, uid(P1))[0] == 409)
# ---------- إلغاء ثم إعادة الطلب + سباق
inq2 = call("POST", "/medical/inquiries", {"medicine_name": "دواء2", "region_id": 3}, tk[CU])[1]["id"]; resp(inq2, P1, "available", 10)
oid2 = dl(0, inq2, uid(P1))[1]["id"]; call("POST", f"/delivery/orders/{oid2}/cancel", None, tk[CU])
ok("after cancel the response shows no live delivery", [x for x in [r for r in rows() if r["id"] == inq2][0]["responses"]][0]["delivery_order_id"] is None)
res = []
def hit(): res.append(dl(0, inq2, uid(P1))[0])
ts = [threading.Thread(target=hit) for _ in range(6)]; [t.start() for t in ts]; [t.join() for t in ts]
ok("re-order after cancel works; 6 concurrent requests create exactly one order", sorted(res) == [201] + [409] * 5 and sql("select count(*) from medical_delivery_links l join delivery_orders o on o.id=l.order_id where l.source_id=? and l.source_type='inquiry' and o.status!='cancelled'", inq2)[0][0] == 1)
# ---------- ردود قديمة / صيدلية موقوفة / استعلام ملغي / منطقة بلا رسوم
inq3 = call("POST", "/medical/inquiries", {"medicine_name": "دواء3", "region_id": 3}, tk[CU])[1]["id"]; resp(inq3, P1, "available", 10)
sql("update inquiry_responses set updated_at=updated_at-100000 where inquiry_id=?", inq3)
ok("stale pharmacy answer (>24h) -> 409", dl(0, inq3, uid(P1))[0] == 409)
resp(inq3, P1, "available", 10)
sql("update providers set status='suspended' where user_id=?", uid(P1)); r1 = dl(0, inq3, uid(P1))[0]; sql("update providers set status='approved' where user_id=?", uid(P1))
ok("suspended pharmacy -> 409", r1 == 409)
fee = sql("select fee from region_fees where region_id=3")[0][0]; sql("delete from region_fees where region_id=3"); r2 = dl(0, inq3, uid(P1))[0]; sql("insert into region_fees(region_id,fee) values(3,?)", fee)
ok("pharmacy region without delivery fee -> 400", r2 == 400)
call("POST", f"/medical/inquiries/{inq3}/cancel", None, tk[CU])
ok("cancelled inquiry -> 409", dl(0, inq3, uid(P1))[0] == 409)
# ---------- روشتة
png = __import__("imgutil").png(); fid = call("POST", "/files", {"data": png}, tk[CU])[1]["id"]
rx = call("POST", "/medical/prescriptions", {"file_id": fid, "region_id": 3, "note": NOTE}, tk[CU])[1]["id"]
ok("prescription: pharmacy without access cannot answer, so cannot be ordered from", call("POST", f"/provider/prescriptions/{rx}/respond", {"status": "available", "price": 5}, tk[P1])[0] == 404 and dl(0, rx, uid(P1), st="prescription")[0] == 404)
call("POST", f"/admin/prescriptions/{rx}/forward", {"provider_id": uid(P1)}, at)
ok("forwarded but unanswered -> 404", dl(0, rx, uid(P1), st="prescription")[0] == 404)
call("POST", f"/provider/prescriptions/{rx}/respond", {"status": "available", "price": 210}, tk[P1])
ok("another customer cannot order from my prescription (404)", dl(0, rx, uid(P1), st="prescription", t=CU2)[0] == 404)
st, o3 = dl(0, rx, uid(P1), st="prescription")
ok("prescription order created with reference R<id>", st == 201 and o3["reference"] == f"R{rx}")
call("POST", f"/courier/orders/{o3['id']}/accept", None, tk[CR])
cv = json.dumps([call("GET", "/courier/orders", None, tk[CR])[1]], ensure_ascii=False)
ok("courier never gets file id, note or prescription details", f"R{rx}" in cv and NOTE not in cv and "file" not in cv)
pd = [x for x in call("GET", "/provider/deliveries", None, tk[P1])[1] if x["order_id"] == o3["id"]][0]
ok("pharmacy delivery list marks prescription orders without leaking customer", pd["source_type"] == "prescription" and pd["medicine_name"] is None and CU not in json.dumps(pd))
rx2 = call("POST", "/medical/prescriptions", {"file_id": call("POST", "/files", {"data": png}, tk[CU])[1]["id"], "region_id": 3}, tk[CU])[1]["id"]
call("POST", f"/admin/prescriptions/{rx2}/forward", {"provider_id": uid(P1)}, at); call("POST", f"/provider/prescriptions/{rx2}/respond", {"status": "available", "price": 9}, tk[P1])
sql("delete from prescription_access where prescription_id=?", rx2)
ok("access revoked -> 409", dl(0, rx2, uid(P1), st="prescription")[0] == 409)
sql("update prescriptions set status='closed' where id=?", rx2); sql("insert or ignore into prescription_access values(?,?)", rx2, uid(P1))
ok("closed prescription -> 409", dl(0, rx2, uid(P1), st="prescription")[0] == 409)
ok("prescription access still private (courier cannot read file)", call("GET", f"/files/{fid}", None, tk[CR])[0] in (403, 404))
# ---------- الواجهات (سكربتات حقيقية في node، ليس متصفحًا)
inq4 = call("POST", "/medical/inquiries", {"medicine_name": "دواء4", "region_id": 3}, tk[CU])[1]["id"]; resp(inq4, P1, "available", 15)
r = ui("index", tk[CU], [{"js": "go(4)", "wait": 900}, {"js": f"mo('i',{inq4})", "wait": 900, "snap": "v"}])
ok("index medical tab (request details): delivery button on fresh available answer", f"md('inquiry',{inq4},{uid(P1)})" in r["v"] and r["errs"] == [])
r = ui("index", tk[CU], [{"prompt": "ab", "js": f"md('inquiry',{inq4},{uid(P1)})"}])
ok("short address in UI creates nothing", sql("select count(*) from medical_delivery_links where source_id=? and source_type='inquiry'", inq4)[0][0] == 0)
r = ui("index", tk[CU], [{"prompt": "شارع التحرير 3 الدور الثاني", "js": f"md('inquiry',{inq4},{uid(P1)})", "wait": 1200}, {"js": "go(4)", "wait": 900}, {"js": f"mo('i',{inq4})", "wait": 900, "snap": "v"}])
ok("UI creates the order; tab then shows it instead of the button", sql("select count(*) from medical_delivery_links where source_id=? and source_type='inquiry'", inq4)[0][0] == 1 and f"md('inquiry',{inq4}" not in r["v"] and "تم طلب التوصيل" in r["v"])
r = ui("pharmacy", tk[P1], [{"snap": "m", "wait": 900}])
ok("pharmacy page lists delivery refs with medicine, no customer identity", f"M{inq4}" in r["m"] and "دواء4" in r["m"] and "طلبات توصيل من عملاء" in r["m"] and r["errs"] == [] and CU not in r["m"])
print("ALL PASSED")
