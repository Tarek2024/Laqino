"""Phase 57: ربط صيدلية بمحافظة كاملة (القاهرة مثلًا): تستلم روشتات عملاء مراكز القاهرة فقط، لا عملاء محافظة تانية."""
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
from imgutil import png
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8863), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8863"; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
s, g = call("POST", "/admin/regions", {"parent_id": 1, "level": "governorate", "slug": "eg-cai", "name_ar": "القاهرة", "is_active": 1}, at); GOV = g["id"]
s, m = call("POST", "/admin/regions", {"parent_id": GOV, "level": "markaz", "slug": "eg-cai-nasr", "name_ar": "مدينة نصر", "is_active": 1}, at); NASR = m["id"]
s, m = call("POST", "/admin/regions", {"parent_id": GOV, "level": "markaz", "slug": "eg-cai-maadi", "name_ar": "المعادي", "is_active": 1}, at); MAADI = m["id"]
pc, pk, cc, ck = user("01011111111"), user("01022222222"), user("01033333333"), user("01044444444")
pcid, pkid = call("GET", "/me", None, pc)[1]["id"], call("GET", "/me", None, pk)[1]["id"]
for t, i, rg in ((pc, pcid, 3), (pk, pkid, 3)):
    call("POST", "/providers/apply", {"name_ar": "صيدلية %d" % i, "region_id": rg, "address": "x"}, t); call("POST", f"/admin/providers/{i}/review", {"status": "approved"}, at)
s, r = call("POST", f"/admin/providers/{pcid}/settings", {"region_id": GOV, "distribution_enabled": True}, at)
ok("admin can put a pharmacy under a whole governorate", s == 200 and sql("SELECT region_id FROM providers WHERE user_id=?", (pcid,))[0][0] == GOV)
ok("country level still rejected", call("POST", f"/admin/providers/{pcid}/settings", {"region_id": 1}, at)[0] == 400)
call("POST", f"/admin/providers/{pkid}/settings", {"distribution_enabled": True}, at)
ok("auto distribution mode", call("POST", "/admin/rx/distribution-mode", {"mode": "auto"}, at)[0] == 200)
def rx(tok, region):
    fid = call("POST", "/files", {"data": png()}, tok)[1]["id"]
    s, r = call("POST", "/medical/prescriptions", {"file_id": fid, "region_id": region}, tok); assert s == 201, r; return r["id"]
def offered(rid): return {x[0] for x in sql("SELECT provider_id FROM rx_offers WHERE prescription_id=? AND state='open'", (rid,))}
r1 = rx(cc, NASR); r2 = rx(cc, MAADI); r3 = rx(ck, 3)
ok("customer in a Cairo markaz (Nasr): Cairo pharmacy gets it, Kafr El-Sheikh pharmacy does not", offered(r1) == {pcid})
ok("customer in another Cairo markaz (Maadi): same", offered(r2) == {pcid})
ok("customer in Kafr El-Sheikh: only the local pharmacy, not Cairo's", offered(r3) == {pkid})
# قائمة الصيدليات للعميل (البحث حسب المنطقة)
import urllib.parse
def listed(tok, region):
    s, r = call("GET", "/search?" + urllib.parse.urlencode({"q": "صيدلية", "region_id": region}), None, tok); assert s == 200, r
    return {x["id"] for x in r.get("pharmacies", [])}
ok("Nasr customer sees the Cairo pharmacy in search, not the Kafr El-Sheikh one", listed(cc, NASR) == {pcid})
ok("Kafr El-Sheikh customer does not see the Cairo pharmacy", pcid not in listed(ck, 3))
print("TOTAL OK")
