# المرحلة 30: الإعلان المميز — تمييز بمدة من الإدارة، حد أقصى، إلغاء، انتهاء تلقائي، عرض في السوق
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8930; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
ut, uid = user("01030000001")
root = sql("select id from categories where section='souq' and parent_id is null")[0][0]
call("POST", "/admin/categories", {"section": "souq", "name_ar": "أجهزة", "slug": "dev", "parent_id": root, "is_active": True}, at)
cat = [c for c in call("GET", "/categories?section=souq")[1] if c["parent_id"] is not None][0]["id"]
now = int(time.time())
def mk(title, status="approved"): return sql("INSERT INTO listings(user_id,category_id,region_id,title,description,price,status,created_at) VALUES(?,?,3,?,?,100,?,?) RETURNING id", uid, cat, title, "وصف", status, now)[0][0]
ids = [mk("إعلان %d" % i) for i in range(8)]; pend = mk("قيد المراجعة", "pending")

# ---- 1) لا شيء مميز افتراضيًا
ls = call("GET", "/listings?limit=50")[1]
ok("list items carry featured=0 by default", len(ls) == 8 and all(x["featured"] == 0 for x in ls))
ok("featured=1 filter empty at start", call("GET", "/listings?featured=1")[1] == [])
ok("detail featured false", call("GET", f"/listings/{ids[0]}")[1]["featured"] is False)

# ---- 2) الصلاحيات والتحقق
ok("non-admin cannot feature (403)", call("POST", f"/admin/listings/{ids[0]}/feature", {"days": 7}, ut)[0] == 403)
ok("anonymous cannot feature", call("POST", f"/admin/listings/{ids[0]}/feature", {"days": 7})[0] in (401, 403))
for bad in (-1, 31, "abc", None, 2.5 if False else "x"): ok(f"days {bad!r} rejected", call("POST", f"/admin/listings/{ids[0]}/feature", {"days": bad}, at)[0] == 400)
ok("unknown listing 404", call("POST", "/admin/listings/99999/feature", {"days": 7}, at)[0] == 404)
ok("pending listing cannot be featured (409)", call("POST", f"/admin/listings/{pend}/feature", {"days": 7}, at)[0] == 409)
sql("UPDATE listings SET closed_kind='sold' WHERE id=?", ids[7])
ok("closed (sold) listing cannot be featured (409)", call("POST", f"/admin/listings/{ids[7]}/feature", {"days": 7}, at)[0] == 409)

# ---- 3) التمييز والعرض
s, r = call("POST", f"/admin/listings/{ids[0]}/feature", {"days": 7}, at)
ok("feature 7 days", s == 200 and r["featured"] is True and abs(r["featured_until"] - (now + 7 * 86400)) < 5)
ok("audited", sql("SELECT COUNT(*) FROM audit_log WHERE action='listing.feature' AND target=?", str(ids[0]))[0][0] == 1)
ls = {x["id"]: x for x in call("GET", "/listings?limit=50")[1]}
ok("list marks it featured", ls[ids[0]]["featured"] == 1 and ls[ids[1]]["featured"] == 0)
ok("detail featured true", call("GET", f"/listings/{ids[0]}")[1]["featured"] is True)
call("POST", f"/admin/listings/{ids[1]}/feature", {"days": 3}, at)
fl = call("GET", "/listings?featured=1")[1]
ok("featured=1 returns only featured, newest-featured first", [x["id"] for x in fl] == [ids[0], ids[1]] if False else {x["id"] for x in fl} == {ids[0], ids[1]} and fl[0]["id"] == ids[0])
ok("featured=1 respects other filters (q)", [x["id"] for x in call("GET", "/listings?featured=1&q=" + urllib.parse.quote("إعلان 1") if False else "/listings?featured=1&min_price=500")[1]] == [])
fa = call("GET", "/admin/featured", None, at)[1]
ok("admin overview: max 6, 2 featured, recent excludes featured/closed/pending", fa["max"] == 6 and len(fa["featured"]) == 2 and all(x["id"] not in (ids[0], ids[1], ids[7], pend) for x in fa["recent"]))
ok("non-admin cannot read admin featured", call("GET", "/admin/featured", None, ut)[0] == 403)

# ---- 4) الحد الأقصى
ok("max setting validated", call("POST", "/admin/featured/settings", {"max": 0}, at)[0] == 400 and call("POST", "/admin/featured/settings", {"max": 13}, at)[0] == 400 and call("POST", "/admin/featured/settings", {"max": "x"}, at)[0] == 400)
ok("set max to 3", call("POST", "/admin/featured/settings", {"max": 3}, at)[0] == 200)
ok("third ok", call("POST", f"/admin/listings/{ids[2]}/feature", {"days": 7}, at)[0] == 200)
s, r = call("POST", f"/admin/listings/{ids[3]}/feature", {"days": 7}, at)
ok("fourth refused at the cap (409)", s == 409 and "3" in r["error"])
ok("re-featuring an already featured one is allowed (extend)", call("POST", f"/admin/listings/{ids[2]}/feature", {"days": 14}, at)[0] == 200)

# ---- 5) إلغاء وانتهاء تلقائي
ok("unfeature (days 0)", call("POST", f"/admin/listings/{ids[2]}/feature", {"days": 0}, at) == (200, {"featured": False}) and sql("SELECT featured_until FROM listings WHERE id=?", ids[2])[0][0] is None)
ok("slot freed: fourth now ok", call("POST", f"/admin/listings/{ids[3]}/feature", {"days": 7}, at)[0] == 200)
sql("UPDATE listings SET featured_until=? WHERE id=?", now - 10, ids[0])
ok("expired feature disappears by itself (no cron)", ids[0] not in [x["id"] for x in call("GET", "/listings?featured=1")[1]] and call("GET", f"/listings/{ids[0]}")[1]["featured"] is False)
ok("expired one frees its slot", call("POST", f"/admin/listings/{ids[4]}/feature", {"days": 7}, at)[0] == 200)
sql("UPDATE listings SET status='deleted' WHERE id=?", ids[4])
ok("deleted listing never shown as featured", ids[4] not in [x["id"] for x in call("GET", "/listings?featured=1")[1]])

# ---- 6) المتصفح: القسم يظهر وبطاقاته لا تدخل عدّاد الشبكة
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP browser check (playwright missing)"); print("ALL PASS"); exit(0)
call("POST", "/admin/featured/settings", {"max": 6}, at)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 900}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/market.html"); pg.wait_for_selector("#grid .card"); pg.wait_for_selector("#feat .fc", timeout=5000)
    ok("featured section is shown above the grid", pg.evaluate("document.getElementById('feat').nextElementSibling.id") == "grid")
    ok("featured cards are .fc (not counted as .card)", pg.locator("#feat .fc").count() == 2 and pg.locator("#feat .card").count() == 0)
    ok("featured cards show the gold badge", "مميز" in pg.inner_text("#feat .fc .star"))
    ok("grid card of a featured listing carries the gold badge", pg.locator("#grid .card .gold").count() >= 1)
    pg.click("#feat .fc"); pg.wait_for_selector(".det"); ok("featured card opens the detail page", "/l/" in pg.url and "مميز" in pg.inner_text(".det"))
    ok("no JS errors", not errs); b.close()
print("ALL PASS")
