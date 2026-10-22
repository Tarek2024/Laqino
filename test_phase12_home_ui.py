# المرحلة 12 / المرحلة 3: كروت الأقسام والمحتوى المتغير في الرئيسية. fake-DOM في node، ليس متصفحًا.
# البيانات هنا بيانات اختبار داخل قاعدة مؤقتة فقط.
import os, re, json, threading, urllib.request, urllib.error, urllib.parse, tempfile, time, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8790), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8790"; D = os.path.dirname(os.path.abspath(__file__)); HN = os.path.join(D, "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + urllib.parse.quote(p, safe="/?=&"), json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def page(tok, steps):
    o = subprocess.run(["node", HN, "index", BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); return json.loads(o.stdout)
call("POST", "/register", {"phone": "01012345678", "name": "سارة", "password": "password1"}); cu = call("POST", "/login", {"phone": "01012345678", "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
# --- بدون أي بيانات: الأقسام المستقلة الأربعة، لا محتوى متغير وهمي
r = page("", [{"js": "go(0)", "snap": "v", "wait": 900}]); v = r["v"]
heads = re.findall(r'<span class="h">(.*?)</span>', v)
ok("four independent section cards in the required order, no script errors", not r["errs"] and heads == ["الخدمات الطبية", "سوق لاقينو", "الخدمات المحلية", "التوصيل"])
ok("each card has an icon, a short description and an open indicator (except the disabled one)", v.count('class="ti"') == 4 and v.count('class="d"') == 4 and v.count("svg class=\"i go\"") == 3)
ok("cards route to the right sections", "mt='rx';go(4)" in v and "mt='pr';PQ={q:'',c:0,n:1,showCats:true};go(4)" not in v and 'onclick="go(1)"' in v and 'onclick="go(2)"' in v)
ok("no dynamic section without real content (no ads, no service types)", "أحدث إعلانات السوق" not in v and "خدمات متاحة" not in v)
ok("search bar still first, heading present", v.index('id="gq"') < v.index('class="tiles"') and "تدور على إيه النهارده؟" in v)
# --- إعلان حقيقي معتمد + مزوّد خدمة منشور
cid = call("POST", "/admin/categories", {"parent_id": 2, "section": "souq", "slug": "furn", "name_ar": "أثاث", "is_active": True}, at)[1]["id"]
call("POST", f"/admin/categories/{cid}/fields", {"key": "price", "label_ar": "السعر", "type": "price", "required": True}, at)
lid = call("POST", "/listings", {"category_id": cid, "region_id": 3, "title": "كنبة ثلاثية", "description": "x", "fields": {"price": 3500}}, cu)[1]["id"]
r = page("", [{"js": "go(0)", "snap": "v", "wait": 900}])
ok("pending ad is not shown on home", "كنبة ثلاثية" not in r["v"] and "أحدث إعلانات السوق" not in r["v"])
call("POST", f"/admin/listings/{lid}/review", {"status": "approved"}, at)
r = page("", [{"js": "go(0)", "snap": "v", "wait": 1000}])
ok("approved ad appears under the latest-ads section with its price", not r["errs"] and "أحدث إعلانات السوق" in r["v"] and "كنبة ثلاثية" in r["v"] and any(x in r["v"] for x in ("3,500", "٣٬٥٠٠", "3٬500", "٣,٥٠٠")))
t1 = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
s1 = call("POST", "/admin/services", {"name_ar": "الأسطى محمود", "type_id": t1, "region_id": 3, "description": "x", "address": "y", "phone": "01012340000"}, at)[1]["id"]
r = page("", [{"js": "go(0)", "snap": "v", "wait": 900}]); ok("unpublished provider: services card stays disabled, no chips", "soon" in r["v"] and "خدمات متاحة" not in r["v"])
call("POST", f"/admin/services/{s1}/publish", {"published": True}, at)
r = page("", [{"js": "go(0)", "snap": "v", "wait": 1000}]); v = r["v"]
ok("published provider: services card becomes a link and a type chip appears", not r["errs"] and "soon" not in v and "SV={q:'',t:0};go(6)" in v and "خدمات متاحة" in v and f"svt({t1})" in v and "الأسطى محمود" not in v)
r = page("", [{"js": f"svt({t1})", "snap": "v", "wait": 1000}]); ok("type chip opens the filtered services list", "الأسطى محمود" in r["v"])
# --- فشل الشبكة لا يكسر الرئيسية
r = page("", [{"js": "var _f=fetch;fetch=(u,o)=>String(u).includes('/api/listings')||String(u).includes('/service-types')?Promise.reject(new Error('x')):_f(u,o);go(0)", "snap": "v", "wait": 1000}])
ok("dynamic content failing leaves the cards and search intact", not r["errs"] and r["v"].count('class="ti"') == 4 and 'id="gq"' in r["v"])
# Product catalogue remains available inside the medical section only.
source = open(os.path.join(D, "static/index.html"), encoding="utf-8").read()
ok("products remain accessible from the medical tabs (only when the admin flag is on)", "MT('pr','prod'" in source and "FT.products" in source and "const tabs=`" in source)
ok("no standalone products homepage card or config key", "prod:()=>card('prod'" not in source and "{key:'prod',name:'المنتجات'" not in source)
print("ALL PASSED")
