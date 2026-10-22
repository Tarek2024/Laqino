# الخطوة 5 في Chromium حقيقي (مقاس موبايل): العميل يقيّم بتعليق ثم يعدّل ثم يحذف، المقدم يبلّغ، الإدارة تخفي من لوحتها،
# والصفحة العامة تعرض التوزيع بلا هوية. يُتخطى بأمان إن لم يتوفر playwright/Chromium.
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
CU, PV = user("01066660001"), user("01066660002")
tid = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
pid = call("POST", "/admin/services", {"name_ar": "المعلم سمير", "type_id": tid, "region_id": 3, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
call("POST", f"/admin/services/{pid}/publish", {"published": True}, at); call("POST", "/admin/service-owners", {"provider_id": pid, "phone": "01066660002"}, at)
rid = call("POST", "/service-requests", {"type_id": tid, "region_id": 3, "description": "محتاج سباك لتسريب في الحمام"}, CU)[1]["id"]
call("POST", f"/my/service-jobs/{rid}/accept", {}, PV); call("POST", f"/my/service-jobs/{rid}/done", {}, PV)
errs, bad = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    def page_for(token, url="", prompt_text=""):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: d.accept(prompt_text))
        pg.on("response", lambda r: bad.append((r.status, r.url.replace(BASE, ""))) if r.status >= 400 else None)
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "ERR_TUNNEL" not in m.text and "ERR_NAME_NOT_RESOLVED" not in m.text and "fonts" not in m.text and "status of 4" not in m.text else None)
        pg.add_init_script("try{localStorage.setItem('t','%s');localStorage.setItem('rg','3');localStorage.setItem('rgn','المنطقة')}catch(e){}" % token); pg.goto(BASE + url); return pg
    # ---- العميل: تقييم بتعليق
    pc = page_for(CU); pc.wait_for_timeout(600); pc.evaluate("go(6)"); pc.wait_for_selector("button:has-text('قيّم المقدم')", timeout=8000)
    pc.select_option("#rq%d" % rid, "4"); pc.fill("#rcm%d" % rid, "شغل نضيف"); pc.click("button:has-text('قيّم المقدم')"); pc.wait_for_selector("text=تقييمك: ★★★★ — شغل نضيف", timeout=8000)
    ok("customer rated with a comment from the UI", sql("SELECT stars,comment FROM service_ratings")[0] == (4, "شغل نضيف"))
    # ---- تعديل
    pc.click("button:has-text('عدّل تقييمك')"); pc.wait_for_selector("button:has-text('حفظ التعديل')"); pc.select_option("#rq%d" % rid, "2"); pc.fill("#rcm%d" % rid, "اتغير رأيي"); pc.click("button:has-text('حفظ التعديل')")
    pc.wait_for_selector("text=تقييمك: ★★ — اتغير رأيي", timeout=8000)
    ok("customer edited the rating from the UI", sql("SELECT stars,comment,updated_at FROM service_ratings")[0][:2] == (2, "اتغير رأيي") and sql("SELECT updated_at FROM service_ratings")[0][0])
    # ---- الصفحة العامة
    pp = page_for(CU); pp.wait_for_timeout(600); pp.evaluate("go(6)"); pp.wait_for_selector("button:has-text('التقييمات (1)')", timeout=8000); pp.click("button:has-text('التقييمات (1)')")
    pp.wait_for_selector("text=اتغير رأيي", timeout=8000); body = pp.inner_text("body")
    ok("public ratings panel shows distribution, comment and edited mark, no identity", "2★ — 1" in body and "(معدّل)" in body and "01066660001" not in body and "u01" not in body)
    # ---- المقدم يبلّغ
    pv = page_for(PV, prompt_text="التقييم ده من حساب وهمي"); pv.wait_for_timeout(600); pv.evaluate("go(3)"); pv.wait_for_selector("button:has-text('تقييمات عملائي')", timeout=8000); pv.click("button:has-text('تقييمات عملائي')")
    pv.wait_for_selector("button:has-text('بلّغ عن التقييم')", timeout=8000); pv.click("button:has-text('بلّغ عن التقييم')"); pv.wait_for_selector("text=بلاغك قيد المراجعة", timeout=8000)
    ok("provider reported the rating from the UI", sql("SELECT status,reason FROM service_rating_reports")[0] == ("pending", "التقييم ده من حساب وهمي"))
    # ---- الإدارة تخفي
    pa = page_for("", "/admin.html", prompt_text="التعليق مخالف لسياسة الاستخدام"); pa.fill("input >> nth=0", "01000000000"); pa.fill("input[type=password]", "AdminPass123"); pa.click("button >> text=دخول"); pa.wait_for_selector("nav", timeout=8000)
    pa.click("nav button[data-k='svcreq']"); pa.wait_for_selector("text=بلاغات على تقييمات (1)", timeout=8000); pa.wait_for_timeout(500)
    pa.click("button:has-text('إخفاء التقييم')"); pa.wait_for_selector("text=بلاغات على تقييمات (0)", timeout=8000)
    ok("admin hid the rating from the panel", sql("SELECT hidden FROM service_ratings")[0][0] == 1 and sql("SELECT status FROM service_rating_reports")[0][0] == "upheld")
    # ---- العميل يرى الإخفاء ويحذف
    pc.evaluate("go(6)"); pc.wait_for_selector("text=الإدارة أخفت تقييمك", timeout=8000)
    ok("customer sees hidden notice and no edit button", pc.locator("button:has-text('عدّل تقييمك')").count() == 0)
    pc.click("button:has-text('احذف تقييمي')"); pc.wait_for_selector("button:has-text('قيّم المقدم')", timeout=8000)
    ok("customer deleted the rating from the UI and can rate again", sql("SELECT COUNT(*) FROM service_ratings")[0][0] == 0)
    br.close()
ok("no JS errors on any page", not errs)
ok("no unexpected 4xx/5xx responses", not [b for b in bad if b[0] >= 500])
print("ALL PASS")
