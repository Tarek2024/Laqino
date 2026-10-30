# المرحلة 66 (م1 المحلات): أنواع المحلات + التقديم + الاعتماد + صلاحيات المالك + المفتاح العام + حذف الحساب
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, shops
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8966; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}; R1 = Z["المجد 55"]
o1, o1id = user("01060000001"); o2, o2id = user("01060000002"); cust, cid = user("01060000003"); stf, sid = user("01060000004")
sql("UPDATE users SET role='staff' WHERE id=?", sid)
def apply(t=o1, **x):
    d = {"type_id": 1, "name_ar": "مطعم الريف", "address": "شارع البحر", "phone": "01012345678", "region_id": R1}; d.update(x); return call("POST", "/shops/apply", d, t)
def mine(t=o1): return call("GET", "/owner/shops", None, t)[1]["items"]

# ---- 1) البذر والمفتاح العام (مطفي افتراضيًا)
ok("4 types seeded", [r[0] for r in sql("SELECT name_ar FROM shop_types ORDER BY sort")] == ["مطاعم", "سوبر ماركت", "محلات حلويات", "محلات ملابس"])
ok("default off: public types closed", call("GET", "/shop-types")[1] == {"enabled": False, "items": []})
ok("default off: apply refused", apply()[0] == 403 and sql("SELECT COUNT(*) FROM shops")[0][0] == 0)
ok("settings default off", call("GET", "/admin/shops-settings", None, at)[1] == {"enabled": False, "regions": []})
ok("settings: customer 403, staff cannot write", call("GET", "/admin/shops-settings", None, cust)[0] == 403 and call("POST", "/admin/shops-settings", {"enabled": True}, stf)[0] == 403)
ok("settings invalid value 400", call("POST", "/admin/shops-settings", {"enabled": "yes"}, at)[0] == 400)
ok("admin enables", call("POST", "/admin/shops-settings", {"enabled": True}, at)[1] == {"enabled": True, "regions": []})
ok("public types open (4 items, no auth)", len(call("GET", "/shop-types")[1]["items"]) == 4)

# ---- 2) التقديم: تحقق من المدخلات
ok("anonymous apply 401", call("POST", "/shops/apply", {})[0] == 401)
bad = [{"type_id": 999}, {"type_id": None}, {"type_id": True}, {"name_ar": "ab"}, {"name_ar": "x" * 81}, {"address": ""}, {"phone": "abc"}, {"phone": "123"},
       {"region_id": 99999}, {"region_id": None}, {"lat": 30.1}, {"lat": 100, "lng": 30}, {"lat": "x", "lng": 30}, {"lat": True, "lng": True}]
for b in bad: ok("invalid apply rejected %s" % json.dumps(b, ensure_ascii=False), apply(**b)[0] == 400)
ok("nothing inserted by invalid applies", sql("SELECT COUNT(*) FROM shops")[0][0] == 0)
inactive = sql("SELECT id FROM regions WHERE is_active=1 AND id!=? LIMIT 1", R1)[0][0]; sql("UPDATE regions SET is_active=0 WHERE id=?", inactive)
ok("inactive region refused", apply(region_id=inactive)[0] == 400)
sql("UPDATE regions SET is_active=1 WHERE id=?", inactive)

# ---- 3) التقديم الناجح = pending + إشعار للإدارة، ولا يغيّر دور المستخدم
s, r = apply(lat=30.5, lng=31.2); sid1 = r["id"]
ok("apply creates pending", s == 201 and r["status"] == "pending" and mine()[0]["status"] == "pending" and mine()[0]["is_open"] is False)
ok("apply keeps lat/lng", (mine()[0]["lat"], mine()[0]["lng"]) == (30.5, 31.2))
ok("role unchanged", call("GET", "/me", None, o1)[1]["role"] == "customer")
adm_n = call("GET", "/notifications", None, at)[1]["items"]
ok("admin notified of new shop", any(n["kind"] == "admin.shop" and n["ref_id"] == sid1 for n in adm_n))
ok("duplicate name 409", apply()[0] == 409 and sql("SELECT COUNT(*) FROM shops")[0][0] == 1)
ok("duplicate name ignores case/spaces", apply(name_ar="  مطعم   الريف ")[0] == 409)
ok("owner list is private", mine(o2) == [] and mine(cust) == [])

# ---- 4) حد الطلبات المعلقة
apply(name_ar="محل ثاني"); apply(name_ar="محل ثالث")
s, r = apply(name_ar="محل رابع")
ok("4th pending refused (429), nothing inserted", s == 429 and sql("SELECT COUNT(*) FROM shops WHERE owner_id=?", o1id)[0][0] == 3)

# ---- 5) صلاحيات الإدارة والمراجعة
ok("customer cannot list/review", call("GET", "/admin/shops", None, cust)[0] == 403 and call("POST", f"/admin/shops/{sid1}/review", {"status": "approved"}, cust)[0] == 403)
ok("anonymous admin 401", call("GET", "/admin/shops")[0] == 401)
ok("admin list default pending (3)", len(call("GET", "/admin/shops", None, at)[1]) == 3)
ok("admin list bad status 400", call("GET", "/admin/shops?status=zzz", None, at)[0] == 400)
ok("admin list filter by type/region", len(call("GET", f"/admin/shops?type_id=1&region_id={R1}", None, at)[1]) == 3 and call("GET", "/admin/shops?type_id=2", None, at)[1] == [])
ok("admin list search by name", [x["name_ar"] for x in call("GET", "/admin/shops?q=" + urllib.request.quote("ثالث"), None, at)[1]] == ["محل ثالث"])
ok("admin list search treats % literally", call("GET", "/admin/shops?q=%25", None, at)[1] == [])
ok("admin list shows owner phone", call("GET", "/admin/shops", None, at)[1][0]["owner_phone"] == "01060000001")
ok("review invalid status 400", call("POST", f"/admin/shops/{sid1}/review", {"status": "pending"}, at)[0] == 400 and call("POST", f"/admin/shops/{sid1}/review", {"status": "x"}, at)[0] == 400)
ok("reject needs reason", call("POST", f"/admin/shops/{sid1}/review", {"status": "rejected"}, at)[0] == 400 and call("POST", f"/admin/shops/{sid1}/review", {"status": "suspended", "reason": "ab"}, at)[0] == 400)
ok("review unknown shop 404", call("POST", "/admin/shops/99999/review", {"status": "approved"}, at)[0] == 404)
ok("pending shop cannot open (403)", call("POST", f"/owner/shops/{sid1}/open", None, o1)[0] == 403)
ok("staff can approve", call("POST", f"/admin/shops/{sid1}/review", {"status": "approved"}, stf)[1] == {"id": sid1, "status": "approved"})
ok("owner notified of approval", any(n["kind"] == "shop.review" and n["title"] == "تم اعتماد محلك" for n in call("GET", "/notifications", None, o1)[1]["items"]))
ok("role still unchanged after approval", call("GET", "/me", None, o1)[1]["role"] == "customer")

# ---- 6) المالك: فتح/غلق وعزل بين المُلّاك
ok("owner opens", call("POST", f"/owner/shops/{sid1}/open", None, o1)[1]["is_open"] is True and mine()[0]["is_open"] is True)
ok("other owner gets 404 (no leak)", call("POST", f"/owner/shops/{sid1}/open", None, o2)[0] == 404 and call("POST", f"/owner/shops/{sid1}/close", None, cust)[0] == 404)
ok("anonymous open 401", call("POST", f"/owner/shops/{sid1}/open")[0] == 401)
ok("owner closes", call("POST", f"/owner/shops/{sid1}/close", None, o1)[1]["is_open"] is False)
call("POST", f"/owner/shops/{sid1}/open", None, o1)
ok("suspend with reason closes shop", call("POST", f"/admin/shops/{sid1}/review", {"status": "suspended", "reason": "مخالفة الشروط"}, at)[0] == 200 and mine()[0]["status"] == "suspended" and mine()[0]["is_open"] is False)
ok("suspended owner sees reason + notification", mine()[0]["review_reason"] == "مخالفة الشروط" and any(n["title"] == "تم إيقاف محلك" for n in call("GET", "/notifications", None, o1)[1]["items"]))
ok("suspended shop cannot open (403)", call("POST", f"/owner/shops/{sid1}/open", None, o1)[0] == 403)
call("POST", f"/admin/shops/{sid1}/review", {"status": "approved"}, at)
ok("re-approve clears reason", mine()[0]["status"] == "approved" and mine()[0]["review_reason"] is None)

# ---- 7) الرفض يسمح بإعادة التقديم بنفس الاسم
sid2 = [x["id"] for x in mine() if x["name_ar"] == "محل ثاني"][0]
ok("reject with reason", call("POST", f"/admin/shops/{sid2}/review", {"status": "rejected", "reason": "بيانات ناقصة"}, at)[0] == 200 and any(n["title"] == "تم رفض طلب محلك" for n in call("GET", "/notifications", None, o1)[1]["items"]))
ok("reapply same name after rejection allowed", apply(name_ar="محل ثاني")[0] == 201)
ok("two shops under one owner (switch list)", len(mine()) == 4 and sorted({x["status"] for x in mine()}) == ["approved", "pending", "rejected"])

# ---- 8) تعديل نوع المحل من الإدارة
ok("admin edits type", call("POST", f"/admin/shops/{sid1}/edit", {"type_id": 2}, at)[0] == 200 and mine()[0]["type_name"] == "سوبر ماركت")
ok("edit type invalid", call("POST", f"/admin/shops/{sid1}/edit", {"type_id": 999}, at)[0] == 400 and call("POST", "/admin/shops/99999/edit", {"type_id": 1}, at)[0] == 404)

# ---- 9) إدارة الأنواع (بلا كود)
ok("types admin-only write (staff 403, customer 403)", call("POST", "/admin/shop-types", {"name_ar": "مخبز"}, stf)[0] == 403 and call("POST", "/admin/shop-types", {"name_ar": "مخبز"}, cust)[0] == 403)
s, r = call("POST", "/admin/shop-types", {"name_ar": "مخابز", "icon": "🥖", "sort": 9}, at); tb = r["id"]
ok("admin adds a new type (no code)", s == 201 and r["slug"].startswith("type-") and "مخابز" in [x["name_ar"] for x in call("GET", "/shop-types")[1]["items"]])
ok("new type usable for apply", apply(o2, type_id=tb, name_ar="مخبز النور")[0] == 201)
ok("type validation", all(call("POST", "/admin/shop-types", b, at)[0] == 400 for b in ({"name_ar": "a"}, {"name_ar": "مخبز", "slug": "Bad Slug"}, {"name_ar": "مخبز", "sort": "x"}, {"name_ar": "مخبز", "is_active": 5}, {"name_ar": "مخبز", "icon": "x" * 9})))
ok("duplicate slug 409", call("POST", "/admin/shop-types", {"name_ar": "مخبز", "slug": "restaurants"}, at)[0] == 409)
ok("edit type + require_image", call("POST", f"/admin/shop-types/{tb}/edit", {"require_image": True, "name_ar": "مخابز وفطائر"}, at)[0] == 200 and sql("SELECT name_ar,require_image FROM shop_types WHERE id=?", tb)[0] == ("مخابز وفطائر", 1))
ok("edit unknown type 404", call("POST", "/admin/shop-types/99999/edit", {"name_ar": "مخبز"}, at)[0] == 404)
call("POST", f"/admin/shops/{mine(o2)[0]['id']}/review", {"status": "approved"}, at)
ok("types list counts approved shops", {x["id"]: x["approved_shops"] for x in call("GET", "/admin/shop-types", None, at)[1]}[tb] == 1)
ok("disabling a type hides it and blocks new applies, shops untouched", call("POST", f"/admin/shop-types/{tb}/edit", {"is_active": False}, at)[0] == 200 and tb not in [x["id"] for x in call("GET", "/shop-types")[1]["items"]]
   and apply(o2, type_id=tb, name_ar="مخبز آخر")[0] == 400 and mine(o2)[0]["status"] == "approved")
c = server.db(); shops.install(c); c.close()
ok("reinstall is idempotent and does not reseed", sql("SELECT COUNT(*) FROM shop_types")[0][0] == 5)

# ---- 10) المفتاح العام يغلق التقديم والواجهة العامة مجددًا
call("POST", "/admin/shops-settings", {"enabled": False}, at)
ok("switch off again closes public + apply", call("GET", "/shop-types")[1]["items"] == [] and apply(cust)[0] == 403 and mine(o1)[0]["id"] == sid1)

# ---- 11) حذف الحساب يخفي بيانات المحل ويوقفه
ok("account deletion succeeds", call("POST", "/me/delete", {"password": "password1"}, o2)[0] == 200)
row = sql("SELECT status,name_ar,address,phone,is_open FROM shops WHERE owner_id=?", o2id)[0]
ok("deleted owner's shop suspended + anonymized", row[0] == "suspended" and "مخبز" not in row[1] and row[2] == "" and row[3] == "" and row[4] == 0)
ok("other owners unaffected", mine(o1)[0]["name_ar"] == "مطعم الريف")
print("ALL PASS")
