"""Phase 8: concurrent claim attempts yield one active pharmacy; expiry moves image access."""
import os, tempfile, threading, time, sqlite3, json
DB = tempfile.mktemp(suffix='.db')
UP = tempfile.mkdtemp(prefix='laqino-p8-uploads-')
os.environ['LAQINO_DB'] = DB
os.environ['LAQINO_UPLOADS'] = UP
import server
server.init('01000000000', 'AdminPass123')

c = server.db()
try:
    region = c.execute("SELECT id FROM regions WHERE level='markaz' ORDER BY id LIMIT 1").fetchone()
    if not region:
        region = c.execute("SELECT id FROM regions ORDER BY id LIMIT 1").fetchone()
    assert region, 'init should seed at least one region'
    rid = int(region['id']); now = int(time.time())
    def user(phone, name):
        salt = 'ab' * 16
        cur = c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,?)",
                        (phone, name, server.hp('password1', salt), salt, 'medical_provider', rid, now))
        return cur.lastrowid
    customer = user('01012345678', 'customer')
    p1 = user('01011111111', 'pharmacy1')
    p2 = user('01022222222', 'pharmacy2')
    c.execute("UPDATE users SET role='customer' WHERE id=?", (customer,))
    for pid, name in ((p1, 'صيدلية أ'), (p2, 'صيدلية ب')):
        c.execute("INSERT INTO providers(user_id,name_ar,kind,region_id,address,status,created_at,distribution_enabled) VALUES(?,?,'pharmacy',?,?,'approved',?,1)",
                  (pid, name, rid, 'عنوان', now))
    fcur = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (customer, 'test.png', 'image/png', 1, now))
    fid = fcur.lastrowid
    cur = c.execute("INSERT INTO prescriptions(customer_id,region_id,file_id,note,status,created_at,kind) VALUES(?,?,?,?,'pending',?,'rx')", (customer, rid, fid, '', now-120))
    rxid = cur.lastrowid
    for key, value in [('rx_claim_mode','1'),('rx_routing_mode','auto'),('rx_distribution_regions',json.dumps([rid])),('rx_claim_timeout_minutes','10'),('rx_total_timeout_minutes','60')]:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    c.commit()
finally:
    c.close()

barrier = threading.Barrier(2)
results = []
errors = []
def attempt():
    con = server.db()
    try:
        barrier.wait(timeout=5)
        result = server.rx._claim_next(con, rxid, int(time.time()))
        con.commit()
        results.append(result)
    except Exception as e:
        errors.append(repr(e))
        try: con.rollback()
        except Exception: pass
    finally: con.close()
threads = [threading.Thread(target=attempt) for _ in range(2)]
for t in threads: t.start()
for t in threads: t.join(10)
assert not any(t.is_alive() for t in threads), 'claim threads should finish'
assert not errors, errors
con = server.db()
try:
    active = con.execute("SELECT provider_id FROM rx_claims WHERE prescription_id=? AND status='active'", (rxid,)).fetchall()
    access = con.execute("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (rxid,)).fetchall()
    assert len(active) == 1, active
    assert len(access) == 1 and access[0][0] == active[0][0], (active, access)
    first = active[0][0]
    con.execute("UPDATE rx_claims SET expires_at=? WHERE prescription_id=? AND status='active'", (int(time.time())-1, rxid))
    con.commit()
    processed = server.rx.refresh_claims(con, int(time.time()))
    active2 = con.execute("SELECT provider_id FROM rx_claims WHERE prescription_id=? AND status='active'", (rxid,)).fetchall()
    access2 = con.execute("SELECT provider_id FROM prescription_access WHERE prescription_id=?", (rxid,)).fetchall()
    assert processed == 1, processed
    assert len(active2) == 1 and active2[0][0] != first, (first, active2)
    assert len(access2) == 1 and access2[0][0] == active2[0][0], (active2, access2)
finally:
    con.close()
print('PASS concurrent claims serialize to one active pharmacy')
print('PASS expired claim transfers image access to the next pharmacy only')
