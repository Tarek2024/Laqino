# phase-32: Souq tab cards open the detail page (with the image gallery)
import os, sys, json, threading, time, tempfile, shutil, sqlite3, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); UP = tempfile.mkdtemp(); os.environ["LAQINO_UPLOADS"] = UP
os.environ["LAQINO_AUTO_BACKUP"] = "0"
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8952; BASE = "http://127.0.0.1:%d" % PORT
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
call("POST", "/register", {"phone": "01030000001", "name": "seller", "password": "password1"})
sql = lambda q, *a: (lambda cn: (cn.execute(q, a).fetchall(), cn.commit(), cn.close())[0])(sqlite3.connect(DB))
uid = sql("select id from users where phone='01030000001'")[0][0]
root = sql("select id from categories where section='souq' and parent_id is null")[0][0]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "x", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [x for x in call("GET", "/categories?section=souq")[1] if x["parent_id"] is not None][0]["id"]
now = int(time.time())
imgs = ["logo.jpg", "mascot.jpg", "icon-512.png"]
lids = []
for n in range(3):
    lid = sql("INSERT INTO listings(user_id,category_id,region_id,title,description,price,status,created_at) VALUES(?,?,3,?,?,100,'approved',?) RETURNING id", uid, cat, "listing %d" % n, "desc", now)[0][0]
    lids.append(lid)
    for i, nm in enumerate(imgs if n == 0 else imgs[:1]):
        name = "f%d_%d" % (n, i); shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "assets") + "/" + nm, os.path.join(UP, name))
        fid = sql("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?) RETURNING id", uid, name, "image/png" if nm.endswith("png") else "image/jpeg", 1000, now)[0][0]
        sql("INSERT INTO market_files(file_id,user_id,created_at) VALUES(?,?,?)", fid, uid, now)
        sql("INSERT INTO listing_images(listing_id,file_id,position,created_at) VALUES(?,?,?,?)", lid, fid, i, now)


res = []
def ok(n, c):
    print(("PASS " if c else "FAIL ") + n); res.append(bool(c))
ok("API: listing 1 carries 3 images", len(call("GET", "/listings/%d" % lids[0])[1]["images"]) == 3)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, service_workers="block")
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/"); pg.wait_for_timeout(800)
    pg.evaluate("go(1)"); pg.wait_for_selector(".card.ad", timeout=8000)
    ok("souq tab lists the 3 ads", pg.locator(".card.ad").count() == 3)
    multi = pg.locator(".card.ad", has=pg.locator(".tg", has_text="3")).count()
    ok("multi-image ad shows an image-count tag", multi == 1)
    # tapping a button inside the card must NOT open the detail page
    btn = pg.locator(".card.ad button").first
    if btn.count():
        btn.tap(); pg.wait_for_timeout(500)
        ok("tapping a card button does not navigate to the detail", "/market.html" not in pg.url)
    pg.goto(BASE + "/"); pg.wait_for_timeout(500); pg.evaluate("go(1)"); pg.wait_for_selector(".card.ad")
    card = pg.locator(".card.ad", has=pg.locator(".tg", has_text="3")).first
    card.locator("h3").tap(); pg.wait_for_url("**/market.html#/l/%d" % lids[0], timeout=6000)
    pg.wait_for_selector(".det .main", timeout=6000)
    ok("tapping the ad opens its detail page", pg.url.endswith("/market.html#/l/%d" % lids[0]))
    ok("detail shows all 3 thumbnails", pg.locator(".thumbs img").count() == 3)
    pg.locator(".thumbs img").nth(2).tap(); pg.wait_for_timeout(300)
    ok("tapping a thumbnail switches the main image", pg.evaluate("document.querySelector('.det .main').src").endswith("/images/3"))
    ok("no page errors", not errs)
    b.close()
print("DONE %d/%d" % (sum(res), len(res))); exit(0 if all(res) else 1)
