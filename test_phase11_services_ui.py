# المرحلة 11 / A-4: واجهة الخدمات (تبويب العميل + بلاطة الرئيسية + البحث العام + تبويب الإدارة). fake-DOM في node، ليس متصفحًا.
# البيانات هنا بيانات اختبار داخل قاعدة مؤقتة فقط.
import os, json, threading, urllib.request, urllib.error, urllib.parse, tempfile, time, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8786), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8786"; D = os.path.dirname(os.path.abspath(__file__)); HN = os.path.join(D, "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + urllib.parse.quote(p, safe="/?=&"), json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def page(pg, tok, steps):
    o = subprocess.run(["node", HN, pg, BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); return json.loads(o.stdout)
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]; cu = user("01012345678")
# --- قبل أي بيانات: لا يظهر شيء وهمي
r = page("index", cu, [{"js": "go(0)", "snap": "v", "wait": 900}, {"js": "$('t6').textContent=String($('t6').hidden)", "snap": "t6", "wait": 50}])
ok("no providers: services card is shown disabled with a coming-soon badge (never a link to an empty page), nav button is always shown (hub keeps delivery)", not r["errs"] and "الخدمات المحلية" in r["v"] and "قريبًا" in r["v"] and "go(6)" not in r["v"] and "قيد التجهيز" not in r["v"] and "الخدمات المنزلية" not in r["v"] and r["t6"] == "false")
r = page("index", cu, [{"js": "go(6)", "snap": "v", "wait": 900}])
ok("no types: services view says nothing is available (no invented rows)", not r["errs"] and "مفيش خدمات متاحة" in r["v"] and "card ad" not in r["v"])
# --- بيانات اختبار
t1 = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]; t2 = call("POST", "/admin/service-types", {"name_ar": "كهرباء"}, at)[1]["id"]
def add(**k): return call("POST", "/admin/services", {"name_ar": "الأسطى محمود", "type_id": t1, "region_id": 3, "description": "تركيب وصيانة مواسير", "address": "شارع البحر", "phone": "01012340000", **k}, at)[1]["id"]
s1 = add(); call("POST", f"/admin/services/{s1}/publish", {"published": True}, at)
s2 = add(name_ar="كهربائي النور", type_id=t2, phone="", whatsapp="01099990000", description="تمديدات ولمبات"); call("POST", f"/admin/services/{s2}/publish", {"published": True}, at)
add(name_ar="مخفي غير منشور", phone="01011112222")
r = page("index", cu, [{"js": "go(0)", "snap": "v", "wait": 1000}])
ok("with published providers: home card becomes a link", not r["errs"] and 't:0};go(6)"' in r["v"] and "الخدمات" in r["v"])
r = page("index", cu, [{"js": "go(6)", "snap": "v", "wait": 1000}])
ok("services tab lists published providers only, with type chips, no phone number shown", not r["errs"] and "الأسطى محمود" in r["v"] and "كهربائي النور" in r["v"] and "مخفي غير منشور" not in r["v"] and "01012340000" not in r["v"] and "سباكة" in r["v"] and "كهرباء" in r["v"])
r = page("index", cu, [{"js": f"SV.t={t2};go(6)", "snap": "v", "wait": 1000}])
ok("type filter narrows the list", "كهربائي النور" in r["v"] and "الأسطى محمود" not in r["v"])
r = page("index", cu, [{"js": "SV={q:'zzqq',t:0};go(6)", "snap": "v", "wait": 1000}])
ok("no match: clear empty state with a way back", not r["errs"] and "مفيش مقدّمي خدمة مطابقين" in r["v"] and "مسح البحث" in r["v"])
r = page("index", cu, [{"js": "go(6)", "wait": 800}, {"js": f"svct({s1})", "wait": 900}, {"js": f"0", "snap": f"sc{s1}", "wait": 50}])
ok("logged-in user reveals the number (call link)", not r["errs"] and "tel:01012340000" in r[f"sc{s1}"])
r = page("index", cu, [{"js": "go(6)", "wait": 800}, {"js": f"svct({s2})", "wait": 900}, {"js": "0", "snap": f"sc{s2}", "wait": 50}])
ok("WhatsApp-only provider shows a WhatsApp link, no empty call link", "wa.me/201099990000" in r[f"sc{s2}"] and "tel:" not in r[f"sc{s2}"])
r = page("index", "", [{"js": "go(6)", "wait": 800}, {"js": f"svct({s1})", "snap": "v", "wait": 900}])
ok("guest is asked to sign in before seeing a number", not r["errs"] and "سجّل الدخول" in r["v"])
# --- البحث العام
r = page("index", cu, [{"js": "window.gq='محمود';go(5)", "snap": "v", "wait": 1300}])
ok("global search returns the service section", not r["errs"] and "الخدمات" in r["v"] and "الأسطى محمود" in r["v"] and "مخفي غير منشور" not in r["v"])
r = page("index", cu, [{"js": "window.gq='محمود';go(5)", "wait": 1000}, {"js": "gsAll('svc')", "snap": "v", "wait": 1200}])
ok("'show all' for services opens the services tab with the query", not r["errs"] and "الأسطى محمود" in r["v"] and 'value="محمود"' in r["v"])
# --- إصلاح رابط واتساب للأطباء (كان 21… بدل 201…)
sp = call("POST", "/admin/specialties", {"name_ar": "أطفال"}, at)[1]["id"]
dd = call("POST", "/admin/doctors", {"name_ar": "د. أحمد محمود", "specialty_id": sp, "region_id": 3, "clinic_name": "عيادة النور", "whatsapp": "01099999999", "schedule": "السبت 5-9"}, at)[1]["id"]; call("POST", f"/admin/doctors/{dd}/publish", {"published": True}, at)
r = page("index", cu, [{"js": "mt='dr';go(4)", "wait": 900}, {"js": f"dv({dd})", "wait": 900}, {"js": f"dct({dd})", "snap": "dco", "wait": 900}])
ok("doctor WhatsApp link (shown after the reveal) uses the 20 country code (wa.me/201099999999)", not r["errs"] and "wa.me/201099999999" in r["dco"] and "wa.me/21099999999" not in r["dco"])
# --- لوحة الإدارة
r = page("admin", at, [{"js": "tab='services';shell()", "snap": "v", "wait": 1500}])
ok("admin services tab renders types + providers with publish state", not r["errs"] and "أنواع الخدمات" in r["v"] and "سباكة" in r["v"] and "الأسطى محمود" in r["v"] and "غير منشور" in r["v"] and "منشور" in r["v"])
print("ALL PASSED")
