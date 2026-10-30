# المرحلة 68 (م3): لوحة المحل static/shop.html عبر test_ui_page_harness.js (DOM وهمي، ليس متصفحًا حقيقيًا ولا يرفع ملفات فعلية).
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8969; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__))
H = os.path.join(HERE, "test_ui_page_harness.js")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def ui(token, steps):
    r = subprocess.run(["node", H, "shop", BASE, token, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    if r.returncode: print(r.stderr[:600])
    return json.loads(r.stdout)
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
o1 = user("01090000001"); o2 = user("01090000002"); o3 = user("01090000003")
call("POST", "/admin/shops-settings", {"enabled": True}, at)
def mk(t, tid, nm, appr=True):
    r = call("POST", "/shops/apply", {"type_id": tid, "name_ar": nm, "address": "شارع الجمهورية", "phone": "01012345678", "region_id": 3}, t)
    if appr: call("POST", "/admin/shops/%d/review" % r[1]["id"], {"status": "approved"}, at)
    return r[1]["id"]
S1 = mk(o1, 1, "مطعم <i>الأمل</i>"); S2 = mk(o1, 2, "سوبر الأمل")
SNAP = {"snap": "m"}

# الصفحة والملفات
ok("shop.html is served", urllib.request.urlopen(BASE + "/shop.html").status == 200)
ok("notif.js maps 'shop' link to /shop.html", "shop: ['/shop.html'" in open(os.path.join(HERE, "static", "notif.js"), encoding="utf-8").read())
ok("service worker shell caches /shop.html", '"/shop.html"' in open(os.path.join(HERE, "static", "sw.js"), encoding="utf-8").read())

# 1) لوحة بمحلين معتمدين: مبدّل المحلات + فتح/غلق + تعقيم الأسماء
r = ui(o1, [{"wait": 700, **SNAP}]); v = r["m"]
ok("no script errors on load", r["errs"] == [])
ok("two approved shops -> switcher shown", 'id="shsel"' in v and v.count("<option") >= 2)
ok("shop name is HTML-escaped", "&lt;i&gt;الأمل&lt;/i&gt;" in v and "<i>الأمل</i>" not in v)
ok("closed by default with an open button", "مغلق الآن" in v and "shtog(%d,1)" % S1 in v)
r = ui(o1, [{"js": "shtog(%d,1)" % S1, "wait": 900, **SNAP}])
ok("open button opens the shop (DB + UI)", sql("SELECT is_open FROM shops WHERE id=?", S1)[0][0] == 1 and "مفتوح الآن" in r["m"] and "shtog(%d,0)" % S1 in r["m"])
ui(o1, [{"js": "shtog(%d,0)" % S1, "wait": 900}])
ok("close button closes it", sql("SELECT is_open FROM shops WHERE id=?", S1)[0][0] == 0)

# 2) الأصناف من الواجهة (بدون صور: الـharness لا يرفع ملفات)
NOF = "document.getElementById('if').files=[];"
r = ui(o1, [{"js": NOF + "document.getElementById('in').value='كشري <b>كبير</b>';document.getElementById('ip').value='35.5';document.getElementById('id').value='وصف';iadd()", "wait": 1000, **SNAP}])
row = sql("SELECT shop_id,name_ar,price,is_available FROM shop_items")
ok("UI add item creates the row for the selected shop", len(row) == 1 and row[0][1] == "كشري <b>كبير</b>" and row[0][2] == 35.5 and row[0][3] == 1 and row[0][0] in (S1, S2))
ok("item name is escaped in the list", "كشري &lt;b&gt;كبير&lt;/b&gt;" in r["m"] and "<b>كبير</b>" not in r["m"])
ok("add success message shown", "تمت إضافة الصنف" in r["m"])
iid = sql("SELECT id FROM shop_items")[0][0]; SH = sql("SELECT shop_id FROM shop_items")[0][0]
r = ui(o1, [{"js": NOF + "document.getElementById('in').value='ا';document.getElementById('ip').value='5';iadd()", "wait": 900, **SNAP}])
ok("invalid item shows the server error and adds nothing", sql("SELECT COUNT(*) FROM shop_items")[0][0] == 1 and "اسم الصنف" in r["m"])
ui(o1, [{"js": "iav(%d,0)" % iid, "wait": 800}])
ok("UI toggles availability off", sql("SELECT is_available FROM shop_items WHERE id=?", iid)[0][0] == 0)
r = ui(o1, [{"js": "document.getElementById('ef%d').files=[]" % iid, "wait": 700}, {"js": "document.getElementById('en%d').value='كشري ممتاز';document.getElementById('ep%d').value='40';document.getElementById('ed%d').value='';isv(%d,5)" % (iid, iid, iid, iid), "wait": 1000, **SNAP}])
ok("UI edit saves name/price and clears description", sql("SELECT name_ar,price,description FROM shop_items WHERE id=?", iid)[0] == ("كشري ممتاز", 40.0, None) and "تم حفظ الصنف" in r["m"])
r = ui(o1, [{"confirm": False, "js": "idl(%d)" % iid, "wait": 700}])
ok("declining delete confirm keeps the item", sql("SELECT status FROM shop_items WHERE id=?", iid)[0][0] == "active")
ui(o1, [{"confirm": True, "js": "idl(%d)" % iid, "wait": 900}])
ok("confirming delete removes the item", sql("SELECT status FROM shop_items WHERE id=?", iid)[0][0] == "deleted")

# 3) مستخدم بمحل معلق فقط + مستخدم بلا محلات (نموذج الانضمام)
SP = mk(o2, 3, "حلويات معلقة", appr=False)
r = ui(o2, [{"wait": 700, **SNAP}]); v = r["m"]
ok("pending-only owner: no open/close or switcher, sees status and pending note", r["errs"] == [] and "shtog(" not in v and 'id="shsel"' not in v and "قيد المراجعة" in v and "بانتظار مراجعة الإدارة" in v)
call("POST", "/admin/shops/%d/review" % SP, {"status": "rejected", "reason": "بيانات ناقصة"}, at)
v = ui(o2, [{"wait": 700, **SNAP}])["m"]
ok("rejected shop shows its reason", "مرفوض" in v and "بيانات ناقصة" in v)
r = ui(o3, [{"wait": 700, **SNAP}]); v = r["m"]
ok("user with no shops sees the apply form with the 4 types", r["errs"] == [] and 'id="at"' in v and v.count("<option") == 4 and "shap()" in v)
r = ui(o3, [{"js": "document.getElementById('at').value='2';document.getElementById('an').value='سوبر الحارة';document.getElementById('aa').value='شارع المحطة';document.getElementById('ap').value='01011112222';shap()", "wait": 1000, **SNAP}])
row = sql("SELECT type_id,name_ar,region_id,status FROM shops WHERE name_ar='سوبر الحارة'")
ok("apply from the panel creates a pending shop in the saved region", row == [(2, "سوبر الحارة", 3, "pending")] and "تم إرسال طلب انضمام" in r["m"])
call("POST", "/admin/shops-settings", {"enabled": False}, at)
v = ui(o3, [{"wait": 700, **SNAP}])["m"]
ok("section disabled: no apply form, friendly note", 'id="at"' not in v and "غير مفعّل" in v)
ok("existing approved shop still manageable while section is off", "shtog(" in ui(o1, [{"wait": 700, **SNAP}])["m"])

# 4) بدون تسجيل دخول
r = subprocess.run(["node", H, "shop", BASE, "", "[]"], capture_output=True, text=True, timeout=60)
ok("no token: asks to log in, no JS errors", json.loads(r.stdout)["errs"] == [])

# 5) ثوابت الملف
s = open(os.path.join(HERE, "static", "shop.html"), encoding="utf-8").read()
ok("shop.html never injects raw server fields (all through esc)", not re.search(r"\$\{(s|x|t)\.(name_ar|address|description|type_name|region_name|review_reason)\}", s))
ok("localStorage keys used are limited to t, rg, shsel", set(re.findall(r"localStorage\.(?:getItem|setItem)\('(\w+)'", s)) == {"t", "rg", "shsel"})
print("ALL PASS")
