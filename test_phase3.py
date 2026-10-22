import urllib.parse, os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
s = ThreadingHTTPServer(("127.0.0.1", 8768), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8768/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
a, b = user("01012345678"), user("01112345678")
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cid = call("POST", "/admin/categories", {"parent_id": 2, "section": "souq", "slug": "furn", "name_ar": "أثاث", "is_active": True}, at)[1]["id"]
call("POST", f"/admin/categories/{cid}/fields", {"key": "price", "label_ar": "السعر", "type": "price", "required": True}, at)
call("POST", f"/admin/categories/{cid}/fields", {"key": "cond", "label_ar": "الحالة", "type": "select", "options": ["جديد", "مستعمل"], "required": True}, at)
good = {"category_id": cid, "region_id": 3, "title": "كنبة ثلاثية", "description": "حالة ممتازة", "fields": {"price": 3500, "cond": "مستعمل"}}
ok("anonymous cannot post", call("POST", "/listings", good)[0] == 401)
ok("missing required field rejected", call("POST", "/listings", {**good, "fields": {"price": 10}}, a)[0] == 400)
ok("invalid select rejected", call("POST", "/listings", {**good, "fields": {"price": 10, "cond": "x"}}, a)[0] == 400)
ok("negative price rejected", call("POST", "/listings", {**good, "fields": {"price": -5, "cond": "جديد"}}, a)[0] == 400)
ok("non-souq category rejected", call("POST", "/listings", {**good, "category_id": 1}, a)[0] == 400)
st, r = call("POST", "/listings", good, a); lid = r["id"]
ok("post goes pending", st == 201 and r["status"] == "pending")
ok("pending not public", call("GET", "/listings")[1] == [])
ok("customer cannot review", call("POST", f"/admin/listings/{lid}/review", {"status": "approved"}, b)[0] == 403)
ok("reject needs reason", call("POST", f"/admin/listings/{lid}/review", {"status": "rejected"}, at)[0] == 400)
ok("admin approves", call("POST", f"/admin/listings/{lid}/review", {"status": "approved"}, at)[0] == 200)
ok("cannot review twice", call("POST", f"/admin/listings/{lid}/review", {"status": "rejected", "reason": "x"}, at)[0] == 409)
pub = call("GET", "/listings")[1]
ok("approved is public, phone hidden", len(pub) == 1 and "phone" not in json.dumps(pub) and pub[0]["seller"])
ok("search by text hit", len(call("GET", "/listings?q=" + urllib.parse.quote("كنبة"))[1]) == 1)
ok("search miss returns empty", call("GET", "/listings?q=" + urllib.parse.quote("سيارة"))[1] == [])
ok("price filter", len(call("GET", "/listings?max_price=1000")[1]) == 0 and len(call("GET", "/listings?min_price=3000&max_price=4000")[1]) == 1)
ok("region filter includes children", len(call("GET", "/listings?region_id=2")[1]) == 1 and len(call("GET", "/listings?region_id=3")[1]) == 1)
ok("other user cannot delete", call("POST", f"/listings/{lid}/delete", {}, b)[0] == 404)
ok("my listings isolated", len(call("GET", "/my/listings", None, a)[1]) == 1 and call("GET", "/my/listings", None, b)[1] == [])
ok("owner deletes", call("POST", f"/listings/{lid}/delete", {}, a)[0] == 200 and call("GET", "/listings")[1] == [])
print("ALL PASSED")
