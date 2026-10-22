# المرحلة 3: سعّر روشتتك (rx.py). قاعدة مؤقتة. fake-DOM لا يُستخدم هنا؛ اختبار API + سلامة الواجهات النصية.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
from imgutil import png
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8793), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8793"; DB = os.environ["LAQINO_DB"]
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
import sqlite3 as _sq3
_call = call
def call(m, p, *a, **k):  # الخطوة 4: رد الصيدلية يلزمه اعتماد الإدارة قبل أن يراه العميل؛ هذا الاختبار يفترض أن الإدارة اعتمدت كل الردود (الاعتماد نفسه في test_step4_rx.py)
    if (m == "GET" and p.startswith("/medical/prescriptions")) or p == "/medical/delivery":
        _c = _sq3.connect(os.environ["LAQINO_DB"]); _c.execute("UPDATE prescription_responses SET review='approved' WHERE review='pending'"); _c.commit(); _c.close()
    return _call(m, p, *a, **k)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cust, other, pa, pb, pc, pd = (user(x) for x in ("01012345678", "01099999999", "01011111111", "01022222222", "01033333333", "01044444444"))
ids = {n: call("GET", "/me", None, t)[1]["id"] for n, t in (("a", pa), ("b", pb), ("c", pc), ("d", pd))}
sql("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(99,2,'markaz','eg-kfs-other','مركز آخر',1)")
for n, t, reg in (("a", pa, 3), ("b", pb, 3), ("c", pc, 99)):
    call("POST", "/providers/apply", {"name_ar": "صيدلية " + n, "region_id": reg, "address": "عنوان " + n}, t); call("POST", f"/admin/providers/{ids[n]}/review", {"status": "approved"}, at)
call("POST", "/providers/apply", {"name_ar": "صيدلية معلقة", "region_id": 3, "address": "x"}, pd)  # لم تُعتمد
sql("INSERT OR REPLACE INTO region_fees(region_id,fee) VALUES(3,10)")

def new_rx(tok=cust, region=3):
    f = call("POST", "/files", {"data": png()}, tok)[1]["id"]
    s, r = call("POST", "/medical/prescriptions", {"file_id": f, "region_id": region, "note": "n"}, tok); assert s == 201, (s, r); return r["id"]
R1 = new_rx()
ITEMS = [{"name": "باراسيتامول", "qty": 2, "unit_price": 20}, {"name": "فيتامين د", "qty": 1, "unit_price": 55.5}]

# ---- صلاحيات
ok("anonymous cannot quote", call("POST", f"/provider/prescriptions/{R1}/quote", {"items": ITEMS})[0] == 401)
ok("customer (not pharmacy) cannot quote", call("POST", f"/provider/prescriptions/{R1}/quote", {"items": ITEMS}, cust)[0] == 403)
ok("pharmacy without access gets 404", call("POST", f"/provider/prescriptions/{R1}/quote", {"items": ITEMS}, pa)[0] == 404)
ok("auto-forward is OFF by default (nothing forwarded on upload)", sql("SELECT COUNT(*) FROM prescription_access WHERE prescription_id=?", (R1,))[0][0] == 0)

# ---- تحويل الإدارة لعدة صيدليات
ok("forward-many is admin/staff only", call("POST", f"/admin/prescriptions/{R1}/forward-many", {"provider_ids": [ids["a"]]}, cust)[0] == 403 and call("POST", f"/admin/prescriptions/{R1}/forward-many", {"provider_ids": [ids["a"]]})[0] == 401)
ok("forward-many validates list", all(call("POST", f"/admin/prescriptions/{R1}/forward-many", b, at)[0] == 400 for b in ({}, {"provider_ids": []}, {"provider_ids": "x"}, {"provider_ids": ["x"]}, {"provider_ids": list(range(1, 15))})))
s, r = call("POST", f"/admin/prescriptions/{R1}/forward-many", {"provider_ids": [ids["a"], ids["b"], ids["d"], 99999]}, at)
ok("forward-many adds only approved pharmacies (pending/unknown skipped)", s == 200 and r["added"] == 2)
ok("forward-many is idempotent", call("POST", f"/admin/prescriptions/{R1}/forward-many", {"provider_ids": [ids["a"], ids["b"]]}, at)[1]["added"] == 0)
ok("prescription status becomes forwarded", sql("SELECT status FROM prescriptions WHERE id=?", (R1,))[0][0] == "forwarded")
ok("existing notification trigger tells each pharmacy", all(sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='provider.prescription'", (ids[k],))[0][0] == 1 for k in "ab"))
ok("audit entry written", sql("SELECT COUNT(*) FROM audit_log WHERE action='prescription.forward' AND target=?", (str(R1),))[0][0] >= 1)

# ---- تسعيرة ببنود: تحقق المدخلات
Q = f"/provider/prescriptions/{R1}/quote"
for bad, nm in (({"items": []}, "empty list"), ({"items": "x"}, "not a list"), ({}, "missing items"), ({"items": [{"name": "a", "unit_price": 5}]}, "short name"),
                ({"items": [{"name": "دواء", "unit_price": 0}]}, "zero price"), ({"items": [{"name": "دواء", "unit_price": "x"}]}, "text price"), ({"items": [{"name": "دواء", "unit_price": True}]}, "bool price"),
                ({"items": [{"name": "دواء", "unit_price": 5, "qty": 0}]}, "qty 0"), ({"items": [{"name": "دواء", "unit_price": 5, "qty": 100}]}, "qty 100"), ({"items": [{"name": "دواء", "unit_price": 5, "qty": True}]}, "bool qty"),
                ({"items": [{"name": "دواء", "unit_price": 1e9}]}, "huge price"), ({"items": ["x"]}, "non-dict item"), ({"items": [{"name": "دواء", "unit_price": 5}] * 31}, "31 items"),
                ({"items": [{"name": "دواء", "unit_price": 100000, "qty": 99}] * 2}, "total over cap")):
    ok("quote validation rejects " + nm, call("POST", Q, bad, pa)[0] == 400)
ok("rejected quotes wrote nothing", sql("SELECT COUNT(*) FROM prescription_responses WHERE prescription_id=?", (R1,))[0][0] == 0)

# ---- تسعيرات صحيحة + مقارنة
s, r = call("POST", Q, {"items": ITEMS, "note": "توصيل متاح"}, pa); ok("pharmacy A quote complete → available, total 95.5", s == 200 and r["status"] == "available" and r["total"] == 95.5)
s, r = call("POST", f"/provider/prescriptions/{R1}/quote", {"items": [{"name": "باراسيتامول", "qty": 2, "unit_price": 15}, {"name": "فيتامين د", "qty": 1, "unit_price": 50}]}, pb); ok("pharmacy B cheaper total 80", s == 200 and r["total"] == 80)
ok("response row total matches (old flow keeps working)", sql("SELECT status,price FROM prescription_responses WHERE prescription_id=? AND provider_id=?", (R1, ids["a"]))[0] == ("available", 95.5))
ok("existing notification trigger tells the customer", sql("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind LIKE 'medical.%'", (call("GET", "/me", None, cust)[1]["id"],))[0][0] >= 1)
s, r = call("GET", f"/provider/prescriptions/{R1}/quote", None, pa); ok("pharmacy can read back own lines", s == 200 and [i["name"] for i in r["items"]] == ["باراسيتامول", "فيتامين د"] and r["response"]["price"] == 95.5)
ok("pharmacy cannot read another pharmacy's lines (no access → 404)", call("GET", f"/provider/prescriptions/{R1}/quote", None, pc)[0] == 404)
s, r = call("GET", f"/medical/prescriptions/{R1}/quotes", None, cust); qs = r["quotes"]
ok("customer sees both quotes cheapest first", s == 200 and [x["pharmacy"] for x in qs] == ["صيدلية b", "صيدلية a"] and qs[0]["price"] == 80)
ok("only the cheapest complete fresh quote is flagged", qs[0]["cheapest"] and not qs[1]["cheapest"])
ok("quote carries line items with availability", qs[0]["items"][0] == {"name": "باراسيتامول", "qty": 2, "unit_price": 15.0, "available": True})
ok("no phone numbers in the comparison payload", not any(p in json.dumps(r, ensure_ascii=False) for p in ("01011111111", "01022222222", "01012345678")) and '"phone"' not in json.dumps(r))
ok("another customer cannot see my quotes; anonymous 401", call("GET", f"/medical/prescriptions/{R1}/quotes", None, other)[0] == 404 and call("GET", f"/medical/prescriptions/{R1}/quotes")[0] == 401)
ok("quotes for unknown prescription 404", call("GET", "/medical/prescriptions/99999/quotes", None, cust)[0] == 404)

# ---- تسعيرة جزئية وغير متوفرة
s, r = call("POST", Q, {"items": [{"name": "باراسيتامول", "qty": 2, "unit_price": 10}, {"name": "دواء نادر", "available": False}]}, pa)
ok("partial quote → needs_confirmation with partial total", s == 200 and r["status"] == "needs_confirmation" and r["total"] == 20)
qa = next(x for x in call("GET", f"/medical/prescriptions/{R1}/quotes", None, cust)[1]["quotes"] if x["pharmacy"] == "صيدلية a")
ok("partial flagged, missing item named, not cheapest", qa["partial"] and qa["missing"] == ["دواء نادر"] and not qa["cheapest"])
ok("partial ranks after complete quotes", call("GET", f"/medical/prescriptions/{R1}/quotes", None, cust)[1]["quotes"][-1]["pharmacy"] == "صيدلية a")
ok("quote update replaces lines (no leftovers)", sql("SELECT COUNT(*) FROM rx_quote_items WHERE prescription_id=? AND provider_id=?", (R1, ids["a"]))[0][0] == 2)
ok("customer cannot order from a partial quote", call("POST", "/medical/delivery", {"source_type": "prescription", "source_id": R1, "provider_id": ids["a"], "dropoff_text": "شارع النيل"}, cust)[0] == 409)
s, r = call("POST", Q, {"items": [{"name": "دواء أ", "available": False}, {"name": "دواء ب", "available": False}]}, pa)
ok("all-unavailable quote → unavailable, no price", s == 200 and r["status"] == "unavailable" and sql("SELECT price FROM prescription_responses WHERE prescription_id=? AND provider_id=?", (R1, ids["a"]))[0][0] is None)
call("POST", Q, {"items": ITEMS}, pa)

# ---- الطلب بعد المقارنة + الحداثة
s, r = call("POST", "/medical/delivery", {"source_type": "prescription", "source_id": R1, "provider_id": ids["b"], "dropoff_text": "شارع النيل"}, cust)
ok("customer orders delivery from the cheapest pharmacy", s == 201 and r["reference"] == "R%d" % R1)
qb = next(x for x in call("GET", f"/medical/prescriptions/{R1}/quotes", None, cust)[1]["quotes"] if x["pharmacy"] == "صيدلية b"); ok("quote shows the delivery order id", qb["delivery_order_id"] == r["id"])
sql("UPDATE prescription_responses SET updated_at=? WHERE prescription_id=? AND provider_id=?", (int(time.time()) - 3 * 86400, R1, ids["a"]))
qs = call("GET", f"/medical/prescriptions/{R1}/quotes", None, cust)[1]["quotes"]; qa = next(x for x in qs if x["pharmacy"] == "صيدلية a")
ok("stale quote flagged not fresh and not cheapest", qa["fresh"] is False and not qa["cheapest"])

# ---- إغلاق الروشتة
ok("another customer cannot close mine", call("POST", f"/medical/prescriptions/{R1}/close", {}, other)[0] == 404 and call("POST", f"/medical/prescriptions/{R1}/close", {})[0] == 401)
ok("owner closes prescription", call("POST", f"/medical/prescriptions/{R1}/close", {}, cust)[0] == 200 and call("POST", f"/medical/prescriptions/{R1}/close", {}, cust)[0] == 409)
ok("close revokes access for pharmacies without an order but keeps the ordered one", sql("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (R1,)) == [(ids["b"],)])
ok("closed prescription refuses new quotes", call("POST", Q, {"items": ITEMS}, pa)[0] == 404)
ok("revoked pharmacy cannot fetch the prescription image", call("GET", "/files/%d" % sql("SELECT file_id FROM prescriptions WHERE id=?", (R1,))[0][0], None, pa)[0] in (403, 404))

# ---- صلاحية الروشتة (14 يومًا)
R2 = new_rx(); call("POST", f"/admin/prescriptions/{R2}/forward-many", {"provider_ids": [ids["a"]]}, at)
sql("UPDATE prescriptions SET created_at=? WHERE id=?", (int(time.time()) - 20 * 86400, R2))
ok("expired prescription refuses quotes (409)", call("POST", f"/provider/prescriptions/{R2}/quote", {"items": ITEMS}, pa)[0] == 409)

# ---- تحويل تلقائي لصيدليات المنطقة
R3 = new_rx(); ok("auto-forward toggle is admin-only", call("POST", "/admin/rx/auto-forward", {"enabled": True}, cust)[0] == 403 and call("GET", "/admin/rx/auto-forward", None, cust)[0] == 403)
ok("auto-forward default disabled", call("GET", "/admin/rx/auto-forward", None, at)[1] == {"enabled": False})
s, r = call("POST", f"/admin/prescriptions/{R3}/forward-many", {"auto": True}, at)
ok("manual auto=true forwards to approved pharmacies of the region only (a,b; not c in another markaz)", s == 200 and sorted(x[0] for x in sql("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (R3,))) == sorted([ids["a"], ids["b"]]))
ok("enable auto-forward", call("POST", "/admin/rx/auto-forward", {"enabled": True}, at)[1]["enabled"] is True and call("GET", "/admin/rx/auto-forward", None, at)[1]["enabled"] is True)
R4 = new_rx(); ok("new upload auto-forwarded to region pharmacies and marked forwarded", sorted(x[0] for x in sql("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (R4,))) == sorted([ids["a"], ids["b"]]) and sql("SELECT status FROM prescriptions WHERE id=?", (R4,))[0][0] == "forwarded")
R5 = new_rx(region=99); ok("auto-forward respects region (markaz 99 → only c)", [x[0] for x in sql("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (R5,))] == [ids["c"]])
call("POST", "/admin/rx/auto-forward", {"enabled": False}, at); R6 = new_rx(); ok("disabling stops auto-forward", sql("SELECT COUNT(*) FROM prescription_access WHERE prescription_id=?", (R6,))[0][0] == 0)
ok("manual auto=true works after toggle is off", call("POST", f"/admin/prescriptions/{R6}/forward-many", {"auto": True}, at)[0] == 200)
sql("UPDATE providers SET status='suspended'"); R7 = new_rx(other); ok("no approved pharmacies → 409", call("POST", f"/admin/prescriptions/{R7}/forward-many", {"auto": True}, at)[0] == 409)
sql("UPDATE providers SET status='approved' WHERE user_id IN (?,?,?)", (ids["a"], ids["b"], ids["c"]))

# ---- الواجهات (فحص نصي: الدوال والمسارات موجودة ومربوطة)
rd = lambda p: open(os.path.join(os.path.dirname(os.path.abspath(__file__)), p), encoding="utf8").read()
ph, ad, ix, sw = rd("static/pharmacy.html"), rd("static/admin.html"), rd("static/index.html"), rd("static/sw.js")
ok("pharmacy UI: line-item quote form wired to /quote", all(x in ph for x in ("window.qsend", "window.qadd", "window.qinit", "/provider/prescriptions/'+id+'/quote", "p.forEach(qinit)")) and "form('p'" not in ph)
ok("admin UI: multi-select + region forward + auto toggle", all(x in ad for x in ("forward-many", "window.fmany", "/admin/rx/auto-forward", "تحويل لصيدليات المنطقة")))
ok("customer UI: comparison + close wired", all(x in ix for x in ("const rxq=", "/quotes", "window.rc=", "/close", "الأرخص", "rxq(qs[k]")))
ok("every UI string is escaped through esc() for pharmacy/customer data", all(x in ix for x in ("esc(x.pharmacy)", "esc(i.name)")) and "esc(it.name" in ph)
ok("service worker cache version >= v32", (lambda m: bool(m) and int(m.group(1)) >= 32)(__import__("re").search(r'const V = "laqino-v(\d+)"', sw)))
print("ALL PASSED")
