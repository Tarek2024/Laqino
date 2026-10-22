# المهمة 4: جرس الإشعارات — Chromium حقيقي (هاتف 390x844 وكمبيوتر 1280x800) مع API وهمي يحاكي شكل مسارات notif.py.
# يخدم static/ من مجلد المشروع. لا يلمس أي قاعدة بيانات. يُتخطى إن لم يتوفر playwright.
import os, sys, json, threading, functools, http.server
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP (no playwright)"); sys.exit(0)
HERE = os.path.dirname(os.path.abspath(__file__)); ST = os.path.join(HERE, "static"); SH = os.environ.get("LAQINO_SHOTS")
if SH: os.makedirs(SH, exist_ok=True)
FAKE = os.path.join(os.environ.get("TMPDIR", "/tmp"), "laq-fake-index"); os.makedirs(FAKE, exist_ok=True)
open(os.path.join(FAKE, "index.html"), "w").write('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>لاقينو</title></head><body><header style="background:#0f2a5c;color:#fff;padding:14px">لاقينو</header><main>تطبيق</main><script src="/notif.js" defer></script></body></html>')
class Q(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, p):
        p = p.split("?")[0]; f = os.path.join(FAKE if p in ("/", "/index.html") else ST, "index.html" if p == "/" else p.lstrip("/")); return f
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Q); threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def ok(n, c):
    print(("PASS " if c else "FAIL ") + n); (c or sys.exit(1))
S = {"items": [], "reads": []}
def mk(i, t, link="orders", rd=0): return {"id": i, "title": t, "body": "تفاصيل " + str(i), "link": link, "read": rd, "created_at": int(__import__("time").time()) - 7200, "read_at": None}
def api(route):
    r = route.request; u = r.url.split("/api")[1]; h = r.headers
    if h.get("authorization") != "Bearer TOK": return route.fulfill(status=401, content_type="application/json", body=json.dumps({"error": "سجّل الدخول أولًا"}))
    J = lambda o, c=200: route.fulfill(status=c, content_type="application/json", body=json.dumps(o))
    if u.startswith("/notifications/count"): return J({"unread": sum(1 for n in S["items"] if not n["read"])})
    if u.startswith("/notifications/read"):
        b = json.loads(r.post_data or "{}"); S["reads"].append(b)
        for n in S["items"]:
            if b.get("all") or n["id"] in b.get("ids", []): n["read"] = 1
        return J({"ok": True})
    if u.startswith("/notifications"):
        import urllib.parse as up; q = up.parse_qs(up.urlparse(u).query); a = int(q.get("after", [0])[0])
        return J(sorted([n for n in S["items"] if n["id"] > a], key=lambda n: -n["id"]))
    return J({"error": "x"}, 404)
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, page_url in (("phone-index", (390, 844), "/"), ("phone-pharm", (390, 844), "/pharmacy.html"), ("phone-courier", (390, 844), "/courier.html"), ("desk-pharm", (1280, 800), "/pharmacy.html")):
        S["items"] = [mk(1, "تم قبول طلبك", rd=1), mk(2, "مندوب في الطريق"), mk(3, "رد جديد من صيدلية", "medical")]; S["reads"] = []
        ctx = b.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block"); ctx.add_init_script("localStorage.setItem('t','TOK')")
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/api/**", api); pg.route("**/fonts.*/**", lambda r: r.abort())
        pg.goto(BASE + page_url); pg.wait_for_selector(".lqn-b", state="visible"); pg.wait_for_function("document.querySelector('.lqn-c') && !document.querySelector('.lqn-c').hidden")
        T = name + ": "
        ok(T + "badge shows 2 unread", pg.inner_text(".lqn-c") == "2")
        ok(T + "title prefixed (2)", pg.title().startswith("(2)"))
        ok(T + "aria-label mentions count", "2" in pg.get_attribute(".lqn-b", "aria-label"))
        box = pg.locator(".lqn-b").bounding_box(); ok(T + "bell tap target >=44px", box["width"] >= 44 and box["height"] >= 44)
        ok(T + "bell inside viewport", box["x"] >= 0 and box["x"] + box["width"] <= vp[0] and box["y"] >= 0)
        if "pharm" in name or "courier" in name:
            ok(T + "bell mounted in #ph-end", pg.evaluate("!!document.querySelector('#ph-end .lqn')"))
            ok(T + "bell and back link don't overlap", pg.evaluate("(()=>{const a=document.querySelector('.back').getBoundingClientRect(),b=document.querySelector('.lqn-b').getBoundingClientRect();return a.right<=b.left||b.right<=a.left})()"))
        pg.click(".lqn-b"); pg.wait_for_selector(".lqn-p")
        pg.wait_for_selector(".lqn-i")
        ok(T + "list shows 3 items", pg.locator(".lqn-i").count() == 3)
        ok(T + "2 marked unread", pg.locator(".lqn-i.u").count() == 2)
        pb = pg.locator(".lqn-p").bounding_box(); ok(T + "panel inside viewport", pb["x"] >= 0 and pb["x"] + pb["width"] <= vp[0] + 1 and pb["y"] + pb["height"] <= vp[1])
        ok(T + "no horizontal scroll", pg.evaluate("document.documentElement.scrollWidth<=innerWidth"))
        if SH: pg.screenshot(path=os.path.join(SH, name + "-open.png"))
        pg.keyboard.press("Escape"); ok(T + "Escape closes", pg.locator(".lqn-p").count() == 0)
        pg.click(".lqn-b"); pg.wait_for_selector(".lqn-p"); pg.mouse.click(5, vp[1] - 5); ok(T + "outside click closes", pg.locator(".lqn-p").count() == 0)
        pg.click(".lqn-b"); pg.wait_for_selector(".lqn-i"); pg.click(".all"); pg.wait_for_function("document.querySelector('.lqn-c').hidden")
        ok(T + "mark-all sent {all:true}", {"all": True} in S["reads"]); ok(T + "badge hidden after mark-all", pg.evaluate("document.querySelector('.lqn-c').hidden"))
        ok(T + "title prefix removed", not pg.title().startswith("("))
        ok(T + "no JS errors", not errs)
        ctx.close()
    # --- إشعار جديد يظهر كتنبيه، والنقر عليه يعلّم ويفتح اللوحة الصحيحة ---
    S["items"] = [mk(1, "قديم", rd=1)]; S["reads"] = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); ctx.add_init_script("localStorage.setItem('t','TOK')")
    pg = ctx.new_page(); pg.route("**/api/**", api); pg.route("**/fonts.*/**", lambda r: r.abort()); pg.goto(BASE + "/")
    pg.wait_for_selector(".lqn-b"); pg.wait_for_timeout(600)
    ok("first load: no toast for existing", pg.locator(".lqn-t").count() == 0 and pg.locator(".lqn-c").is_hidden())
    S["items"].append(mk(2, "طلب توصيل جديد", "courier")); pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    pg.wait_for_selector(".lqn-t", timeout=5000); ok("new notification toast appears", "طلب توصيل جديد" in pg.inner_text(".lqn-t")); ok("badge = 1", pg.inner_text(".lqn-c") == "1")
    S["items"].append(mk(3, "ثانٍ", "courier")); pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_function("document.querySelector('.lqn-c').textContent=='2'")
    pg.click(".lqn-t"); pg.wait_for_url("**/courier.html"); ok("toast click navigates to courier panel by link", pg.url.endswith("/courier.html"))
    ok("toast click marked it read", {"ids": [3]} in S["reads"] or {"ids": [2]} in S["reads"])
    ctx.close()
    # --- بلا تسجيل دخول: لا جرس. توكن منتهٍ: الجرس يختفي ---
    ctx = b.new_context(service_workers="block"); pg = ctx.new_page(); pg.route("**/api/**", api); pg.goto(BASE + "/pharmacy.html"); pg.wait_for_timeout(500)
    ok("logged out: bell hidden", not pg.locator(".lqn-b").is_visible()); ctx.close()
    ctx = b.new_context(service_workers="block"); ctx.add_init_script("localStorage.setItem('t','BAD')"); pg = ctx.new_page(); pg.route("**/api/**", api); pg.goto(BASE + "/pharmacy.html"); pg.wait_for_timeout(700)
    ok("expired token: bell hidden", not pg.locator(".lqn-b").is_visible()); ctx.close()
    # --- لوحة المندوب تُعاد رسمها كل 5 ثوانٍ: الجرس يبقى ---
    ctx = b.new_context(service_workers="block"); ctx.add_init_script("localStorage.setItem('t','TOK')"); pg = ctx.new_page(); S["items"] = [mk(1, "x")]
    pg.route("**/api/**", api); pg.goto(BASE + "/courier.html"); pg.wait_for_selector(".lqn-b"); pg.wait_for_timeout(6500)
    ok("courier bell survives 5s re-render", pg.locator("#ph-end .lqn-b").is_visible()); ctx.close()
    b.close()
print("ALL PASS")
