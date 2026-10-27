# Marketplace ad management isolated regression tests.
# Run: python test_phase_marketplace_ad_management.py
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, re
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
contact=call("GET",f"/listings/{lid}/contact",None,buyer)[1]
ok("anonymous seller name is hidden in contact endpoint too",contact["seller"]=="مستخدم مجهول" and bool(contact.get("phone")))
own=call("GET",f"/listings/{lid}",None,seller)[1]
ok("owner still sees own account name and edit controls metadata",own["seller"]=="بائع 01" and own["is_owner"])
edited=call("POST",f"/listings/{lid}/edit",{"title":"كرسي خشب للبيع","description":"وصف بعد التعديل","anonymous":False,"condition":None},seller)
ok("editing returns pending for admin review",edited[0]==200 and edited[1]["status"]=="pending")
row=sql("select title,description,status,anonymous,condition from listings where id=?",(lid,))[0]
ok("edit updates requested fields, queues review, and can clear condition",row==("كرسي خشب للبيع","وصف بعد التعديل","pending",0,None))
ok("edited ad is hidden from public while awaiting approval",all(x["id"]!=lid for x in call("GET","/listings",None,buyer)[1]))
ok("admin can approve edited ad",call("POST",f"/admin/listings/{lid}/review",{"status":"approved"},admin)[0]==200)
pub2=call("GET","/listings",None,buyer)[1]
item2=next(x for x in pub2 if x["id"]==lid)
ok("approved edit shows seller name when anonymous is disabled",item2["seller"]=="بائع 01")
# Admin featured flow: the API flag must affect public ordering regardless of selected sort.
status, second=call("POST","/listings",{"category_id":cat,"region_id":rid,"title":"طاولة للبيع","description":"إعلان ثانٍ"},seller)
ok("second marketplace ad can be created for featured-order test",status==201)
second_id=second["id"]
ok("admin can approve second listing",call("POST",f"/admin/listings/{second_id}/review",{"status":"approved"},admin)[0]==200)
feature_status, feature_result=call("POST",f"/admin/listings/{second_id}/feature",{"days":7},admin)
ok("admin can feature a published open listing",feature_status==200 and feature_result.get("featured") is True)
ordered=call("GET","/listings?sort=oldest",None,buyer)[1]
ok("featured listing is first even when another sort is selected",bool(ordered) and ordered[0]["id"]==second_id and bool(ordered[0]["featured"]))
unfeature_status, unfeature_result=call("POST",f"/admin/listings/{second_id}/feature",{"days":0},admin)
ok("admin can remove featured status",unfeature_status==200 and unfeature_result.get("featured") is False)
# Static front-end safeguards: primary-image chooser reorders the selected image first.
root_dir=os.path.dirname(os.path.abspath(__file__))
idx=open(os.path.join(root_dir,"static","index.html"),encoding="utf-8").read()
market_html=open(os.path.join(root_dir,"static","market.html"),encoding="utf-8").read()
css=open(os.path.join(root_dir,"static","market-enhancements.css"),encoding="utf-8").read()
ok("primary image chooser moves selected image to first position", "window.lImgs.unshift(x)" in idx and "mainImg(" in idx)
ok("post form offers named and anonymous publishing", "id=\"lanon\"" in idx and "anonymous:$('lanon').value==='1'" in idx)
ok("owner editor resubmits edits for review", "إرسال التعديلات للموافقة" in idx and "status='pending'" in open(os.path.join(root_dir,"server.py"),encoding="utf-8").read())
ok("edit form supports image upload and image ordering", "addEditImgs(this," in idx and "image_file_ids=window._editImgs[id]" in idx and "initEditImgs" in idx)
sw=open(os.path.join(root_dir,"static","sw.js"),encoding="utf-8").read()
version_file=open(os.path.join(root_dir,"VERSION"),encoding="utf-8").read()
cache_version=next((x.split("=",1)[1].strip() for x in version_file.splitlines() if x.startswith("cache=")), "")
sw_version=sw.split('const V = "',1)[1].split('"',1)[0] if 'const V = "' in sw else ""
ok("service-worker cache version is declared", bool(sw_version) and sw_version.startswith("laqino-v"))
ok("VERSION metadata matches the service-worker cache version", bool(cache_version) and cache_version==sw_version)
ok("marketplace enhancement stylesheet is cached in the app shell", "/market-enhancements.css" in sw)
market_css=re.search(r'<link rel="stylesheet" href="(/market-enhancements\.css\?v=\d+)">',market_html)
ok("versioned stylesheet URL is cached for offline compatibility", bool(market_css) and market_css.group(1) in sw)
card_html=market_html.split("function card(x) {",1)[1].split("function featCard(x)",1)[0]
ok("market listing cards keep only publisher metadata", 'class: "seller-only"' in card_html and 'x.condition) tags.push' not in card_html and 'x.negotiable) tags.push' not in card_html and 'ago(x.created_at)' not in card_html)
ok("homepage market metadata keeps the publisher name only", 'class="meta market-seller-only"' in idx)
ok("edit form can clear product condition when selecting no condition", "body.condition=cond||null" in idx)
ok("edit form includes category, region, and dynamic fields", "id=" + chr(34) + "ek${x.id}" + chr(34) in idx and "id=" + chr(34) + "er${x.id}" + chr(34) in idx and "data-ek" in idx and "category_id,region_id,fields" in idx)
ok("standalone market uses individual cards, not featured shelf", "loadFeatured();" not in market_html and ".grid>.card" in css)
ok("featured listings receive a dedicated card class from server-provided featured flag", 'isFeatured(x) ? " featured-card" : ""' in market_html)
ok("gold featured treatment is scoped to featured cards, not every listing", ".grid>.card.featured-card .gold" in css and "linear-gradient(135deg,#fff0b5" in css and "content:none;" in css)
ok("featured badge says ad and appears only when server marks listing featured", 'class: "gold", text: "إعلان"' in market_html and 'isFeatured(x) ? " featured-card" : ""' in market_html)
ok("ordinary listings keep neutral styling without decorative frames", ".grid>.card:not(.featured-card)" in css and "border-inline-start:1px solid var(--bd" in css)
ok("featured listings are ordered before ordinary listings in API results", 'CASE WHEN l.featured_until>" + str(int(time.time())) + " THEN 0 ELSE 1 END," + SORTS[srt]' in open(os.path.join(root_dir,"server.py"),encoding="utf-8").read())
admin_html=open(os.path.join(root_dir,"static","admin.html"),encoding="utf-8").read()
ok("admin panel includes active featured list and unfeature control", "api('/admin/featured')" in admin_html and "days:0" in admin_html)
ok("admin panel allows choosing feature duration and setting featured status", "تمييز إعلان منشور" in admin_html and "days:+document.getElementById" in admin_html)
ok("service-worker cache version bumped for gold featured design", bool(cache_version) and cache_version==sw_version)

ok("home latest marketplace cards show listing photos", "home-market-photo" in idx and "l.images[0]" in idx and "home-market-no-image" in idx)
ok("home latest marketplace cards open the selected listing detail", 'href="/market.html#/l/${Number(l.id)|0}"' in idx and "onclick=\\"location.href=\'/market.html#/l/\'" not in idx)
ok("market add button routes to the existing publish form", 'id="addlisting"' in market_html and 'href="/?market-add=1"' in market_html and 'id="listing-publish"' in idx and "market-add" in idx)
ok("gold styling applies only to featured ad cards", ".card.ad.featured-card{position:relative;" in css and ".card.ad:not(.featured-card)" in css and ".card.ad{position:relative;" not in css)
ok("featured status checks reject truthy non-boolean strings", "function isFeatured(x)" in market_html and "isFeaturedListing(l)" in idx)
print("Marketplace ad-management regression checks passed.")
