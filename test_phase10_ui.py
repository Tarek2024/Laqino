# المرحلة 10 (واجهات): تشغيل سكربتات الصفحات الحقيقية في node على DOM وهمي ضد الخادم الفعلي. ليست اختبار متصفح ولا عرضًا بصريًا.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(); os.environ["LAQINO_TEST_PRESENCE"] = "1"
import server
from testutil import fare_ok
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8780), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8780"; H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def page(pg, tok, steps):
    o = subprocess.run(["node", H, pg, BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); assert o.returncode == 0, o.stderr
    return json.loads(o.stdout)
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cr, cu = user("01011111111"), user("01012345678"); ci = call("GET", "/me", None, cr)[1]["id"]; apply_docs(call, cr); call("POST", f"/admin/couriers/{ci}/review", {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
call("POST", "/courier/topups", {"amount": 100, "transfer_ref": "REFUI01"}, cr); call("POST", f"/admin/topups/{call('GET', '/admin/topups', None, at)[1][0]['id']}/review", {"status": "approved"}, at)
sp = call("POST", "/admin/specialties", {"name_ar": "أطفال"}, at)[1]["id"]
d = call("POST", "/admin/doctors", {"name_ar": "د. أحمد محمود", "specialty_id": sp, "region_id": 3, "clinic_name": "عيادة النور", "address": "شارع البحر", "phone": "0473123456", "schedule": "السبت 5-9"}, at)[1]["id"]
call("POST", f"/admin/doctors/{d}/publish", {"published": True}, at)

# --- الإدارة
r = page("admin", at, [{"js": "tab='doctors';shell()", "snap": "v", "wait": 1200}]); ok("admin doctors tab: no script errors, shows specialty+doctor+forms", not r["errs"] and "أطفال" in r["v"] and "أحمد محمود" in r["v"] and "إضافة تخصص" in r["v"] and "إخفاء" in r["v"])
r = page("admin", at, [{"js": "tab='dispatch';shell()", "snap": "v", "wait": 1200}]); ok("admin dispatch tab: settings + couriers + log", not r["errs"] and ("مهل توزيع طلبات الدليفري" in r["v"] or "مهل التوزيع" in r["v"]) and "المندوبون المعتمدون" in r["v"] and "غير متصل" in r["v"])
# --- العميل: البحث عن طبيب
r = page("index", cu, [{"js": "mt='dr';go(4)", "snap": "v", "wait": 1000}, {"js": "document.getElementById('dq').value='احمد';dsr()", "snap": "dres", "wait": 800}, {"js": "document.getElementById('dq').value='زيدان';dsr()", "snap": "dres", "wait": 800}])
ok("customer medical tab shows doctor search", not r["errs"] and "ابحث عن طبيب" in r["v"])
r1 = page("index", cu, [{"js": "go(4)", "wait": 800}, {"js": "document.getElementById('dq').value='احمد';dsr()", "snap": "dres", "wait": 800}]); ok("name search renders result", "أحمد محمود" in r1["dres"] and "عيادة النور" in r1["dres"])
r2 = page("index", cu, [{"js": "go(4)", "wait": 800}, {"js": "document.getElementById('dq').value='زيدان';dsr()", "snap": "dres", "wait": 800}]); ok("no match -> clear message, no invented results", "لا يوجد أطباء منشورون" in r2["dres"] and "أحمد" not in r2["dres"])
r3 = page("index", cu, [{"js": f"go(4)", "wait": 800}, {"js": f"document.getElementById('dq').value='احمد';dsr()", "wait": 600}, {"js": f"dv({d})", "snap": "dres", "wait": 800}]); ok("detail view shows address, schedule and a reveal button, but no number yet", "شارع البحر" in r3["dres"] and "السبت 5-9" in r3["dres"] and "tel:" not in r3["dres"] and "عرض رقم التواصل" in r3["dres"] and not r3["errs"])
r3b = page("index", cu, [{"js": f"go(4)", "wait": 800}, {"js": f"document.getElementById('dq').value='احمد';dsr()", "wait": 600}, {"js": f"dv({d})", "wait": 800}, {"js": f"dct({d})", "snap": "dco", "wait": 800}]); ok("reveal shows the call link", "tel:0473123456" in r3b["dco"] and not r3b["errs"])
# --- العميل: طلب دليفري ورمز
oid = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb", "request_key": "ui1"}, cu)[1]["id"]
r = page("index", cu, [{"js": "go(3)", "snap": "v", "wait": 1000}]); ok("customer sees order, status 'searching', no code yet", "#%d" % oid in r["v"] and "بنبحث عن مندوب" in r["v"] and "رمز التسليم" not in r["v"] and not r["errs"])
# --- المندوب
r = page("courier", cr, [{"js": "load()", "snap": "m", "wait": 800}]); ok("courier page offline by default with connect button", "غير متصل" in r["m"] and "اتصل بالشبكة" in r["m"])
r = page("courier", cr, [{"js": "setOn(true)", "snap": "m", "wait": 1200}]); ok("after connect: online, offer shown with accept/reject, no address", "متصل" in r["m"] and "acc(%d)" % oid in r["m"] and "rej(%d)" % oid in r["m"] and "aaa" not in r["m"] and not r["errs"])
r = page("courier", cr, [{"js": f"acc({oid})", "snap": "m", "wait": 1200}]); ok("accept via UI shows order with addresses and next step", "aaa" in r["m"] and "bbb" in r["m"] and "fare(%d)" % oid in r["m"] and "heading_pickup" not in r["m"])
fare_ok(oid)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{oid}/status", {"to": to}, cr)
code = call("GET", "/delivery/orders", None, cu)[1][0]["delivery_code"]
r = page("index", cu, [{"js": "go(3)", "snap": "v", "wait": 1000}]); ok("customer UI shows delivery code during handover", code in r["v"])
r = page("courier", cr, [{"js": "load()", "snap": "m", "wait": 800}]); ok("courier UI offers handover input, never shows the code", "hov(%d)" % oid in r["m"] and code not in r["m"])
print("ALL OK")
