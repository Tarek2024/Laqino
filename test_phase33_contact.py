# صفحة تواصل معنا (المرحلة 33 — Google Play).
import os, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8798), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8798"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
r = urllib.request.urlopen(BASE + "/contact"); h = r.read().decode()
ok("contact served 200 html", r.status == 200 and "text/html" in r.headers["Content-Type"])
ok("support email present", "Laqino100@gmail.com" in h)
ok("international WhatsApp link built", "wa.me/20" + server.WA_NUMBER.lstrip("0") in h)
ok("international phone displayed", "+20 10 1701 1170" in h)
ok("deletion page clearly offers external email and WhatsApp requests", "اطلب الحذف عبر البريد" in urllib.request.urlopen(BASE + "/delete-account").read().decode() and "اطلب الحذف عبر واتساب" in urllib.request.urlopen(BASE + "/delete-account").read().decode())
ok("privacy policy states in-app deletion is available now", "متاح بالفعل داخل التطبيق" in urllib.request.urlopen(BASE + "/privacy").read().decode())
ok("no unreplaced placeholders", "{{" not in h)
ok("links to delete-account and privacy", "/delete-account" in h and "/privacy" in h)
for p in ("/privacy", "/terms", "/delete-account"):
    ok("footer link on " + p, 'href="/contact"' in urllib.request.urlopen(BASE + p).read().decode())
