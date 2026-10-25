"""phase-62: كارت رد الصيدلية (شاشة 1) + صفحة الرد الكاملة (شاشة 2) في Chromium حقيقي بمقاس موبايل.
قاعدة مؤقتة وسيرفر حقيقي؛ md() لم تتغير ويتأكد الاختبار إنها هي اللي بتنشئ طلب التوصيل. LAQINO_SHOTS=dir يحفظ لقطات."""
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, shutil
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP (playwright not installed)"); sys.exit(0)
import server
from imgutil import png
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % srv.server_address[1]
SHOTS = os.environ.get("LAQINO_SHOTS")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
res = []
def ok(n, c): print(("PASS " if c else "FAIL ") + n); res.append(bool(c))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(os.environ["LAQINO_DB"]); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
CU = user("01062000001"); PT = {}; PID = {}
for k, (ph, nm) in {"cheap": ("01062000002", "صيدلية الشفاء"), "dear": ("01062000003", "صيدلية النور"), "part": ("01062000004", "صيدلية الأمل")}.items():
    PT[k] = user(ph); PID[k] = call("GET", "/me", None, PT[k])[1]["id"]
    call("POST", "/providers/apply", {"name_ar": nm, "region_id": 3, "address": "x"}, PT[k]); call("POST", f"/admin/providers/{PID[k]}/review", {"status": "approved"}, at)
call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at); call("POST", "/admin/settings", {"commission_type": "fixed", "commission_value": 4}, at)
fid = call("POST", "/files", {"data": png()}, CU)[1]["id"]
R = call("POST", "/medical/prescriptions", {"file_ids": [fid], "region_id": 3, "note": ""}, CU)[1]["id"]
call("POST", f"/admin/prescriptions/{R}/forward-many", {"provider_ids": list(PID.values())}, at)
it = lambda n, q, p, s="available": {"name": n, "qty": q, "unit_price": p if s == "available" else None, "item_status": s}
call("POST", f"/provider/prescriptions/{R}/quote", {"items": [it("باراسيتامول", 2, 25), it("أموكسيسيلين", 1, 80), it("فيتامين سي", 1, 40), it("كحول", 1, 10)], "note": "التوصيل متاح بعد الظهر"}, PT["cheap"])
call("POST", f"/provider/prescriptions/{R}/quote", {"items": [it("باراسيتامول", 2, 30), it("أموكسيسيلين", 1, 95), it("فيتامين سي", 1, 50), it("كحول", 1, 12)]}, PT["dear"])
call("POST", f"/provider/prescriptions/{R}/quote", {"items": [it("باراسيتامول", 2, 22), it("أموكسيسيلين", 1, 75), it("فيتامين سي", 1, None, "needs_confirmation"), it("كحول", 1, None, "unavailable")]}, PT["part"])
api_q = call("GET", f"/medical/prescriptions/{R}/quotes", None, CU)[1]
ok("API: 3 approved quotes", len(api_q["quotes"]) == 3)
errs = []
with sync_playwright() as pw:
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    br = pw.chromium.launch(executable_path=chromium, args=["--no-sandbox"] if chromium else None)
    ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and not any(s in m.text for s in ("ERR_TUNNEL", "ERR_NAME_NOT_RESOLVED", "fonts", "status of 4")) else None)
    dialogs = []
    def on_dialog(d):
        dialogs.append(d.message); d.accept("شارع النصر، عمارة 5" if d.type == "prompt" else None)
    pg.on("dialog", on_dialog)
    pg.add_init_script("try{localStorage.setItem('t','%s');localStorage.setItem('rg','3');localStorage.setItem('rgn','المنطقة')}catch(e){}" % CU)
    try: pg.goto(BASE)
    except Exception as e:
        if "ERR_BLOCKED_BY_ADMINISTRATOR" in str(e): print("SKIP (browser policy blocks localhost)"); sys.exit(0)
        raise
    pg.wait_for_timeout(600); pg.evaluate("mt='rx';rxm='quote';go(4)"); pg.wait_for_selector(".qcard", timeout=8000)
    cards = pg.locator(".qcard")
    ok("screen 1: one card per pharmacy reply (3)", cards.count() == 3)
    ok("exactly one 'الأكمل' badge, with a blue-framed card", pg.locator(".qbest").count() == 1 and pg.locator(".qcard.best").count() == 1)
    best = pg.locator(".qcard.best")
    ok("'الأكمل' is the cheapest complete reply (الشفاء، 180)", "صيدلية الشفاء" in best.inner_text() and "180" in best.inner_text())
    ok("complete badge is 'كامل' on 2 cards, partial badge 'جزئي' on 1", pg.locator(".qb.ok").count() == 2 and pg.locator(".qb.wn").count() == 1 and pg.locator(".qb.wn").inner_text() == "جزئي")
    part = pg.locator(".qcard", has_text="صيدلية الأمل")
    ok("partial card shows its total (119) without item counts", "119" in part.inner_text() and "أصناف" not in part.inner_text())
    ok("each card has the open-arrow", pg.locator(".qcard .qar").count() == 3)
    ok("card total is large (font >= 24px)", pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.qtot')).fontSize)") >= 24)
    ok("no delivery button inside the cards (moved to screen 2)", pg.locator(".qcard button").count() == 0)
    ok("no horizontal scroll on 390px", pg.evaluate("document.documentElement.scrollWidth<=document.documentElement.clientWidth+1"))
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, "screen1_cards.png"), full_page=True)
    # شاشة 2: الكامل الأغلى (يختبر الترتيب) ثم الجزئي
    part.click(); pg.wait_for_selector(".qd", timeout=8000)
    ok("detail view has no item-count display", "أصناف" not in pg.locator(".qd").inner_text())
    t = pg.locator(".qt tbody tr")
    ok("screen 2: table with 4 item rows", t.count() == 4)
    ok("row shows qty × price and line total (أموكسيسيلين 1 × 75 = 75)", pg.locator(".qt tbody tr", has_text="أموكسيسيلين").inner_text().replace("\n", " ").count("75") >= 2)
    ok("status icons: 2 available, 1 needs review, 1 unavailable in table", pg.locator(".qt .qi.ok").count() == 2 and pg.locator(".qt .qi.wn").count() == 1 and pg.locator(".qt .qi.no").count() == 1)
    ok("items sorted: available first, unavailable last", pg.locator(".qt tbody tr").nth(3).get_attribute("class") == "no" and pg.locator(".qt tbody tr").nth(2).get_attribute("class") == "wn")
    ok("prominent total box shows 119 ج", "119" in pg.locator(".qtotbox").inner_text() and "الإجمالي" in pg.locator(".qtotbox").inner_text())
    ok("last-update line shown", "آخر تحديث" in pg.locator(".qd").inner_text())
    ok("partial reply uses the optional-delivery wording", "اختياري" in pg.locator("button.qdel").inner_text())
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, "screen2_partial.png"), full_page=True)
    pg.click("button:has-text('رجوع للردود')"); pg.wait_for_selector(".qcard", timeout=8000)
    ok("back returns to the cards", pg.locator(".qcard").count() == 3)
    # الكامل الأرخص: ملاحظة الصيدلية + زر التوصيل الكبير يستدعي md() الأصلية
    pg.locator(".qcard.best").click(); pg.wait_for_selector(".qd", timeout=8000)
    ok("note from pharmacy shown", "التوصيل متاح بعد الظهر" in pg.locator(".qnote").inner_text())
    ok("all 4 rows available, total 180", pg.locator(".qt .qi.ok").count() == 4 and "180" in pg.locator(".qtotbox").inner_text())
    btn = pg.locator("button.qdel")
    ok("big delivery button at the end, full-width, complete wording", btn.inner_text() == "اطلب توصيل من هذه الصيدلية" and btn.bounding_box()["width"] > 300 and btn.bounding_box()["height"] >= 54)
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, "screen2_complete.png"), full_page=True)
    btn.click(); pg.wait_for_timeout(1500)
    row = sql("SELECT source_type,source_id,provider_id FROM medical_delivery_links")
    ok("md() created the delivery order for the right pharmacy (unchanged logic, prompt+confirm)", len(row) == 1 and row[0] == ("prescription", R, PID["cheap"]) and any("عنوان التسليم" in m for m in dialogs))
    pg.evaluate("go(4)")
    ok("no page errors", not errs)
    if errs: print(errs[:5])
    br.close()
print("DONE %d/%d" % (sum(res), len(res))); exit(0 if all(res) else 1)
