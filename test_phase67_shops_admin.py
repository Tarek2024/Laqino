# المرحلة 67 (م2 من خطة المحلات): تبويب «المحلات» في لوحة الإدارة + عدّاد النظرة العامة + إشعار الإدارة. قاعدة مؤقتة معزولة، واجهة الإدارة عبر test_ui_page_harness.js (ليست متصفحًا حقيقيًا).
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8967; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def sql(q, *a):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def ui(token, steps):
    r = subprocess.run(["node", H, "admin", BASE, token, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    if r.returncode: print(r.stderr[:600])
    return json.loads(r.stdout)
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-3:], "password": "password1"}); t = call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]; return t, call("GET", "/me", None, t)[1]["id"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
o1, o1id = user("01070000001"); stf, sid = user("01070000002"); cust, cid = user("01070000003")
sql("UPDATE users SET role='staff' WHERE id=?", sid)
R1 = call("GET", "/regions?parent_id=3")[1][0]["id"]
ov = lambda t=at: call("GET", "/admin/overview", None, t)[1]
SHOPS_BADGE = lambda: ov()["pending"].get("shops")

# ---- 1) النظرة العامة: مفتاح shops بصفر ثم يرتفع مع كل طلب معلق
ok("overview has shops pending key = 0 on empty system", SHOPS_BADGE() == 0)
ok("overview META maps shops key to the 'shops' admin tab", {"key": "shops", "tab": "shops"}.items() <= next(i for i in ov()["items"] if i["key"] == "shops").items())
call("POST", "/admin/shops-settings", {"enabled": True}, at)
r = call("POST", "/shops/apply", {"type_id": 1, "name_ar": "محل <b>تجربة</b>", "address": "شارع الجمهورية", "phone": "01012345678", "region_id": R1}, o1)
sh1 = r[1]["id"]
ok("apply 201 and badge counts the pending shop", r[0] == 201 and SHOPS_BADGE() == 1)
ok("staff sees the same badge", SHOPS_BADGE and call("GET", "/admin/overview", None, stf)[1]["pending"]["shops"] == 1)
ok("admin got the 'admin:shops' notification (link opens the new tab)", sql("SELECT COUNT(*) FROM notifications WHERE link='admin:shops' AND ref_id=?", str(sh1))[0][0] >= 1)

# ---- 2) الواجهة: التبويب يعرض الطلب المعلق (مع تعقيم HTML) والأنواع والمفتاح
SHELL = {"js": "tab='shops';shell()", "wait": 900, "snap": "v"}
r = ui(at, [SHELL])
v = r["v"]
ok("UI: no script errors on load", r["errs"] == [])
ok("UI: pending shop card shows owner phone + address + type", "01070000001" in v and "شارع الجمهورية" in v and "مطاعم" in v)
ok("UI: shop name is HTML-escaped (no injected <b>)", "&lt;b&gt;تجربة&lt;/b&gt;" in v and "<b>تجربة</b>" not in v)
ok("UI: approve/reject buttons present for a pending shop", "/review',{status:'approved'}" in v and "shr(%d,'rejected')" % sh1 in v)
ok("UI: global switch shown ON (enabled) and 4 seeded types listed", 'id="she" type="checkbox" checked' in v and v.count("حفظ</button>") >= 4)
ok("UI: staff can open the tab too (read-only data loads)", ui(stf, [SHELL])["errs"] == [])

# ---- 3) رفض بسبب مطلوب (prompt) ثم ظهوره في فلتر «مرفوضة»
r = ui(at, [{"prompt": "x", "js": "shr(%d,'rejected')" % sh1, "wait": 700}])
ok("UI: reason shorter than 3 chars is NOT sent", sql("SELECT status FROM shops WHERE id=?", sh1)[0][0] == "pending")
ui(at, [{"prompt": "بيانات غير مكتملة", "js": "shr(%d,'rejected')" % sh1, "wait": 900}])
row = sql("SELECT status,review_reason FROM shops WHERE id=?", sh1)[0]
ok("UI: reject sends status + reason", row == ("rejected", "بيانات غير مكتملة"))
ok("badge drops back to 0 after rejection", SHOPS_BADGE() == 0)
r = ui(at, [{"js": "SHP.st='rejected';tab='shops';shell()", "wait": 900, "snap": "v"}])
ok("UI: 'rejected' filter lists the shop with its reason and a re-activate button", "بيانات غير مكتملة" in r["snap" if "snap" in r else "v"] and "اعتماد/إعادة تفعيل" in r["v"])

# ---- 4) اعتماد من الواجهة ثم إيقاف ثم تغيير النوع
ui(at, [{"js": "go('/admin/shops/%d/review',{status:'approved'})" % sh1, "wait": 800}])
ok("UI/API: approve works", sql("SELECT status FROM shops WHERE id=?", sh1)[0][0] == "approved")
r = ui(at, [{"js": "SHP.st='approved';tab='shops';shell()", "wait": 900, "snap": "v"}])
ok("UI: approved shop shows suspend button and closed state", "shr(%d,'suspended')" % sh1 in r["v"] and "مغلق الآن" in r["v"])
ui(at, [{"js": "SHP.st='approved';tab='shops';shell()", "wait": 700}, {"js": "document.getElementById('shty%d').value='2'; shEdT(%d)" % (sh1, sh1), "wait": 800}])
ok("UI: change type sends type_id", sql("SELECT type_id FROM shops WHERE id=?", sh1)[0][0] == 2)
ui(at, [{"prompt": "مخالفة الشروط", "js": "shr(%d,'suspended')" % sh1, "wait": 900}])
ok("UI: suspend stores status + reason and force-closes", sql("SELECT status,review_reason,is_open FROM shops WHERE id=?", sh1)[0] == ("suspended", "مخالفة الشروط", 0))

# ---- 5) مفتاح التفعيل من الواجهة (مع تأكيد) + إلغاء التأكيد لا يغيّر شيئًا
ui(at, [{"js": "tab='shops';shell()", "wait": 700}, {"confirm": False, "js": "(async()=>{const e=document.getElementById('she');e.checked=false;await shEn(e)})()", "wait": 700}])
ok("UI: switching OFF sends enabled=false", call("GET", "/admin/shops-settings", None, at)[1] == {"enabled": False, "regions": []})
ui(at, [{"js": "tab='shops';shell()", "wait": 700}, {"confirm": False, "js": "(async()=>{const e=document.getElementById('she');e.checked=true;await shEn(e)})()", "wait": 700}])
ok("UI: declining the enable confirm changes nothing", call("GET", "/admin/shops-settings", None, at)[1] == {"enabled": False, "regions": []})
ui(at, [{"js": "tab='shops';shell()", "wait": 700}, {"confirm": True, "js": "(async()=>{const e=document.getElementById('she');e.checked=true;await shEn(e)})()", "wait": 700}])
ok("UI: confirming enable turns the section on", call("GET", "/admin/shops-settings", None, at)[1] == {"enabled": True, "regions": []})

# ---- 6) أنواع المحلات من الواجهة
n0 = sql("SELECT COUNT(*) FROM shop_types")[0][0]
ui(at, [{"js": "tab='shops';shell()", "wait": 700}, {"js": "document.getElementById('ntn').value='صيدليات منزلية';document.getElementById('nti').value='💊';document.getElementById('nts').value='9';shTn()", "wait": 800}])
t = sql("SELECT id,name_ar,icon,sort,is_active,require_image FROM shop_types ORDER BY id DESC LIMIT 1")[0]
ok("UI: add type creates an active row", sql("SELECT COUNT(*) FROM shop_types")[0][0] == n0 + 1 and t[1:] == ("صيدليات منزلية", "💊", 9, 1, 0))
ui(at, [{"js": "tab='shops';shell()", "wait": 700}, {"js": "document.getElementById('stn%d').value='محلات منزلية';document.getElementById('sta%d').checked=false;document.getElementById('str%d').checked=true;shTs(%d)" % (t[0], t[0], t[0], t[0]), "wait": 800}])
ok("UI: edit type saves name + inactive + require_image", sql("SELECT name_ar,is_active,require_image FROM shop_types WHERE id=?", t[0])[0] == ("محلات منزلية", 0, 1))
ok("inactive type disappears from the public list", all(i["id"] != t[0] for i in call("GET", "/shop-types")[1]["items"]))
ok("UI: short type name rejected client-side (no row added)", (ui(at, [{"js": "tab='shops';shell()", "wait": 600}, {"js": "document.getElementById('ntn').value='ا';shTn()", "wait": 500}]), sql("SELECT COUNT(*) FROM shop_types")[0][0] == n0 + 1)[1])
ok("staff cannot write types (API still enforces 403)", call("POST", "/admin/shop-types", {"name_ar": "ممنوع"}, stf)[0] == 403)

# ---- 7) بحث وفلتر النوع
r = ui(at, [{"js": "SHP={st:'all',t:'',q:'01070000001'};tab='shops';shell()", "wait": 900, "snap": "v"}])
ok("UI: search by owner phone finds the shop", "01070000001" in r["v"])
r = ui(at, [{"js": "SHP={st:'all',t:'',q:'لا-يوجد-ابدا'};tab='shops';shell()", "wait": 900, "snap": "v"}])
ok("UI: empty search shows the empty message", "لا توجد محلات مطابقة" in r["v"])

# ---- 8) ثوابت ثابتة في الملفات
s = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "admin.html"), encoding="utf-8").read()
tabs = re.search(r"const TABS=\{(.*?)\};", s, re.S).group(1)
ok("admin.html declares the shops tab (24 sections)", "shops:'المحلات'" in tabs and len(re.findall(r"(\w+):'", tabs)) == 24)
ok("admin.html never uses innerHTML with raw shop fields (all via esc)", "${x.name_ar}" not in s and "${x.address}" not in s)
print("ALL PASS")
