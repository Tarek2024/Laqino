# المرحلة 11 / A-2 + المرحلة 4: ترتيب التنقل (الرئيسية، الطبي، السوق، خدمات لاقينو، حسابي) وتبويب حسابي. fake-DOM في node، ليس متصفحًا.
import os, re, json, threading, urllib.request, urllib.error, tempfile, time, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8783), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8783"; D = os.path.dirname(os.path.abspath(__file__)); HN = os.path.join(D, "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def page(tok, steps):
    o = subprocess.run(["node", HN, "index", BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    return json.loads(o.stdout)
html = open(os.path.join(D, "static", "index.html"), encoding="utf-8").read()
nav = re.search(r"<nav>(.*?)</nav>", html, re.S).group(1)
labels = [re.sub(r"<[^>]+>", "", re.findall(r"<span>[^<]+</span>", b)[-1]) for b in re.findall(r'<button id="t\d".*?</button>', nav, re.S)]
ok("nav has exactly 5 destinations: home, medical, souq, services, account", labels == ["الرئيسية", "الطبي", "السوق", "خدمات لاقينو", "حسابي"])
ok("delivery and the sub-sections are not separate nav items", len(labels) == 5 and not any(x in labels for x in ("دليفري", "التوصيل", "الأطباء", "المعامل", "العقارات")))
ok("no stale 'طلباتي' nav label", "طلباتي" not in labels)
ok("services nav button is always shown (never hidden)", '<button id="t6" hidden' not in html and '<button id="t6"' in html)
g = page("", [{"js": "go(3)", "snap": "v"}])
ok("guest account tab asks to sign in, no script errors", not g["errs"] and "سجّل دخولك" in g["v"] and "تسجيل الخروج" not in g["v"])
call("POST", "/register", {"phone": "01011111111", "name": "سارة", "password": "password1"}); tk = call("POST", "/login", {"phone": "01011111111", "password": "password1"})[1]["token"]
h = page(tk, [{"js": "go(0)", "snap": "v", "wait": 900}])
ok("home greets user, no change-password form / logout there", not h["errs"] and "أهلًا سارة" in h["v"] and 'id="cpo"' not in h["v"] and "تسجيل الخروج" not in h["v"])
a = page(tk, [{"js": "go(3)", "snap": "v", "wait": 900}])
ok("account tab: name, phone, logout, orders section", not a["errs"] and "حسابي" in a["v"] and "سارة" in a["v"] and "01011111111" in a["v"] and "تسجيل الخروج" in a["v"] and "طلباتي" in a["v"])
c = page(tk, [{"js": "CP=1;go(3)", "snap": "v", "wait": 900}])
ok("account tab shows change-password form once", 'id="cpo"' in c["v"] and c["v"].count('id="cpo"') == 1)
for i in (1, 2, 4):
    r = page(tk, [{"js": f"go({i})", "snap": "v", "wait": 900}]); ok(f"internal view {i} still renders without errors", not r["errs"] and len(r["v"]) > 50)
hub = page(tk, [{"js": "go(6)", "snap": "v", "wait": 900}])
ok("services hub holds delivery + local services, no script errors", not hub["errs"] and "التوصيل" in hub["v"] and "go(2)" in hub["v"] and "الخدمات المحلية" in hub["v"])
cls = page(tk, [{"js": "go(2)", "wait": 700}, {"js": "document.getElementById('t6').textContent=document.getElementById('t6').className+'|'+document.getElementById('t0').className", "snap": "t6", "wait": 50}])
ok("delivery view keeps the Services tab highlighted", not cls["errs"] and cls["t6"] == "on|")
print("ALL PASSED")
