# المرحلة 30 (إصلاح): بعد إعادة تشغيل السيرفر تُستأنف حلقات إيقاظ المناديب للطلبات التي ما زالت تبحث، ويُرسل sweep واحد لمسح تنبيهات قديمة
import os, tempfile, time, sqlite3, threading
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(); os.environ["LAQINO_PUSH_ALLOW_ANY"] = "1"
import server
server.init("01000000000", "AdminPass123")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
db = sqlite3.connect(server.DB); now = int(time.time())
uid = db.execute("SELECT id FROM users LIMIT 1").fetchone()[0]; reg = db.execute("SELECT id FROM regions LIMIT 1").fetchone()[0]
def order(status, age, courier=None):
    return db.execute("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,fee,status,courier_id,created_at,updated_at,search_started_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (uid, reg, "a", "b", 10, status, courier, now - age, now - age, now - age)).lastrowid
fresh = order("searching", 30); old = order("searching", 99999); done = order("completed", 30); taken = order("searching", 30, courier=uid)
db.execute("INSERT INTO push_subs(endpoint,user_id,created_at) VALUES('http://127.0.0.1:9/x',?,?)", (uid, now)); db.commit()
armed, swept = [], []
server.push_new_order = lambda oid: armed.append(oid)
server._push_to_users = lambda c, uids, ttl, native=True, kind="order": swept.append((tuple(uids), native)) or 0
ids = server.push_resume(); time.sleep(.3)
ok("only the fresh searching order is re-armed", ids == [fresh] and armed == [fresh])
ok("expired / finished / already-taken orders are not re-armed", old not in armed and done not in armed and taken not in armed)
ok("one sweep push (no native FCM) goes to subscribed users", swept == [((uid,), False)])
db.execute("DELETE FROM push_subs"); db.commit(); swept.clear(); armed.clear()
server.push_resume(); time.sleep(.2)
ok("no subscribers -> no sweep, order still re-armed", swept == [] and armed == [fresh])
print("ALL PASSED")
