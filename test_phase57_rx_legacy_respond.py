"""Phase 57: رد الصيدلية عبر المسار القديم /respond (الوضع اليدوي الافتراضي) يُعتمد تلقائيًا ويظهر للعميل؛ ومع تفعيل الاعتماد اليدوي يبقى pending.
وحد الروشتات المفتوحة (5) لا يحسب المكتملة."""
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
from imgutil import png
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8857), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8857"; DB = os.environ["LAQINO_DB"]
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
cust, pa = user("01012345678"), user("01011111111")
cid = call("GET", "/me", None, cust)[1]["id"]; pid = call("GET", "/me", None, pa)[1]["id"]
call("POST", "/providers/apply", {"name_ar": "صيدلية أ", "region_id": 3, "address": "x"}, pa); call("POST", f"/admin/providers/{pid}/review", {"status": "approved"}, at)
def new_rx():
    s, r = call("POST", "/medical/prescriptions", {"file_id": call("POST", "/files", {"data": png()}, cust)[1]["id"], "region_id": 3}, cust); assert s == 201, r; return r["id"]
def seen_by_customer(rid): return [x for x in call("GET", "/medical/prescriptions", None, cust)[1] if x["id"] == rid][0]["responses"]

# الوضع الافتراضي (اعتماد تلقائي): الرد عبر /respond يظهر للعميل
R = new_rx(); call("POST", f"/admin/prescriptions/{R}/forward", {"provider_id": pid}, at)
s, r = call("POST", f"/provider/prescriptions/{R}/respond", {"status": "available", "price": 50, "note": "n"}, pa); ok("legacy respond accepted", s == 200)
ok("review approved automatically", sql("SELECT review FROM prescription_responses WHERE prescription_id=?", (R,))[0][0] == "approved")
ok("customer sees the response", len(seen_by_customer(R)) == 1)
ok("customer got ONE notification", sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='rx.quote'", (cid,))[0][0] == 1)
call("POST", f"/provider/prescriptions/{R}/respond", {"status": "available", "price": 55, "note": "n"}, pa)
ok("edited response stays approved", sql("SELECT review FROM prescription_responses WHERE prescription_id=?", (R,))[0][0] == "approved")

# مفتاح الاعتماد اليدوي: يبقى pending ولا يراه العميل
sql("INSERT OR REPLACE INTO settings(key,value) VALUES('rx_manual_review','1')")
R2 = new_rx(); call("POST", f"/admin/prescriptions/{R2}/forward", {"provider_id": pid}, at)
call("POST", f"/provider/prescriptions/{R2}/respond", {"status": "available", "price": 50}, pa)
ok("manual review: stays pending and hidden", sql("SELECT review FROM prescription_responses WHERE prescription_id=?", (R2,))[0][0] == "pending" and seen_by_customer(R2) == [])
sql("DELETE FROM settings WHERE key='rx_manual_review'")

# حد الـ5: المكتملة لا تُحسب
for i in range(3): new_rx()
sql("INSERT OR IGNORE INTO rx_completed(prescription_id,provider_id,completed_at) VALUES(?,?,?)", (R, pid, int(time.time())))
ok("completed prescription does not count toward the open limit", sql(server.COUNT_SQL["prescriptions"], (cid,))[0][0] == 4)  # R2 + 3 جديدة؛ R مكتملة
print("TOTAL OK")
