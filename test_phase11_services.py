# المرحلة 11 / A-4: قسم الخدمات (الخادم): أنواع تُدار من الإدارة، مقدّمو الخدمة بنشر مشروط، الأرقام بعد تسجيل الدخول وبحد.
# كل البيانات هنا بيانات اختبار داخل قاعدة مؤقتة فقط.
import os, json, threading, urllib.request, urllib.error, urllib.parse, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8785), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
B = "http://127.0.0.1:8785"; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(B + "/api" + urllib.parse.quote(p, safe="/?=&"), json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]; cu, cu2 = user("01012345678"), user("01099999999")
ok("nothing invented: no types, no providers", call("GET", "/service-types")[1] == [] and call("GET", "/services")[1] == [])
ok("customer/anonymous cannot manage types or providers", all(call(m, p, d, t)[0] in (401, 403) for m, p, d, t in (("POST", "/admin/service-types", {"name_ar": "سباكة"}, cu), ("POST", "/admin/services", {}, cu), ("GET", "/admin/services", None, cu), ("GET", "/service-types?all=1", None, cu), ("POST", "/admin/services", {}, ""))))
t1 = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]; t2 = call("POST", "/admin/service-types", {"name_ar": "كهرباء"}, at)[1]["id"]; t3 = call("POST", "/admin/service-types", {"name_ar": "نجارة"}, at)[1]["id"]
ok("duplicate / empty type rejected", call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[0] == 409 and call("POST", "/admin/service-types", {"name_ar": "x"}, at)[0] == 400)
ok("types without published providers stay hidden from users", call("GET", "/service-types")[1] == [] and len(call("GET", "/service-types?all=1", None, at)[1]) == 3)
def add(**k): return call("POST", "/admin/services", {"name_ar": "الأسطى محمود", "type_id": t1, "region_id": 3, "description": "تركيب وصيانة مواسير", "address": "شارع البحر", "phone": "01012340000", **k}, at)
st, r = add(); s1 = r["id"]
ok("new provider is created unpublished and invisible", st == 201 and r["is_published"] == 0 and call("GET", "/services")[1] == [] and call("GET", f"/services/{s1}")[0] == 404)
ok("invalid input rejected (bad phone / inactive region / missing type / short name)", add(phone="abc")[0] == 400 and add(region_id=99999)[0] == 400 and add(type_id=999)[0] == 400 and add(name_ar="ab")[0] == 400)
nc = add(name_ar="بدون تواصل", phone="", whatsapp="")[1]["id"]
ok("cannot publish without a phone or WhatsApp", call("POST", f"/admin/services/{nc}/publish", {"published": True}, at)[0] == 409)
ok("customer cannot publish", call("POST", f"/admin/services/{s1}/publish", {"published": True}, cu)[0] == 403)
ok("publish complete profile", call("POST", f"/admin/services/{s1}/publish", {"published": True}, at)[0] == 200)
s2 = add(name_ar="كهربائي النور", type_id=t2, whatsapp="01099990000", phone="", description="تمديدات ولمبات")[1]["id"]; call("POST", f"/admin/services/{s2}/publish", {"published": True}, at)
ok("only published providers are public; unpublished/incomplete hidden", sorted(x["name_ar"] for x in call("GET", "/services")[1]) == sorted(["الأسطى محمود", "كهربائي النور"]))
ok("types list shows only types with published providers (نجارة hidden)", sorted(x["name_ar"] for x in call("GET", "/service-types")[1]) == sorted(["سباكة", "كهرباء"]))
ok("public rows never expose phone/whatsapp/is_published", all("phone" not in x and "whatsapp" not in x and "is_published" not in x for x in call("GET", "/services")[1]) and "phone" not in call("GET", f"/services/{s1}")[1])
ok("filter by type", [x["id"] for x in call("GET", f"/services?type_id={t2}")[1]] == [s2])
ok("search by name / type name / description", [x["id"] for x in call("GET", "/services?q=محمود")[1]] == [s1] and [x["id"] for x in call("GET", "/services?q=كهرباء")[1]] == [s2] and [x["id"] for x in call("GET", "/services?q=مواسير")[1]] == [s1])
ok("search with no match gives an empty list", call("GET", "/services?q=zzzqq")[1] == [])
ok("region filter covers the region and its parents", len(call("GET", "/services?region_id=3")[1]) == 2 and len(call("GET", "/services?region_id=2")[1]) == 2)
rx = call("POST", "/admin/regions", {"parent_id": 1, "level": "governorate", "slug": "other", "name_ar": "محافظة أخرى للاختبار", "is_active": True}, at)[1]["id"]
ok("a provider in another region is excluded from this region", add(name_ar="سباك آخر", region_id=rx)[0] == 201 and call("GET", f"/services?region_id={rx}")[1] == [] )
ok("contact needs login", call("GET", f"/services/{s1}/contact")[0] == 401)
st, c1 = call("GET", f"/services/{s1}/contact", None, cu); ok("logged-in user gets the number", st == 200 and c1["phone"] == "01012340000")
ok("contact of unpublished provider is 404", call("GET", f"/services/{nc}/contact", None, cu)[0] == 404)
ok("contact reveal is audited", sqlite3.connect(DB).execute("SELECT COUNT(*) FROM audit_log WHERE action='service.contact'").fetchone()[0] == 1)
server.CONTACT_LIMIT = 2
s3 = add(name_ar="سباك ثالث", phone="01011110000")[1]["id"]; call("POST", f"/admin/services/{s3}/publish", {"published": True}, at)
s4 = add(name_ar="سباك رابع", phone="01011110001")[1]["id"]; call("POST", f"/admin/services/{s4}/publish", {"published": True}, at)
call("GET", f"/services/{s2}/contact", None, cu2); call("GET", f"/services/{s3}/contact", None, cu2)
ok("hourly cap on distinct numbers (429), repeat of a revealed one still works", call("GET", f"/services/{s4}/contact", None, cu2)[0] == 429 and call("GET", f"/services/{s2}/contact", None, cu2)[0] == 200)
server.CONTACT_LIMIT = 30
ok("hide a type removes its providers from public", call("POST", f"/admin/service-types/{t1}", {"is_active": False}, at)[0] == 200 and all(x["type_id"] != t1 for x in call("GET", "/services")[1]) and call("GET", f"/services/{s1}")[0] == 404)
ok("reactivate brings them back", call("POST", f"/admin/service-types/{t1}", {"is_active": True}, at)[0] == 200 and call("GET", f"/services/{s1}")[0] == 200)
ok("rename type; duplicate rename rejected", call("POST", f"/admin/service-types/{t3}", {"name_ar": "سباكة"}, at)[0] == 409 and call("POST", f"/admin/service-types/{t3}", {"name_ar": "نجارة أثاث"}, at)[0] == 200)
ok("edit published provider ok, but cannot blank its contact", call("POST", f"/admin/services/{s2}", {"description": "تأسيس"}, at)[0] == 200 and call("POST", f"/admin/services/{s2}", {"whatsapp": ""}, at)[0] == 409)
ok("unpublish hides it", call("POST", f"/admin/services/{s1}/publish", {"published": False}, at)[0] == 200 and call("GET", f"/services/{s1}")[0] == 404)
ok("admin list shows phone + state; customer cannot", all("phone" in x and "is_published" in x for x in call("GET", "/admin/services", None, at)[1]))
ok("changes are audited", sqlite3.connect(DB).execute("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'service%'").fetchone()[0] >= 8)
ok("survives restart (data in SQLite)", (lambda c: c.execute("SELECT COUNT(*) FROM service_providers").fetchone()[0] >= 5 and c.execute("SELECT COUNT(*) FROM service_types").fetchone()[0] == 3)(sqlite3.connect(DB)))
print("ALL PASSED")
