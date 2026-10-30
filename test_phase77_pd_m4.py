# phase-77 / م4: لوحة الإدارة لدليفري كل الصيدليات — اختبار معزول (SQLite في الذاكرة، بلا server.py)؛ يغطي: التجميع، الترتيب، العمولة (خصم−عكس)، التنبيهات، الصلاحيات، CSV
import sqlite3, time, json, provider_delivery as pd
c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
c.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,phone TEXT,role TEXT);CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE providers(user_id INTEGER PRIMARY KEY,name_ar TEXT,status TEXT DEFAULT 'approved');
CREATE TABLE delivery_orders(id INTEGER PRIMARY KEY,customer_id INTEGER,courier_id INTEGER,status TEXT,created_at INTEGER,dropoff_text TEXT);
CREATE TABLE order_events(id INTEGER PRIMARY KEY,order_id INTEGER,actor_id INTEGER,from_status TEXT,to_status TEXT,at INTEGER);
CREATE TABLE wallet_entries(id INTEGER PRIMARY KEY,user_id INTEGER,kind TEXT,amount REAL,ref_type TEXT,ref_id INTEGER,created_at INTEGER);""")
pd.install(c)
ok = lambda n, x: print(("PASS " if x else "FAIL ") + n) or (x or exit(1))
now = int(time.time()); T = now - 600
for i, (n, ph, r) in enumerate([("admin", "01000000000", "admin"), ("صيدلية النور", "01011111111", "user"), ("صيدلية الأمل", "01022222222", "user"), ("مندوب أ", "01033333333", "user"), ("مندوب ب", "01044444444", "user"), ("=cmd", "01055555555", "user")], 1):
    c.execute("INSERT INTO users VALUES(?,?,?,?)", (i, n, ph, r))
c.execute("INSERT INTO providers(user_id,name_ar) VALUES(2,'صيدلية النور')"); c.execute("INSERT INTO providers(user_id,name_ar) VALUES(3,'صيدلية الأمل')")
def order(ph, cour, status, cust, price, evs=(), comm=None):
    oid = c.execute("INSERT INTO delivery_orders(customer_id,courier_id,status,created_at,origin_type,pd_cust_phone,pd_cust_norm,pd_price) VALUES(?,?,?,?,?,?,?,?)", (ph, cour, status, T, pd.KIND, cust, pd.norm_phone(cust), price)).lastrowid
    c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, ph, None, "searching", T))
    for a, f, t, at in evs: c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, a, f, t, T + at))
    if comm: c.execute("INSERT INTO wallet_entries(user_id,kind,amount,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?)", (cour, "commission", -comm, "order", oid, T))
    return oid
full = lambda cour, leg: [(cour, "searching", "assigned", 30), (cour, "assigned", "heading_pickup", 60), (cour, "heading_pickup", "picked_up", 120), (cour, "picked_up", "heading_customer", 130), (cour, "heading_customer", "completed", 120 + leg)]
o1 = order(2, 4, "completed", "01001230001", 40, full(4, 600), 5)       # توصيل 10 د
o2 = order(2, 4, "completed", "01001230002", 60, full(4, 3000), 5)      # 50 د = متأخر (حد 45)
o3 = order(3, 5, "completed", "+20 100 123 0001", 25, full(5, 300), 5)  # نفس رقم o1 عند صيدلية أخرى
o4 = order(3, None, "cancelled", "01001230009", None)
for _ in range(3): c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (o1, 4, "assigned", "searching", T + 40))  # مندوب أ تخلّى 3×
o5 = order(3, 6, "completed", "01001230004", 10, full(6, 400), 2)
c.execute("INSERT INTO wallet_entries(user_id,kind,amount,ref_type,ref_id,created_at) VALUES(6,'reversal',2,'order',?,?)", (o5, T))  # عُكست عمولة o5 → صافيها 0
c.commit()
class H:
    def send(s, code, body=None, *a, **k): s.code, s.body = code, body
    def body(s): return {}
def call(u, path, qs=""):
    h = H(); q = {k: [v] for k, v in (x.split("=") for x in qs.split("&") if x)}
    r = pd.handle(h, c, u, "GET", path, q); return r, h
adm = {"id": 1, "role": "admin"}; D = "/api/admin/provider-delivery/dashboard"
r, h = call(adm, D, "range=today"); b = h.body
ok("admin sees summary across pharmacies", r and h.code == 200 and b["summary"]["total"] == 5 and b["summary"]["completed"] == 4 and b["summary"]["cancelled"] == 1 and b["summary"]["pharmacies"] == 2)
ok("cancel pct", b["summary"]["cancel_pct"] == 20)
ok("commission net = charged − reversed", b["summary"]["commission"] == 15 and b["summary"]["price_sum"] == 135)
ok("pharmacy ranking by orders", [p["name"] for p in b["pharmacies"]] == ["صيدلية الأمل", "صيدلية النور"] and b["pharmacies"][0]["total"] == 3 and b["pharmacies"][0]["cancel_pct"] == 33)
ok("pharmacy late pct + commission", [p for p in b["pharmacies"] if p["name"] == "صيدلية النور"][0]["late_pct"] == 50 and [p for p in b["pharmacies"] if p["name"] == "صيدلية النور"][0]["commission"] == 10)
ok("courier ranking has abandons attributed to the abandoner", [x for x in b["couriers"] if x["name"] == "مندوب أ"][0]["abandons_by"] == 3)
ok("alert: same phone at 2 pharmacies (normalised)", b["alerts"]["cross_pharmacy_phones"] == [{"phone": "01001230001", "orders": 2, "pharmacies": ["صيدلية الأمل", "صيدلية النور"]}])
ok("alert: frequent abandoner", [x["name"] for x in b["alerts"]["frequent_abandoners"]] == ["مندوب أ"] and b["alerts"]["frequent_abandoners"][0]["abandons"] == 3)
ok("cancelled orders excluded from cross-pharmacy alert", all(a["phone"] != "01001230009" for a in b["alerts"]["cross_pharmacy_phones"]))
r, h = call(adm, D, "sort=cancel"); ok("sort by cancel", h.code == 200 and h.body["pharmacies"][0]["name"] == "صيدلية الأمل")
r, h = call(adm, D, "sort=commission"); ok("sort by commission", h.body["pharmacies"][0]["name"] == "صيدلية النور")
ok("bad sort 400", call(adm, D, "sort=x")[1].code == 400)
ok("bad date 400", call(adm, D, "from=oops")[1].code == 400)
ok("old range excludes today's orders", call(adm, D, "from=2020-01-01&to=2020-01-02")[1].body["summary"]["total"] == 0)
ok("non-admin 403", call({"id": 2, "role": "user"}, D)[1].code == 403)
ok("anonymous 401", call(None, D)[1].code == 401)
h = H(); ok("POST not handled (read-only)", pd.handle(h, c, adm, "POST", D, {}) is False)
r, h = call(adm, "/api/admin/provider-delivery/export", "range=today"); cs = h.body["csv"]
ok("csv export: all pharmacies, BOM, commission", h.code == 200 and h.body["count"] == 5 and cs.startswith("﻿") and "صيدلية الأمل" in cs and "صيدلية النور" in cs)
c.execute("UPDATE users SET name='=HYPERLINK(1)' WHERE id=5"); c.commit()
ok("csv neutralises formulas", "'=HYPERLINK(1)" in call(adm, "/api/admin/provider-delivery/export", "range=today")[1].body["csv"])
ok("old admin settings route still handled", call(adm, "/api/admin/provider-delivery")[1].code == 200)
ok("pharmacy dash route untouched (needs approved pharmacy → 403 for admin)", call(adm, "/api/provider/delivery-dashboard")[1].code == 403)
print("ALL PASS")
