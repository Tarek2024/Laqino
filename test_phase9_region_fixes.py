import os, json, threading, urllib.request, urllib.error, tempfile, time, socket
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8766), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8766/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
vil = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "v1", "name_ar": "قرية أ", "is_active": True}, at)[1]["id"]
vil2 = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "v2", "name_ar": "قرية ب", "is_active": True}, at)[1]["id"]
mk2 = call("POST", "/admin/regions", {"parent_id": 2, "level": "markaz", "slug": "m2", "name_ar": "مركز آخر", "is_active": True}, at)[1]["id"]
def pharmacy(ph, name, rid):
    t = user(ph, name); call("POST", "/providers/apply", {"name_ar": name, "region_id": rid}, t)
    uid = call("GET", "/me", None, t)[1]["id"]; call("POST", f"/admin/providers/{uid}/review", {"status": "approved"}, at); return t
pv = pharmacy("01011111111", "صيدلية القرية", vil)
pm = pharmacy("01033333333", "صيدلية المركز", 3)
call("POST", "/provider/stock", {"medicine_name": "panadol", "available": True, "price": 20}, pv)
cu = user("01022222222", "عميل")
ok("search from the village finds the village pharmacy", len(call("GET", f"/medical/search?q=panadol&region_id={vil}")[1]) == 1)
ok("search from the parent markaz finds the village pharmacy", len(call("GET", "/medical/search?q=panadol&region_id=3")[1]) == 1)
ok("search from a sibling village does not", len(call("GET", f"/medical/search?q=panadol&region_id={vil2}")[1]) == 0)
ok("search from another markaz does not", len(call("GET", f"/medical/search?q=panadol&region_id={mk2}")[1]) == 0)
st, r = call("POST", "/medical/inquiries", {"medicine_name": "drug-A", "region_id": 3}, cu); iid = r["id"]
ok("village pharmacy sees an inquiry made at the markaz", any(x["id"] == iid for x in call("GET", "/provider/inquiries", None, pv)[1]))
ok("village pharmacy can respond to it", call("POST", f"/provider/inquiries/{iid}/respond", {"status": "available", "price": 10}, pv)[0] == 200)
call("POST", "/medical/inquiries", {"medicine_name": "drug-sib", "region_id": vil2}, cu)
ok("village pharmacy does not see a sibling-village inquiry", all(x["medicine_name"] != "drug-sib" for x in call("GET", "/provider/inquiries", None, pv)[1]))
sid = [x["id"] for x in call("GET", "/medical/inquiries", None, cu)[1] if x["medicine_name"] == "drug-sib"][0]
ok("...and cannot respond to it", call("POST", f"/provider/inquiries/{sid}/respond", {"status": "unavailable"}, pv)[0] == 404)
# LIMIT starvation: one older local inquiry + 105 newer ones elsewhere
call("POST", "/medical/inquiries", {"medicine_name": "LOCAL-OLD", "region_id": 3}, cu)
for k in range(11):  # several customers: each is capped at 10 open inquiries, together they exceed the 100-row LIMIT
    ck = user("0105000%04d" % k, "عميل%d" % k)
    for i in range(10): call("POST", "/medical/inquiries", {"medicine_name": f"other-{k}-{i}", "region_id": mk2}, ck)
names = [x["medicine_name"] for x in call("GET", "/provider/inquiries", None, pm)[1]]
ok("local inquiry still visible after 110 newer ones in another markaz", "LOCAL-OLD" in names)
ok("no foreign-region inquiries leak", not any(n.startswith("other-") for n in names))
def raw(cl):
    sk = socket.create_connection(("127.0.0.1", 8766), timeout=3)
    sk.sendall(("POST /api/login HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: %s\r\nConnection: close\r\n\r\n" % cl).encode())
    buf = b""
    while True:
        d = sk.recv(4096)
        if not d: break
        buf += d
    sk.close(); return buf.split(b"\r\n")[0]
ok("non-numeric Content-Length -> 400", b" 400 " in raw("abc"))
ok("negative Content-Length -> 400", b" 400 " in raw("-5"))
ok("stock-fresh: customer forbidden", call("POST", "/admin/settings/stock-fresh", {"hours": 48}, cu)[0] == 403)
ok("stock-fresh: invalid rejected", call("POST", "/admin/settings/stock-fresh", {"hours": 0}, at)[0] == 400)
ok("stock-fresh: admin saves and it is stored", call("POST", "/admin/settings/stock-fresh", {"hours": 48}, at)[0] == 200 and call("GET", "/admin/settings", None, at)[1]["settings"]["stock_fresh_hours"] == "48")
con = server.db(); con.execute("UPDATE provider_stock SET confirmed_at=? WHERE provider_id=(SELECT user_id FROM providers WHERE name_ar='صيدلية القرية')", (int(time.time()) - 30 * 3600,)); con.commit(); con.close()
ok("30h-old stock is fresh under a 48h window", len(call("GET", "/medical/search?q=panadol&region_id=3")[1]) == 1)
call("POST", "/admin/settings/stock-fresh", {"hours": 24}, at)
ok("30h-old stock is stale under a 24h window", len(call("GET", "/medical/search?q=panadol&region_id=3")[1]) == 0)
print("ALL PASSED")
