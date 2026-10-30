# المرحلة 70 (م5 المحلات): تصفح العميل — GET /api/shops، صور الأصناف (menu.image_ids + قراءة /api/files للمسجَّلين)، صفحة shops.html، كارت الرئيسية، الكاش.
import struct, zlib, os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, base64, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8973; BASE = "http://127.0.0.1:%d" % PORT; HERE = os.path.dirname(os.path.abspath(__file__))
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); b = x.read(); return x.status, (b if raw else json.loads(b))
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
rd = lambda *p: open(os.path.join(HERE, *p), encoding="utf-8").read()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
own, cust, other = user("01080000001"), user("01080000002"), user("01080000003")
def png(seed=0):
    def ch(t, b): return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 4, 1, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(b"\x00" + bytes([seed % 256, 80, 160]) * 4)) + ch(b"IEND", b"")
SEED = [0]
def upload(t): SEED[0] += 1; s, r = call("POST", "/files", {"data": base64.b64encode(png(SEED[0])).decode()}, t); return s, r

# 1) المفتاح مطفي: القائمة فارغة و«enabled:false»
c, r = call("GET", "/shops"); ok("off: public list is empty and says disabled", c == 200 and r == {"enabled": False, "items": []})
call("POST", "/admin/shops-settings", {"enabled": True}, at)
S = call("POST", "/shops/apply", {"type_id": 1, "name_ar": "مطعم الأمل", "address": "شارع النصر", "phone": "01012345678", "region_id": 3}, own)[1]["id"]
S2 = call("POST", "/shops/apply", {"type_id": 2, "name_ar": "سوبر الخير", "address": "شارع السلام", "phone": "01012345679", "region_id": 4}, user("01080000004"))[1]["id"]
c, r = call("GET", "/shops"); ok("pending shops are not listed", c == 200 and r["enabled"] and r["items"] == [])
for i in (S, S2): call("POST", "/admin/shops/%d/review" % i, {"status": "approved"}, at)
call("POST", "/owner/shops/%d/open" % S, {}, own)

# 2) الفلاتر والترتيب (المفتوح أولًا)
c, r = call("GET", "/shops"); ok("approved shops listed, open first", c == 200 and [x["id"] for x in r["items"]] == [S, S2] and r["items"][0]["is_open"] and not r["items"][1]["is_open"])
ok("region filter", [x["id"] for x in call("GET", "/shops?region_id=4")[1]["items"]] == [S2])
ok("type filter", [x["id"] for x in call("GET", "/shops?type_id=1")[1]["items"]] == [S])
ok("name search, and LIKE wildcards are escaped", [x["id"] for x in call("GET", "/shops?q=" + urllib.request.quote("الأمل"))[1]["items"]] == [S] and call("GET", "/shops?q=%25")[1]["items"] == [] and call("GET", "/shops?q=_")[1]["items"] == [])
ok("bad filters are 400", call("GET", "/shops?region_id=abc")[0] == 400 and call("GET", "/shops?type_id=" + "9" * 12)[0] == 400)
ok("no private fields leak", all(set(x) == {"id", "name_ar", "type_id", "type_name", "region_id", "region_name", "address", "is_open", "item_count", "cover_file_id"} for x in call("GET", "/shops")[1]["items"]))

# 3) الأصناف والصور
f1 = upload(own)[1]["id"]; f2 = upload(own)[1]["id"]
it = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "كشري", "price": 35.5, "image_ids": [f1, f2]}, own)[1]["id"]
it2 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "شاي", "price": 5}, own)[1]["id"]
r = call("GET", "/shops")[1]["items"][0]; ok("item_count and cover image", r["item_count"] == 2 and r["cover_file_id"] == f1)
m = call("GET", "/shops/%d/menu" % S)[1]
ok("menu carries image_ids and order_enabled=false while delivery is off", m["items"][0]["image_ids"] == [f1, f2] and m["items"][1]["image_ids"] == [] and m["order_enabled"] is False)
call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 0}, at)
ok("order_enabled=true when both switches on", call("GET", "/shops/%d/menu" % S)[1]["order_enabled"] is True)
c, b = call("GET", "/files/%d" % f1, None, cust, raw=True); ok("customer can read a shop item image (png bytes)", c == 200 and b[:4] == b"\x89PNG")
ok("anonymous still cannot read files", call("GET", "/files/%d" % f1)[0] in (401, 403))
ok("customer still cannot DELETE the owner's image", call("POST", "/files/%d/delete" % f1, {}, cust)[0] == 404)
priv = upload(own)[1]["id"]; ok("a private (unattached) file stays private", call("GET", "/files/%d" % priv, None, cust)[0] == 404)
call("POST", "/owner/shops/%d/items/%d/delete" % (S, it), {}, own)
ok("image of a deleted item stops being public", call("GET", "/files/%d" % f1, None, cust)[0] in (404,))
it3 = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "فول", "price": 8, "image_ids": [priv]}, own)[1]["id"]
call("POST", "/admin/shops/%d/review" % S, {"status": "suspended", "reason": "اختبار الإيقاف"}, at)
ok("suspended shop: image hidden again", call("GET", "/files/%d" % priv, None, cust)[0] == 404)
call("POST", "/admin/shops/%d/review" % S, {"status": "approved"}, at); call("POST", "/admin/shops-settings", {"enabled": False}, at)
ok("global switch off hides the images", call("GET", "/files/%d" % priv, None, cust)[0] == 404)
call("POST", "/admin/shops-settings", {"enabled": True}, at)

# 4) الصفحة والكارت والكاش والإصدار
s = rd("static", "shops.html"); sw = rd("static", "sw.js"); ix = rd("static", "index.html")
ok("shops.html uses esc and the public endpoints only", "const esc=" in s and "/shops" in s and "/shop-types" in s and "innerHTML=" in s)
ok("service worker caches shops.html and cache bumped", '"/shops.html"' in sw and __import__("re").search(r'V = "laqino-v\d+"', sw) is not None and __import__("re").search(r"cache=laqino-v\d+", rd("VERSION")) is not None)
ok("home shows the shops card only when the section is enabled", "api('/shop-types')" in ix and "shOn?card('shops'" in ix and "/shops.html" in ix)
js = re.search(r"<script>(.*?)</script>", s, re.S).group(1); tmp = tempfile.mktemp(suffix=".js"); open(tmp, "w", encoding="utf-8").write(js)
ok("shops.html script parses (node --check)", subprocess.run(["node", "--check", tmp], capture_output=True).returncode == 0)
print("ALL PASS")
