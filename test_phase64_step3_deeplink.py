"""phase-64 خطوة 3: رابط مباشر #rx=<رقم> لكارت روشتة + رسالة «اتحجز لصيدلية أخرى» لو الطلب مش في القايمة.
ملاحظة: الاختبار ده مستقل عن السيرفر (بيستبدل /api بردود جاهزة عن طريق route)، فمش محتاج server.py.
اختبار التكامل الحقيقي مع السيرفر يتضاف لما ملفات المشروع الكاملة تتوفر."""
import os, sys, json
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP (playwright not installed)"); sys.exit(0)
HERE = os.path.dirname(os.path.abspath(__file__))
HTML = open(os.path.join(HERE, "static", "pharmacy.html"), "rb").read()
RX = [{"id": i, "file_id": i, "images": [], "note": "روشتة %d" % i} for i in (5, 7)]
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
errs = []
def handler(route):
    u = route.request.url.split("laqino.test", 1)[1]
    path = u.split("#")[0].split("?")[0]
    if path == "/pharmacy.html": return route.fulfill(status=200, body=HTML, content_type="text/html; charset=utf-8")
    if path.startswith("/api/"):
        a = path[4:]
        if a == "/provider/prescriptions": body = RX
        elif a.endswith("/quote"): body = {"items": []}
        elif a.startswith("/provider/exchange"): body = {"items": []} if a == "/provider/exchange" else []
        else: body = []
        return route.fulfill(status=200, body=json.dumps(body), content_type="application/json")
    return route.fulfill(status=200, body="", content_type="text/plain")
def open_page(br, hash_):
    ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, service_workers="block")
    ctx.route("http://laqino.test/**", handler)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("try{localStorage.setItem('t','x');localStorage.setItem('rg','3')}catch(e){}")
    pg.goto("http://laqino.test/pharmacy.html" + hash_); pg.wait_for_selector("#rxc5", timeout=8000); pg.wait_for_timeout(400)
    return pg
with sync_playwright() as pw:
    br = pw.chromium.launch(args=["--no-sandbox"])
    pg = open_page(br, "#rx=7")
    ok("الرابط #rx=7: الكارت موجود ومتظلّل", pg.evaluate("document.getElementById('rxc7').style.outline!==''"))
    ok("الكارت ظاهر في الشاشة", pg.evaluate("(()=>{const r=document.getElementById('rxc7').getBoundingClientRect();return r.top<844&&r.bottom>0})()"))
    ok("مفيش رسالة «اتحجز» لروشتة موجودة", pg.query_selector("#rxgone") is None)
    ok("تبويب الطلبات هو المفتوح والـ hash اتنضّف لـ #o", pg.evaluate("document.querySelector('section[data-t=o]').classList.contains('on') && location.hash==='#o'"))
    pg.wait_for_timeout(3800)
    ok("التظليل بيختفي بعد ثواني", pg.evaluate("document.getElementById('rxc7').style.outline===''"))
    pg.evaluate("load()"); pg.wait_for_timeout(500)
    ok("إعادة التحميل ما بتكررش التظليل (مرة واحدة)", pg.evaluate("document.getElementById('rxc7').style.outline===''"))
    pg.context.close()
    pg = open_page(br, "#rx=99")
    t = pg.query_selector("#rxgone")
    ok("روشتة مش موجودة (#rx=99): ظهرت رسالة", t is not None and "اتحجز لصيدلية أخرى" in t.inner_text())
    ok("باقي الكروت لسه سليمة", pg.query_selector("#rxc5") is not None and pg.query_selector("#rxc7") is not None)
    ok("الـ hash اتنضّف", pg.evaluate("location.hash")=="#o")
    pg.evaluate("load()"); pg.wait_for_timeout(500)
    ok("الرسالة ما بتتكررش بعد تحميل تاني", pg.query_selector("#rxgone") is None)
    pg.context.close()
    for h in ("", "#o", "#s", "#rx=abc", "#rx="):
        pg = open_page(br, h)
        ok("بدون رابط صالح (%r): لا رسالة ولا تظليل" % h, pg.query_selector("#rxgone") is None and pg.evaluate("[...document.querySelectorAll('[id^=rxc]')].every(e=>e.style.outline==='')"))
        pg.context.close()
    pg = open_page(br, "#s")
    ok("#s لسه بيفتح تبويب المخزون", pg.evaluate("document.querySelector('section[data-t=s]').classList.contains('on')"))
    pg.context.close(); br.close()
ok("لا أخطاء JS", not errs)
print("ALL OK")
