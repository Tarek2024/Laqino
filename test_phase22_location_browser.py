"""المرحلة 22 (الموقع الموحد) — Chromium حقيقي بمحاكاة GPS على قاعدة مؤقتة: موافقة، رفض، تعذّر، منطقة يدوية سابقة،
طلب توصيل بدبوس/بدونه، نافذة المنطقة، market.html، وعدم وجود تتبع مستمر."""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error, subprocess
ROOT = os.path.dirname(os.path.abspath(__file__)); S = ROOT + "/static/"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
js = open(S + "location.js", encoding="utf-8").read()
ok("node --check location.js", subprocess.run(["node", "--check", S + "location.js"]).returncode == 0)
ok("no continuous tracking anywhere in the project (watchPosition never used)", "watchPosition" not in js and all("watchPosition" not in open(S + f, encoding="utf-8").read() for f in ("index.html", "market.html", "native.js", "shell.js", "courier.html")))
ok("index.html loads location.js before shell.js; service worker caches it", S and open(S + "index.html", encoding="utf-8").read().index("/location.js") < open(S + "index.html", encoding="utf-8").read().index("/shell.js") and '"/location.js"' in open(S + "sw.js", encoding="utf-8").read())
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser checks (playwright not installed)"); print("ALL PASSED (static only)"); sys.exit(0)
_T = tempfile.mkdtemp(prefix="lq22b-"); os.environ["LAQINO_DB"] = _T + "/t.db"; os.environ["LAQINO_UPLOADS"] = _T + "/up"; os.makedirs(_T + "/up")
sys.path.insert(0, ROOT)
import server, testutil, sqlite3
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
# مناطق بإحداثيات: المركز 3 (الرياض) وقريتان
call("POST", "/admin/regions/3/coords", {"lat": 31.05, "lng": 30.95}, at)
VA = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "va", "name_ar": "قرية الأمل", "is_active": True, "lat": 31.06, "lng": 30.96}, at)[1]["id"]
VB = call("POST", "/admin/regions", {"parent_id": 3, "level": "village", "slug": "vb", "name_ar": "قرية النور", "is_active": True, "lat": 31.12, "lng": 31.02}, at)[1]["id"]
call("POST", "/admin/region-fees", {"region_id": VA, "fee": 15}, at); call("POST", "/admin/region-fees", {"region_id": VB, "fee": 15}, at); call("POST", "/admin/region-fees", {"region_id": 3, "fee": 20}, at)
POS = {"latitude": 31.0601, "longitude": 30.9601, "accuracy": 25}
# عدّاد استدعاءات الـGPS: لا استدعاء أكثر من اللازم، ولا watchPosition
SPY = """(()=>{const g=navigator.geolocation;window.__gp=0;window.__wp=0;if(!g)return;const o=g.getCurrentPosition.bind(g),w=g.watchPosition?g.watchPosition.bind(g):null;
g.getCurrentPosition=function(){window.__gp++;return o.apply(g,arguments)};g.watchPosition=function(){window.__wp++;return w?w.apply(g,arguments):0}})()"""
errs_ignored = ("ERR_NAME_NOT_RESOLVED", "ERR_TUNNEL_CONNECTION_FAILED", "ERR_INTERNET_DISCONNECTED", "Failed to load resource", "navigator.vibrate")
with sync_playwright() as p:
    b = p.chromium.launch()
    def page(geo=True, init="", w=390, h=844):
        kw = {"geolocation": POS, "permissions": ["geolocation"]} if geo else {}
        ctx = b.new_context(viewport={"width": w, "height": h}, locale="ar-EG", service_workers="block", **kw); pg = ctx.new_page(); pg.errs = []; pg.ctx = ctx
        pg.on("pageerror", lambda e: pg.errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and not any(x in m.text for x in errs_ignored) and pg.errs.append(m.text))
        pg.add_init_script(SPY)
        if init: pg.add_init_script(init)
        return pg
    ls = lambda pg, k: pg.evaluate("k=>localStorage.getItem(k)", k)
    def until(pg, key="laq_loc", n=80):   # الخادم يفرض CSP بلا unsafe-eval، فلا نستخدم wait_for_function بنص
        for _ in range(n):
            if ls(pg, key): return
            pg.wait_for_timeout(100)
        raise AssertionError("timeout waiting for " + key)

    # 1) أول فتح + موافقة: تحديد المنطقة تلقائيًا وحفظ الموقع
    pg = page(); pg.goto(BASE + "/"); until(pg); pg.wait_for_timeout(600)
    ok("granted: region chosen automatically (nearest village)", ls(pg, "rg") == str(VA) and ls(pg, "rgn") == "قرية الأمل")
    ok("granted: header chip shows the detected region", "قرية الأمل" in pg.inner_text("#rcn"))
    loc = json.loads(ls(pg, "laq_loc"))
    ok("granted: location saved on device with coordinates, accuracy and time", abs(loc["lat"] - 31.0601) < 1e-4 and abs(loc["lng"] - 30.9601) < 1e-4 and loc["acc"] == 25 and loc["rid"] == VA and loc["ts"] > 0)
    ok("granted: exactly one GPS read, no continuous tracking", pg.evaluate("window.__gp") == 1 and pg.evaluate("window.__wp") == 0)
    ok("granted: no JS errors", not pg.errs)
    pg.reload(); pg.wait_for_timeout(1500)
    ok("reload within 30 minutes: reuses the saved location without asking the GPS again", pg.evaluate("window.__gp") == 0 and ls(pg, "rg") == str(VA))
    ok("saved region drives the sections (souq tab queries use it)", pg.evaluate("R") == VA)
    pg.evaluate("go(1)"); pg.wait_for_timeout(700)
    ok("other sections open normally with the GPS region", not pg.errs and pg.evaluate("document.querySelector('#v').innerText.length>10"))
    # نافذة المنطقة
    pg.evaluate("openRg()"); pg.wait_for_timeout(400)
    t = pg.inner_text("#lq-loc-t")
    ok("region sheet shows the GPS status and keeps the manual pickers", "قرية الأمل" in t and pg.query_selector("#g") and pg.query_selector("#k") and pg.query_selector("#vl"))
    ok("region sheet: 'clear my location' available", pg.is_visible("#lq-loc-clr"))
    pg.click("#lq-loc-clr"); pg.wait_for_timeout(300)
    ok("clearing removes the saved coordinates but keeps the chosen region", ls(pg, "laq_loc") is None and ls(pg, "rg") == str(VA))
    pg.ctx.close()

    # 2) رفض الإذن: التطبيق يعمل والاختيار اليدوي كما هو، بلا إلحاح
    pg = page(geo=False, init="Object.defineProperty(navigator,'permissions',{value:{query:()=>Promise.resolve({state:'prompt'})}});"
              "{const g=navigator.geolocation;g.getCurrentPosition=function(ok,no){window.__gp=(window.__gp||0)+1;setTimeout(()=>no({code:1,message:'denied'}),20)}}")
    pg.goto(BASE + "/"); pg.wait_for_timeout(2000)
    ok("denied: app renders normally, no region forced", not pg.errs and ls(pg, "rg") is None and "اختار منطقتك" in pg.inner_text("#rcn"))
    ok("denied: asked once only", pg.evaluate("window.__gp") == 1 and ls(pg, "laq_loc_ask") == "1")
    pg.evaluate("openRg()"); pg.wait_for_timeout(400)
    ok("denied: sheet explains how to proceed and the manual flow is intact", "مرفوض" in pg.inner_text("#lq-loc-t") and pg.query_selector("#g"))
    pg.select_option("#g", index=1); pg.wait_for_timeout(500); pg.select_option("#k", value="3"); pg.wait_for_timeout(800)
    ok("denied: manual selection (governorate → markaz) still works and is saved", ls(pg, "rg") == "3" and not pg.errs)
    pg.reload(); pg.wait_for_timeout(1500)
    ok("denied: not asked again on the next open", pg.evaluate("window.__gp||0") == 0)
    pg.ctx.close()

    # 3) تعذّر تحديد الموقع (POSITION_UNAVAILABLE) وتعطّل الدعم نهائيًا
    for label, init in (("unavailable", "navigator.geolocation.getCurrentPosition=function(ok,no){setTimeout(()=>no({code:2}),20)}"),
                        ("timeout", "navigator.geolocation.getCurrentPosition=function(ok,no){setTimeout(()=>no({code:3}),20)}"),
                        ("no geolocation API", "Object.defineProperty(navigator,'geolocation',{value:undefined,configurable:true})")):
        pg = page(geo=False, init=init); pg.goto(BASE + "/"); pg.wait_for_timeout(1800)
        ok("%s: app works, no region forced, no errors" % label, not pg.errs and ls(pg, "rg") is None and pg.evaluate("document.querySelector('#v').innerText.length>10"))
        pg.evaluate("openRg()"); pg.wait_for_timeout(300)
        ok("%s: sheet gives a clear fallback message" % label, "يدويًا" in pg.inner_text("#lq-loc-t") or "اختار" in pg.inner_text("#lq-loc-t"))
        pg.ctx.close()

    # 4) منطقة مختارة يدويًا من قبل: لا تُستبدل بصمت، والزر يغيّرها بإرادة المستخدم
    pg = page(init="localStorage.setItem('rg','%d');localStorage.setItem('rgn','قرية النور')" % VB)
    pg.goto(BASE + "/"); until(pg); pg.wait_for_timeout(800)
    ok("existing manual region is NOT overridden by GPS at startup", ls(pg, "rg") == str(VB) and ls(pg, "rgn") == "قرية النور")
    pg.evaluate("openRg()"); pg.wait_for_timeout(300); pg.click("#lq-loc-go"); pg.wait_for_timeout(1200)
    ok("pressing 'حدّد موقعي' applies the GPS region explicitly", ls(pg, "rg") == str(VA) and "قرية الأمل" in pg.inner_text("#rcn"))
    ok("button path: still one-shot reads only (no watch)", pg.evaluate("window.__wp") == 0 and not pg.errs)
    pg.ctx.close()

    # 5) التوصيل: ملء تلقائي، تعديل، تحديد يدوي، وإرسال بدبوس/بدونه
    cu = user("01022222222", "عميل")
    init = "localStorage.setItem('t','%s')" % cu
    def orders(): return sqlite3.connect(os.environ["LAQINO_DB"]).execute("SELECT dropoff_text,dropoff_lat,dropoff_lng,region_id FROM delivery_orders ORDER BY id").fetchall()
    pg = page(init=init); pg.goto(BASE + "/"); until(pg); pg.wait_for_timeout(800)
    pg.evaluate("go(2)"); pg.wait_for_selector("#lq-dl", timeout=5000); pg.wait_for_timeout(500)
    ok("delivery: drop-off field is filled automatically from GPS", pg.input_value("#dr") == "موقعي الحالي (GPS)")
    ok("delivery: pickup field is NOT touched", pg.input_value("#pk") == "")
    ok("delivery: user is told the pin will be shared after acceptance", "بعد ما يقبل" in pg.inner_text("#lq-dl") and "25" in pg.inner_text("#lq-dl"))
    pg.fill("#dr", "عمارة 5 الدور 2 — موقعي"); pg.fill("#pk", "سوبرماركت الأمل"); pg.fill("#dt", "طلب تجريبي")
    ok("delivery: address can be edited freely", pg.input_value("#dr").startswith("عمارة 5"))
    pg.click("button.full:has-text('تأكيد الطلب')"); pg.wait_for_timeout(1200)
    o = orders()
    ok("delivery: order created with edited text AND the pin", len(o) == 1 and o[0][0].startswith("عمارة 5") and abs(o[0][1] - 31.0601) < 1e-4 and abs(o[0][2] - 30.9601) < 1e-4 and not pg.errs)  # المرحلة 28: المنطقة داخلية ولا يرسلها العميل
    # تحديد يدوي: إزالة الدبوس
    pg.evaluate("go(2)"); pg.wait_for_selector("#lq-dl"); pg.wait_for_timeout(400)
    pg.click("#lq-dl button:has-text('تحديد يدوي')"); pg.wait_for_timeout(200)
    ok("delivery: manual mode clears the auto text and the pin", pg.input_value("#dr") == "" and "اكتب عنوان التسليم" in pg.inner_text("#lq-dl"))
    pg.fill("#dr", "شارع المدرسة"); pg.fill("#pk", "محل"); pg.fill("#dt", "x")
    pg.click("button.full:has-text('تأكيد الطلب')"); pg.wait_for_timeout(1200)
    o = orders()
    ok("delivery: manual order has NO coordinates", len(o) == 2 and o[1][0] == "شارع المدرسة" and o[1][1] is None and o[1][2] is None)
    # زر استخدم موقعي بعد الإزالة (قراءة جديدة مرة واحدة)
    pg.evaluate("go(2)"); pg.wait_for_selector("#lq-dl"); pg.wait_for_timeout(300)
    pg.click("#lq-dl button:has-text('تحديد يدوي')"); pg.wait_for_timeout(100); pg.click("#lq-dl button:has-text('استخدم موقعي الحالي')"); pg.wait_for_timeout(1000)
    ok("delivery: 'use my location' re-applies the pin on demand", pg.input_value("#dr") == "موقعي الحالي (GPS)" and "موقع التسليم محدّد" in pg.inner_text("#lq-dl"))
    pg.ctx.close()

    # 6) التوصيل مع رفض GPS: الحقل يدوي بالكامل والطلب ينجح بلا إحداثيات
    pg = page(geo=False, init=init + ";navigator.geolocation.getCurrentPosition=function(ok,no){setTimeout(()=>no({code:1}),10)}")
    pg.goto(BASE + "/"); pg.wait_for_timeout(1200); pg.evaluate("localStorage.setItem('rg','%d');localStorage.setItem('rgn','قرية الأمل')" % VA); pg.reload(); pg.wait_for_timeout(1200)
    pg.evaluate("go(2)"); pg.wait_for_selector("#dr", timeout=5000); pg.wait_for_timeout(500)
    ok("delivery without GPS: field is empty and editable", pg.input_value("#dr") == "")
    pg.fill("#dr", "بيتي"); pg.fill("#pk", "المحل"); pg.fill("#dt", "y"); pg.click("button.full:has-text('تأكيد الطلب')"); pg.wait_for_timeout(1200)
    o = orders()
    ok("delivery without GPS: order succeeds exactly as before, no coordinates", len(o) == 3 and o[2][0] == "بيتي" and o[2][1] is None)
    pg.ctx.close()

    # 7) market.html يلتقط المنطقة المحفوظة؛ والأقسام الأخرى لا تتأثر
    pg = page(init="localStorage.setItem('rg','%d');localStorage.setItem('rgn','قرية الأمل')" % VA); pg.goto(BASE + "/market.html"); pg.wait_for_timeout(1200)
    ok("market.html: region filter preselects the saved region (can still choose all)", pg.input_value("#reg") == str(VA) and pg.evaluate("[...document.querySelectorAll('#reg option')][0].value===''") and not pg.errs)
    pg.ctx.close()

    # 8) لوحات أخرى تعمل: المندوب يرى رابط الخريطة بعد القبول فقط
    co = user("01033333333", "مندوب"); testutil.apply_docs(call, co, 3); cuid = call("GET", "/me", None, co)[1]["id"]
    call("POST", "/admin/couriers/%d/review" % cuid, {"status": "approved"}, at); call("POST", "/courier/online", {"online": True}, co)
    oid = call("GET", "/delivery/orders", None, cu)[1]
    pinned = sqlite3.connect(os.environ["LAQINO_DB"]).execute("SELECT id FROM delivery_orders WHERE dropoff_lat IS NOT NULL").fetchone()[0]
    ok("courier accepts the pinned order", call("POST", "/courier/orders/%d/accept" % pinned, None, co)[0] == 200); testutil.fare_ok(pinned)
    pg = page(geo=False); pg.add_init_script("localStorage.setItem('t','%s')" % co); pg.goto(BASE + "/courier.html"); pg.wait_for_timeout(2500)
    html = pg.inner_text("body")
    link = pg.query_selector("a[href*='google.com/maps']")
    ok("courier panel: map link for the drop-off appears for the accepted pinned order", link is not None and "31.0601" in (link.get_attribute("href") or "") .replace("%2C", ","))
    ok("courier panel: no JS errors %s" % pg.errs[:3], not pg.errs)
    pg.ctx.close()

    # 9) لا تتبّع في الخلفية: بعد 5 ثوانٍ لا قراءات إضافية
    pg = page(); pg.goto(BASE + "/"); until(pg); n = pg.evaluate("window.__gp"); pg.wait_for_timeout(5000)
    ok("no background polling: GPS read count unchanged after 5 s", pg.evaluate("window.__gp") == n == 1 and pg.evaluate("window.__wp") == 0)
    pg.ctx.close(); b.close()
print("ALL PASSED")
