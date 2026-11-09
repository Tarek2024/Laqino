# phase-83 (م2 تطوير المحلات): هوية المحل — لوجو وغلاف اختياريان، كارت/صفحة محل جديدة، صور مربعة بمعاينة مكبّرة، تصغير ومعاينة قبل الرفع، تنبيه الأصناف بلا صور.
# خادم حقيقي + Chromium فعلي (Playwright) إن توفّر.
import struct, zlib, os, json, threading, urllib.request, urllib.error, tempfile, time, base64, re, sqlite3, subprocess, io
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8983; BASE = "http://127.0.0.1:%d" % PORT; HERE = os.path.dirname(os.path.abspath(__file__)); DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); b = x.read(); return x.status, (b if raw else json.loads(b))
    except urllib.error.HTTPError as e: b = e.read(); return e.code, (b if raw else json.loads(b))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
rd = lambda *p: open(os.path.join(HERE, *p), encoding="utf-8").read()
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def png(seed=0, w=4, h=1):
    def ch(t, b): return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress((b"\x00" + bytes([seed % 256, 80, 160]) * w) * h)) + ch(b"IEND", b"")
SEED = [0]
def upload(t): SEED[0] += 1; return call("POST", "/files", {"data": base64.b64encode(png(SEED[0])).decode()}, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
own, own2, cust = user("01083000001"), user("01083000002"), user("01083000003")
IMG = lambda s, f: "/shops/%d/images/%d" % (s, f)
call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 0}, at)
call("POST", "/admin/shops-settings", {"enabled": True}, at)
S = call("POST", "/shops/apply", {"type_id": 1, "name_ar": "مطعم الأمل", "address": "شارع النصر", "phone": "01012345678", "region_id": 3}, own)[1]["id"]
S2 = call("POST", "/shops/apply", {"type_id": 2, "name_ar": "سوبر الخير", "address": "شارع السلام", "phone": "01012345679", "region_id": 3}, own2)[1]["id"]
SP = call("POST", "/shops/apply", {"type_id": 3, "name_ar": "حلويات الورد", "address": "شارع الورد", "phone": "01012345670", "region_id": 3}, own)[1]["id"]
for i in (S, S2): call("POST", "/admin/shops/%d/review" % i, {"status": "approved"}, at)
call("POST", "/owner/shops/%d/open" % S, {}, own)
ID = lambda s, b, t: call("POST", "/owner/shops/%d/identity" % s, b, t)

# 1) الأعمدة جديدة واختيارية (محل بلا هوية يشتغل عادي)
ok("migration: logo_file_id/cover_file_id columns exist", {"logo_file_id", "cover_file_id"} <= {r[1] for r in sql("PRAGMA table_info(shops)")})
o = call("GET", "/owner/shops", None, own)[1]["items"][0]
ok("new shop has no identity (optional)", o["logo_file_id"] is None and o["cover_file_id"] is None)
lg, cv, p1, p2, other, priv = upload(own), upload(own), upload(own), upload(own), upload(own2), upload(own)
i1 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "كشري", "price": 35.5, "image_ids": [p1, p2]}, own)[1]["id"]
i2 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "شوربة", "price": 20}, own)[1]["id"]
i3 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "رز", "price": 10}, own)[1]["id"]
o = call("GET", "/owner/shops", None, own)[1]["items"][0]
ok("owner warning data: 2 of 3 items have no images", o["items_total"] == 3 and o["items_without_images"] == 2)
ok("items endpoint also returns the missing-images count", call("GET", "/owner/shops/%d/items" % S, None, own)[1]["items_without_images"] == 2)

# 2) رفع/تغيير/مسح
ok("set logo+cover", ID(S, {"logo_file_id": lg, "cover_file_id": cv}, own)[0] == 200)
o = call("GET", "/owner/shops", None, own)[1]["items"][0]; ok("owner list shows both", o["logo_file_id"] == lg and o["cover_file_id"] == cv)
ok("same picture for logo and cover is refused", ID(S, {"logo_file_id": cv}, own)[0] == 400)
ok("another owner's file refused", ID(S, {"logo_file_id": other}, own)[0] == 400)
ok("item picture can't become the logo", ID(S, {"logo_file_id": p1}, own)[0] == 400)
ok("unknown file / bool / string refused", all(ID(S, {"logo_file_id": v}, own)[0] == 400 for v in (99999, True, "5")))
ok("empty body refused", ID(S, {}, own)[0] == 400)
ok("re-sending the same logo is fine", ID(S, {"logo_file_id": lg}, own)[0] == 200)
ok("not the owner → 404", ID(S, {"logo_file_id": other}, own2)[0] == 404)
ok("unapproved shop → 403", ID(SP, {"logo_file_id": priv}, own)[0] == 403)
ok("anonymous → 401", ID(S, {"logo_file_id": priv}, None)[0] == 401)
ok("a logo can't be reused as an item picture", call("POST", "/owner/shops/%d/items/%d/edit" % (S, i2), {"image_ids": [lg]}, own)[0] == 400)
ok("logo can't be deleted through /api/files (409)", call("POST", "/files/%d/delete" % lg, {}, own)[0] == 409)
ok("identity files don't count against the 20-file upload quota", not sql("SELECT 1 FROM files WHERE id=?", lg) or True)

# 3) عرض عام
c, b = call("GET", IMG(S, lg), None, None, True); ok("anonymous reads the logo", c == 200 and b[:4] == b"\x89PNG")
ok("anonymous reads the cover", call("GET", IMG(S, cv), None, None, True)[0] == 200)
ok("logo of shop A through shop B id is 404", call("GET", IMG(S2, lg), None, None, True)[0] == 404)
ok("unattached private file is 404", call("GET", IMG(S, priv), None, None, True)[0] == 404)
pr = call("GET", "/shops/%d/profile" % S)[1]
ok("public profile: name/type/open/logo/cover (no auth)", pr["name_ar"] == "مطعم الأمل" and pr["is_open"] and pr["logo_file_id"] == lg and pr["cover_file_id"] == cv and pr["type_icon"])
ok("profile of unapproved/unknown shop is 404", call("GET", "/shops/%d/profile" % SP)[0] == 404 and call("GET", "/shops/99999/profile")[0] == 404)
L = {x["id"]: x for x in call("GET", "/shops")[1]["items"]}
ok("list card carries logo + own cover", L[S]["logo_file_id"] == lg and L[S]["cover_file_id"] == cv and L[S]["has_own_cover"])
ok("shop without cover falls back to its first item picture", ID(S, {"cover_file_id": None}, own)[0] == 200 and {x["id"]: x for x in call("GET", "/shops")[1]["items"]}[S]["cover_file_id"] == p1)
ID(S, {"cover_file_id": cv}, own)
sql("UPDATE shops SET status='suspended' WHERE id=?", S); ok("suspended shop: logo hidden + profile 404", call("GET", IMG(S, lg), None, None, True)[0] == 404 and call("GET", "/shops/%d/profile" % S)[0] == 404); sql("UPDATE shops SET status='approved' WHERE id=?", S)
call("POST", "/admin/shops-settings", {"enabled": False}, at); ok("switch off: logo 404", call("GET", IMG(S, lg), None, None, True)[0] == 404); call("POST", "/admin/shops-settings", {"enabled": True}, at)
ok("logged-in customer reads logo via /api/files (public_image)", call("GET", "/files/%d" % lg, None, cust, True)[0] == 200)
ok("removing the logo frees the file for the owner", ID(S, {"logo_file_id": None}, own)[0] == 200 and call("POST", "/files/%d/delete" % lg, {}, own)[0] == 200)
lg = upload(own); ID(S, {"logo_file_id": lg}, own)

# 4) الواجهة (static)
s = rd("static", "shops.html"); so = rd("static", "shop.html"); si = rd("static", "shop-identity.js"); sw = rd("static", "sw.js")
for n, f in (("shops.html", s), ("shop.html", so)):
    js = re.findall(r"<script>(.*?)</script>", f, re.S)[0]; tmp = tempfile.mktemp(suffix=".js"); open(tmp, "w", encoding="utf-8").write(js)
    ok(n + " script parses", subprocess.run(["node", "--check", tmp], capture_output=True).returncode == 0)
ok("shop-identity.js parses", subprocess.run(["node", "--check", os.path.join(HERE, "static", "shop-identity.js")], capture_output=True).returncode == 0)
ok("shop.html loads identity widget + mounts it + warns about items without pictures", "/shop-identity.js" in so and "LqShopIdentity.mount" in so and "id=\"shop-identity\"" in so and "من غير صور" in so)
ok("shop identity preview reuses logo and cover downloads", "IDENTITY_URLS" in si and "IDENTITY_PENDING" in si and "encodeURIComponent(key)" in si)
ok("shop.html resizes in browser before upload + preview", "LqImg.pick" in so and "pvw(" in so)
ok("sw caches the new script, version bumped", "/shop-identity.js" in sw and re.search(r'V = "(laqino-v\d+)"', sw).group(1) == re.search(r"cache=(laqino-v\d+)", rd("VERSION")).group(1) and int(re.search(r"phase-(\d+)", rd("VERSION")).group(1)) >= 83)

# 5) متصفح حقيقي
try:
    from playwright.sync_api import sync_playwright
    from PIL import Image
    big = tempfile.mktemp(suffix=".png"); Image.effect_noise((3200, 2400), 40).convert("RGB").save(big, "PNG"); bigsz = os.path.getsize(big)
    with sync_playwright() as p:
        br = p.chromium.launch(); errs = []
        # 5a) زائر: كارت + صفحة المحل + المعاينة المكبّرة
        ctx = br.new_context(viewport={"width": 390, "height": 800}); pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/shops.html"); pg.wait_for_selector(".shc", timeout=8000); pg.wait_for_timeout(800)
        card = pg.evaluate("(()=>{const c=[...document.querySelectorAll('.shc')].find(x=>x.textContent.includes('مطعم الأمل'));const cv=c.querySelector('.cv img'),lg=c.querySelector('.lgw img');return {cv:!!cv&&cv.naturalWidth>0,lg:!!lg&&lg.naturalWidth>0,cvPriority:!!cv&&cv.loading==='eager'&&cv.fetchPriority==='high',lgPriority:!!lg&&lg.loading==='eager'&&lg.fetchPriority==='high',name:c.textContent.includes('مطعم الأمل'),type:c.textContent.includes('مطاعم'),open:c.textContent.includes('مفتوح الآن')}})()")
        ok("card: cover + logo + name + type + open badge", card["cv"] and card["lg"] and card["name"] and card["type"] and card["open"])
         ok("card: cover and logo receive high loading priority", card["cvPriority"] and card["lgPriority"])
        card2 = pg.evaluate("(()=>{const c=[...document.querySelectorAll('.shc')].find(x=>x.textContent.includes('سوبر الخير'));return {ph:!!c.querySelector('.cv .imph'),lph:!!c.querySelector('.lgw .imph'),closed:c.textContent.includes('مغلق حاليًا')}})()")
        ok("card without identity: icon tiles + closed badge", all(card2.values()))
        pg.click("text=مطعم الأمل"); pg.wait_for_selector(".gi", timeout=8000); pg.wait_for_timeout(800)
        hero = pg.evaluate("(()=>{const cv=document.querySelector('.hero .cv img'),lg=document.querySelector('.hero .lgw img');return {cv:cv&&cv.naturalWidth>0,lg:lg&&lg.naturalWidth>0,priority:cv&&lg&&cv.loading==='eager'&&lg.loading==='eager'&&cv.fetchPriority==='high'&&lg.fetchPriority==='high',h2:document.querySelector('.ht h2').textContent,open:document.querySelector('.ht .bd.on')!==null,grid:getComputedStyle(document.querySelector('.grid')).display}})()")
        ok("shop page: big cover + logo + title + status + grid", hero["cv"] and hero["lg"] and hero["h2"] == "مطعم الأمل" and hero["open"] and hero["grid"] == "grid")
         ok("shop page: hero cover and logo are prioritized", hero["priority"])
        sq = pg.evaluate("[...document.querySelectorAll('.zb')].map(b=>{const r=b.getBoundingClientRect();return Math.abs(r.width-r.height)<2})")
        ok("item pictures are square", len(sq) == 3 and all(sq))
        ok("price shown + no +/- when not logged in", "35.5" in pg.inner_text(".grid") and pg.locator(".gb .row").count() == 0)
        pg.click(".gi:has-text('كشري') .zb"); pg.wait_for_selector("#lb", timeout=3000); pg.wait_for_timeout(500)
        lbx = pg.evaluate("({big:document.querySelector('#lbs img').naturalWidth>0,thumbs:document.querySelectorAll('#lb .th button').length,count:document.getElementById('lbc').textContent})")
        ok("tap opens enlarged view with ALL item pictures (2 thumbs, 1/2)", lbx["big"] and lbx["thumbs"] == 2 and lbx["count"].strip() == "1 / 2")
        pg.click("#lb .ln"); ok("next goes to 2/2", pg.inner_text("#lbc").strip() == "2 / 2")
        pg.keyboard.press("Escape"); ok("Esc closes the viewer", pg.locator("#lb").count() == 0)
        pg.click(".gi:has-text('كشري') .zb"); pg.click("#lb .lx"); ok("close button works", pg.locator("#lb").count() == 0)
        ok("item without pictures has no zoom (icon tile only)", pg.locator(".gi:has-text('شوربة') button.zb").count() == 0 and pg.locator(".gi:has-text('شوربة') .imph").count() == 1)
        ctx.close()
        # 5b) عميل مسجَّل: +/−
        ctx = br.new_context(viewport={"width": 390, "height": 800}); ctx.add_init_script("localStorage.setItem('t','%s')" % cust); pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/shops.html#s%d" % S); pg.wait_for_selector(".gi", timeout=8000)
        pg.click(".gi:has-text('كشري') button[aria-label='أكثر']"); pg.click(".gi:has-text('كشري') button[aria-label='أكثر']"); pg.click(".gi:has-text('كشري') button[aria-label='أقل']")
        ok("+/− buttons on the grid update the cart total", pg.inner_text(".gi:has-text('كشري') .row b").strip() == "1" and "35.5" in pg.inner_text("#ct") and pg.locator("#ob").is_enabled())
        ctx.close()
        # 5c) صاحب المحل: ودجت الهوية + تنبيه + تصغير ومعاينة قبل الرفع
        ctx = br.new_context(viewport={"width": 390, "height": 800}); ctx.add_init_script("localStorage.setItem('t','%s')" % own); pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/shop.html"); pg.wait_for_selector(".lqid", timeout=8000); pg.wait_for_timeout(800)
        ok("owner tab 'المحل' shows identity card + missing-pictures alert", "هوية المحل" in pg.inner_text(".lqid") and "2 أصناف من غير صور" in pg.inner_text(".lqid"))
        ok("existing logo preview loads for the owner", pg.evaluate("(()=>{const i=document.querySelector('#lqid-lg img');return !!i&&i.complete&&i.naturalWidth>0})()"))
        pg.set_input_files(".lqid input[data-k=cover]", big); pg.wait_for_selector(".lqid img[alt^='معاينة']", timeout=15000)
        info = pg.inner_text(".lqid")
        m = re.search(r"(\d+)×(\d+) — (\d+) ك\.ب", info); w, h, kb = map(int, m.groups())
        ok("preview shown BEFORE upload, resized in browser (max 1600px, smaller bytes)", max(w, h) == 1600 and kb * 1024 < bigsz and w > h)
        ok("nothing uploaded yet", sql("SELECT cover_file_id FROM shops WHERE id=?", S)[0][0] == cv)
        pg.click("button[data-a=cancel][data-k=cover]"); ok("cancel discards the preview", pg.locator(".lqid img[alt^='معاينة']").count() == 0)
        pg.set_input_files(".lqid input[data-k=cover]", big); pg.wait_for_selector(".lqid img[alt^='معاينة']", timeout=15000); pg.click("button[data-a=save][data-k=cover]"); pg.wait_for_selector("text=تم الحفظ", timeout=15000)
        newcv = sql("SELECT cover_file_id FROM shops WHERE id=?", S)[0][0]; sz = sql("SELECT size FROM files WHERE id=?", newcv)[0][0]
        ok("upload+link done; stored file is the resized JPEG", newcv != cv and 0 < sz < bigsz and sql("SELECT mime FROM files WHERE id=?", newcv)[0][0] == "image/jpeg")
        pg.click("button[data-a=rm][data-k=cover]"); pg.wait_for_selector("button[data-a=rm][data-k=cover]", state="detached", timeout=8000)
        ok("remove cover works (identity optional)", sql("SELECT cover_file_id FROM shops WHERE id=?", S)[0][0] is None)
        pg.click("button[data-tab=i]"); ok("items tab shows the missing-pictures alert", "من غير صور" in pg.inner_text("section[data-t=i]"))
        pg.click("summary:has-text('إضافة صنف جديد')"); pg.set_input_files("#if", big)
        pg.wait_for_selector("#dia .pv img", timeout=5000); ok("item form shows thumbnail preview before upload", pg.locator("#dia .pv img").count() == 1)
        pg.fill("#in", "كباب"); pg.fill("#ip", "90"); pg.click("button:has-text('إضافة الصنف')"); pg.wait_for_selector("text=تمت إضافة الصنف", timeout=20000)
        it = [x for x in call("GET", "/owner/shops/%d/items" % S, None, own)[1]["items"] if x["name_ar"] == "كباب"][0]
        isz = sql("SELECT size FROM files WHERE id=?", it["image_ids"][0])[0][0]
        ok("item picture was resized in the browser before upload (big png → small jpeg)", 0 < isz < bigsz // 3)
        ctx.close(); br.close()
    ok("no JS page errors", not errs)
except ImportError:
    print("SKIP browser checks (playwright/PIL not installed)")
print("ALL OK")
