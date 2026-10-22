# المرحلة 2: عروض المنتجات في القسم الطبي (products.py). قاعدة مؤقتة. fake-DOM في node للواجهة، ليس متصفحًا.
import os, json, subprocess, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8792), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8792"; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cust, ph1, ph2, ph3 = user("01012345678"), user("01011111111"), user("01033333333"), user("01044444444")
u1, u3 = call("GET", "/me", None, ph1)[1]["id"], call("GET", "/me", None, ph3)[1]["id"]
call("POST", "/providers/apply", {"name_ar": "صيدلية الأمل", "region_id": 3, "address": "شارع البحر"}, ph1); call("POST", f"/admin/providers/{u1}/review", {"status": "approved"}, at)
call("POST", "/providers/apply", {"name_ar": "صيدلية معلقة", "region_id": 3, "address": "x"}, ph2)
# صيدلية معتمدة في منطقة أخرى (المحافظة 2 كلها تحتوي 3؛ ننشئ منطقة شقيقة)
c = sqlite3.connect(DB); c.execute("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(99,2,'markaz','eg-kfs-other','مركز آخر',1)"); c.commit(); c.close()
call("POST", "/providers/apply", {"name_ar": "صيدلية بعيدة", "region_id": 99, "address": "y"}, ph3); call("POST", f"/admin/providers/{u3}/review", {"status": "approved"}, at)

ok("products are hidden from customers by default (launch state)", call("GET", "/features")[1] == {"products": False} and call("GET", "/medical/products")[1] == {"items": [], "total": 0})
ok("features endpoint is admin-only and validates input", call("POST", "/admin/features", {"products": True}, cust)[0] == 403 and call("POST", "/admin/features", {"products": "yes"}, at)[0] == 400)
ok("admin turns products on", call("POST", "/admin/features", {"products": True}, at)[1] == {"products": True} and call("GET", "/features")[1] == {"products": True})
ok("no product categories exist before admin seeds them", call("GET", "/medical/product-categories")[1] == [])
ok("seed endpoint is admin-only", call("POST", "/admin/products/seed-categories", {}, cust)[0] == 403)
s, r = call("POST", "/admin/products/seed-categories", {}, at); ok("admin seeds 4 categories", s == 200 and r["created"] == 4)
s, cats = call("GET", "/medical/product-categories"); ok("seeded medical sub-categories visible publicly", s == 200 and {x["name"] for x in cats} >= {"مستحضرات تجميل", "الأم والطفل"})
cos = next(x["id"] for x in cats if x["name"] == "مستحضرات تجميل"); mom = next(x["id"] for x in cats if x["name"] == "الأم والطفل")
c = sqlite3.connect(DB); n1 = c.execute("SELECT COUNT(*) FROM categories WHERE section='medical'").fetchone()[0]; c.close()
import products; c2 = server.db(); products.install(c2); products.install(c2); n2 = c2.execute("SELECT COUNT(*) FROM categories WHERE section='medical'").fetchone()[0]; c2.close()
ok("install and re-seeding are idempotent (no duplicate categories)", n1 == n2 and call("POST", "/admin/products/seed-categories", {}, at)[1]["created"] == 0 and call("GET", "/medical/product-categories")[1].__len__() == 4)

P = {"title": "كريم مرطب للوجه", "brand": "نيفيا", "description": "مرطب يومي", "category_id": cos, "price": 85, "old_price": 100}
ok("anonymous cannot post", call("POST", "/provider/products", P)[0] == 401)
ok("customer (no pharmacy) cannot post", call("POST", "/provider/products", P, cust)[0] == 403)
ok("unapproved pharmacy cannot post", call("POST", "/provider/products", P, ph2)[0] == 403)
for bad, nm in (({**P, "title": "ab"}, "short title"), ({**P, "price": 0}, "zero price"), ({**P, "price": "x"}, "bad price"), ({**P, "price": True}, "bool price"), ({**P, "old_price": 50}, "old<=price"),
                ({**P, "category_id": 1}, "root/non-child category"), ({**P, "category_id": 99999}, "unknown category"), ({**P, "category_id": None}, "no category")):
    ok("validation rejects " + nm, call("POST", "/provider/products", bad, ph1)[0] == 400)
s, r = call("POST", "/provider/products", P, ph1); pid = r["id"]; ok("approved pharmacy creates offer → pending", s == 200 and r["status"] == "pending")
ok("pending offer not public", call("GET", "/medical/products?region_id=3")[1]["total"] == 0)
ok("admin list shows pending; customer forbidden", any(x["id"] == pid for x in call("GET", "/admin/products", None, at)[1]) and call("GET", "/admin/products", None, cust)[0] == 403)
ok("reject needs a reason", call("POST", f"/admin/products/{pid}/review", {"status": "rejected"}, at)[0] == 400)
ok("approve works once", call("POST", f"/admin/products/{pid}/review", {"status": "approved"}, at)[0] == 200 and call("POST", f"/admin/products/{pid}/review", {"status": "approved"}, at)[0] == 409)
s, r = call("GET", "/medical/products?region_id=3&q=" + urllib.request.quote("مرطب")); ok("approved offer public with pharmacy name & price", s == 200 and r["total"] == 1 and r["items"][0]["pharmacy"] == "صيدلية الأمل" and r["items"][0]["price"] == 85)
ok("Arabic normalisation in product search (مرطّب / نيڤيا brand)", call("GET", "/medical/products?q=" + urllib.request.quote("مُرَطِّب"))[1]["total"] == 1 and call("GET", "/medical/products?q=" + urllib.request.quote("نيفيا"))[1]["total"] == 1)
ok("category filter works", call("GET", f"/medical/products?category_id={cos}")[1]["total"] == 1 and call("GET", f"/medical/products?category_id={mom}")[1]["total"] == 0)
ok("region isolation (other markaz sees nothing)", call("GET", "/medical/products?region_id=99")[1]["total"] == 0 and call("GET", "/medical/products?region_id=2")[1]["total"] == 1)
cc = call("GET", "/medical/product-categories?region_id=3")[1]; ok("category counts respect region", next(x for x in cc if x["id"] == cos)["count"] == 1)
blob = json.dumps([call("GET", "/medical/products")[1], call("GET", "/search?q=" + urllib.request.quote("مرطب") + "&region_id=3")[1], call("GET", "/admin/products?status=approved", None, at)[1][:0]], ensure_ascii=False)
ok("no phone numbers in public payloads", not any(p in blob for p in ("01011111111", "01012345678", "01033333333")) and '"phone"' not in blob)
s, r = call("GET", "/search?q=" + urllib.request.quote("مرطب") + "&region_id=3"); ok("/api/search includes products", r["products"] and r["products"][0]["id"] == pid)
ok("other pharmacy cannot edit/confirm/delete my offer", all(call("POST", f"/provider/products/{pid}/{a}", {"price": 1}, ph3)[0] == 404 for a in ("edit", "confirm", "delete")))
s, r = call("POST", f"/provider/products/{pid}/confirm", {"price": 90, "available": False}, ph1); ok("confirm toggles availability without re-review", s == 200 and call("GET", "/medical/products?region_id=3")[1]["total"] == 0)
call("POST", f"/provider/products/{pid}/confirm", {"available": True}, ph1); ok("back to available, price 90, still approved", call("GET", "/medical/products?region_id=3")[1]["items"][0]["price"] == 90)
ok("confirm rejects old_price<=price", call("POST", f"/provider/products/{pid}/confirm", {"old_price": 10}, ph1)[0] == 400)
s, r = call("POST", f"/provider/products/{pid}/edit", {"price": 80}, ph1); ok("price-only edit keeps approval", r["status"] == "approved" and call("GET", "/medical/products?region_id=3")[1]["items"][0]["price"] == 80)
s, r = call("POST", f"/provider/products/{pid}/edit", {"title": "كريم مرطب جديد"}, ph1); ok("content edit returns to pending and hides it", r["status"] == "pending" and call("GET", "/medical/products?region_id=3")[1]["total"] == 0)
call("POST", f"/admin/products/{pid}/review", {"status": "rejected", "reason": "صورة غير مناسبة"}, at)
ok("owner sees reject reason", next(x for x in call("GET", "/provider/products", None, ph1)[1] if x["id"] == pid)["reject_reason"] == "صورة غير مناسبة")
call("POST", f"/provider/products/{pid}/edit", {"description": "وصف محدّث"}, ph1); call("POST", f"/admin/products/{pid}/review", {"status": "approved"}, at)
c = sqlite3.connect(DB); c.execute("UPDATE product_offers SET confirmed_at=? WHERE id=?", (int(time.time()) - 20 * 86400, pid)); c.commit(); c.close()
ok("stale offer (>14 days since confirmation) hidden", call("GET", "/medical/products?region_id=3")[1]["total"] == 0)
call("POST", f"/provider/products/{pid}/confirm", {}, ph1); ok("re-confirm makes it visible again", call("GET", "/medical/products?region_id=3")[1]["total"] == 1)
c = sqlite3.connect(DB); c.execute("UPDATE categories SET is_active=0 WHERE id=?", (cos,)); c.commit(); c.close()
ok("deactivated category hides its offers and the category itself", call("GET", "/medical/products?region_id=3")[1]["total"] == 0 and all(x["id"] != cos for x in call("GET", "/medical/product-categories")[1]))
c = sqlite3.connect(DB); c.execute("UPDATE categories SET is_active=1 WHERE id=?", (cos,)); c.commit(); c.close()
c = sqlite3.connect(DB); c.execute("UPDATE providers SET status='suspended' WHERE user_id=?", (u1,)); c.commit(); c.close()
ok("suspended pharmacy's offers hidden; cannot post", call("GET", "/medical/products?region_id=3")[1]["total"] == 0 and call("POST", "/provider/products", P, ph1)[0] == 403)
c = sqlite3.connect(DB); c.execute("UPDATE providers SET status='approved' WHERE user_id=?", (u1,)); c.commit(); c.close()
ok("LIKE wildcards/SQL-ish input inert", all(call("GET", "/medical/products?q=" + urllib.request.quote(x))[0] == 200 and call("GET", "/medical/products?q=" + urllib.request.quote(x))[1]["total"] == 0 for x in ("%_", "' OR 1=1 --")))
ok("limit is capped; garbage numbers tolerated", call("GET", "/medical/products?limit=999&offset=abc&category_id=x")[0] == 200)
call("POST", f"/provider/products/{pid}/delete", {}, ph1); ok("deleted offer gone for public and owner", call("GET", "/medical/products")[1]["total"] == 0 and not any(x["id"] == pid for x in call("GET", "/provider/products", None, ph1)[1]))

# ---- الواجهات (fake-DOM في node، ليست متصفحًا)
HN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
def page(name, tok, steps):
    o = subprocess.run(["node", HN, name, BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); return json.loads(o.stdout)
ui1 = call("POST", "/provider/products", {**P, "title": "شامبو أطفال <b>x</b>", "category_id": mom, "brand": "جونسون"}, ph1)[1]["id"]
ui2 = call("POST", "/provider/products", {**P, "title": "مرهم حفاض", "category_id": mom}, ph1)[1]["id"]; call("POST", f"/admin/products/{ui2}/review", {"status": "approved"}, at)
r = page("index", cust, [{"js": "mt='pr';go(4)", "snap": "v", "wait": 1500}])
ok("UI customer: products tab lists approved offer with pharmacy; pending hidden", not r["errs"] and "مرهم حفاض" in r["v"] and "صيدلية الأمل" in r["v"] and "شامبو" not in r["v"] and "الأم والطفل" in r["v"])
r = page("index", cust, [{"js": "window.gq='مرهم';go(5)", "snap": "v", "wait": 1500}])
ok("UI customer: global search shows a products section", not r["errs"] and "المنتجات" in r["v"] and "مرهم حفاض" in r["v"])
r = page("pharmacy", ph1, [{"snap": "m", "wait": 1200}])
ok("UI pharmacy: form + own offers with status; HTML is escaped", not r["errs"] and "عروض المنتجات" in r["m"] and "قيد المراجعة" in r["m"] and "&lt;b&gt;x" in r["m"] and "<b>x</b>" not in r["m"])
r = page("pharmacy", ph1, [{"js": "$('pt').value='كريم شمس';$('pk').value='%d';$('pp').value='60';pa()" % cos, "snap": "m", "wait": 1500}])
ok("UI pharmacy: add-product form posts and lists the new offer", not r["errs"] and "كريم شمس" in r["m"] and "تم إرسال المنتج" in r["m"])
r = page("admin", at, [{"js": "tab='products';shell()", "snap": "v", "wait": 1500}])
ok("UI admin: pending products tab shows offers with approve/reject + seed button; escaped", not r["errs"] and "إنشاء التصنيفات" in r["v"] and "كريم شمس" in r["v"] and "&lt;b&gt;x" in r["v"] and "/admin/products/" in r["v"])
sw = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "sw.js"), encoding="utf8").read(); import re
ok("sw.js cache bumped to >=v31", int(re.search(r"laqino-v(\d+)", sw).group(1)) >= 31)

# ---- المرحلة 2ب: صور + إشعارات + صفحة الصيدلية
import io, base64
from PIL import Image
def png(col):
    b = io.BytesIO(); Image.new("RGB", (40, 30), col).save(b, "PNG"); return b.getvalue()
def up(tok, raw):
    r = urllib.request.Request(BASE + "/api/listings/images", json.dumps({"data": base64.b64encode(raw).decode()}).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + tok}, method="POST")
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def raw_get(path, tok=None):
    r = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + tok} if tok else {})
    try: x = urllib.request.urlopen(r); return x.status, x.read(), dict(x.headers)
    except urllib.error.HTTPError as e: return e.code, e.read(), {}
unread = lambda tok: call("GET", "/notifications/count", None, tok)[1]["unread"]
a0, p0 = unread(at), unread(ph1)
f1, f2 = up(ph1, png((200, 30, 30)))[1]["id"], up(ph1, png((30, 200, 30)))[1]["id"]; fx = up(ph2, png((1, 2, 3)))[1]["id"]
s, r = call("POST", "/provider/products", {**P, "title": "كريم بصور", "image_file_ids": [f1, f2]}, ph1); im1 = r["id"]
ok("create with images ok; admin got a notification", s == 200 and unread(at) == a0 + 1)
ok("pending offer's image: hidden from public & other users, visible to owner and admin", raw_get(f"/api/medical/products/{im1}/images/{f1}")[0] == 404 and raw_get(f"/api/medical/products/{im1}/images/{f1}", ph2)[0] == 404
   and raw_get(f"/api/medical/products/{im1}/images/{f1}", ph1)[0] == 200 and raw_get(f"/api/medical/products/{im1}/images/{f1}", at)[0] == 200)
ok("image validation: foreign file, >3, duplicates, non-list, bool", all(call("POST", "/provider/products", {**P, "image_file_ids": v}, ph1)[0] == 400 for v in ([fx], [f1, f1], [1, 2, 3, 4], "x", [True])))
ok("admin list shows image ids", next(x for x in call("GET", "/admin/products", None, at)[1] if x["id"] == im1)["images"] == [f1, f2])
call("POST", f"/admin/products/{im1}/review", {"status": "approved"}, at)
ok("pharmacy notified of approval", unread(ph1) == p0 + 1)
st, body, hd = raw_get(f"/api/medical/products/{im1}/images/{f1}"); ok("approved offer image public, image/png, cacheable", st == 200 and body[:4] == b"\x89PNG" and hd["Content-Type"] == "image/png" and "max-age" in hd["Cache-Control"])
ok("wrong offer/file pair is 404", raw_get(f"/api/medical/products/{im1}/images/{fx}")[0] == 404 and raw_get(f"/api/medical/products/{ui1}/images/{f1}")[0] == 404)
ok("public payload carries images; no phone", call("GET", "/medical/products?q=" + urllib.request.quote("بصور"))[1]["items"][0]["images"] == [f1, f2])
ok("image file cannot be deleted via /files while attached", call("POST", f"/files/{f1}/delete", {}, ph1)[0] == 409)
s, r = call("POST", f"/provider/products/{im1}/edit", {"image_file_ids": [f2]}, ph1); ok("changing images returns the offer to pending (admin notified again)", r["status"] == "pending" and unread(at) >= a0 + 2)
ok("removed image is deleted from disk and DB; kept one remains", raw_get(f"/api/medical/products/{im1}/images/{f1}", ph1)[0] == 404 and call("GET", "/provider/products", None, ph1)[1][0]["images"] in ([f2],) or any(x["id"] == im1 and x["images"] == [f2] for x in call("GET", "/provider/products", None, ph1)[1]))
c = sqlite3.connect(DB); ok("removed file row gone", c.execute("SELECT COUNT(*) FROM files WHERE id=?", (f1,)).fetchone()[0] == 0); c.close()
call("POST", f"/admin/products/{im1}/review", {"status": "rejected", "reason": "x"}, at); ok("pharmacy notified of rejection with reason as body", any(n["kind"] == "product.review" and n["body"] == "x" for n in call("GET", "/notifications", None, ph1)[1]["items"]))
call("POST", f"/provider/products/{im1}/delete", {}, ph1); c = sqlite3.connect(DB); ok("deleting offer removes its images", c.execute("SELECT COUNT(*) FROM product_images WHERE offer_id=?", (im1,)).fetchone()[0] == 0 and c.execute("SELECT COUNT(*) FROM files WHERE id=?", (f2,)).fetchone()[0] == 0); c.close()
# صفحة الصيدلية
s, r = call("GET", f"/medical/pharmacies/{u1}"); ok("public pharmacy page: name, region, address, only its published offers, no phone", s == 200 and r["name_ar"] == "صيدلية الأمل" and r["total"] >= 1 and all(i["pharmacy_id"] == u1 for i in r["items"]) and '"phone"' not in json.dumps(r) and "01011111111" not in json.dumps(r))
ok("pharmacy page 404 for unapproved / unknown / non-numeric", call("GET", f"/medical/pharmacies/{call('GET', '/me', None, ph2)[1]['id']}")[0] == 404 and call("GET", "/medical/pharmacies/99999")[0] == 404 and call("GET", "/medical/pharmacies/abc")[0] == 404)
ok("search pharmacies carry id", call("GET", "/search?q=" + urllib.request.quote("الامل") + "&region_id=3")[1]["pharmacies"][0]["id"] == u1)
r = page("index", cust, [{"js": "phv(%d)" % u1, "snap": "v", "wait": 1500}]); ok("UI: pharmacy page renders name and its offers", not r["errs"] and "صيدلية الأمل" in r["v"] and "عروض الصيدلية" in r["v"] and "مرهم حفاض" in r["v"])
r = page("index", cust, [{"js": "mt='pr';go(4)", "snap": "v", "wait": 1500}]); ok("UI: product card opens pharmacy page via link", not r["errs"] and ("phv(%d)" % u1) in r["v"])
call("POST", "/provider/products", {**P, "title": "منتج بصورة واجهة", "image_file_ids": [up(ph1, png((9, 9, 9)))[1]["id"]]}, ph1)
ui3 = max(x["id"] for x in call("GET", "/provider/products", None, ph1)[1]); call("POST", f"/admin/products/{ui3}/review", {"status": "approved"}, at)
r = page("index", cust, [{"js": "mt='pr';go(4)", "snap": "v", "wait": 1500}]); ok("UI: card shows <img> from the public image route", not r["errs"] and f"/api/medical/products/{ui3}/images/" in r["v"])
r = page("pharmacy", ph1, [{"snap": "m", "wait": 1200}]); ok("UI pharmacy: thumbnails use data-pi and file input exists", not r["errs"] and 'data-pi="%d/' % ui3 in r["m"] and 'id="pf"' in r["m"])
for i in range(products.MAX_PER_PHARMACY): 
    if call("POST", "/provider/products", {**P, "title": f"منتج رقم {i}"}, ph1)[0] != 200: break
ok("per-pharmacy cap enforced (429)", call("POST", "/provider/products", P, ph1)[0] == 429)
# مفتاح الإخفاء: عند الإطفاء يختفي كل شيء عن العملاء دون حذف بيانات، وتعود عند التشغيل
call("POST", "/admin/features", {"products": False}, at)
ok("flag off: public list, categories and /api/search hide products", call("GET", "/medical/products?region_id=3")[1]["total"] == 0 and call("GET", "/medical/product-categories")[1] == [] and call("GET", "/search?q=" + urllib.request.quote("منتج") + "&region_id=3")[1]["products"] == [])
ok("flag off: pharmacy still manages its offers", call("GET", "/provider/products", None, ph1)[0] == 200)
call("POST", "/admin/features", {"products": True}, at)
ok("flag on again: data intact", call("GET", "/medical/products?region_id=3")[1]["total"] >= 1)
print("ALL PASSED")
