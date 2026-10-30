# phase-74 / م1 «دفتر الصيدلية»: تفاصيل اختيارية (رقم العميل، السعر، ملاحظة) في طلب الصيدلية — اختبار توافق: الزر بضغطة واحدة يعمل كما كان والطلبات العادية لا تتأثر
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, provider_delivery
from testutil import apply_docs
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8974; BASE = "http://127.0.0.1:%d" % PORT; DB = os.environ["LAQINO_DB"]
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
Z = {r["name_ar"]: r["id"] for r in call("GET", "/regions?parent_id=3")[1]}; Z2 = Z["المجد 55"]
cust, cid = user("01070000001"); ph, pid = user("01070000002"); ph2, pid2 = user("01070000003"); c1, u1 = user("01070000004"); c2, u2 = user("01070000005")
for t, i, n in ((ph, pid, "صيدلية النور"), (ph2, pid2, "صيدلية الأمل")):
    call("POST", "/providers/apply", {"name_ar": n, "region_id": Z2, "address": "شارع البحر"}, t); call("POST", f"/admin/providers/{i}/review", {"status": "approved"}, at)
for t, u in ((c1, u1), (c2, u2)):
    apply_docs(call, t); call("POST", f"/admin/couriers/{u}/review", {"status": "approved"}, at); call("POST", "/courier/topups", {"amount": 300, "transfer_ref": "REF" + str(u).zfill(4)}, t)
for tp in call("GET", "/admin/topups", None, at)[1]: call("POST", f"/admin/topups/{tp['id']}/review", {"status": "approved"}, at)
for t in (c1, c2): call("POST", "/courier/online", {"online": True}, t)
call("POST", "/admin/provider-delivery", {"enabled": True, "commission": 0}, at)
mk = lambda t=ph, **x: call("POST", "/provider/delivery-request", x, t)
cord = lambda t, oid: ([o for o in call("GET", "/courier/orders", None, t)[1] if o["id"] == oid] or [None])[0]
mine = lambda oid, t=ph: ([o for o in call("GET", "/provider/delivery-requests", None, t)[1]["items"] if o["id"] == oid] or [None])[0]

# 1) توافق: الضغطة الواحدة القديمة تعمل كما كانت (بلا حقول) والأعمدة الجديدة فارغة
s, r = mk(request_key="a1"); oid0 = r["id"]
ok("legacy one-tap still 201 searching", s == 201 and r["status"] == "searching")
ok("legacy order has empty new columns", sql("SELECT pd_cust_phone,pd_cust_norm,pd_price,pd_note FROM delivery_orders WHERE id=?", oid0)[0] == (None, None, None, None))
ok("legacy order: details text unchanged", sql("SELECT details FROM delivery_orders WHERE id=?", oid0)[0][0] == "طلب استلام من صيدلية")
ok("provider list: new keys present but empty", mine(oid0)["pd_cust_phone"] is None and mine(oid0)["pd_price"] is None and mine(oid0)["pd_note"] is None)

# 2) التحقق من المدخلات
for bad in ({"customer_phone": "12"}, {"customer_phone": "abcdefghij"}, {"customer_phone": "0" * 40}, {"price": "abc"}, {"price": -5}, {"price": "nan"}, {"price": "inf"}, {"price": 1000001}):
    ok(f"invalid input {bad} rejected 400", mk(**bad)[0] == 400)
ok("rejections created no order", sql("SELECT COUNT(*) FROM delivery_orders")[0][0] == 1)
ok("phone normaliser: arabic digits / +20 / 0020 / spaces", provider_delivery.norm_phone("٠١٠٠ ١٢٣ ٤٥٦٧") == "01001234567" and provider_delivery.norm_phone("+20 100 123 4567") == "01001234567" and provider_delivery.norm_phone("0020-100-123-4567") == "01001234567" and provider_delivery.norm_phone("") is None and provider_delivery.norm_phone("123") is None)

# 3) إنشاء بالتفاصيل
s, r = mk(request_key="b1", customer_phone="٠١٠٠١٢٣٤٥٦٧", price="85.5", note="  كيسين — دفع عند الاستلام  ", dropoff_text="عمارة 5"); oid = r["id"]
ok("order with details created", s == 201)
ok("stored normalised + trimmed", sql("SELECT pd_cust_phone,pd_cust_norm,pd_price,pd_note,dropoff_text FROM delivery_orders WHERE id=?", oid)[0] == ("01001234567", "01001234567", 85.5, "كيسين — دفع عند الاستلام", "عمارة 5"))
ok("owner sees details in list", (lambda o: o["pd_cust_phone"] == "01001234567" and o["pd_price"] == 85.5 and o["pd_note"].startswith("كيسين"))(mine(oid)))
ok("duplicate key returns same order, no second insert", mk(request_key="b1", customer_phone="01009999999")[1].get("id") == oid and sql("SELECT pd_cust_norm FROM delivery_orders WHERE id=?", oid)[0][0] == "01001234567")
ok("zero price accepted", mk(request_key="b2", price=0)[0] == 201)
ok("other pharmacy cannot see it", mine(oid, ph2) is None)

# 4) خصوصية: لا تظهر للمندوب قبل القبول ولا في قائمة الطلبات المتاحة
av = call("GET", "/courier/available", None, c1)
txt = json.dumps(av[1], ensure_ascii=False)
ok("available list hides customer phone/price/note", av[0] == 200 and "01001234567" not in txt and "85.5" not in txt and "كيسين" not in txt and "pd_" not in txt)
ok("courier cannot see unaccepted order at all", cord(c1, oid) is None)

# 5) بعد القبول: المندوب المقبول فقط يرى التفاصيل
ok("courier accepts directly", call("POST", f"/courier/orders/{oid}/accept", {}, c1)[0] == 200)
o = cord(c1, oid)
ok("accepted courier sees phone/price/note", o["pd_cust_phone"] == "01001234567" and o["pd_price"] == 85.5 and "كيسين" in o["pd_note"])
ok("other courier sees nothing of it", cord(c2, oid) is None)
# 6) المراحل (محدَّث في م2/phase-75: الدورة تمتد حتى التسليم للعميل): التفاصيل ظاهرة طوال النشاط وتختفي عن المندوب بعد الإتمام
ok("heading to pharmacy", call("POST", f"/courier/orders/{oid}/status", {"to": "heading_pickup"}, c1)[0] == 200)
ok("still visible while active", cord(c1, oid).get("pd_cust_phone") == "01001234567")
ok("pickup from pharmacy no longer completes (m2)", call("POST", f"/courier/orders/{oid}/status", {"to": "picked_up"}, c1)[1]["status"] == "picked_up")
ok("still visible after pickup", cord(c1, oid).get("pd_cust_phone") == "01001234567")
ok("heading to customer", call("POST", f"/courier/orders/{oid}/status", {"to": "heading_customer"}, c1)[1]["status"] == "heading_customer")
ok("delivery completes the order", call("POST", f"/courier/orders/{oid}/status", {"to": "completed"}, c1)[1]["status"] == "completed")
o = cord(c1, oid)
ok("after completion courier no longer sees details", "pd_cust_phone" not in o and "pd_price" not in o and "pd_note" not in o)
ok("pharmacy still keeps the record", mine(oid)["pd_cust_phone"] == "01001234567" and mine(oid)["status"] == "completed")

# 7) الطلبات العادية: شكل الاستجابة لم يتغيّر
code, reg = call("GET", "/regions?parent_id=3")
ok("ordinary delivery orders unaffected (no pd_ keys leak)", all(not k.startswith("pd_") for r_ in call("GET", "/courier/orders", None, c2)[1] for k in r_))

# 8) ترحيل قاعدة قديمة: الأعمدة تُضاف مرة واحدة والتشغيل المتكرر آمن
c_ = sqlite3.connect(DB); provider_delivery.install(c_); provider_delivery.install(c_)
cols = [r[1] for r in c_.execute("PRAGMA table_info(delivery_orders)")]; c_.close()
ok("install idempotent, columns present once", all(cols.count(x) == 1 for x in ("pd_cust_phone", "pd_cust_norm", "pd_price", "pd_note", "origin_type")))
print("ALL PASS")
