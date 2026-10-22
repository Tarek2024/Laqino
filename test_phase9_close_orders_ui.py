# سكربتات index/admin الحقيقية داخل node (DOM وهمي) على خادم حقيقي — اعتراض العميل، الإكمال الإداري، عكس العمولة، إعداد المهلة. ليس اختبار متصفح.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import fare_ok
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8778; BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def ui(page, token, steps):
    r = subprocess.run(["node", H, page, BASE, token, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    if r.returncode: print(r.stderr[:600])
    return json.loads(r.stdout)
q = lambda sql, *a: sqlite3.connect(os.environ["LAQINO_DB"]).execute(sql, a).fetchall()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cr, cu = user("01011111111"), user("01012345678")
apply_docs(call, cr); call("POST", f"/admin/couriers/{call('GET', '/me', None, cr)[1]['id']}/review", {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
call("POST", "/courier/topups", {"amount": 500, "transfer_ref": "REF0001"}, cr); call("POST", f"/admin/topups/{call('GET', '/admin/topups', None, at)[1][0]['id']}/review", {"status": "approved"}, at)
def awaiting():
    o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cu)[1]["id"]
    call("POST", f"/courier/orders/{o}/accept", None, cr)
    fare_ok(o)
    for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"): call("POST", f"/courier/orders/{o}/status", {"to": to}, cr)
    return o
st = lambda o: q("select status from delivery_orders where id=?", o)[0][0]
cm = lambda o, k: q("select count(*),coalesce(sum(amount),0) from wallet_entries where kind=? and ref_id=?", k, o)[0]
o1 = awaiting()
# --- العميل
r = ui("index", cu, [{"js": "go(3)", "snap": "v"}])
ok("index loads without script errors", r["errs"] == [])
ok("customer sees confirm + dispute buttons and auto-confirm note", f"oa({o1},'confirm')" in r["v"] and f"dp({o1})" in r["v"] and "يتأكد تلقائيًا" in r["v"])
r = ui("index", cu, [{"prompt": "ab", "js": f"dp({o1})"}])
ok("short dispute reason in UI does not call server", st(o1) == "awaiting_confirmation")
r = ui("index", cu, [{"prompt": "<img src=x onerror=1> لم يصلني الطلب", "js": f"dp({o1})", "wait": 900}, {"js": "go(3)", "snap": "v"}])
ok("dispute through UI reaches server", st(o1) == "disputed" and r["errs"] == [])
ok("customer sees disputed label, no confirm button", "قيد مراجعة الإدارة" in r["v"] and f"oa({o1},'confirm')" not in r["v"])
# --- الإدارة
r = ui("admin", at, [{"js": "tab='orders';shell()", "snap": "v"}])
ok("admin page loads without script errors", r["errs"] == [])
ok("admin sees dispute reason, complete + cancel buttons for disputed order", "لم يصلني الطلب" in r["v"] and f"cp({o1})" in r["v"] and f"/admin/orders/{o1}/cancel" in r["v"])
ok("admin page escapes customer-written dispute text", "&lt;img" in r["v"] and "<img src=x" not in r["v"])
r = ui("admin", at, [{"prompt": "ab", "js": f"cp({o1})"}])
ok("short admin reason in UI does not call server", st(o1) == "disputed")
r = ui("admin", at, [{"prompt": "تم التحقق من التسليم", "js": f"cp({o1})", "wait": 900}, {"js": "tab='orders';shell()", "snap": "v"}])
ok("admin complete through UI: completed + one commission", st(o1) == "completed" and cm(o1, "commission") == (1, -5.0) and r["errs"] == [])
ok("completed order shows reverse-commission button, no complete button", f"rv({o1})" in r["v"] and f"cp({o1})" not in r["v"])
ok("reverse declined at confirm() does nothing", ui("admin", at, [{"prompt": "سبب", "confirm": False, "js": f"rv({o1})"}]) and cm(o1, "reversal") == (0, 0))
ui("admin", at, [{"prompt": "خطأ في التقدير", "confirm": True, "js": f"rv({o1})", "wait": 900}])
ok("reverse through UI: one reversal +5", cm(o1, "reversal") == (1, 5.0))
ui("admin", at, [{"prompt": "مرة ثانية", "confirm": True, "js": f"rv({o1})", "wait": 900}])
ok("second reverse via UI still one reversal", cm(o1, "reversal") == (1, 5.0) and cm(o1, "commission") == (1, -5.0))
# --- إعداد المهلة من الواجهة
r = ui("admin", at, [{"js": "tab='settings';shell()", "wait": 1200, "snap": "v"}])
ok("settings tab shows auto-confirm hours (default 24)", 'id="ah"' in r["v"] and 'value="24"' in r["v"] and r["errs"] == [])
ui("admin", at, [{"js": "tab='settings';shell()", "wait": 1200}, {"js": "document.getElementById('ah').value=5;document.getElementById('ah').value", "wait": 100}, {"js": "go('/admin/settings/auto-confirm',{hours:+document.getElementById('ah').value})", "wait": 900}])
ok("auto-confirm hours saved from UI", q("select value from settings where key='auto_confirm_hours'") == [("5",)])
# --- المندوب يرى حالة الاعتراض بشكل صحيح
o2 = awaiting(); call("POST", f"/delivery/orders/{o2}/dispute", {"reason": "المنتج تالف"}, cu)
r = ui("courier", cr, [{"snap": "m", "wait": 800}])
ok("courier page shows disputed order in history with its label, no action buttons", "متنازع عليه" in r["m"] and f"adv({o2}" not in r["m"] and r["errs"] == [])
print("ALL PASSED")
