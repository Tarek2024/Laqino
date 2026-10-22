# حذف الحساب بإخفاء الهوية (المرحلة 32 — Google Play).
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from imgutil import png
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8799), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8799"; DB = os.environ["LAQINO_DB"]; UP = os.environ["LAQINO_UPLOADS"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def q(sql, *a):
    c = sqlite3.connect(DB); r = c.execute(sql, a).fetchall(); c.commit(); return r
def reg(ph, pw="password1"):
    call("POST", "/register", {"phone": ph, "name": "اسم" + ph[-2:], "password": pw}); return call("POST", "/login", {"phone": ph, "password": pw})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
ok("legal page served", urllib.request.urlopen(BASE + "/delete-account").status == 200 and "Laqino100" in urllib.request.urlopen(BASE + "/delete-account").read().decode())
t = reg("01011111111"); other = reg("01022222222"); uid = call("GET", "/me", None, t)[1]["id"]
ok("no auth 401", call("POST", "/me/delete", {"password": "password1"})[0] == 401)
ok("admin cannot delete (403)", call("POST", "/me/delete", {"password": "AdminPass123"}, at)[0] == 403)
ok("wrong password 403 and account intact", call("POST", "/me/delete", {"password": "nope"}, t)[0] == 403 and call("GET", "/me", None, t)[0] == 200)
fid = call("POST", "/files", {"data": png()}, t)[1]["id"]; path = q("SELECT path FROM files WHERE id=?", fid)[0][0]
ok("uploaded file exists on disk", os.path.exists(os.path.join(UP, path)))
now = int(time.time())
q("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,details,fee,status,created_at,updated_at) VALUES(?,3,'شارع س','بيت 5','سري',10,'searching',?,?)", uid, now, now)
st, r = call("POST", "/me/delete", {"password": "password1"}, t)
ok("active order blocks deletion (409)", st == 409 and q("SELECT COUNT(*) FROM users WHERE id=? AND deleted_at IS NOT NULL", uid)[0][0] == 0)
q("UPDATE delivery_orders SET status='completed' WHERE customer_id=?", uid)
q("INSERT INTO medicine_inquiries(customer_id,region_id,medicine_name,note,created_at) VALUES(?,3,'دواء','ملاحظة خاصة',?)", uid, now)
st, _ = call("POST", "/me/delete", {"password": "password1"}, t); ok("deletion succeeds", st == 200)
ok("session dead", call("GET", "/me", None, t)[0] == 401)
ok("cannot log in with old password", call("POST", "/login", {"phone": "01011111111", "password": "password1"})[0] == 401)
row = q("SELECT name,phone,deleted_at FROM users WHERE id=?", uid)[0]
ok("name/phone anonymized", row[0] == "حساب محذوف" and row[1] == "deleted-%d" % uid and row[2])
ok("order kept but addresses scrubbed", q("SELECT pickup_text,dropoff_text,details FROM delivery_orders WHERE customer_id=?", uid)[0] == ("[محذوف]", "[محذوف]", None))
ok("inquiry note scrubbed", q("SELECT note FROM medicine_inquiries WHERE customer_id=?", uid)[0][0] is None)
ok("file removed from db and disk", not q("SELECT 1 FROM files WHERE owner_id=?", uid) and not os.path.exists(os.path.join(UP, path)))
ok("audit has deletion, no phone", q("SELECT COUNT(*) FROM audit_log WHERE action='account.delete'")[0][0] == 1)
ok("phone can register again as a new account", call("POST", "/register", {"phone": "01011111111", "name": "جديد", "password": "password2"})[0] in (200, 201))
ok("other user untouched", call("GET", "/me", None, other)[0] == 200)
# مندوب بوثائق
tc = reg("01033333333"); cid = call("GET", "/me", None, tc)[1]["id"]; apply_docs(call, tc)
ok("courier docs exist", q("SELECT COUNT(*) FROM courier_documents WHERE courier_id=?", cid)[0][0] == 2)
ok("courier deletion succeeds", call("POST", "/me/delete", {"password": "password1"}, tc)[0] == 200)
ok("courier docs + files purged, courier suspended", q("SELECT COUNT(*) FROM courier_documents WHERE courier_id=?", cid)[0][0] == 0 and not q("SELECT 1 FROM files WHERE owner_id=?", cid) and q("SELECT status FROM couriers WHERE user_id=?", cid)[0][0] == "suspended")
print("ALL OK")
