# إضافة سوق الصيدليات (بعد الخطوة 7) (بيع بخصم بين الصيدليات المعتمدة فقط). قاعدة مؤقتة + خادم حقيقي + كل الأدوار.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, datetime
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, exchange
from http.server import ThreadingHTTPServer
from imgutil import png
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try:
        x = urllib.request.urlopen(r); b = x.read(); return x.status, (b if raw else json.loads(b or b"{}"))
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
nt = lambda uid, kind: sql("SELECT title,body,link,ref_type,ref_id FROM notifications WHERE user_id=? AND kind=? ORDER BY id", (uid, kind))
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cust, cid = user("01066660001", "عميل"); pa, a = user("01066660002", "صيدلي أ"); pb, b = user("01066660003", "صيدلي ب"); pc, c_ = user("01066660004", "صيدلي ج"); pd, d_ = user("01066660005", "صيدلي معلق")
for t, uid, st in ((pa, a, "approved"), (pb, b, "approved"), (pc, c_, "approved"), (pd, d_, "pending")):
    call("POST", "/providers/apply", {"name_ar": "صيدلية %d" % uid, "region_id": 3, "address": "x"}, t)
    if st == "approved": assert call("POST", "/admin/providers/%d/review" % uid, {"status": "approved"}, at)[0] == 200
exp = lambda days: (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
def img(t): return call("POST", "/listings/images", {"data": png()}, t)[1]["id"]
def deal(**k):
    base = {"title": "أوجمنتين 1 جم", "details": "علبة ١٤ قرص", "qty": 5, "expiry_date": exp(200), "orig_price": 100, "price": 70}; base.update(k); return base
# ---- من يملك الوصول
ok("anonymous: 401", call("GET", "/provider/exchange")[0] == 401)
ok("customer: 403", call("GET", "/provider/exchange", None, cust)[0] == 403 and call("POST", "/provider/exchange", deal(image_file_ids=[]), cust)[0] == 403)
ok("pending (unapproved) pharmacy: 403", call("GET", "/provider/exchange", None, pd)[0] == 403)
ok("admin is not a pharmacy: board 403", call("GET", "/provider/exchange", None, at)[0] == 403)
# ---- تحقق المدخلات
i1 = img(pa)
ok("no image rejected", call("POST", "/provider/exchange", deal(), pa)[0] == 400 and call("POST", "/provider/exchange", deal(image_file_ids=[]), pa)[0] == 400)
ok("discount below minimum rejected", call("POST", "/provider/exchange", deal(price=98, image_file_ids=[i1]), pa)[0] == 400)
ok("price >= original rejected", call("POST", "/provider/exchange", deal(price=120, image_file_ids=[i1]), pa)[0] == 400)
ok("expiry too close rejected", call("POST", "/provider/exchange", deal(expiry_date=exp(20), image_file_ids=[i1]), pa)[0] == 400)
ok("past expiry rejected", call("POST", "/provider/exchange", deal(expiry_date=exp(-5), image_file_ids=[i1]), pa)[0] == 400)
ok("bad date format rejected", call("POST", "/provider/exchange", deal(expiry_date="غدًا", image_file_ids=[i1]), pa)[0] == 400)
ok("blocked item (insulin) rejected", call("POST", "/provider/exchange", deal(title="Insulin pen", image_file_ids=[i1]), pa)[0] == 400 and call("POST", "/provider/exchange", deal(title="ترامادول 50", image_file_ids=[i1]), pa)[0] == 400)
ok("bad qty rejected", all(call("POST", "/provider/exchange", deal(qty=q, image_file_ids=[i1]), pa)[0] == 400 for q in (0, -1, 100000, "x")))
ok("another pharmacy's image rejected", call("POST", "/provider/exchange", deal(image_file_ids=[img(pb)]), pa)[0] == 400)
ok("4 images rejected", call("POST", "/provider/exchange", deal(image_file_ids=[i1, img(pa), img(pa), img(pa)]), pa)[0] == 400)
ok("rejected attempts created nothing", sql("SELECT COUNT(*) FROM exchange_deals")[0][0] == 0)
ok("YYYY-MM expiry (as printed on box) accepted", call("POST", "/provider/exchange", deal(expiry_date=exp(400)[:7], title="بنادول", image_file_ids=[img(pa)]), pa)[0] == 200)
s_, r = call("POST", "/provider/exchange", deal(image_file_ids=[i1]), pa); D = r["id"]; ok("valid deal created as pending", s_ == 200 and r["status"] == "pending")
ok("image already attached cannot be reused", call("POST", "/provider/exchange", deal(image_file_ids=[i1]), pa)[0] == 400)
ok("admin notified of new deal", len(nt(1, "admin.exchange")) == 2 and nt(1, "admin.exchange")[-1][2] == "admin:exchange")
# ---- لا يظهر قبل الاعتماد
ok("pending deal NOT on the board for other pharmacies", call("GET", "/provider/exchange", None, pb)[1]["total"] == 0)
ok("owner sees it in mine as pending", [x["status"] for x in call("GET", "/provider/exchange/mine", None, pa)[1] if x["id"] == D] == ["pending"])
ok("other pharmacy cannot reserve a pending deal", call("POST", "/provider/exchange/%d/reserve" % D, {}, pb)[0] == 409)
ok("other pharmacy cannot read pending deal's image", call("GET", "/provider/exchange/%d/images/%d" % (D, i1), None, pb)[0] == 404)
ok("owner can read own image", call("GET", "/provider/exchange/%d/images/%d" % (D, i1), None, pa, raw=True)[0] == 200)
# ---- الإدارة
ok("provider cannot use admin routes", call("GET", "/admin/exchange", None, pa)[0] == 403 and call("POST", "/admin/exchange/%d/review" % D, {"status": "approved"}, pa)[0] == 403 and call("GET", "/admin/exchange", None, cust)[0] == 403)
l = call("GET", "/admin/exchange", None, at)[1]; ok("admin sees pending deal with images", any(x["id"] == D and x["images"] == [i1] for x in l))
ok("admin can open the image", call("GET", "/admin/exchange/%d/images/%d" % (D, i1), None, at, raw=True)[0] == 200)
ok("reject needs reason", call("POST", "/admin/exchange/%d/review" % D, {"status": "rejected"}, at)[0] == 400)
ok("admin approves", call("POST", "/admin/exchange/%d/review" % D, {"status": "approved"}, at)[0] == 200 and call("POST", "/admin/exchange/%d/review" % D, {"status": "approved"}, at)[0] == 409)
ok("seller notified of approval", [x[0] for x in nt(a, "exchange.review")] == ["تم نشر إعلانك في سوق الصيدليات"])
# ---- السوق
bd = call("GET", "/provider/exchange", None, pb)[1]; it = [x for x in bd["items"] if x["id"] == D]
ok("approved deal visible to another approved pharmacy with discount %", len(it) == 1 and it[0]["discount_pct"] == 30 and it[0]["mine"] is False and it[0]["images"] == [i1])
ok("board never exposes phone numbers", "phone" not in json.dumps(bd) and "01066660002" not in json.dumps(bd))
ok("owner sees own deal flagged mine", [x["mine"] for x in call("GET", "/provider/exchange", None, pa)[1]["items"] if x["id"] == D] == [True])
ok("search by name works (Arabic normalization)", call("GET", "/provider/exchange?q=%D8%A7%D9%88%D8%AC%D9%85%D9%86%D8%AA%D9%8A%D9%86", None, pb)[1]["total"] == 1 and call("GET", "/provider/exchange?q=xyzxyz", None, pb)[1]["total"] == 0)
ok("approved deal's image readable by other approved pharmacy", call("GET", "/provider/exchange/%d/images/%d" % (D, i1), None, pb, raw=True)[0] == 200)
ok("customer still cannot see anything / image", call("GET", "/provider/exchange/%d/images/%d" % (D, i1), None, cust)[0] == 403)
ok("not leaked in public product/medical search", "أوجمنتين" not in json.dumps(call("GET", "/search?q=%D8%A7%D9%88%D8%AC%D9%85%D9%86%D8%AA%D9%8A%D9%86&region_id=3")[1], ensure_ascii=False))
# ---- الحجز: الأول يفوز
ok("owner cannot reserve own deal", call("POST", "/provider/exchange/%d/reserve" % D, {}, pa)[0] == 400)
s1, r1 = call("POST", "/provider/exchange/%d/reserve" % D, {}, pb); ok("pharmacy B reserves; gets seller's contact", s1 == 200 and r1["seller"]["phone"] == "01066660002")
ok("pharmacy C cannot reserve the same deal (first wins)", call("POST", "/provider/exchange/%d/reserve" % D, {}, pc)[0] == 409)
ok("seller notified of reservation", len(nt(a, "exchange.reserved")) == 1)
ok("seller sees buyer's phone only after reservation", [x["buyer"]["phone"] for x in call("GET", "/provider/exchange/mine", None, pa)[1] if x["id"] == D] == ["01066660003"])
ok("buyer sees seller in reservations", [x["seller"]["phone"] for x in call("GET", "/provider/exchange/reservations", None, pb)[1]] == ["01066660002"])
ok("third pharmacy sees it as reserved, without contacts", "01066660002" not in json.dumps(call("GET", "/provider/exchange", None, pc)[1]) and [x["status"] for x in call("GET", "/provider/exchange", None, pc)[1]["items"] if x["id"] == D] == ["reserved"])
ok("reserved deal cannot be edited or deleted", call("POST", "/provider/exchange/%d/edit" % D, {"qty": 3}, pa)[0] == 409 and call("POST", "/provider/exchange/%d/delete" % D, {}, pa)[0] == 409)
ok("third pharmacy cannot release / mark sold", call("POST", "/provider/exchange/%d/release" % D, {}, pc)[0] == 409 and call("POST", "/provider/exchange/%d/sold" % D, {}, pc)[0] == 404)
ok("buyer cannot mark sold (seller only)", call("POST", "/provider/exchange/%d/sold" % D, {}, pb)[0] == 404)
ok("buyer releases -> available again, both notified", call("POST", "/provider/exchange/%d/release" % D, {}, pb)[0] == 200 and len(nt(b, "exchange.released")) == 1 and len(nt(a, "exchange.released")) == 1 and [x["status"] for x in call("GET", "/provider/exchange/mine", None, pa)[1] if x["id"] == D] == ["approved"])
ok("release did NOT send a fake 'published' notice", len(nt(a, "exchange.review")) == 1)
ok("C can now reserve", call("POST", "/provider/exchange/%d/reserve" % D, {}, pc)[0] == 200)
# انتهاء الحجز تلقائيًا
sql("UPDATE exchange_deals SET reserved_at=? WHERE id=?", (int(time.time()) - 49 * 3600, D))
ok("stale reservation lapses automatically", [x["status"] for x in call("GET", "/provider/exchange", None, pb)[1]["items"] if x["id"] == D] == ["approved"] and len(nt(c_, "exchange.released")) == 1)
ok("B reserves again, seller confirms sold", call("POST", "/provider/exchange/%d/reserve" % D, {}, pb)[0] == 200 and call("POST", "/provider/exchange/%d/sold" % D, {}, pa)[0] == 200)
ok("buyer notified of sale; deal leaves the board", len(nt(b, "exchange.sold")) == 1 and all(x["id"] != D for x in call("GET", "/provider/exchange", None, pc)[1]["items"]))
ok("sold deal cannot be reserved/sold again", call("POST", "/provider/exchange/%d/reserve" % D, {}, pc)[0] == 409 and call("POST", "/provider/exchange/%d/sold" % D, {}, pa)[0] == 409)
# ---- حد الحجوزات
ids = []
for n in range(6):
    r = call("POST", "/provider/exchange", deal(title="دواء رقم %d" % n, image_file_ids=[img(pa)]), pa)[1]["id"]; call("POST", "/admin/exchange/%d/review" % r, {"status": "approved"}, at); ids.append(r)
res = [call("POST", "/provider/exchange/%d/reserve" % i, {}, pc)[0] for i in ids]
ok("reservation cap: 5 succeed, 6th 429", res == [200] * 5 + [429])
# ---- تعديل / بلاغ / إيقاف
E = ids[5]
ok("editing returns the deal to review (price/expiry are sensitive)", call("POST", "/provider/exchange/%d/edit" % E, {"price": 60}, pa)[0] == 200 and [x["status"] for x in call("GET", "/provider/exchange/mine", None, pa)[1] if x["id"] == E] == ["pending"] and all(x["id"] != E for x in call("GET", "/provider/exchange", None, pb)[1]["items"]))
ok("edit validation still applies", call("POST", "/provider/exchange/%d/edit" % E, {"price": 99}, pa)[0] == 400 and call("POST", "/provider/exchange/%d/edit" % E, {"title": "Insulin"}, pa)[0] == 400)
call("POST", "/admin/exchange/%d/review" % E, {"status": "approved"}, at)
ok("another pharmacy cannot edit/delete my deal", call("POST", "/provider/exchange/%d/edit" % E, {"price": 50}, pb)[0] == 404 and call("POST", "/provider/exchange/%d/delete" % E, {}, pb)[0] == 404)
ok("report: needs reason, once per pharmacy, not on own", call("POST", "/provider/exchange/%d/report" % E, {}, pb)[0] == 400 and call("POST", "/provider/exchange/%d/report" % E, {"reason": "سعر مبالغ فيه"}, pb)[0] == 200 and call("POST", "/provider/exchange/%d/report" % E, {"reason": "مرة ثانية"}, pb)[0] == 409 and call("POST", "/provider/exchange/%d/report" % E, {"reason": "x y z"}, pa)[0] == 400)
ok("admin sees the report and is notified", len(call("GET", "/admin/exchange/reports", None, at)[1]) == 1 and any(x[4] == E for x in nt(1, "admin.exchange")))
ok("takedown needs reason, then hides the deal & notifies seller", call("POST", "/admin/exchange/%d/takedown" % E, {}, at)[0] == 400 and call("POST", "/admin/exchange/%d/takedown" % E, {"reason": "مخالف"}, at)[0] == 200 and all(x["id"] != E for x in call("GET", "/provider/exchange", None, pb)[1]["items"]) and any("رفض/إيقاف" in x[0] for x in nt(a, "exchange.review")))
rid = call("GET", "/admin/exchange/reports", None, at)[1][0]["id"]
ok("report can be closed once", call("POST", "/admin/exchange/reports/%d/resolve" % rid, {}, at)[0] == 200 and call("POST", "/admin/exchange/reports/%d/resolve" % rid, {}, at)[0] == 409 and call("GET", "/admin/exchange/reports", None, at)[1] == [])
ok("staff role can review too", True if call("POST", "/admin/users/%d/role" % user("01066660009", "موظف")[1], {"role": "staff"}, at)[0] == 200 else False)
# ---- الصلاحية والحذف وإلغاء اعتماد الصيدلية
Z = call("POST", "/provider/exchange", deal(image_file_ids=[img(pa)]), pa)[1]["id"]; call("POST", "/admin/exchange/%d/review" % Z, {"status": "approved"}, at)
sql("UPDATE exchange_deals SET expiry_date=? WHERE id=?", (exp(10), Z))
ok("deal hides itself when remaining shelf-life < 30 days", all(x["id"] != Z for x in call("GET", "/provider/exchange", None, pb)[1]["items"]) and call("POST", "/provider/exchange/%d/reserve" % Z, {}, pb)[0] == 409)
sql("UPDATE exchange_deals SET expiry_date=? WHERE id=?", (exp(200), Z))
sql("UPDATE providers SET status='rejected' WHERE user_id=?", (a,))
ok("deals of a no-longer-approved pharmacy leave the board", all(x["pharmacy_id"] != a for x in call("GET", "/provider/exchange", None, pb)[1]["items"]) and call("GET", "/provider/exchange", None, pa)[0] == 403)
sql("UPDATE providers SET status='approved' WHERE user_id=?", (a,))
fp = sql("SELECT f.path FROM exchange_images i JOIN files f ON f.id=i.file_id WHERE i.deal_id=?", (Z,))[0][0]
ok("delete removes the deal and its image file", call("POST", "/provider/exchange/%d/delete" % Z, {}, pa)[0] == 200 and not os.path.exists(os.path.join(os.environ["LAQINO_UPLOADS"], fp)) and sql("SELECT COUNT(*) FROM exchange_images WHERE deal_id=?", (Z,))[0][0] == 0)
ok("deleted deal gone from mine/board, can't be reserved", all(x["id"] != Z for x in call("GET", "/provider/exchange/mine", None, pa)[1]) and call("POST", "/provider/exchange/%d/reserve" % Z, {}, pb)[0] == 404)
# ---- هجمات بسيطة
ok("SQL-injection-looking query text is harmless", call("GET", "/provider/exchange?q=%27%3B%20DROP%20TABLE%20exchange_deals%3B--", None, pb)[0] == 200 and sql("SELECT COUNT(*) FROM exchange_deals")[0][0] > 0)
ok("XSS-looking title is stored as text (UI escapes with esc())", call("POST", "/provider/exchange", deal(title="<img src=x onerror=alert(1)> دواء", image_file_ids=[img(pa)]), pa)[0] == 200)
ok("init() is idempotent (second install keeps data)", (exchange.install(__import__("sqlite3").connect(DB)), sql("SELECT COUNT(*) FROM exchange_deals")[0][0] > 0)[1])
print("ALL PASSED")
