import os, json, threading, urllib.request, urllib.error, tempfile, time, base64
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8767), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8767/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 15}, at)
cu, other = user("01022222222", "عميل"), user("01022222223", "آخر")
# --- delivery orders: 5 open
ids = []
for i in range(5):
    st, r = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "المخبز", "dropoff_text": "البيت"}, cu); ids.append(r.get("id")); ok("order %d allowed" % (i + 1), st == 201)
st, r = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "المخبز", "dropoff_text": "البيت"}, cu)
ok("6th open order -> 429", st == 429)
ok("another customer unaffected", call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "المخبز", "dropoff_text": "البيت"}, other)[0] == 201)
ok("cancelling one frees a slot", call("POST", f"/delivery/orders/{ids[0]}/cancel", {}, cu)[0] == 200 and call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "المخبز", "dropoff_text": "البيت"}, cu)[0] == 201)
# --- the same cap covers pharmacy delivery
t = user("01011111111", "صيدلي"); call("POST", "/providers/apply", {"name_ar": "صيدلية المركز", "region_id": 3}, t)
pid = call("GET", "/me", None, t)[1]["id"]; call("POST", f"/admin/providers/{pid}/review", {"status": "approved"}, at)
st, r = call("POST", "/medical/inquiries", {"medicine_name": "drug-A", "region_id": 3}, cu); iid = r["id"]
call("POST", f"/provider/inquiries/{iid}/respond", {"status": "available", "price": 10}, t)
dv = {"source_type": "inquiry", "source_id": iid, "provider_id": pid, "dropoff_text": "البيت بالتفصيل"}
ok("pharmacy delivery blocked by the shared open-order cap", call("POST", "/medical/delivery", dv, cu)[0] == 429)
ok("...and nothing was created", len(call("GET", "/provider/deliveries", None, t)[1]) == 0)
call("POST", f"/delivery/orders/{ids[1]}/cancel", {}, cu)
ok("after a slot frees, pharmacy delivery works", call("POST", "/medical/delivery", dv, cu)[0] == 201)
# --- inquiries: 10 open
for i in range(9): call("POST", "/medical/inquiries", {"medicine_name": f"d{i}", "region_id": 3}, cu)  # 1 + 9 = 10 open
ok("11th open inquiry -> 429", call("POST", "/medical/inquiries", {"medicine_name": "d-extra", "region_id": 3}, cu)[0] == 429)
ok("another customer unaffected (inquiries)", call("POST", "/medical/inquiries", {"medicine_name": "x1", "region_id": 3}, other)[0] == 201)
ok("cancelling an inquiry frees a slot", call("POST", f"/medical/inquiries/{iid}/cancel", {}, cu)[0] == 200 and call("POST", "/medical/inquiries", {"medicine_name": "d-again", "region_id": 3}, cu)[0] == 201)
# --- files (20) and prescriptions (5 open)
png = __import__("imgutil").png()
fids = []
for i in range(20):
    st, r = call("POST", "/files", {"data": png}, other); fids.append(r.get("id"))
ok("20 uploads allowed", all(fids))
ok("21st upload -> 429", call("POST", "/files", {"data": png}, other)[0] == 429)
ok("deleting a file frees a slot", call("POST", f"/files/{fids[-1]}/delete", {}, other)[0] == 200 and call("POST", "/files", {"data": png}, other)[0] == 201)
third = user("01022222224", "ثالث"); pf = []
for i in range(5):
    f = call("POST", "/files", {"data": png}, third)[1]["id"]; st, r = call("POST", "/medical/prescriptions", {"file_id": f, "region_id": 3}, third); pf.append((f, r.get("id"))); ok("prescription %d allowed" % (i + 1), st == 201)
f = call("POST", "/files", {"data": png}, third)[1]["id"]
ok("6th open prescription -> 429", call("POST", "/medical/prescriptions", {"file_id": f, "region_id": 3}, third)[0] == 429)
ok("deleting a prescription image frees a slot", call("POST", f"/files/{pf[0][0]}/delete", {}, third)[0] == 200 and call("POST", "/medical/prescriptions", {"file_id": f, "region_id": 3}, third)[0] == 201)
ok("429 carries an Arabic error message", "مفتوحة" in call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "المخبز", "dropoff_text": "البيت"}, cu)[1].get("error", ""))
print("ALL PASSED")
