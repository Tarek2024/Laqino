# المرحلة 8ب: مفضلة الإعلانات وبلاغاتها (lsocial.py) — الـAPI والصلاحيات وعدّاد «نظرة عامة»، وواجهة السوق والإدارة في Chromium بمقاس هاتف.
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, re
_TMP = tempfile.mkdtemp(prefix="laqino-p8b-")
os.environ["LAQINO_DB"] = os.path.join(_TMP, "t.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "up"); os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % srv.server_address[1]
DB = server.DB
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
seller, buyer, other = user("01044440001"), user("01044440002"), user("01044440003")
root = sql("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "أجهزة", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [x for x in call("GET", "/categories?section=souq")[1] if x["parent_id"]][0]["id"]
def mk(title, approve=True):
    i = call("POST", "/listings", {"category_id": cat, "region_id": 3, "title": title}, seller)[1]["id"]
    if approve: call("POST", f"/admin/listings/{i}/review", {"status": "approved"}, at)
    return i
L = mk("غسالة للبيع"); P = mk("إعلان معلّق", approve=False)
fav = lambda t, i, on=True: call("POST", f"/listings/{i}/favorite", {"on": on}, t)
rep = lambda t, i, reason="scam", det=None: call("POST", f"/listings/{i}/report", {"reason": reason, **({"details": det} if det else {})}, t)

# ---- مفضلة
ok("anonymous: favorite/report/my-favorites -> 401", fav(None, L)[0] == 401 and rep(None, L)[0] == 401 and call("GET", "/my/favorites")[0] == 401)
ok("favorite a published listing", fav(buyer, L) == (200, {"favorite": True}))
ok("favorite is idempotent (no duplicate row)", fav(buyer, L)[0] == 200 and sql("select count(*) from listing_favorites")[0][0] == 1)
ok("pending listing cannot be favorited (404, no leak)", fav(buyer, P)[0] == 404 and fav(buyer, 99999)[0] == 404)
ok("'on' must be a boolean", call("POST", f"/listings/{L}/favorite", {"on": "yes"}, buyer)[0] == 400)
s, fl = call("GET", "/my/favorites", None, buyer)
ok("my favorites lists it with images list and no phone/seller contact", s == 200 and [x["id"] for x in fl] == [L] and "images" in fl[0] and "phone" not in json.dumps(fl))
ok("other user's favorites are separate (empty)", call("GET", "/my/favorites", None, other)[1] == [])
d = call("GET", f"/listings/{L}", None, buyer)[1]
ok("detail shows is_favorite/reported flags to the logged-in user only", d["is_favorite"] is True and d["reported"] is False and "is_favorite" not in call("GET", f"/listings/{L}")[1])
sql("update listings set status='hidden' where id=?", (L,))
ok("hidden listing disappears from favorites (not leaked) but removal still allowed", call("GET", "/my/favorites", None, buyer)[1] == [] and fav(buyer, L, False)[1] == {"favorite": False} and sql("select count(*) from listing_favorites")[0][0] == 0)
sql("update listings set status='approved' where id=?", (L,))
fav(buyer, L)
ok("un-favorite removes the row", fav(buyer, L, False)[0] == 200 and sql("select count(*) from listing_favorites")[0][0] == 0)
import lsocial; lsocial.MAX_FAVORITES = 1; L2 = mk("ثلاجة"); fav(buyer, L)
ok("favorites cap enforced (400) but re-adding an existing one is fine", fav(buyer, L2)[0] == 400 and fav(buyer, L)[0] == 200); lsocial.MAX_FAVORITES = 500

# ---- بلاغات
ok("invalid / missing reason -> 400; 'other' needs details", rep(buyer, L, "nope")[0] == 400 and call("POST", f"/listings/{L}/report", {}, buyer)[0] == 400 and rep(buyer, L, "other")[0] == 400)
ok("seller cannot report their own listing", rep(seller, L)[0] == 400)
ok("pending/unknown listing: 404", rep(buyer, P)[0] == 404 and rep(buyer, 99999)[0] == 404)
ok("report accepted", rep(buyer, L, "scam", "x" * 500)[0] == 200 and sql("select reason,length(details),status from listing_reports") == [("scam", 300, "open")])
ok("second report by the same user -> 409 (one per user per listing)", rep(buyer, L, "spam")[0] == 409)
ok("detail now says reported=true", call("GET", f"/listings/{L}", None, buyer)[1]["reported"] is True)
rep(other, L, "other", "مضلل")
ok("reports from two users: 2 open rows", sql("select count(*) from listing_reports where status='open'")[0][0] == 2)
lsocial.MAX_REPORTS_DAY = 1; L3 = mk("تلفزيون")
ok("daily report cap -> 429", rep(buyer, L3)[0] == 429); lsocial.MAX_REPORTS_DAY = 10
ok("reports do NOT auto-hide the listing (abuse protection)", sql("select status from listings where id=?", (L,))[0][0] == "approved")

# ---- إدارة
ok("admin endpoints: customer 403, anonymous 401", call("GET", "/admin/listing-reports", None, buyer)[0] == 403 and call("POST", "/admin/listing-reports/1/resolve", {"status": "resolved"}, buyer)[0] == 403 and call("GET", "/admin/listing-reports")[0] == 401)
s, rows = call("GET", "/admin/listing-reports", None, at)
ok("admin lists open reports with title, reporter, seller, reason label, open_count=2 — no phones", s == 200 and len(rows) == 2 and rows[0]["open_count"] == 2 and rows[0]["title"] == "غسالة للبيع" and rows[0]["reason_label"] and rows[0]["reporter"] and "phone" not in json.dumps(rows))
ok("status filter validated", call("GET", "/admin/listing-reports?status=zzz", None, at)[0] == 400 and call("GET", "/admin/listing-reports?status=resolved", None, at)[1] == [])
ov = call("GET", "/admin/overview", None, at)[1]; ok("overview 'listing_reports' counter = 2 (no longer always 0)", ov["pending"]["listing_reports"] == 2)
r1, r2 = rows[0]["id"], rows[1]["id"]
ok("bad resolve input -> 400 (status, hide with dismissed, non-bool hide)", all(call("POST", f"/admin/listing-reports/{r1}/resolve", b, at)[0] == 400 for b in ({}, {"status": "x"}, {"status": "dismissed", "hide": True}, {"status": "resolved", "hide": "yes"})))
ok("dismiss one report touches only that report", call("POST", f"/admin/listing-reports/{r2}/resolve", {"status": "dismissed"}, at)[0] == 200 and sorted(x[0] for x in sql("select status from listing_reports")) == ["dismissed", "open"])
ok("resolving an already-handled report -> 409", call("POST", f"/admin/listing-reports/{r2}/resolve", {"status": "resolved"}, at)[0] == 409 and call("POST", "/admin/listing-reports/99999/resolve", {"status": "resolved"}, at)[0] == 409)
ok("resolve with hide=true hides the listing, closes all its open reports, audits", call("POST", f"/admin/listing-reports/{r1}/resolve", {"status": "resolved", "hide": True}, at)[0] == 200 and sql("select status from listings where id=?", (L,))[0][0] == "hidden" and sql("select count(*) from listing_reports where status='open'")[0][0] == 0 and sql("select count(*) from audit_log where action='listing.report.resolved'")[0][0] == 1)
ok("hidden listing is gone from the public API and overview counter back to 0", call("GET", f"/listings/{L}")[0] == 404 and call("GET", "/admin/overview", None, at)[1]["pending"]["listing_reports"] == 0)
staff_ph = "01044440009"; stt = user(staff_ph); sql("update users set role='staff' where phone=?", (staff_ph,)); stt = call("POST", "/login", {"phone": staff_ph, "password": "password1"})[1]["token"]
ok("staff can read the report queue", call("GET", "/admin/listing-reports", None, stt)[0] == 200)
# ---- إشعارات الجرس
nts = lambda tok: call("GET", "/notifications?limit=50", None, tok)[1]["items"]
sql("delete from notifications"); LN = mk("مكتب خشب"); stid = call("GET", "/me", None, stt)[1]["id"]; adid = call("GET", "/me", None, at)[1]["id"]
rep(buyer, LN, "spam"); rep(other, LN, "scam")
an = [n for n in nts(at) if n["kind"] == "admin.listing_report"]; sn = [n for n in nts(stt) if n["kind"] == "admin.listing_report"]
ok("new report notifies every admin and staff once, linking to the listings tab", len(an) == 1 and len(sn) == 1 and an[0]["link"] == "admin:listings")
ok("a second report does not pile up another unread admin notification (anti-flood)", sql("select count(*) from notifications where kind='admin.listing_report' and user_id=?", (adid,))[0][0] == 1)
call("POST", "/notifications/read", {"all": True}, at); third = user("01044440004"); rep(third, LN, "prohibited")
ok("after the admin reads it, the next report notifies again", sql("select count(*) from notifications where kind='admin.listing_report' and user_id=?", (adid,))[0][0] == 2 and not [n for n in nts(buyer) + nts(seller) if n["kind"] == "admin.listing_report"])
rows = [x for x in call("GET", "/admin/listing-reports", None, at)[1] if x["listing_id"] == LN]; rb = [x for x in rows if x["reporter"] == "u02"][0]["id"]
call("POST", f"/admin/listing-reports/{rb}/resolve", {"status": "dismissed"}, at)
ok("dismissing notifies only that reporter ('no violation'); seller is not notified", [n["body"] for n in nts(buyer) if n["kind"] == "listing.report_result"] and "ولم تجد مخالفة" in nts(buyer)[0]["body"] and not [n for n in nts(seller) if n["kind"] == "listing.hidden"] and not [n for n in nts(other) if n["kind"] == "listing.report_result"])
rc = [x for x in call("GET", "/admin/listing-reports", None, at)[1] if x["listing_id"] == LN][0]["id"]
call("POST", f"/admin/listing-reports/{rc}/resolve", {"status": "resolved", "hide": True}, at)
hn = [n for n in nts(seller) if n["kind"] == "listing.hidden"]
ok("hiding notifies the seller with the title, no reporter names, and fills hidden_reason", len(hn) == 1 and "مكتب خشب" in hn[0]["body"] and "u0" not in hn[0]["body"] and hn[0]["link"] == "souq" and sql("select hidden_reason from listings where id=?", (LN,))[0][0])
ok("every reporter whose report was closed by the hide gets a result notice", all([n for n in nts(t) if n["kind"] == "listing.report_result"] for t in (other, third)) and "تم إخفاء الإعلان" in [n for n in nts(other) if n["kind"] == "listing.report_result"][0]["body"])
ok("no phone numbers in any of these notifications", not any("0104444" in json.dumps(nts(t), ensure_ascii=False) for t in (at, stt, seller, buyer, other, third)))
dc = server.db(); dc.execute("DELETE FROM listings WHERE id=?", (L2,)); dc.commit(); dc.close()
ok("deleting a listing cascades its favorites (no orphans)", sql("select count(*) from listing_favorites where listing_id=?", (L2,))[0][0] == 0)

# ---- Chromium (هاتف 390px)
try: from playwright.sync_api import sync_playwright
except Exception: print("SKIP browser part (playwright not installed)"); print("ALL PASSED"); sys.exit(0)
L = mk("طابعة"); sql("delete from listing_reports"); sql("delete from listing_favorites")
with sync_playwright() as p:
    b = p.chromium.launch(); errs = []
    def page(tok, path, key="t"):
        ctx = b.new_context(viewport={"width": 390, "height": 780}, is_mobile=True, has_touch=True, locale="ar-EG", service_workers="block")
        if tok: ctx.add_init_script("localStorage.setItem('%s','%s');localStorage.setItem('rg','3');sessionStorage.setItem('at','%s')" % (key, tok, tok))
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(BASE + path); return pg
    noscroll = lambda pg: pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    pg = page(buyer, f"/market.html#/l/{L}"); pg.wait_for_selector("text=أضف للمفضلة")
    ok("browser: buyer sees favorite + report buttons, no horizontal scroll", pg.locator("button:has-text('إبلاغ عن الإعلان')").count() == 1 and noscroll(pg))
    pg.click("button:has-text('أضف للمفضلة')"); pg.wait_for_selector("text=في المفضلة")
    ok("browser: favoriting works and persists server-side", sql("select count(*) from listing_favorites")[0][0] == 1)
    pg.click("button:has-text('إبلاغ عن الإعلان')"); pg.select_option("select[aria-label='سبب البلاغ']", "other"); pg.click("button:has-text('إرسال البلاغ')")
    ok("browser: 'other' without details is refused with a message (no request sent)", sql("select count(*) from listing_reports")[0][0] == 0 and pg.locator("textarea").count() == 1)
    pg.fill("textarea", "<img src=x onerror=window.__x=1> مضلل"); pg.click("button:has-text('إرسال البلاغ')"); pg.wait_for_selector("text=شكرًا")
    ok("browser: report sent; button disabled afterwards", sql("select count(*) from listing_reports")[0][0] == 1 and pg.locator("button:has-text('تم إرسال بلاغك')").is_disabled())
    pg.goto(BASE + "/market.html#/fav"); pg.reload(); pg.wait_for_selector(".grid .card, .grid a, .grid > *")
    ok("browser: 'مفضلتي' page lists the listing", "طابعة" in pg.inner_text("#app") and noscroll(pg))
    pg2 = page(seller, f"/market.html#/l/{L}"); pg2.wait_for_selector("text=نُشر")
    ok("browser: owner sees no favorite/report buttons on their own listing", pg2.locator("button:has-text('أضف للمفضلة')").count() == 0 and pg2.locator("button:has-text('إبلاغ')").count() == 0)
    pg3 = page(None, f"/market.html#/l/{L}"); pg3.wait_for_selector("text=أضف للمفضلة"); pg3.click("button:has-text('أضف للمفضلة')")
    ok("browser: anonymous favoriting asks to log in (no crash)", pg3.locator("text=سجّل").count() >= 1)
    # لوحة الإدارة: بلاغ جديد يظهر في تبويب الإعلانات بأزرار القرار، والنص يُهرَّب
    sql("delete from listing_reports"); rep(other, L, "other", "<img src=x onerror=window.__y=1> مضلل")
    ap = page(at, "/admin.html", key="zz"); ap.wait_for_selector("nav"); ap.click("nav button[data-k=listings]"); ap.wait_for_selector("text=بلاغات الإعلانات (1)")
    ok("admin UI: report card shows reason/details/reporter; injected HTML did not run; no horizontal scroll", "مضلل" in ap.inner_text("#v") and ap.evaluate("window.__y === undefined") and ap.locator("#v img").count() == 0 and ap.locator("button:has-text('إخفاء الإعلان')").count() == 1 and noscroll(ap))
    ap.click("button:has-text('إخفاء الإعلان')"); ap.wait_for_selector("text=بلاغات الإعلانات (0)")
    ok("admin UI: 'hide listing' hides it and clears the queue", sql("select status from listings where id=?", (L,))[0][0] == "hidden" and sql("select count(*) from listing_reports where status='open'")[0][0] == 0)
    ok("browser: no page errors at all", not errs)
    b.close()
print("ALL PASSED")
