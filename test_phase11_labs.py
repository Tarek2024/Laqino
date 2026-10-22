# المرحلة 11 / A-5: معامل التحاليل (الخادم): إضافة من الإدارة بنشر مشروط، بحث بالاسم أو التحليل، فلتر المنطقة.
# كل البيانات هنا بيانات اختبار داخل قاعدة مؤقتة فقط.
import os, json, threading, urllib.request, urllib.error, urllib.parse, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8787), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
B = "http://127.0.0.1:8787"; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(B + "/api" + urllib.parse.quote(p, safe="/?=&"), json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]; cu = user("01012345678")
ok("nothing invented: no labs", call("GET", "/labs")[1] == [])
ok("customer/anonymous cannot manage labs", all(call(m, p, d, t)[0] in (401, 403) for m, p, d, t in (("POST", "/admin/labs", {}, cu), ("GET", "/admin/labs", None, cu), ("POST", "/admin/labs", {}, ""), ("POST", "/admin/labs/1/publish", {"published": True}, cu))))
def add(**k): return call("POST", "/admin/labs", {"name_ar": "معمل الشفاء", "region_id": 3, "address": "شارع المحطة", "hours": "يوميًا 8ص-10م", "tests": "صورة دم كاملة، سكر صائم، وظائف كبد", "home_visit": True, "phone": "0473111111", **k}, at)
st, r = add(); l1 = r["id"]
ok("new lab is created unpublished and invisible", st == 201 and r["is_published"] == 0 and call("GET", "/labs")[1] == [] and call("GET", f"/labs/{l1}")[0] == 404)
ok("invalid input rejected", add(phone="abc")[0] == 400 and add(region_id=99999)[0] == 400 and add(name_ar="ab")[0] == 400)
nc = add(name_ar="بدون عنوان", address="")[1]["id"]; nn = add(name_ar="بدون تواصل", phone="", whatsapp="")[1]["id"]
ok("cannot publish without address or contact", call("POST", f"/admin/labs/{nc}/publish", {"published": True}, at)[0] == 409 and call("POST", f"/admin/labs/{nn}/publish", {"published": True}, at)[0] == 409)
ok("customer cannot publish; admin can", call("POST", f"/admin/labs/{l1}/publish", {"published": True}, cu)[0] == 403 and call("POST", f"/admin/labs/{l1}/publish", {"published": True}, at)[0] == 200)
l2 = add(name_ar="مختبر النيل", tests="تحليل بول، هرمونات الغدة", home_visit=False, phone="", whatsapp="01055550000")[1]["id"]; call("POST", f"/admin/labs/{l2}/publish", {"published": True}, at)
rows = call("GET", "/labs")[1]
ok("only published labs are public, with home-visit flag", sorted(x["name_ar"] for x in rows) == sorted(["معمل الشفاء", "مختبر النيل"]) and next(x for x in rows if x["id"] == l1)["home_visit"] == 1 and next(x for x in rows if x["id"] == l2)["home_visit"] == 0)
ok("public rows hide the publish flag", all("is_published" not in x for x in rows))
ok("public list and detail carry no phone/whatsapp (numbers need login via /contact)", all("phone" not in x and "whatsapp" not in x for x in rows) and "phone" not in call("GET", f"/labs/{l1}")[1] and "whatsapp" not in call("GET", f"/labs/{l1}")[1])
ok("lab contact: anonymous 401, logged-in gets numbers, unpublished 404", call("GET", f"/labs/{l1}/contact")[0] == 401 and call("GET", f"/labs/{l1}/contact", None, cu)[1]["phone"] == "0473111111" and call("GET", f"/labs/{l2}/contact", None, cu)[1]["whatsapp"] == "01055550000" and call("GET", f"/labs/{nc}/contact", None, cu)[0] == 404)
ok("admin lab list still shows numbers", next(x for x in call("GET", "/admin/labs", None, at)[1] if x["id"] == l1)["phone"] == "0473111111")
ok("search by lab name", [x["id"] for x in call("GET", "/labs?q=الشفاء")[1]] == [l1])
ok("search by test name (Arabic-normalised: ه/ة, أ/ا)", [x["id"] for x in call("GET", "/labs?q=هرمونات")[1]] == [l2] and [x["id"] for x in call("GET", "/labs?q=سكر صايم")[1]] == [l1] and [x["id"] for x in call("GET", "/labs?q=وظايف")[1]] == [l1] and [x["id"] for x in call("GET", "/labs?q=وظائف")[1]] == [l1] and [x["id"] for x in call("GET", "/labs?q=سكر هرمونات")[1]] == [])
ok("search with no match gives an empty list", call("GET", "/labs?q=zzzqq")[1] == [])
rx = call("POST", "/admin/regions", {"parent_id": 1, "level": "governorate", "slug": "other", "name_ar": "محافظة أخرى للاختبار", "is_active": True}, at)[1]["id"]
l3 = add(name_ar="معمل آخر", region_id=rx, phone="0100000000")[1]["id"]; call("POST", f"/admin/labs/{l3}/publish", {"published": True}, at)
ok("region filter: covers parents, excludes other regions", sorted(x["id"] for x in call("GET", "/labs?region_id=3")[1]) == sorted([l1, l2]) and [x["id"] for x in call("GET", f"/labs?region_id={rx}")[1]] == [l3] and len(call("GET", "/labs?region_id=1")[1]) == 3)
ok("limit param", len(call("GET", "/labs?limit=1")[1]) == 1)
ok("bad limit/region values are a 400, not a crash", call("GET", "/labs?limit=x")[0] == 400 and call("GET", "/labs?region_id=x")[0] == 400)
ok("detail of published / unpublished", call("GET", f"/labs/{l1}")[0] == 200 and call("GET", f"/labs/{nc}")[0] == 404)
ok("edit published lab ok, but cannot blank its address or contact", call("POST", f"/admin/labs/{l1}", {"hours": "24 ساعة"}, at)[0] == 200 and call("POST", f"/admin/labs/{l1}", {"address": ""}, at)[0] == 409 and call("POST", f"/admin/labs/{l2}", {"whatsapp": ""}, at)[0] == 409)
ok("edit keeps unchanged fields (home_visit retained)", call("GET", f"/labs/{l1}")[1]["home_visit"] == 1 and call("GET", f"/labs/{l1}")[1]["hours"] == "24 ساعة")
ok("deactivated region hides its labs", call("POST", f"/admin/regions/{rx}/active", {"is_active": False}, at)[0] == 200 and call("GET", "/labs?region_id=1")[1] != [] and l3 not in [x["id"] for x in call("GET", "/labs")[1]] and call("GET", f"/labs/{l3}")[0] == 404)
ok("unpublish hides it", call("POST", f"/admin/labs/{l1}/publish", {"published": False}, at)[0] == 200 and call("GET", f"/labs/{l1}")[0] == 404)
ok("admin list shows state; changes audited", all("is_published" in x for x in call("GET", "/admin/labs", None, at)[1]) and sqlite3.connect(DB).execute("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'lab.%'").fetchone()[0] >= 8)
ok("survives restart (data in SQLite)", sqlite3.connect(DB).execute("SELECT COUNT(*) FROM labs").fetchone()[0] == 5)
print("ALL PASSED")
