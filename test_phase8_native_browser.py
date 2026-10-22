# المرحلة 8: static/native.js في Chromium حقيقي مع Capacitor وهمي (لا جهاز ولا Firebase). يُتخطى إن غاب playwright.
import os, sys, json, threading, urllib.request, urllib.error, tempfile, time
_TMP = tempfile.mkdtemp(prefix="laqino-p8b-")
os.environ["LAQINO_DB"] = os.path.join(_TMP, "t.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "up"); os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
from http.server import ThreadingHTTPServer
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP (playwright not installed)"); sys.exit(0)
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN"
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % srv.server_address[1]
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
MOCK = """
window.__calls = []; window.__ls = {};
window.Capacitor = { isNativePlatform: () => %s, Plugins: { PushNotifications: {
  _l: {}, addListener(n, f) { this._l[n] = f; window.__calls.push('on:' + n); return Promise.resolve({remove(){}}); },
  createChannel(c) { window.__calls.push('channel:' + c.id); return Promise.resolve(); },
  checkPermissions() { return Promise.resolve({ receive: 'prompt' }); },
  requestPermissions() { window.__calls.push('ask'); return Promise.resolve({ receive: 'granted' }); },
  register() { window.__calls.push('register'); setTimeout(() => this._l.registration && this._l.registration({ value: 'FCMTOKEN_' + 'x'.repeat(40) }), 50); return Promise.resolve(); } } } };
"""
def run(native):
    posts = []
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(MOCK % ("true" if native else "false"))
        def route(r):
            rq = r.request
            if "/api/fcm/" in rq.url: posts.append((rq.url.split("/api/fcm/")[1], rq.headers.get("authorization"), json.loads(rq.post_data or "{}"))); r.fulfill(status=200, content_type="application/json", body='{"ok":true}')
            else: r.continue_()
        pg.route("**/*", route)
        pg.goto(BASE + "/"); pg.wait_for_timeout(700)
        if native:   # phase-34: نافذة الشرح (perm.js) تسبق إذن النظام؛ نضغط «تمام، تابع» كما يفعل المستخدم
            pg.click("#laq-perm-y", timeout=5000); pg.wait_for_timeout(700)
        calls = pg.evaluate("window.__calls")
        pre = list(posts)
        pg.evaluate("localStorage.setItem('t','SESSIONTOKEN')"); pg.wait_for_timeout(16500)   # الدخول بعد التشغيل: مزامنة كل 15ث
        after = list(posts)
        pg.evaluate("fetch('/api/logout',{method:'POST',body:'{}'}).catch(()=>{})"); pg.wait_for_timeout(500)
        out = list(posts); b.close()
    return calls, pre, after, out, errs
calls, pre, after, out, errs = run(True)
ok("native: asks permission, creates laqino_alerts channel, registers, listens for tap/receive", {"ask", "register", "channel:laqino_alerts", "on:registration", "on:pushNotificationActionPerformed", "on:pushNotificationReceived"} <= set(calls))
ok("native: no register POST before login (no token)", pre == [])
ok("native: after login the device token is POSTed once with the session bearer", after == [("register", "Bearer SESSIONTOKEN", {"token": "FCMTOKEN_" + "x" * 40, "platform": "android"})])
ok("native: logout unregisters the device token before the session is dropped", out[-1][0] == "unregister" and out[-1][1] == "Bearer SESSIONTOKEN" and out[-1][2]["token"].startswith("FCMTOKEN_"))
ok("native: no page errors", not errs)
calls, pre, after, out, errs = run(False)
ok("plain browser/PWA: native.js is inert (no plugin calls, no POST, no errors)", calls == [] and out == [] and not errs)
print("ALL PASSED")
