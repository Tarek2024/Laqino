# المرحلة 68 (م3 من خطة المحلات): أصناف المحل (API). قاعدة مؤقتة معزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, base64, zlib, struct
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, account
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8968; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def png(seed=0):
    def ch(t, b): return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    raw = b"\x00" + bytes([seed % 256, 80, 160]) * 4
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 4, 1, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")
def up(t, seed=0): s, r = call("POST", "/files", {"data": base64.b64encode(png(seed)).decode()}, t); return r.get("id") if s == 201 else None
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
o1, o1id = user("01080000001"); o2, o2id = user("01080000002"); cu, cuid = user("01080000003")
R1 = call("GET", "/regions?parent_id=3")[1][0]["id"]
call("POST", "/admin/shops-settings", {"enabled": True}, at)
def mk(t, tid, nm, approve=True):
    r = call("POST", "/shops/apply", {"type_id": tid, "name_ar": nm, "address": "شارع النصر", "phone": "01012345678", "region_id": R1}, t)[1]["id"]
    if approve: call("POST", "/admin/shops/%d/review" % r, {"status": "approved"}, at)
    return r
S1 = mk(o1, 1, "مطعم الأمل"); S2 = mk(o2, 2, "سوبر ماركت النور"); SP = mk(cu, 3, "حلويات معلقة", approve=False)
I = lambda s: "/owner/shops/%d/items" % s

# ---- الإنشاء والقراءة
r = call("POST", I(S1), {"name_ar": "كشري", "price": 35.5, "description": "طبق كبير"}, o1)
ok("create item 201", r[0] == 201); i1 = r[1]["id"]
r = call("GET", I(S1), None, o1)
ok("list returns the item with price/availability/empty images", r[0] == 200 and r[1]["items"][0] == {"id": i1, "name_ar": "كشري", "description": "طبق كبير", "price": 35.5, "is_available": True, "sort": 1, "image_ids": [], "created_at": r[1]["items"][0]["created_at"]} and r[1]["max_images"] == 5 and r[1]["require_image"] is False)
ok("second item sorts after the first", call("POST", I(S1), {"name_ar": "فول", "price": 10}, o1)[0] == 201 and [x["name_ar"] for x in call("GET", I(S1), None, o1)[1]["items"]] == ["كشري", "فول"])

# ---- الصلاحيات
ok("anonymous 401", call("GET", I(S1))[0] == 401)
ok("another owner gets 404 (existence not leaked)", call("GET", I(S1), None, o2)[0] == 404 and call("POST", I(S1), {"name_ar": "اختراق", "price": 5}, o2)[0] == 404)
ok("owner of a pending shop gets 403", call("GET", I(SP), None, cu)[0] == 403 and call("POST", I(SP), {"name_ar": "صنف", "price": 5}, cu)[0] == 403)
ok("admin who is not the owner gets 404", call("GET", I(S1), None, at)[0] == 404)
ok("cannot edit an item through another shop's path", call("POST", I(S2) + "/%d/edit" % i1, {"price": 1}, o2)[0] == 404)

# ---- التحقق من المدخلات
bad = lambda b: call("POST", I(S1), b, o1)[0]
ok("name too short / missing -> 400", bad({"name_ar": "ا", "price": 5}) == 400 and bad({"price": 5}) == 400)
ok("price must be > 0, finite, numeric, <= 1,000,000", all(bad({"name_ar": "صنف", "price": p}) == 400 for p in (0, -5, "abc", True, None, 1000001, "nan", "inf")))
ok("is_available must be a boolean", bad({"name_ar": "صنف", "price": 5, "is_available": "yes"}) == 400)
ok("price rounds to 2 decimals", call("POST", I(S1), {"name_ar": "بسبوسة", "price": "12.345"}, o1)[0] == 201 and call("GET", I(S1), None, o1)[1]["items"][-1]["price"] == 12.35)

# ---- التعديل وغير متاح
ok("edit availability only", call("POST", I(S1) + "/%d/edit" % i1, {"is_available": False}, o1)[0] == 200)
it = call("GET", I(S1), None, o1)[1]["items"][0]
ok("only availability changed", it["is_available"] is False and it["name_ar"] == "كشري" and it["price"] == 35.5)
ok("edit name+price+clear description", call("POST", I(S1) + "/%d/edit" % i1, {"name_ar": "كشري كبير", "price": 40, "description": ""}, o1)[0] == 200 and call("GET", I(S1), None, o1)[1]["items"][0]["description"] == "")
ok("edit with invalid price -> 400 and nothing changed", call("POST", I(S1) + "/%d/edit" % i1, {"price": -1}, o1)[0] == 400 and call("GET", I(S1), None, o1)[1]["items"][0]["price"] == 40)

# ---- الصور
f1, f2, f3 = up(o1, 1), up(o1, 2), up(o1, 3); fo2 = up(o2, 9)
r = call("POST", I(S1) + "/%d/edit" % i1, {"image_ids": [f1, f2]}, o1)
ok("link two images in order", r[0] == 200 and call("GET", I(S1), None, o1)[1]["items"][0]["image_ids"] == [f1, f2])
ok("reorder images", call("POST", I(S1) + "/%d/edit" % i1, {"image_ids": [f2, f1]}, o1)[0] == 200 and call("GET", I(S1), None, o1)[1]["items"][0]["image_ids"] == [f2, f1])
ok("another user's file rejected", call("POST", I(S1) + "/%d/edit" % i1, {"image_ids": [fo2]}, o1)[0] == 400)
ok("nonexistent / duplicate / non-int / too many rejected", all(call("POST", I(S1) + "/%d/edit" % i1, {"image_ids": b}, o1)[0] == 400 for b in ([99999], [f1, f1], ["1"], [True], "x", [f1, f2, f3, 1, 2, 3])))
i2 = call("GET", I(S1), None, o1)[1]["items"][1]["id"]
ok("an image already used by another item is rejected", call("POST", I(S1) + "/%d/edit" % i2, {"image_ids": [f1]}, o1)[0] == 400)
ok("create with images", (lambda r: r[0] == 201 and call("GET", I(S1), None, o1)[1]["items"][-1]["image_ids"] == [f3])(call("POST", I(S1), {"name_ar": "صنف بصورة", "price": 7, "image_ids": [f3]}, o1)))
# ملفات لا تصلح كصورة صنف: ملف سوق/روشتة/مرتبط
mf = sql("INSERT INTO market_files(file_id,user_id,created_at) SELECT ?,?,? ", up(o1, 5), o1id, 1) or None
fm = sql("SELECT file_id FROM market_files ORDER BY file_id DESC LIMIT 1")[0][0]
ok("a market-linked upload cannot be used as an item image", call("POST", I(S1) + "/%d/edit" % i2, {"image_ids": [fm]}, o1)[0] == 400)
ok("deleting a linked image through /api/files is blocked (409)", call("POST", "/files/%d/delete" % f1, None, o1)[0] == 409)
ok("owner can still read the image file", urllib.request.urlopen(urllib.request.Request(BASE + "/api/files/%d" % f1, headers={"Authorization": "Bearer " + o1})).status == 200)

# ---- الحذف
r = call("POST", I(S1) + "/%d/delete" % i1, None, o1)
ok("delete item returns freed image ids", r[0] == 200 and sorted(r[1]["freed_image_ids"]) == sorted([f1, f2]))
ok("deleted item gone from list, row kept as 'deleted'", i1 not in [x["id"] for x in call("GET", I(S1), None, o1)[1]["items"]] and sql("SELECT status FROM shop_items WHERE id=?", i1)[0][0] == "deleted")
ok("freed image can now be deleted by the owner", call("POST", "/files/%d/delete" % f1, None, o1)[0] == 200)
ok("editing/deleting a deleted item -> 404", call("POST", I(S1) + "/%d/edit" % i1, {"price": 5}, o1)[0] == 404 and call("POST", I(S1) + "/%d/delete" % i1, None, o1)[0] == 404)

# ---- require_image لنوع معيّن
sql("UPDATE shop_types SET require_image=1 WHERE id=2")
ok("type with require_image: create without image -> 400", call("POST", I(S2), {"name_ar": "زيت", "price": 50}, o2)[0] == 400)
fi = up(o2, 7)
r = call("POST", I(S2), {"name_ar": "زيت", "price": 50, "image_ids": [fi]}, o2); iz = r[1]["id"]
ok("with an image it is accepted", r[0] == 201)
ok("cannot remove the last image of a require_image item", call("POST", I(S2) + "/%d/edit" % iz, {"image_ids": []}, o2)[0] == 400)
ok("other edits on it still work", call("POST", I(S2) + "/%d/edit" % iz, {"price": 55}, o2)[0] == 200)

# ---- الحد الأقصى
c = sqlite3.connect(DB); now = int(time.time())
n = c.execute("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active'", (S1,)).fetchone()[0]
for k in range(300 - n): c.execute("INSERT INTO shop_items(shop_id,name_ar,price,sort,created_at,updated_at) VALUES(?,?,?,?,?,?)", (S1, "x%d" % k, 5, 100 + k, now, now))
c.commit(); c.close()
ok("301st active item -> 429 and rolled back", call("POST", I(S1), {"name_ar": "زيادة", "price": 5}, o1)[0] == 429 and sql("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active'", S1)[0][0] == 300)
ok("deleting frees a slot", call("POST", I(S1) + "/%d/delete" % i2, None, o1)[0] == 200 and call("POST", I(S1), {"name_ar": "بعد الحذف", "price": 5}, o1)[0] == 201)

# ---- التدقيق والمحل الموقوف
ok("audit log has item actions", sql("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'shopitem.%'")[0][0] >= 5)
call("POST", "/admin/shops/%d/review" % S2, {"status": "suspended", "reason": "مخالفة"}, at)
ok("suspended shop: owner cannot manage items (403)", call("GET", I(S2), None, o2)[0] == 403 and call("POST", I(S2), {"name_ar": "صنف", "price": 5}, o2)[0] == 403)

# ---- حذف الحساب
ok("account deletion succeeds", call("POST", "/me/delete", {"password": "password1"}, o2)[0] == 200)
ok("deleted owner's items are soft-deleted and anonymised, image links gone", sql("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status!='deleted'", S2)[0][0] == 0 and sql("SELECT COUNT(*) FROM shop_item_images WHERE item_id=?", iz)[0][0] == 0 and sql("SELECT name_ar FROM shop_items WHERE id=?", iz)[0][0] == "حساب محذوف")
ok("their uploaded files are gone from the DB", sql("SELECT COUNT(*) FROM files WHERE owner_id=?", o2id)[0][0] == 0)
print("ALL PASS")
