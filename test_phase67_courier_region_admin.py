# phase-67: admin can safely change courier region; existing application region remains intact unless explicitly changed.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
HTTPD = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
PORT = HTTPD.server_address[1]; BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=HTTPD.serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    req = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None,
        {"Content-Type":"application/json", **({"Authorization":"Bearer "+t} if t else {})}, method=m)
    try:
        r=urllib.request.urlopen(req); return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok=lambda n,c: print(("PASS " if c else "FAIL ")+n) or (c or exit(1))
def user(ph):
    call("POST","/register",{"phone":ph,"name":"courier","password":"password1"})
    return call("POST","/login",{"phone":ph,"password":"password1"})[1]["token"]
admin=call("POST","/login",{"phone":"01000000000","password":"AdminPass123"})[1]["token"]
courier=user("01011111111"); uid=call("GET","/me",None,courier)[1]["id"]
apply_docs(call,courier)
def db(sql, *a):
    con = sqlite3.connect(os.environ["LAQINO_DB"])
    try: return con.execute(sql, a).fetchall()
    finally: con.close()
active=[r[0] for r in db("SELECT id FROM regions WHERE is_active=1 ORDER BY id")]
ok("seed has at least two active regions",len(active)>=2)
before=db("SELECT region_id,status,review_reason FROM couriers WHERE user_id=?",uid)[0]
old=before[0]
role_before=db("SELECT role FROM users WHERE id=?",uid)[0][0]
wallet_before=db("SELECT COUNT(*) FROM wallet_entries WHERE user_id=?",uid)[0][0]
orders_before=db("SELECT COUNT(*) FROM delivery_orders WHERE courier_id=?",uid)[0][0]
audit_before=db("SELECT COUNT(*) FROM audit_log WHERE action='courier.region_update'")[0][0]
target=next((r for r in active if r!=old),None)
ok("target active region exists",target is not None)
ok("non-admin cannot change courier region",call("POST",f"/admin/couriers/{uid}/region",{"region_id":target},courier)[0]==403)
res=call("POST",f"/admin/couriers/{uid}/region",{"region_id":target},admin)
ok("admin changes region successfully",res[0]==200 and res[1]["region_id"]==target)
ok("new region persists in database",db("SELECT region_id FROM couriers WHERE user_id=?",uid)[0][0]==target)
after=db("SELECT region_id,status,review_reason FROM couriers WHERE user_id=?",uid)[0]
ok("region update does not change courier review status/reason",after==(target,before[1],before[2]))
ok("region update does not change user role",db("SELECT role FROM users WHERE id=?",uid)[0][0]==role_before)
ok("region update does not change wallet entries",db("SELECT COUNT(*) FROM wallet_entries WHERE user_id=?",uid)[0][0]==wallet_before)
ok("region update does not change existing assigned orders",db("SELECT COUNT(*) FROM delivery_orders WHERE courier_id=?",uid)[0][0]==orders_before)
ok("setting the same region again is idempotent",call("POST",f"/admin/couriers/{uid}/region",{"region_id":target},admin)[0]==200 and db("SELECT COUNT(*) FROM audit_log WHERE action='courier.region_update'")[0][0]==audit_before+1)
ok("invalid/nonexistent region rejected",call("POST",f"/admin/couriers/{uid}/region",{"region_id":999999},admin)[0]==400)
ok("unknown courier rejected",call("POST","/admin/couriers/999999/region",{"region_id":target},admin)[0]==404)
audit=[json.loads(r[0]) if r[0] else {} for r in db("SELECT detail FROM audit_log WHERE action='courier.region_update' ORDER BY rowid DESC LIMIT 1")]
ok("region change is audited with old and new region",bool(audit) and audit[0].get("old_region_id")==old and audit[0].get("new_region_id")==target)
root=os.path.dirname(os.path.abspath(__file__))
ui=open(os.path.join(root,"static","admin.html"),encoding="utf-8").read()
sw=open(os.path.join(root,"static","sw.js"),encoding="utf-8").read()
ok("admin UI exposes region editor safely", "window.cRegion=async id=>" in ui and "تعديل المنطقة" in ui)
match=re.search(r'const V = "laqino-v(\d+)"',sw)
ok("service worker cache bumped",bool(match) and int(match.group(1))>=103)
print("ALL OK")
HTTPD.shutdown()
HTTPD.server_close()
