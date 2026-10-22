# index/courier الحقيقية داخل node (DOM وهمي) على خادم حقيقي — منطقة الطلب للمندوب قبل القبول، روابط الصيدلية، نص الرئيسية. ليس اختبار متصفح.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8780; BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def ui(page, token, steps):
    r = subprocess.run(["node", H, page, BASE, token, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    if r.returncode: print(r.stderr[:600])
    return json.loads(r.stdout)
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
vil = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "v1", "name_ar": "قرية السلام", "is_active": True}, at)[1]["id"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 15}, at); call("POST", "/admin/region-fees", {"region_id": vil, "fee": 25}, at)
cu, co = user("01022222222", "عميل"), user("01044444444", "مندوب")
apply_docs(call, co); call("POST", f"/admin/couriers/{call('GET', '/me', None, co)[1]['id']}/review", {"status": "approved"}, at)
call("POST", "/delivery/orders", {"region_id": vil, "pickup_text": "المخبز السري", "dropoff_text": "منزل العميل", "details": "تفاصيل خاصة"}, cu)
# medical delivery order (pharmacy in the markaz)
pt = user("01011111111", "صيدلي"); call("POST", "/providers/apply", {"name_ar": "صيدلية النور", "region_id": 3}, pt)
pid = call("GET", "/me", None, pt)[1]["id"]; call("POST", f"/admin/providers/{pid}/review", {"status": "approved"}, at)
iid = call("POST", "/medical/inquiries", {"medicine_name": "دواء-خاص", "region_id": 3}, cu)[1]["id"]
call("POST", f"/provider/inquiries/{iid}/respond", {"status": "available", "price": 10}, pt)
call("POST", "/medical/delivery", {"source_type": "inquiry", "source_id": iid, "provider_id": pid, "dropoff_text": "منزل العميل بالتفصيل"}, cu)
av = call("GET", "/courier/available", None, co)[1]
ok("two open orders offered to the courier", len(av) == 2)
ok("offer fields: region name added, no addresses/details/customer", all(set(x) == {"id", "region_id", "region_name", "offer_fee", "created_at", "expires_in", "taken"} for x in av))
ok("village order shows the village name", any(x["region_name"] == "قرية السلام" for x in av))
raw = json.dumps(av, ensure_ascii=False)
ok("no pickup text, medicine, pharmacy name or reference leaks before accept", not any(w in raw for w in ("المخبز", "دواء-خاص", "صيدلية", "تفاصيل", "منزل", "M1")))
r = ui("courier", co, [{"js": "load()", "wait": 900, "snap": "m"}])
ok("courier page loads without errors", r["errs"] == [])
ok("courier page shows region name and the 'addresses after accepting' note", "قرية السلام" in r["m"] and "العناوين تظهر بعد القبول" in r["m"])
ok("courier page still hides pickup/dropoff text of offers", "المخبز" not in r["m"] and "منزل" not in r["m"])
oid = [x["id"] for x in av if x["region_name"] == "قرية السلام"][0]
ok("accepting works as before", call("POST", f"/courier/orders/{oid}/accept", None, co)[0] == 200)
mine = call("GET", "/courier/orders", None, co)[1]
ok("addresses appear after accept", mine[0]["pickup_text"] == "المخبز السري" and mine[0]["dropoff_text"] == "منزل العميل")
# links and home text
r = ui("index", cu, [{"js": "go(0)", "wait": 900, "snap": "v"}, {"js": "go(4)", "wait": 900, "snap": "v", "as": "med"}])
ok("index loads without errors", r["errs"] == [])
home = ui("index", cu, [{"js": "go(0)", "wait": 900, "snap": "v"}])["v"]
ok("home links to the pharmacy page", 'href="/pharmacy.html"' in home)
ok("home no longer says medical section is 'being prepared', and shows no placeholder services tile when no provider exists", "الأقسام الطبية" not in home and "الخدمات المنزلية" not in home)
med = ui("index", cu, [{"js": "go(4)", "wait": 900, "snap": "v"}])["v"]
ok("medical tab links to the pharmacy page", 'href="/pharmacy.html"' in med)
with urllib.request.urlopen(BASE + "/pharmacy.html") as x: ok("pharmacy page is served", x.status == 200 and "لوحة الصيدلية" in x.read().decode())
print("ALL PASSED")
