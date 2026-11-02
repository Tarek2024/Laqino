# phase-82 (م1 تطوير المحلات): صور أصناف المحلات تظهر للجميع (حتى الزائر بلا تسجيل دخول) عبر مسار عام مخزَّن بالمتصفح، مع lazy وبديل عند الفشل.
# المسار: GET /api/shops/<محل>/images/<ملف>. اختبار الخادم حقيقي، واختبار الواجهة بمتصفح Chromium فعلي (Playwright) إن توفّر.
import struct, zlib, os, json, threading, urllib.request, urllib.error, tempfile, time, base64, re, sqlite3, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8982; BASE = "http://127.0.0.1:%d" % PORT; HERE = os.path.dirname(os.path.abspath(__file__)); DB = os.environ["LAQINO_DB"]; UPD = os.environ["LAQINO_UPLOADS"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None, raw=False, full=False):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); b = x.read(); return (x.status, (b if raw else json.loads(b))) + ((x.headers,) if full else ())
    except urllib.error.HTTPError as e: b = e.read(); return (e.code, b if raw else json.loads(b)) + ((e.headers,) if full else ())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
rd = lambda *p: open(os.path.join(HERE, *p), encoding="utf-8").read()
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def png(seed=0):
    def ch(t, b): return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 4, 1, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(b"\x00" + bytes([seed % 256, 80, 160]) * 4)) + ch(b"IEND", b"")
SEED = [0]
def upload(t): SEED[0] += 1; return call("POST", "/files", {"data": base64.b64encode(png(SEED[0])).decode()}, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
own, own2, cust = user("01082000001"), user("01082000002"), user("01082000003")
IMG = lambda s, f: "/shops/%d/images/%d" % (s, f)

# 1) المفتاح مطفي: لا صور عامة
call("POST", "/admin/shops-settings", {"enabled": True}, at)
S = call("POST", "/shops/apply", {"type_id": 1, "name_ar": "مطعم الأمل", "address": "شارع النصر", "phone": "01012345678", "region_id": 3}, own)[1]["id"]
S2 = call("POST", "/shops/apply", {"type_id": 2, "name_ar": "سوبر الخير", "address": "شارع السلام", "phone": "01012345679", "region_id": 3}, own2)[1]["id"]
for i in (S, S2): call("POST", "/admin/shops/%d/review" % i, {"status": "approved"}, at)
call("POST", "/owner/shops/%d/open" % S, {}, own)
f1, f2, f3 = upload(own), upload(own), upload(own2)
i1 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "كشري", "price": 35.5, "image_ids": [f1, f2]}, own)[1]["id"]
i3 = call("POST", "/owner/shops/%d/items" % S2, {"name_ar": "زيت", "price": 50, "image_ids": [f3]}, own2)[1]["id"]
priv = upload(own)
call("POST", "/admin/shops-settings", {"enabled": False}, at)
ok("switch off: public image route is 404", call("GET", IMG(S, f1))[0] == 404)
call("POST", "/admin/shops-settings", {"enabled": True}, at)

# 2) الزائر بلا تسجيل دخول يقرأ الصورة مع كاش عام
c, b, h = call("GET", IMG(S, f1), raw=True, full=True)
ok("anonymous gets the png bytes", c == 200 and b[:4] == b"\x89PNG" and h["Content-Type"] == "image/png")
ok("browser-cacheable (public, max-age)", "public" in h["Cache-Control"] and "max-age=3600" in h["Cache-Control"])
ok("second image of the same item also served", call("GET", IMG(S, f2), raw=True)[0] == 200)
ok("logged-in customer reads it too", call("GET", IMG(S, f1), None, cust, raw=True)[0] == 200)

# 3) لا تسريب: ملف غير تابع للمحل/خاص/معرّف غير صالح
ok("file of another shop through this shop id is 404", call("GET", IMG(S, f3))[0] == 404 and call("GET", IMG(S2, f1))[0] == 404)
ok("private unattached file is 404", call("GET", IMG(S, priv))[0] == 404)
ok("unknown ids and non-numeric ids are 404", call("GET", IMG(S, 99999))[0] == 404 and call("GET", IMG(99999, f1))[0] == 404 and call("GET", "/shops/%d/images/abc" % S)[0] == 404)
ok("/api/files is still private to anonymous (unchanged)", call("GET", "/files/%d" % f1)[0] in (401, 403))
ok("route is read-only (POST not served)", call("POST", IMG(S, f1), {})[0] in (404, 405))

# 4) حالة الصنف/المحل/المنطقة تقفل الصورة
sql("UPDATE shops SET status='suspended' WHERE id=?", S2); ok("suspended shop image is 404", call("GET", IMG(S2, f3))[0] == 404); sql("UPDATE shops SET status='approved' WHERE id=?", S2)
ok("approved again → visible", call("GET", IMG(S2, f3), raw=True)[0] == 200)
sql("INSERT OR REPLACE INTO settings VALUES('shops_regions','[4]')"); ok("shop outside enabled regions is 404", call("GET", IMG(S, f1))[0] == 404)
sql("DELETE FROM settings WHERE key='shops_regions'"); ok("regions cleared → visible", call("GET", IMG(S, f1), raw=True)[0] == 200)
call("POST", "/owner/shops/%d/items/%d/delete" % (S2, i3), {}, own2); ok("deleted item image is 404", call("GET", IMG(S2, f3))[0] == 404)
ok("file missing on disk is 404 not 500", (lambda p: (os.remove(os.path.join(UPD, p)), call("GET", IMG(S, f2))[0])[1] == 404)(sql("SELECT path FROM files WHERE id=?", f2)[0][0]))

# 5) الواجهة (static)
s = rd("static", "shops.html"); sw = rd("static", "sw.js")
ok("shops.html: direct public url + lazy + decoding + onerror fallback", "/api/shops/" in s and "/images/" in s and 'loading=\\"lazy\\"' in s.replace('loading="lazy"', 'loading=\\"lazy\\"') and "decoding=" in s and "onerror=" in s and "imf(" in s)
ok("shops.html no longer needs a token to show pictures (no files fetch with Authorization)", "fetch('/api/files/'" not in s and "createObjectURL" not in s)
ok("shops.html still escapes server text", "const esc=" in s and "esc(s.name_ar)" in s)
js = re.findall(r"<script>(.*?)</script>", s, re.S)[0]; tmp = tempfile.mktemp(suffix=".js"); open(tmp, "w", encoding="utf-8").write(js)
ok("shops.html script parses (node --check)", subprocess.run(["node", "--check", tmp], capture_output=True).returncode == 0)
ok("cache name bumped to the VERSION value", re.search(r'V = "(laqino-v\d+)"', sw).group(1) == re.search(r"cache=(laqino-v\d+)", rd("VERSION")).group(1))

# 6) متصفح حقيقي: زائر + مسجَّل
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(); res = {}
        for who, tok in (("guest", None), ("customer", cust)):
            ctx = br.new_context(viewport={"width": 390, "height": 800}); pg = ctx.new_page()
            if tok: pg.add_init_script("localStorage.setItem('t','%s')" % tok)
            pg.goto(BASE + "/shops.html"); pg.wait_for_selector(".shc", timeout=8000); pg.wait_for_timeout(700)
            cards = pg.evaluate("[...document.querySelectorAll('.shc')].map(c=>{const i=c.querySelector('.cv img');return {img:!!i,ok:i?(i.complete&&i.naturalWidth>0):false,ph:!!c.querySelector('.cv .imph'),name:c.querySelector('b').textContent}})")
            res[who + "_cards"] = cards
            res[who + "_lazy"] = pg.evaluate("[...document.querySelectorAll('.cv img')].every(i=>i.loading==='lazy')")
            pg.click(".shc"); pg.wait_for_selector(".gi img, .gi .imph", timeout=8000); pg.wait_for_timeout(700)
            res[who + "_items"] = pg.evaluate("[...document.querySelectorAll('#m .gi')].map(c=>({imgs:[...c.querySelectorAll('.zb img')].map(i=>i.complete&&i.naturalWidth>0),ph:!!c.querySelector('.zb .imph')}))")
            ctx.close()
        # الفشل ← أيقونة بدل الصورة المكسورة
        os.remove(os.path.join(UPD, sql("SELECT path FROM files WHERE id=?", f1)[0][0]))
        ctx = br.new_context(); pg = ctx.new_page(); pg.goto(BASE + "/shops.html#s%d" % S); pg.wait_for_selector("#m .gi", timeout=8000); pg.wait_for_timeout(900)
        res["fallback"] = pg.evaluate("({broken:document.querySelectorAll('.gi .zb img').length,ph:document.querySelectorAll('.gi .imph').length})")
        res["fallback_card"] = None
        pg.goto(BASE + "/shops.html"); pg.wait_for_selector(".shc", timeout=8000); pg.wait_for_timeout(900)
        res["fallback_card"] = pg.evaluate("({img:document.querySelectorAll('.shc .cv img').length,ph:document.querySelectorAll('.shc .cv .imph').length})")
        br.close()
    for who in ("guest", "customer"):
        cs = res[who + "_cards"]
        ok("browser/%s: shop card shows a real cover image (loaded, no token needed)" % who, any(x["img"] and x["ok"] for x in cs))
        ok("browser/%s: card images are lazy" % who, res[who + "_lazy"])
        ok("browser/%s: shop without pictures shows the type icon tile" % who, any(x["ph"] and not x["img"] for x in cs))
        its = res[who + "_items"]
        ok("browser/%s: menu item pictures load" % who, any(x["imgs"] and all(x["imgs"]) for x in its))
    ok("browser: a broken image is swapped for the icon tile in the menu", res["fallback"]["ph"] >= 1)
    ok("browser: a broken cover is swapped for the icon tile on the card", res["fallback_card"]["ph"] >= 1)
except ImportError:
    print("SKIP browser checks (playwright not installed)")
print("ALL OK")
