# الخطوة 3 في Chromium حقيقي (مقاس موبايل): العميل يطلب عروضًا، المقدم يقدّم عرضه، الإدارة تعتمد، العميل يختار، المقدم يؤكد ثم يظهر رقم العميل،
# ثم نزاع يفتحه العميل وتحسمه الإدارة. يُتخطى بأمان إن لم يتوفر playwright/Chromium.
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser part (playwright not installed)"); sys.exit(0)
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % srv.server_address[1]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(os.environ["LAQINO_DB"]); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
CU, PV1, PV2 = user("01066660001"), user("01066660002"), user("01066660003")
tid = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
def prov(name, owner):
    p = call("POST", "/admin/services", {"name_ar": name, "type_id": tid, "region_id": 3, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
    call("POST", f"/admin/services/{p}/publish", {"published": True}, at); call("POST", "/admin/service-owners", {"provider_id": p, "phone": owner}, at); return p
p1, p2 = prov("المعلم سمير", "01066660002"), prov("المعلم كمال", "01066660003")
R1 = call("POST", "/service-requests", {"type_id": tid, "region_id": 3, "description": "محتاج سباك لإصلاح تسريب في الحمام", "address": "شارع النصر عمارة 5"}, CU)[1]["id"]
errs, bad = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    def page_for(token, url="", region=True, admin=False, prompt_text=""):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: d.accept(prompt_text))
        pg.on("response", lambda r: bad.append((r.status, r.url.replace(BASE, ""))) if r.status >= 400 else None)
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "ERR_TUNNEL" not in m.text and "ERR_NAME_NOT_RESOLVED" not in m.text and "fonts" not in m.text and "status of 4" not in m.text else None)
        pg.add_init_script("try{localStorage.setItem('t','%s');%s}catch(e){}" % (token, "localStorage.setItem('rg','3');localStorage.setItem('rgn','المنطقة')" if region else "")); pg.goto(BASE + url); return pg
    # ---------- العميل يطلب عروضًا
    pc = page_for(CU, prompt_text="المقدم طلب مبلغًا أكبر من العرض"); pc.wait_for_timeout(600); pc.evaluate("go(6)"); pc.wait_for_selector("text=اطلب عروض أسعار", timeout=8000)
    ok("customer sees both providers pre-checked", pc.locator(f".sqp{R1}:checked").count() == 2 and "المعلم سمير" in pc.inner_text("body"))
    pc.uncheck(f".sqp{R1} >> nth=1"); pc.check(f".sqp{R1} >> nth=1")
    pc.click("button:has-text('اطلب عروض أسعار')"); pc.wait_for_selector("text=اتبعت طلبك", timeout=8000)
    ok("request moved to awaiting_quotes with 2 invites", sql("select status from service_requests where id=?", (R1,))[0][0] == "awaiting_quotes" and sql("select count(*) from service_request_invites")[0][0] == 2)
    ok("invite button is gone afterwards", pc.locator("button:has-text('اطلب عروض أسعار')").count() == 0)
    # ---------- المقدم الأول يقدّم عرضه من الواجهة
    pp = page_for(PV1); pp.wait_for_timeout(600); pp.evaluate("go(3)"); pp.wait_for_selector("#qp%d" % R1, timeout=8000)
    ok("provider sees a quote form and no direct-accept button", pp.locator("button:has-text('اقبل الطلب')").count() == 0 and pp.locator("button:has-text('قدّم عرضك')").count() == 1)
    pp.fill("#qp%d" % R1, "200"); pp.fill("#qn%d" % R1, "شامل الخامات"); pp.click("button:has-text('قدّم عرضك')"); pp.wait_for_selector("text=بانتظار اعتماد الإدارة", timeout=8000)
    ok("quote saved as pending", sql("select price,status from service_quotes where request_id=?", (R1,)) == [(200, "pending")])
    pp.fill("#qp%d" % R1, "190"); pp.click("button:has-text('عدّل عرضك')"); pp.wait_for_timeout(800)
    ok("provider can edit price from the UI", sql("select price from service_quotes where request_id=?", (R1,))[0][0] == 190)
    pp.fill("#qp%d" % R1, "200"); pp.click("button:has-text('عدّل عرضك')"); pp.wait_for_timeout(800)
    pp.fill("#qn%d" % R1, "كلمني 01012345678"); pp.click("button:has-text('عدّل عرضك')"); pp.wait_for_selector("text=ممنوع كتابة أرقام", timeout=8000)
    ok("phone number in note is refused with a message", True)
    call("POST", f"/my/service-jobs/{R1}/quote", {"price": 150}, PV2)
    # ---------- الإدارة تعتمد
    pa = page_for("", "/admin.html", region=False); pa.fill("input >> nth=0", "01000000000"); pa.fill("input[type=password]", "AdminPass123"); pa.click("button >> text=دخول"); pa.wait_for_selector("nav", timeout=8000)
    pa.click("nav button[data-k='svcreq']"); pa.wait_for_selector("text=عروض أسعار بانتظار الاعتماد (2)", timeout=8000)
    ok("admin sees 2 pending quotes with provider names and prices", "المعلم سمير" in pa.inner_text("body") and "150" in pa.inner_text("body") and pa.locator("button:has-text('اعتماد')").count() == 2)
    pa.click("button:has-text('اعتماد') >> nth=0"); pa.wait_for_selector("text=عروض أسعار بانتظار الاعتماد (1)", timeout=8000)
    pa.click("button:has-text('اعتماد') >> nth=0"); pa.wait_for_selector("text=عروض أسعار بانتظار الاعتماد (0)", timeout=8000)
    ok("both quotes approved, request is quotes_received", sql("select count(*) from service_quotes where status='approved'")[0][0] == 2 and sql("select status from service_requests where id=?", (R1,))[0][0] == "quotes_received")
    # ---------- العميل يختار الأرخص
    pc.evaluate("go(6)"); pc.wait_for_selector("button:has-text('اختار العرض ده')", timeout=8000)
    body = pc.inner_text("body")
    ok("customer sees both prices, cheapest first, no phone", body.index("150") < body.index("200") and "01066660002" not in body and "01066660003" not in body)
    pc.click("button:has-text('اختار العرض ده') >> nth=0"); pc.wait_for_timeout(1500); pc.wait_for_selector("text=مستنيين تأكيد", timeout=8000)
    ok("selection recorded for the cheaper provider", sql("select status,provider_id from service_requests where id=?", (R1,)) == [("provider_selected", p2)])
    # ---------- المقدم المختار يؤكد فيظهر رقم العميل
    p2g = page_for(PV2); p2g.wait_for_timeout(600); p2g.evaluate("go(3)"); p2g.wait_for_selector("button:has-text('أكّد القبول')", timeout=8000)
    t2 = p2g.inner_text("body")
    ok("selected provider sees no customer phone/address before confirming", "01066660001" not in t2 and "شارع النصر" not in t2)
    p2g.click("button:has-text('أكّد القبول')"); p2g.wait_for_selector("text=01066660001", timeout=8000)
    ok("after confirming: accepted and customer phone visible", sql("select status from service_requests where id=?", (R1,))[0][0] == "accepted")
    ok("the losing quote was closed", sql("select status from service_quotes where provider_id=?", (p1,))[0][0] == "not_selected")
    # ---------- نزاع
    pc.evaluate("go(6)"); pc.wait_for_selector("button:has-text('فتح نزاع')", timeout=8000); pc.click("button:has-text('فتح نزاع')"); pc.wait_for_selector("text=الطلب في نزاع", timeout=8000)
    ok("customer dispute saved with reason", sql("select status,disputed_by,dispute_reason from service_requests where id=?", (R1,)) == [("disputed", "customer", "المقدم طلب مبلغًا أكبر من العرض")])
    pa2 = page_for("", "/admin.html", region=False, prompt_text="تم الاتفاق على السعر بين الطرفين"); pa2.fill("input >> nth=0", "01000000000"); pa2.fill("input[type=password]", "AdminPass123"); pa2.click("button >> text=دخول"); pa2.wait_for_selector("nav", timeout=8000)
    pa2.click("nav button[data-k='svcreq']"); pa2.wait_for_selector("button:has-text('حسم: اعتماد الطلب منجزًا')", timeout=8000)
    ok("admin sees the dispute reason", "المقدم طلب مبلغًا أكبر من العرض" in pa2.inner_text("body"))
    pa2.click("button:has-text('حسم: اعتماد الطلب منجزًا')"); pa2.wait_for_timeout(1200)
    ok("admin resolves the dispute -> done", sql("select status from service_requests where id=?", (R1,))[0][0] == "done")
    ok("no page errors and no unexpected 5xx", not errs and not [b for b in bad if b[0] >= 500])
    br.close()
if errs: print("ERRORS:", errs[:5])
print("ALL OK")
