# المرحلة 7: نظرة عامة للإدارة (overview.py + تبويب «نظرة عامة» وعدّادات التبويبات). قاعدة مؤقتة معزولة.
import os, re, json, tempfile, threading, time, sys, sqlite3, urllib.request, urllib.error
_TMP = tempfile.mkdtemp(prefix="laqino-p7-")
os.environ["LAQINO_DB"] = os.path.join(_TMP, "test.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "uploads"); os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
from testutil import apply_docs
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8801), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8801"; DB = server.DB; HERE = os.path.dirname(os.path.abspath(__file__))
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
cu = user("01055550001"); cour = user("01055550002")
ov = lambda t=at: call("GET", "/admin/overview", None, t)

ok("anonymous -> 401", ov(None)[0] == 401)
ok("customer -> 403", ov(cu)[0] == 403)
s, r = ov()
ok("empty system: 200, every counter 0, total_pending 0", s == 200 and r["total_pending"] == 0 and all(v == 0 for v in r["pending"].values()) and len(r["pending"]) == 12)
ok("totals present (users counted)", r["totals"]["users"] >= 3 and set(r["totals"]) == {"users", "couriers", "pharmacies", "listings", "orders_24h"})
ok("POST is not allowed (404)", call("POST", "/admin/overview", {}, at)[0] == 404)

# seed one pending item per area
now = int(time.time())
ok("courier application pending", apply_docs(call, cour)[0] == 201)
uid_cu = sql("SELECT id FROM users WHERE phone='01055550001'")[0][0]; uid_c = sql("SELECT id FROM users WHERE phone='01055550002'")[0][0]
sql("INSERT INTO topup_requests(courier_id,amount,transfer_ref,created_at) VALUES(?,?,?,?)", (uid_c, 50, "ref1", now))
sql("INSERT INTO listings(user_id,category_id,region_id,title,created_at) VALUES(?,?,?,?,?)", (uid_cu, 1, 3, "إعلان", now))
sql("INSERT INTO listing_reports(listing_id,reporter_id,reason,created_at) VALUES(1,?,?,?)", (uid_cu, "مخالف", now))
sql("INSERT INTO chat_reports(thread_id,reporter_id,reason,created_at) VALUES(1,?,?,?)", (uid_cu, "إساءة", now))
sql("INSERT INTO service_requests(user_id,type_id,region_id,description,created_at,updated_at) VALUES(?,?,?,?,?,?)", (uid_cu, 1, 3, "وصف طلب خدمة", now, now))
sql("INSERT INTO providers(user_id,name_ar,region_id,status,created_at) VALUES(?,?,?,?,?)", (uid_cu, "صيدلية", 3, "pending", now))
sql("INSERT INTO product_offers(provider_id,category_id,title,price,created_at,updated_at,confirmed_at) VALUES(?,?,?,?,?,?,?)", (uid_cu, 1, "منتج", 10, now, now, now))
sql("INSERT INTO prescriptions(customer_id,region_id,created_at) VALUES(?,?,?)", (uid_cu, 3, now))
sql("INSERT INTO prescription_responses(prescription_id,provider_id,status,price,updated_at) VALUES(1,?,?,?,?)", (uid_cu, "available", 10, now))  # رد جديد = بانتظار اعتماد الإدارة (الخطوة 4)
sql("INSERT INTO service_rating_reports(rating_id,request_id,provider_id,reporter_id,reason,snap_stars,created_at) VALUES(1,1,1,?,?,?,?)", (uid_cu, "سبب البلاغ", 1, now))  # الخطوة 5
sql("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,fee,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (uid_cu, 3, "أ", "ب", 20, "disputed", now, now))
sql("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,fee,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (uid_cu, 3, "أ", "ب", 20, "completed", now - 10 * 86400, now - 10 * 86400))
r = ov()[1]
ok("each of the 12 counters sees exactly its one item", all(r["pending"][k] == 1 for k in r["pending"]) and r["total_pending"] == 12)
ok("orders_24h counts only recent orders (1 of 2)", r["totals"]["orders_24h"] == 1)
ok("approved items are not counted as pending", (sql("UPDATE listings SET status='approved'"), sql("UPDATE service_requests SET status='done'"), ov()[1]["pending"]["listings"] == 0 and ov()[1]["pending"]["svcreq"] == 0 and ov()[1]["totals"]["listings"] == 1)[2])
ok("staff can read the overview", (sql("UPDATE users SET role='staff' WHERE id=?", (uid_cu,)), ov(user("01055550001") if False else call("POST", "/login", {"phone": "01055550001", "password": "password1"})[1]["token"])[0])[1] == 200)
ok("response holds no phone numbers or names", not re.search(r"0\d{10}", json.dumps(ov()[1])))
before = sql("SELECT (SELECT COUNT(*) FROM users),(SELECT COUNT(*) FROM listings),(SELECT COUNT(*) FROM audit_log)")
for _ in range(3): ov()
ok("read-only: repeated calls change nothing", sql("SELECT (SELECT COUNT(*) FROM users),(SELECT COUNT(*) FROM listings),(SELECT COUNT(*) FROM audit_log)") == before)
sql("DROP TABLE listing_reports")
s, r = ov()
ok("missing table gives 0 for that counter, not a 500", s == 200 and r["pending"]["listing_reports"] == 0 and r["pending"]["chats"] == 1)

rd = lambda f: open(os.path.join(HERE, f), encoding="utf8").read()
adm, dock, sw = rd("static/admin.html"), rd("Dockerfile"), rd("static/sw.js")
ok("UI: overview is the default landing tab and first section", "tab='overview'" in adm and re.search(r"TABS=\{overview:'", adm))
ok("UI: counters badge on nav buttons + overview rows use esc()", all(k in adm for k in ("function badges", "/admin/overview", "esc(o.pending[i.key])", "esc(i.label)")))
ok("Dockerfile copies overview.py; cache >= v39", "overview.py" in dock and int(re.search(r"laqino-v(\d+)", sw).group(1)) >= 39)

try:
    from playwright.sync_api import sync_playwright
except Exception: print("SKIP browser tests (playwright not installed)"); print("ALL PASS"); sys.exit(0)
sql("UPDATE users SET role='customer' WHERE phone='01055550001'")
sql("INSERT INTO topup_requests(courier_id,amount,transfer_ref,created_at) VALUES(?,?,?,?)", (uid_c, 70, "ref2", now))
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception: print("SKIP browser tests (Chromium not installed)"); print("ALL PASS"); sys.exit(0)
    errs = []
    pg = b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True, locale="ar-EG").new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/admin.html"); pg.fill("#p", "01000000000"); pg.fill("#w", "AdminPass123"); pg.click('button:has-text("دخول")'); pg.wait_for_selector("nav button")
    pg.wait_for_selector(".ov"); 
    ok("browser: lands on overview (button highlighted)", pg.locator("nav button").first.get_attribute("class") == "on" and "نظرة عامة" in pg.locator("nav button").first.inner_text())
    ok("browser: summary card states the pending total", "بند بانتظار القرار" in pg.inner_text("#v"))
    ok("browser: rows show only areas with pending items", pg.locator(".ov").count() >= 5 and "بلاغات على إعلانات" not in pg.inner_text("#v"))
    pg.locator("button.ov:has-text('طلبات شحن')").click(); pg.wait_for_timeout(500)
    ok("browser: tapping a row opens that section", pg.locator("nav button[data-k=topups]").get_attribute("class") == "on")
    pg.wait_for_timeout(700)
    ok("browser: nav badge shows the topups count (2)", pg.locator("nav button[data-k=topups] .bd").count() == 1 and pg.locator("nav button[data-k=topups] .bd").inner_text().strip() == "2")
    ok("browser: no sideways scroll, no JS errors", pg.evaluate("document.documentElement.scrollWidth<=innerWidth") and not errs); b.close()
print("ALL PASS")
