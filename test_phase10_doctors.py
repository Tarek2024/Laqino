# المرحلة 10: التخصصات والأطباء — إدارة، نشر مشروط، بحث عربي، تصفية منطقة، صلاحيات.
import os, json, threading, urllib.request, urllib.error, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8779), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8779/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
call("POST", "/register", {"phone": "01012345678", "name": "cust", "password": "password1"}); cu = call("POST", "/login", {"phone": "01012345678", "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
ok("customer cannot manage specialties/doctors (403)", all(call(m, p, d, cu)[0] == 403 for m, p, d in (("POST", "/admin/specialties", {"name_ar": "x1"}), ("POST", "/admin/doctors", {}), ("GET", "/admin/doctors", None), ("GET", "/specialties?all=1", None))))
ok("anonymous cannot manage either", call("POST", "/admin/doctors", {})[0] in (401, 403))
ok("no specialties/doctors invented: empty lists", call("GET", "/specialties")[1] == [] and call("GET", "/doctors")[1] == [])
sp = call("POST", "/admin/specialties", {"name_ar": "أطفال"})  # no token
sp = call("POST", "/admin/specialties", {"name_ar": "أطفال"}, at)[1]["id"]; sb = call("POST", "/admin/specialties", {"name_ar": "باطنة"}, at)[1]["id"]; so = call("POST", "/admin/specialties", {"name_ar": "عظام"}, at)[1]["id"]
ok("duplicate specialty rejected", call("POST", "/admin/specialties", {"name_ar": "أطفال"}, at)[0] == 409)
def add(**k):
    return call("POST", "/admin/doctors", {"name_ar": "د. أحمد محمود", "specialty_id": sp, "region_id": 3, "clinic_name": "عيادة النور", "address": "شارع البحر", "phone": "0473123456", "schedule": "السبت والاثنين 5-9", **k}, at)
r = add(); d1 = r[1]["id"]
ok("new doctor is created unpublished and invisible", r[0] == 201 and r[1]["is_published"] == 0 and call("GET", "/doctors")[1] == [] and call("GET", f"/doctors/{d1}")[0] == 404)
ok("incomplete profile cannot be published (no contact/schedule)", (lambda i: call("POST", f"/admin/doctors/{i}/publish", {"published": True}, at)[0] == 409)(add(name_ar="سارة علي", phone="", whatsapp="", schedule="")[1]["id"]))
ok("invalid phone / inactive region / missing specialty rejected", add(phone="abc")[0] == 400 and add(region_id=999)[0] == 400 and add(specialty_id=999)[0] == 400)
ok("publish complete profile", call("POST", f"/admin/doctors/{d1}/publish", {"published": True}, at)[0] == 200)
d2 = add(name_ar="دكتورة منى إبراهيم", specialty_id=sb, phone="01012345678")[1]["id"]; call("POST", f"/admin/doctors/{d2}/publish", {"published": True}, at)
d3 = add(name_ar="خالد عبد الله", specialty_id=so, whatsapp="01099999999", schedule="")[1]["id"]  # stays unpublished
names = lambda q="": [x["name_ar"] for x in call("GET", "/doctors" + q)[1]]
ok("only published doctors listed (2 of 3)", len(names()) == 2 and "خالد عبد الله" not in names())
ok("search by name ignoring title prefix and spacing", names("?q=" + urllib.request.quote("  احمد  محمود")) == ["د. أحمد محمود"])
ok("Arabic variants: أ/ا and ة/ه normalize (دكتورة منى = منى)", names("?q=" + urllib.request.quote("منى")) == ["دكتورة منى إبراهيم"] and names("?q=" + urllib.request.quote("إحمد")) == ["د. أحمد محمود"])
ok("search by specialty name", names("?q=" + urllib.request.quote("اطفال")) == ["د. أحمد محمود"])
ok("filter by specialty id", names(f"?specialty_id={sb}") == ["دكتورة منى إبراهيم"])
ok("filter by region (parent region covers child)", len(names("?region_id=2")) == 2 and len(names("?region_id=3")) == 2)
ok("no match returns empty list, not suggestions", names("?q=" + urllib.request.quote("زيدان")) == [] and names("?q=" + urllib.request.quote("احمد") + f"&specialty_id={sb}") == [])
ok("unpublished doctor not searchable by name", names("?q=" + urllib.request.quote("خالد")) == [])
ok("public specialties only those with published doctors (عظام hidden)", [x["name_ar"] for x in call("GET", "/specialties")[1]] == ["أطفال", "باطنة"])
ok("admin sees all specialties incl. empty", len(call("GET", "/specialties?all=1", None, at)[1]) == 3)
det = call("GET", f"/doctors/{d1}")[1]
ok("detail page shows real stored fields only (no rating/is_published leak)", det["clinic_name"] == "عيادة النور" and det["specialty"] == "أطفال" and "rating" not in det and "is_published" not in det)
ok("published doctor can't be edited into incomplete state", call("POST", f"/admin/doctors/{d1}", {"phone": "", "schedule": "", "whatsapp": ""}, at)[0] == 409)
ok("edit works and search index follows rename", call("POST", f"/admin/doctors/{d1}", {"name_ar": "يوسف حسن"}, at)[0] == 200 and names("?q=" + urllib.request.quote("يوسف")) == ["يوسف حسن"] and names("?q=" + urllib.request.quote("احمد")) == [])
call("POST", f"/admin/doctors/{d1}/publish", {"published": False}, at); ok("unpublish hides doctor", names("?q=" + urllib.request.quote("يوسف")) == [] and call("GET", f"/doctors/{d1}")[0] == 404)
call("POST", f"/admin/specialties/{sb}", {"is_active": False}, at); ok("deactivated specialty hides its doctors and itself", names() == [] and call("GET", "/specialties")[1] == [])
ok("search q injection-safe", call("GET", "/doctors?q=" + urllib.request.quote("' OR 1=1 --"))[1] == [])
import sqlite3; acts = {r[0] for r in sqlite3.connect(os.environ["LAQINO_DB"]).execute("SELECT action FROM audit_log")}
ok("admin actions audited", {"specialty.add", "doctor.add", "doctor.publish", "doctor.update", "doctor.unpublish", "specialty.update"} <= acts)
print("ALL OK")
