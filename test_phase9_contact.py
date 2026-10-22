# البند 4: التواصل — رقم المندوب/العميل أثناء الطلب النشط فقط، ورقم البائع عند الطلب (تسجيل دخول + حد ساعي) بدون تسريبه في القوائم العامة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs, fare_ok
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8779; BASE = f"http://127.0.0.1:{PORT}"
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
SELLER, BUYER, BUYER2, COUR, COUR2, CUST, CUST2 = "01011110001", "01011110002", "01011110003", "01011110004", "01011110005", "01011110006", "01011110007"
tk = {p: user(p) for p in (SELLER, BUYER, BUYER2, COUR, COUR2, CUST, CUST2)}
# ---------- السوق
root = q("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "أجهزة", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [x for x in call("GET", "/categories?section=souq")[1] if x["parent_id"]][0]["id"]
def listing(title, approve=True):
    lid = call("POST", "/listings", {"category_id": cat, "region_id": 3, "title": title}, tk[SELLER])[1]["id"]
    if approve: call("POST", f"/admin/listings/{lid}/review", {"status": "approved"}, at)
    return lid
L1 = listing("ثلاجة"); Lp = listing("معلق", approve=False); Ld = listing("محذوف"); call("POST", f"/listings/{Ld}/delete", {}, tk[SELLER])
pub = call("GET", "/listings")[1]
ok("public listings never leak seller phone", pub and all("phone" not in x and SELLER not in json.dumps(x) for x in pub))
ok("contact requires login", call("GET", f"/listings/{L1}/contact")[0] == 401)
ok("contact on missing / pending / deleted listing -> 404", all(call("GET", f"/listings/{i}/contact", None, tk[BUYER])[0] == 404 for i in (99999, Lp, Ld)))
ok("buyer gets seller phone for approved listing", call("GET", f"/listings/{L1}/contact", None, tk[BUYER])[1]["phone"] == SELLER)
call("GET", f"/listings/{L1}/contact", None, tk[BUYER])
ok("repeat reveal of same listing is logged once", q("select count(*) from audit_log where action='listing.contact' and target=?", str(L1))[0][0] == 1)
ok("seller viewing own listing is not logged", call("GET", f"/listings/{L1}/contact", None, tk[SELLER])[0] == 200 and q("select count(*) from audit_log where action='listing.contact' and target=?", str(L1))[0][0] == 1)
ids = [L1] + [listing("إعلان %d" % i) for i in range(server.CONTACT_LIMIT - 1)]
codes = [call("GET", f"/listings/{i}/contact", None, tk[BUYER2])[0] for i in ids]
ok(f"limit: {server.CONTACT_LIMIT} distinct reveals/hour allowed", codes == [200] * server.CONTACT_LIMIT)
extra = listing("إعلان زائد")
ok("limit: next distinct listing -> 429, phone not leaked", call("GET", f"/listings/{extra}/contact", None, tk[BUYER2])[0] == 429)
ok("limit: already revealed listing still works", call("GET", f"/listings/{ids[0]}/contact", None, tk[BUYER2])[0] == 200)
ok("limit is per user (another buyer unaffected)", call("GET", f"/listings/{extra}/contact", None, tk[BUYER])[0] == 200)
c = sqlite3.connect(os.environ["LAQINO_DB"]); c.execute("update audit_log set at=at-4000 where action='listing.contact' and actor_id=(select id from users where phone=?)", (BUYER2,)); c.commit(); c.close()
ok("limit resets after an hour", call("GET", f"/listings/{extra}/contact", None, tk[BUYER2])[0] == 200)
# ---------- الدليفري
uid = lambda p: call("GET", "/me", None, tk[p])[1]["id"]
for p in (COUR, COUR2):
    apply_docs(call, tk[p]); call("POST", f"/admin/couriers/{uid(p)}/review", {"status": "approved"}, at)
    call("POST", "/courier/topups", {"amount": 500, "transfer_ref": "REF" + p[-4:]}, tk[p])
for t in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{t['id']}/review", {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 40}, at)
o = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, tk[CUST])[1]["id"]
mine = lambda: [x for x in call("GET", "/delivery/orders", None, tk[CUST])[1] if x["id"] == o][0]
cmine = lambda p=COUR: [x for x in call("GET", "/courier/orders", None, tk[p])[1] if x["id"] == o]
ok("searching: no courier phone for customer; available list has no phones", mine()["courier_phone"] is None and all("phone" not in k for x in call("GET", "/courier/available", None, tk[COUR])[1] for k in x))
call("POST", f"/courier/orders/{o}/accept", None, tk[COUR])
fare_ok(o)
for to in (None, "heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation"):
    if to: call("POST", f"/courier/orders/{o}/status", {"to": to}, tk[COUR])
    m, cc = mine(), cmine()[0]
    ok(f"active ({m['status']}): both sides see each other's phone", m["courier_phone"] == COUR and cc["customer_phone"] == CUST and cc["customer_name"] == "u06")
ok("other customer / other courier never see these phones", all(o != x["id"] for x in call("GET", "/delivery/orders", None, tk[CUST2])[1]) and cmine(COUR2) == [])
call("POST", f"/delivery/orders/{o}/dispute", {"reason": "سبب الاعتراض"}, tk[CUST])
ok("disputed: phones hidden on both sides", mine()["courier_phone"] is None and cmine()[0]["customer_phone"] is None and cmine()[0]["customer_name"] is None)
call("POST", f"/admin/orders/{o}/complete", {"reason": "تم التحقق"}, at)
ok("completed: phones hidden on both sides", mine()["courier_phone"] is None and cmine()[0]["customer_phone"] is None)
o2 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, tk[CUST])[1]["id"]
call("POST", f"/courier/orders/{o2}/accept", None, tk[COUR]); call("POST", f"/courier/orders/{o2}/release", None, tk[COUR])
ok("released order: customer has no courier phone, ex-courier no longer lists it", [x for x in call("GET", "/delivery/orders", None, tk[CUST])[1] if x["id"] == o2][0]["courier_phone"] is None and not [x for x in call("GET", "/courier/orders", None, tk[COUR])[1] if x["id"] == o2])
o3 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, tk[CUST])[1]["id"]
call("POST", f"/courier/orders/{o3}/accept", None, tk[COUR]); call("POST", f"/admin/orders/{o3}/cancel", {}, at)
ok("admin-cancelled order: phones hidden", [x for x in call("GET", "/courier/orders", None, tk[COUR])[1] if x["id"] == o3][0]["customer_phone"] is None)
# ---------- الواجهات (سكربتات الصفحات الحقيقية في node، ليس متصفحًا)
LU = listing("إعلان فريدةواجهة")
o4 = call("POST", "/delivery/orders", {"region_id": 3, "pickup_text": "aaa", "dropoff_text": "bbb"}, tk[CUST])[1]["id"]
call("POST", f"/courier/orders/{o4}/accept", None, tk[COUR]); fare_ok(o4)
r = ui("index", tk[BUYER], [{"js": "window.sq='فريدةواجهة';go(1)", "snap": "v"}])
ok("index souq: contact button per listing, no phone shown before click", f"ct({LU})" in r["v"] and SELLER not in r["v"] and r["errs"] == [])
r = ui("index", tk[BUYER], [{"js": "window.sq='فريدةواجهة';go(1)"}, {"js": f"ct({LU})", "wait": 900, "snap": f"ct{LU}"}])
ok("index souq: click reveals phone with tel and WhatsApp links", SELLER in r[f"ct{LU}"] and f'tel:{SELLER}' in r[f"ct{LU}"] and f"wa.me/2{SELLER}" in r[f"ct{LU}"])
r = ui("index", "", [{"js": "window.sq='فريدةواجهة';go(1)"}, {"js": f"ct({LU})", "wait": 900, "snap": "v"}])
ok("index souq: anonymous gets login message, no phone", "سجّل الدخول" in r["v"] and SELLER not in r["v"])
r = ui("index", tk[CUST], [{"js": "go(3)", "snap": "v"}])
ok("index my orders: active order shows courier phone link", f'tel:{COUR}' in r["v"])
r = ui("courier", tk[COUR], [{"snap": "m", "wait": 900}])
ok("courier page: active order shows customer name + phone link", f'tel:{CUST}' in r["m"] and "u06" in r["m"] and r["errs"] == [])
r = ui("courier", tk[COUR], [{"snap": "m", "wait": 900}])
ok("courier page: ended orders (disputed/completed/cancelled) show no customer phone", r["m"].count(f"tel:{CUST}") == 1)
print("ALL PASSED")
