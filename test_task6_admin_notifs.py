# المهمة 6: إشعارات الإدارة/الموظفين (انضمام مندوب/صيدلية، شحن، إعلان) — سيرفر حقيقي على قاعدة مؤقتة + متصفح على admin.html الحقيقي.
import os, sys, json, time, sqlite3, tempfile, threading, urllib.request, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__)); TMP = tempfile.mkdtemp(prefix="laqino-t6-")
os.environ["LAQINO_DB"] = os.path.join(TMP, "t.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(TMP, "up"); os.makedirs(os.environ["LAQINO_UPLOADS"])
sys.path.insert(0, HERE)
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(TMP)), "ISOLATION BROKEN"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
db = lambda q, a=(): sqlite3.connect(os.environ["LAQINO_DB"]).execute(q, a).fetchall()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
staff, sid = user("01055550001", "موظف"); assert call("POST", "/admin/users/%d/role" % sid, {"role": "staff"}, at)[0] == 200
cust, cid = user("01055550002", "عميل"); cour, kid = user("01055550003", "مندوب"); ph, pid = user("01055550004", "صيدلي"); cour2, kid2 = user("01055550005", "مندوب٢")
adm_n = lambda uid, kind=None: db("SELECT kind,title,body,link,ref_type,ref_id FROM notifications WHERE user_id=?" + (" AND kind=?" if kind else "") + " ORDER BY id", (uid, kind) if kind else (uid,))
ok("no admin notifications before anything is submitted", not adm_n(1) and not adm_n(sid))
# --- مندوب ---
assert apply_docs(call, cour)[0] == 201
for who, uid in (("admin", 1), ("staff", sid)):
    r = adm_n(uid, "admin.couriers"); ok(who + " got new-courier notification", len(r) == 1 and r[0][3] == "admin:couriers" and "مندوب" in r[0][1] and r[0][5] == kid)
ok("courier name in body", adm_n(1, "admin.couriers")[0][2] == "مندوب")
# --- صيدلية ---
assert call("POST", "/providers/apply", {"name_ar": "صيدلية النور", "region_id": 3, "address": "ش 1"}, ph)[0] == 201
for who, uid in (("admin", 1), ("staff", sid)):
    r = adm_n(uid, "admin.providers"); ok(who + " got new-pharmacy notification with its name", len(r) == 1 and r[0][3] == "admin:providers" and r[0][2] == "صيدلية النور")
# --- رفض ثم إعادة تقديم المندوب ---
assert call("POST", "/admin/couriers/%d/review" % kid, {"status": "rejected", "reason": "x"}, at)[0] == 200
ok("review itself does not notify admins", len(adm_n(1, "admin.couriers")) == 1)
n0 = len(adm_n(1, "admin.couriers")); ra = apply_docs(call, cour); ok("courier re-apply accepted", ra[0] in (200, 201))
ok("re-apply notifies admins again", len(adm_n(1, "admin.couriers")) == n0 + 1 and "إعادة" in adm_n(1, "admin.couriers")[-1][1])
# --- شحن (مندوب معتمد) ---
assert call("POST", "/admin/couriers/%d/review" % kid, {"status": "approved"}, at)[0] == 200
assert call("POST", "/courier/topups", {"amount": 150, "transfer_ref": "REF-T6-1"}, cour)[0] in (200, 201)
for who, uid in (("admin", 1), ("staff", sid)):
    r = adm_n(uid, "admin.topup"); ok(who + " got top-up notification with amount", len(r) == 1 and r[0][3] == "admin:topups" and "150" in r[0][2])
# --- إعلان ---
c = sqlite3.connect(os.environ["LAQINO_DB"]); c.execute("INSERT OR IGNORE INTO categories(section,slug,name_ar,is_active) VALUES('souq','t6-cat','تصنيف',1)"); c.commit(); cat = c.execute("SELECT id FROM categories WHERE slug='t6-cat'").fetchone()[0]
c.execute("INSERT INTO listings(user_id,category_id,region_id,title,created_at) VALUES(?,?,3,'دراجة للبيع',?)", (cid, cat, int(time.time()))); c.commit()
for who, uid in (("admin", 1), ("staff", sid)):
    r = adm_n(uid, "admin.listing"); ok(who + " got new-listing notification", len(r) == 1 and r[0][3] == "admin:listings" and r[0][2] == "دراجة للبيع")
c.execute("INSERT INTO listings(user_id,category_id,region_id,title,status,created_at) VALUES(?,?,3,'قديم','approved',?)", (cid, cat, int(time.time()))); c.commit()
ok("an already-approved listing insert does not notify", len(adm_n(1, "admin.listing")) == 1)
# --- غير الإدارة لا يتلقى شيئًا إداريًا ---
for nm, uid in (("customer", cid), ("courier", kid), ("pharmacy", pid)):
    ok(nm + " receives no admin.* notifications", not [r for r in adm_n(uid) if r[0].startswith("admin.")])
ok("customer's own pending listing sends nothing to the customer", not [r for r in adm_n(cid) if r[0].startswith("admin.")])
# --- API للإدارة ---
s, j = call("GET", "/notifications", None, at); ok("admin API lists admin notifications", s == 200 and j["unread"] >= 5 and any(i["link"] == "admin:topups" for i in j["items"]))
ok("staff API count", call("GET", "/notifications/count", None, staff)[1]["unread"] >= 5)
# --- متصفح: admin.html الحقيقي ---
try: from playwright.sync_api import sync_playwright
except Exception: print("SKIP browser part"); print("ALL PASS"); sys.exit(0)
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp in (("phone", (390, 844)), ("desktop", (1280, 800))):
        _c = sqlite3.connect(os.environ["LAQINO_DB"]); _c.execute("UPDATE notifications SET read_at=NULL"); _c.commit(); _c.close()
        ctx = b.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block"); ctx.add_init_script("sessionStorage.setItem('at','%s')" % staff)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/fonts.*/**", lambda r: r.abort()); pg.goto(BASE + "/admin.html"); pg.wait_for_selector(".lqn-b", state="visible"); pg.wait_for_selector(".lqn-c:not([hidden])")
        T = "[admin %s] " % name
        ok(T + "bell in admin header", pg.evaluate("!!document.querySelector('header .lqn')")); ok(T + "badge count >= 5", int(pg.inner_text(".lqn-c")) >= 5)
        box = pg.locator(".lqn-b").bounding_box(); ok(T + "bell visible in viewport, >=44px", box["x"] >= 0 and box["x"] + box["width"] <= vp[0] and box["width"] >= 44)
        ok(T + "logout button still visible", pg.locator("#out").is_visible())
        pg.click(".lqn-b"); pg.wait_for_selector(".lqn-i"); ok(T + "list has the admin notifications", pg.locator(".lqn-i").count() >= 5)
        ok(T + "no horizontal scroll", pg.evaluate("document.documentElement.scrollWidth<=innerWidth"))
        if os.environ.get("LAQINO_SHOTS"): os.makedirs(os.environ["LAQINO_SHOTS"], exist_ok=True); pg.screenshot(path=os.path.join(os.environ["LAQINO_SHOTS"], "admin-%s.png" % name))
        pg.locator(".lqn-i", has_text="طلب شحن").first.click()
        pg.wait_for_selector("nav button.on:text-is('الشحن')"); ok(T + "clicking top-up notification opens the Top-ups section", True)
        ok(T + "notification marked read", db("SELECT read_at IS NOT NULL FROM notifications WHERE user_id=? AND kind='admin.topup'", (sid,))[0][0] == 1)
        pg.click(".lqn-b"); pg.wait_for_selector(".lqn-i"); pg.locator(".lqn-i", has_text="إعلان جديد").first.click()
        pg.wait_for_selector("nav button.on:text-is('الإعلانات')"); ok(T + "clicking listing notification opens Listings section", True)
        ok(T + "no JS errors", not errs); ctx.close()
    # بلا توكن إدارة: لا جرس
    ctx = b.new_context(service_workers="block"); pg = ctx.new_page(); pg.route("**/fonts.*/**", lambda r: r.abort()); pg.goto(BASE + "/admin.html"); pg.wait_for_timeout(600)
    ok("admin login screen: no bell", not pg.locator(".lqn-b").is_visible()); ctx.close(); b.close()
print("ALL PASS")
