# المرحلة 69 (م4): تبويب «الطلبات» في static/shop.html عبر test_ui_page_harness.js (DOM وهمي، ليس متصفحًا حقيقيًا).
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8972; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]; HERE = os.path.dirname(os.path.abspath(__file__))
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
own = user("01070000001"); cust = user("01070000002"); late = user("01070000003")
call("POST", "/admin/shops-settings", {"enabled": True}, at); call("POST", "/admin/region-fees", {"region_id": 3, "fee": 30}, at)
S = call("POST", "/shops/apply", {"type_id": 1, "name_ar": "مطعم الأمل", "address": "شارع النصر", "phone": "01012345678", "region_id": 3}, own)[1]["id"]
call("POST", "/admin/shops/%d/review" % S, {"status": "approved"}, at); call("POST", "/owner/shops/%d/open" % S, {}, own)
it = call("POST", "/owner/shops/%d/items" % S, {"name_ar": "كشري <b>كبير</b>", "price": 35.5}, own)[1]["id"]
SNAP = {"snap": "m"}
s = open(os.path.join(HERE, "static", "shop.html"), encoding="utf-8").read()
ok("shop.html loads pdelivery.css and the css is cached by the service worker", "/pdelivery.css" in s and '"/pdelivery.css"' in open(os.path.join(HERE, "static", "sw.js"), encoding="utf-8").read())

# 1) المفتاح مطفي: تبويب الطلبات موجود لكن بلا زر ولا أخطاء
r = ui(own, [{"wait": 700, **SNAP}]); v = r["m"]
ok("orders tab rendered, button hidden while delivery is off, no JS errors", r["errs"] == [] and 'data-t="o"' in v and "dlsend()" not in v and "غير مفعّل حاليًا" in v and "لا توجد طلبات من العملاء" in v)
call("POST", "/admin/shop-delivery", {"enabled": True, "commission": 0}, at)
v = ui(own, [{"wait": 700, **SNAP}])["m"]
ok("enabled: the request-courier card appears inside the orders tab", 'id="oslot"' in v and "dlsend()" in v and 'id="dla"' in v and "جاهز — اضغط عند الحاجة لمندوب" in v)

# 2) ضغطة المحل تنشئ طلب استلام للمحل المختار
r = ui(own, [{"js": "dlsend()", "wait": 1100, **SNAP}]); v = r["m"]
row = sql("SELECT d.origin_type,l.shop_id,d.customer_id FROM delivery_orders d JOIN shop_delivery_links l ON l.order_id=d.id")
ok("UI tap creates a shop_pickup order linked to the selected shop", r["errs"] == [] and len(row) == 1 and row[0][:2] == ("shop_pickup", S) and "بانتظار مندوب" in v and "dlx(" in v)
po = sql("SELECT id FROM delivery_orders")[0][0]
ui(own, [{"confirm": True, "js": "dlx(%d)" % po, "wait": 900}])
ok("cancel from the card cancels the pickup request", sql("SELECT status FROM delivery_orders WHERE id=?", po)[0][0] == "cancelled")

# 3) طلب عميل يظهر للمحل، مع تعقيم النصوص، ويمكن رفضه
oid = call("POST", "/shops/%d/order" % S, {"items": [{"item_id": it, "qty": 2}], "dropoff_text": "عمارة 5", "note": "<script>x</script>"}, cust)[1]["id"]
r = ui(own, [{"wait": 700, **SNAP}]); v = r["m"]
ok("customer order listed with items and total, escaped, reject button", ("طلب #%d" % oid) in v and "2× كشري &lt;b&gt;كبير&lt;/b&gt;" in v and "<b>كبير</b>" not in v and "الإجمالي: 71 ج" in v and "&lt;script&gt;x&lt;/script&gt;" in v and "<script>x" not in v and "ordrej(%d)" % oid in v)
ok("customer data (address/phone) is not shown to the shop", "عمارة 5" not in v and "01070000002" not in v)
ok("orders tab badge shows the open order (items + orders badges)", ui(own, [{"wait": 600, "snap": "tb"}])["tb"].count('class="bd"') == 2)
ok("declining the reject confirm keeps the order", (ui(own, [{"confirm": False, "js": "ordrej(%d)" % oid, "wait": 700}]), sql("SELECT status FROM delivery_orders WHERE id=?", oid)[0][0] == "searching")[1])
r = ui(own, [{"confirm": True, "js": "ordrej(%d)" % oid, "wait": 1000, **SNAP}])
ok("confirming reject cancels it and shows the message", sql("SELECT status FROM delivery_orders WHERE id=?", oid)[0][0] == "cancelled" and "تم رفض الطلب" in r["m"] and "ordrej(%d)" % oid not in r["m"])
ok("orders tab badge counts open orders only (1 item badge remains, order badge gone)", ui(own, [{"wait": 600, "snap": "tb"}])["tb"].count('class="bd"') == 1)

# 4) من لا يملك محلًا معتمدًا: لا تبويب بيانات ولا أخطاء
r = ui(late, [{"wait": 700, **SNAP}])
ok("user without an approved shop: no orders UI, no errors", r["errs"] == [] and "dlsend()" not in r["m"] and "ordrej(" not in r["m"])

# 5) ثوابت الملف
ok("shop.html never injects raw order fields (all through esc)", not re.search(r"\$\{(x|i|d)\.(note|name|dropoff_text|courier_name|courier_phone)\}", s))
ok("localStorage keys still limited to t, rg, shsel", set(re.findall(r"localStorage\.(?:getItem|setItem)\('(\w+)'", s)) == {"t", "rg", "shsel"})
print("ALL PASS")
