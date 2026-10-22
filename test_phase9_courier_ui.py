# يشغّل سكربت static/courier.html الحقيقي داخل node (DOM وهمي) على خادم حقيقي. ليس اختبار متصفح ولا يفحص CSS/التخطيط.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs, fare_ok
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8776; BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def ui(token, steps):
    r = subprocess.run(["node", os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_harness.js"), BASE, token, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    if r.returncode: print(r.stderr[:500])
    return json.loads(r.stdout)
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cr, cu = user("01011111111"), user("01012345678")
cid = call("GET", "/me", None, cr)[1]["id"]
apply_docs(call, cr); call("POST", f"/admin/couriers/{cid}/review", {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 5}, at)
evil = '<img src=x onerror=alert(1)>'
oid = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": evil + "pick", "dropoff_text": "dropoff-addr", "details": "d"}, cu)[1]["id"]
# 1) not logged in / not courier
ok("no token shows login prompt", "تسجيل دخول المندوب" in ui("", [])["final"])
ok("non-courier gets error card, no crash", "card" in ui(cu, [])["final"])
# 2) topup via UI: validation error then success; courier has 0 balance so accept must fail first
r = ui(cr, [{"call": "acc", "args": [oid], "snap": "a"}])
ok("accept with zero balance -> alert from server", len(r["alerts"]) == 1)
r = ui(cr, [{"set": {"ta": "100", "tr": "ab"}, "call": "topup"}])
ok("short topup ref rejected, alert shown", len(r["alerts"]) == 1)
r = ui(cr, [{"set": {"ta": "100", "tr": "REF0001"}, "call": "topup", "snap": "t"}])
ok("topup submitted and shown as pending", "قيد المراجعة" in r["t"] and "REF0001" in r["t"])
tid = call("GET", "/admin/topups", None, at)[1][0]["id"]; call("POST", f"/admin/topups/{tid}/review", {"status": "approved"}, at)
r = ui(cr, [{"snap": "w"}])
ok("approved topup updates balance and wallet history", "100 ج" in r["w"] and "شحن" in r["w"] and "تمت الموافقة" in r["w"])
ok("available order shown with accept button, pickup text escaped", f"acc({oid})" in r["w"] and evil not in r["w"])
# 3) accept -> order card with addresses, escaped
r = ui(cr, [{"call": "acc", "args": [oid], "snap": "acc"}])
ok("accepted order appears in current orders with addresses", "طلباتي الحالية" in r["acc"] and "dropoff-addr" in r["acc"] and "تم قبول الطلب" in r["acc"])
ok("user text is HTML-escaped (no raw tag injected)", evil not in r["acc"] and "&lt;img" in r["acc"])
ok("accept order: fare box (default + limits) and release; no start button before customer approval", "fare(%d)" % oid in r["acc"] and "adv(%d" % oid not in r["acc"] and f"rel({oid})" in r["acc"])
# 4) release declined then accepted via UI
r = ui(cr, [{"call": "acc", "args": [oid]}, {"confirm": False, "call": "rel", "args": [oid], "snap": "keep"}])
ok("release cancelled by confirm keeps order", call("GET", "/courier/orders", None, cr)[1][0]["status"] == "assigned")
# 5) full step flow via UI buttons (بعد موافقة العميل على الأجرة)
fare_ok(oid)
for to in ("heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"):
    r = ui(cr, [{"call": "adv", "args": [oid, to], "snap": "s"}])
    ok("UI advance -> " + to, call("GET", "/courier/orders", None, cr)[1][0]["status"] == to and not r["alerts"])
ok("awaiting confirmation: no advance/release buttons, waiting text", "بانتظار تأكيد العميل" in r["s"] and "hov(" in r["s"] and "adv(" not in r["s"] and "rel(" not in r["s"])
ok("illegal jump via UI is rejected by server (alert)", len(ui(cr, [{"call": "adv", "args": [oid, "picked_up"]}])["alerts"]) == 1)
call("POST", f"/delivery/orders/{oid}/confirm", None, cu)
r = ui(cr, [{"snap": "end"}])
ok("completed order moves to history; commission -5 in wallet; balance 95", "آخر طلباتي المنتهية" in r["end"] and "مكتمل" in r["end"] and "-5" in r["end"] and "95 ج" in r["end"])
# 6) release flow via UI returns order to searching
o2 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, cu)[1]["id"]
r = ui(cr, [{"call": "acc", "args": [o2]}, {"confirm": True, "call": "rel", "args": [o2], "snap": "r"}])
ok("release via UI returns order to searching", call("GET", "/delivery/orders", None, cu)[1][0]["status"] == "searching" and f"acc({o2})" in r["r"])
ok("single commission entry overall", sqlite3.connect(os.environ["LAQINO_DB"]).execute("select count(*) from wallet_entries where kind='commission'").fetchone()[0] == 1)
print("ALL PASSED")
