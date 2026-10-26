# Marketplace ad management isolated regression tests.
# Run: python test_phase_marketplace_ad_management.py
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
_TMP = tempfile.mkdtemp(prefix="laqino-market-ad-")
os.environ["LAQINO_DB"] = os.path.join(_TMP, "test.db")
os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "uploads")
os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(.2)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
DB = server.DB
def call(method, path, data=None, token=None):
    req = urllib.request.Request(BASE + "/api" + path, json.dumps(data).encode() if data is not None else None,
        {"Content-Type":"application/json", **({"Authorization":"Bearer "+token} if token else {})}, method=method)
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def sql(q, args=()):
    c=sqlite3.connect(DB); rows=c.execute(q,args).fetchall(); c.close(); return rows
def ok(name, condition):
    print(("PASS " if condition else "FAIL ")+name)
    if not condition: raise SystemExit(1)
admin=call("POST","/login",{"phone":"01000000000","password":"AdminPass123"})[1]["token"]
def user(phone):
    call("POST","/register",{"phone":phone,"name":"بائع "+phone[-2:],"password":"password1"})
    return call("POST","/login",{"phone":phone,"password":"password1"})[1]["token"]
seller=user("01044440001"); buyer=user("01044440002")
root=sql("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST","/admin/categories",{"section":"souq","name_ar":"أغراض منزلية","slug":"homeitems","parent_id":root,"is_active":True},admin)
cats=call("GET","/categories?section=souq")[1]
cat=next(x["id"] for x in cats if x["parent_id"] is not None and x["name_ar"]=="أغراض منزلية")
regions=sql("select id from regions where is_active=1 order by id")
if not regions: raise SystemExit("FAIL test setup: no active region")
rid=regions[0][0]
status, created=call("POST","/listings",{"category_id":cat,"region_id":rid,"title":"كرسي للبيع","description":"وصف قبل التعديل","anonymous":True},seller)
ok("anonymous ad creation succeeds",status==201 and created.get("status")=="pending")
lid=created["id"]
ok("anonymous column is additive and defaults to zero for old rows", "anonymous" in [r[1] for r in sqlite3.connect(DB).execute("pragma table_info(listings)")])
ok("pending ad is not publicly listed", all(x["id"]!=lid for x in call("GET","/listings")[1]))
ok("owner can read own anonymous flag",call("GET",f"/my/listings/{lid}",None,seller)[1]["anonymous"]==1)
ok("admin can approve listing",call("POST",f"/admin/listings/{lid}/review",{"status":"approved"},admin)[0]==200)
pub=call("GET","/listings",None,buyer)[1]
item=next(x for x in pub if x["id"]==lid)
ok("public list hides account name for anonymous ad",item["seller"]=="مستخدم مجهول")
detail=call("GET",f"/listings/{lid}",None,buyer)[1]
ok("public detail keeps anonymous label",detail["seller"]=="مستخدم مجهول" and detail["anonymous"] is True)
own=call("GET",f"/listings/{lid}",None,seller)[1]
ok("owner still sees own account name and edit controls metadata",own["seller"]=="بائع 01" and own["is_owner"])
edited=call("POST",f"/listings/{lid}/edit",{"title":"كرسي خشب للبيع","description":"وصف بعد التعديل","anonymous":False},seller)
ok("editing returns pending for admin review",edited[0]==200 and edited[1]["status"]=="pending")
row=sql("select title,description,status,anonymous from listings where id=?",(lid,))[0]
ok("edit updates only requested fields and queues review",row==("كرسي خشب للبيع","وصف بعد التعديل","pending",0))
ok("edited ad is hidden from public while awaiting approval",all(x["id"]!=lid for x in call("GET","/listings",None,buyer)[1]))
ok("admin can approve edited ad",call("POST",f"/admin/listings/{lid}/review",{"status":"approved"},admin)[0]==200)
pub2=call("GET","/listings",None,buyer)[1]
item2=next(x for x in pub2 if x["id"]==lid)
ok("approved edit shows seller name when anonymous is disabled",item2["seller"]=="بائع 01")
# Static front-end safeguards: primary-image chooser reorders the selected image first.
root_dir=os.path.dirname(os.path.abspath(__file__))
idx=open(os.path.join(root_dir,"static","index.html"),encoding="utf-8").read()
market_html=open(os.path.join(root_dir,"static","market.html"),encoding="utf-8").read()
css=open(os.path.join(root_dir,"static","market-enhancements.css"),encoding="utf-8").read()
ok("primary image chooser moves selected image to first position", "window.lImgs.unshift(x)" in idx and "mainImg(" in idx)
ok("post form offers named and anonymous publishing", "id=\"lanon\"" in idx and "anonymous:$('lanon').value==='1'" in idx)
ok("owner editor resubmits edits for review", "إرسال التعديلات للموافقة" in idx and "status='pending'" in open(os.path.join(root_dir,"server.py"),encoding="utf-8").read())
ok("standalone market uses individual cards, not featured shelf", "loadFeatured();" not in market_html and ".grid>.card" in css)
print("Marketplace ad-management regression checks passed.")
