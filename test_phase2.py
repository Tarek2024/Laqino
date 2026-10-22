import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
ThreadingHTTPServer(("127.0.0.1", 8766), server.H).server_close
s = ThreadingHTTPServer(("127.0.0.1", 8767), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8767/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
call("POST", "/register", {"phone": "01012345678", "name": "عميل", "password": "password1"})
ct = call("POST", "/login", {"phone": "01012345678", "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
ok("no categories visible before activation", call("GET", "/categories")[1] == [])
ok("customer cannot create category", call("POST", "/admin/categories", {"section": "souq", "slug": "x", "name_ar": "x"}, ct)[0] == 403)
st, r = call("POST", "/admin/categories", {"parent_id": 2, "section": "souq", "slug": "furniture", "name_ar": "أثاث", "is_active": True}, at)
ok("admin creates category", st == 201)
ok("duplicate slug rejected", call("POST", "/admin/categories", {"section": "souq", "slug": "furniture", "name_ar": "أثاث"}, at)[0] == 400)
ok("invalid section rejected", call("POST", "/admin/categories", {"section": "bogus", "slug": "b", "name_ar": "b"}, at)[0] == 400)
ok("public sees active category", [x["slug"] for x in call("GET", "/categories?section=souq")[1]] == ["furniture"])
cid = r["id"]
ok("add price field", call("POST", f"/admin/categories/{cid}/fields", {"key": "price", "label_ar": "السعر", "type": "price", "required": True, "searchable": True}, at)[0] == 201)
ok("select needs options", call("POST", f"/admin/categories/{cid}/fields", {"key": "cond", "label_ar": "الحالة", "type": "select"}, at)[0] == 400)
ok("add select field", call("POST", f"/admin/categories/{cid}/fields", {"key": "cond", "label_ar": "الحالة", "type": "select", "options": ["جديد", "مستعمل"]}, at)[0] == 201)
ok("bad field type rejected", call("POST", f"/admin/categories/{cid}/fields", {"key": "z", "label_ar": "z", "type": "bogus"}, at)[0] == 400)
ok("fields served", [f["key"] for f in call("GET", f"/categories/{cid}/fields")[1]] == ["price", "cond"])
ok("hide category", call("POST", f"/admin/categories/{cid}", {"is_active": False}, at)[0] == 200)
ok("hidden category and fields gone", call("GET", "/categories?section=souq")[1] == [] and call("GET", f"/categories/{cid}/fields")[1] == [])
ok("admin still sees hidden", len(call("GET", "/categories?section=souq&all=1", None, at)[1]) == 2)
print("ALL PASSED")
