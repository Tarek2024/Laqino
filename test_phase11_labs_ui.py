# المرحلة 11 / A-5: واجهة المعامل (تبويب فرعي في الطبي + البحث العام + تبويب الإدارة). fake-DOM في node، ليس متصفحًا.
# البيانات هنا بيانات اختبار داخل قاعدة مؤقتة فقط.
import os, json, threading, urllib.request, urllib.error, urllib.parse, tempfile, time, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8788), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8788"; D = os.path.dirname(os.path.abspath(__file__)); HN = os.path.join(D, "test_ui_page_harness.js")
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
r = page("index", cu, [{"js": "mt='lab';go(4)", "snap": "v", "wait": 1000}])
ok("no labs: medical tab has no labs segment, falls back to medicines, nothing invented", not r["errs"] and "المعامل" not in r["v"] and "الأدوية" in r["v"] and "الأطباء" in r["v"])
def add(**k): return call("POST", "/admin/labs", {"name_ar": "معمل الشفاء", "region_id": 3, "address": "شارع المحطة", "hours": "يوميًا 8ص-10م", "tests": "صورة دم كاملة، سكر صائم", "home_visit": True, "phone": "0473111111", **k}, at)[1]["id"]
l1 = add(); call("POST", f"/admin/labs/{l1}/publish", {"published": True}, at)
l2 = add(name_ar="مختبر النيل", tests="هرمونات الغدة", home_visit=False, phone="", whatsapp="01055550000"); call("POST", f"/admin/labs/{l2}/publish", {"published": True}, at)
add(name_ar="مخفي غير منشور")
r = page("index", cu, [{"js": "mt='lab';go(4)", "snap": "v", "wait": 1200}])
ok("labs segment appears once published labs exist, lists published only", not r["errs"] and "المعامل" in r["v"] and "معمل الشفاء" in r["v"] and "مختبر النيل" in r["v"] and "مخفي غير منشور" not in r["v"])
ok("card shows address, hours, tests, home-visit badge only for the lab that offers it", "شارع المحطة" in r["v"] and "يوميًا 8ص-10م" in r["v"] and "صورة دم كاملة" in r["v"] and r["v"].count("سحب عينات منزلي") == 1)
ok("labs list hides numbers: no tel/wa links, one reveal button per lab", "tel:" not in r["v"] and "wa.me/" not in r["v"] and r["v"].count("عرض رقم التواصل") == 2)
r2 = page("index", cu, [{"js": "mt='lab';go(4)", "wait": 1000}, {"js": f"lbct({l1})", "snap": f"lc{l1}", "wait": 800}, {"js": f"lbct({l2})", "snap": f"lc{l2}", "wait": 800}])
ok("reveal: call link for phone, WhatsApp link with 20 country code, no empty links", not r2["errs"] and "tel:0473111111" in r2[f"lc{l1}"] and "wa.me/" not in r2[f"lc{l1}"] and "wa.me/201055550000" in r2[f"lc{l2}"] and "tel:" not in r2[f"lc{l2}"])
r = page("index", cu, [{"js": "LQ={q:'هرمونات',my:false};mt='lab';go(4)", "snap": "v", "wait": 1200}])
ok("search by test name narrows the list", "مختبر النيل" in r["v"] and "معمل الشفاء" not in r["v"])
r = page("index", cu, [{"js": "LQ={q:'zzqq',my:false};mt='lab';go(4)", "snap": "v", "wait": 1200}])
ok("no match: clear empty state with a way back", not r["errs"] and "مفيش معامل مطابقة" in r["v"] and "مسح البحث" in r["v"])
r = page("index", cu, [{"js": "mt='lab';go(4)", "wait": 800}, {"js": "var _f=fetch;fetch=(u,o)=>String(u).includes('/labs?q=')?Promise.reject(new Error('x')):_f(u,o);go(4)", "snap": "v", "wait": 1200}])
ok("labs request failing shows an error state with retry, not a blank page", not r["errs"] and "حاول تاني" in r["v"])
r = page("index", cu, [{"js": "mt='dr';go(4)", "snap": "v", "wait": 1000}])
ok("doctors and medicines sub-tabs still render", not r["errs"] and "ابحث عن طبيب" in r["v"] and "المعامل" in r["v"])
r = page("index", cu, [{"js": "window.gq='هرمونات';go(5)", "snap": "v", "wait": 1300}])
ok("global search returns the labs section", not r["errs"] and "المعامل" in r["v"] and "مختبر النيل" in r["v"] and "مخفي غير منشور" not in r["v"])
r = page("index", cu, [{"js": "window.gq='هرمونات';go(5)", "wait": 1000}, {"js": "gsAll('lab')", "snap": "v", "wait": 1300}])
ok("'show all' opens the labs sub-tab with the query", not r["errs"] and "مختبر النيل" in r["v"] and "معمل الشفاء" not in r["v"] and 'value="هرمونات"' in r["v"])
r = page("admin", at, [{"js": "tab='labs';shell()", "snap": "v", "wait": 1500}])
ok("admin labs tab renders form + list with publish state", not r["errs"] and "إضافة معمل" in r["v"] and "معمل الشفاء" in r["v"] and "غير منشور" in r["v"] and "سحب عينات منزلي" in r["v"])
print("ALL PASSED")
