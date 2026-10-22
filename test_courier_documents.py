import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs, png
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8781; BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def raw(p, t):
    try: return urllib.request.urlopen(urllib.request.Request(BASE + "/api" + p, headers={"Authorization": "Bearer " + t})).status
    except urllib.error.HTTPError as e: return e.code
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
a, b, other = user("01011111111", "مندوب أ"), user("01022222222", "مندوب ب"), user("01033333333", "عميل")
up = lambda t: call("POST", "/files", {"data": png()}, t)[1]["id"]
ok("apply without documents rejected", call("POST", "/couriers/apply", {"region_id": 3}, a)[0] == 400)
f1, f2 = up(a), up(a); fb = up(b)
ok("only one ID side rejected", call("POST", "/couriers/apply", {"region_id": 3, "id_front_file_id": f1}, a)[0] == 400)
ok("another user's file rejected", call("POST", "/couriers/apply", {"region_id": 3, "id_front_file_id": f1, "id_back_file_id": fb}, a)[0] == 400)
ok("same file for both sides rejected", call("POST", "/couriers/apply", {"region_id": 3, "id_front_file_id": f1, "id_back_file_id": f1}, a)[0] == 400)
ok("garbage file id rejected", call("POST", "/couriers/apply", {"region_id": 3, "id_front_file_id": "x", "id_back_file_id": f2}, a)[0] == 400)
ok("nothing created by failed attempts", sqlite3.connect(os.environ["LAQINO_DB"]).execute("SELECT COUNT(*) FROM couriers").fetchone()[0] == 0)
ok("apply with documents", call("POST", "/couriers/apply", {"region_id": 3, "id_front_file_id": f1, "id_back_file_id": f2}, a)[0] == 201)
ok("duplicate apply while pending with docs -> 409", apply_docs(call, a)[0] == 409)
uid = call("GET", "/me", None, a)[1]["id"]
row = [x for x in call("GET", "/admin/couriers?status=pending", None, at)[1] if x["user_id"] == uid][0]
ok("admin list shows both documents", sorted(d["kind"] for d in row["documents"]) == ["id_back", "id_front"])
ok("admin can read the document", raw(f"/files/{f1}", at) == 200)
ok("other customer cannot read it", raw(f"/files/{f1}", other) == 404)
ok("another applicant cannot read it", raw(f"/files/{f1}", b) == 404)
ok("owner cannot delete a document in an application", call("POST", f"/files/{f1}/delete", {}, a)[0] == 409)
ok("document cannot be reused as a prescription", call("POST", "/medical/prescriptions", {"file_id": f1, "region_id": 3}, a)[0] == 400)
ok("audit records reads by admin", sqlite3.connect(os.environ["LAQINO_DB"]).execute("SELECT COUNT(*) FROM audit_log WHERE action='file.read' AND actor_id=1").fetchone()[0] >= 1)
# legacy pending request without documents (as created before this step)
con = sqlite3.connect(os.environ["LAQINO_DB"]); ub = call("GET", "/me", None, b)[1]["id"]
con.execute("INSERT INTO couriers(user_id,region_id,created_at) VALUES(?,?,?)", (ub, 3, int(time.time()))); con.commit()
ok("cannot approve without documents", call("POST", f"/admin/couriers/{ub}/review", {"status": "approved"}, at)[0] == 409)
ok("legacy pending can add documents", apply_docs(call, b, selfie=True)[0] == 201)
rowb = [x for x in call("GET", "/admin/couriers?status=pending", None, at)[1] if x["user_id"] == ub][0]
ok("selfie optional but stored", sorted(d["kind"] for d in rowb["documents"]) == ["id_back", "id_front", "selfie"])
ok("approve with documents", call("POST", f"/admin/couriers/{uid}/review", {"status": "approved"}, at)[0] == 200 and call("GET", "/me", None, a)[1]["role"] == "courier")
ok("approved courier cannot re-apply", apply_docs(call, a)[0] == 409)
ok("reject", call("POST", f"/admin/couriers/{ub}/review", {"status": "rejected"}, at)[0] == 200)
ok("rejected applicant resubmits with new documents", apply_docs(call, b)[0] == 201)
rowb = [x for x in call("GET", "/admin/couriers?status=pending", None, at)[1] if x["user_id"] == ub][0]
ok("resubmission replaced old documents (2, no selfie)", len(rowb["documents"]) == 2)
ok("approved courier works end to end (wallet endpoint)", call("GET", "/courier/wallet", None, a)[0] == 200)
print("ALL PASSED")
