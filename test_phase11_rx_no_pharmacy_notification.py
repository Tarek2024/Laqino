"""Phase 11: tell the customer when a new claim-mode request has no eligible pharmacy."""
import os, tempfile, time, sqlite3, json
DB = tempfile.mktemp(suffix='.db'); UP = tempfile.mkdtemp(prefix='laqino-p11-')
os.environ['LAQINO_DB'] = DB; os.environ['LAQINO_UPLOADS'] = UP
import server
server.init('01000000000', 'AdminPass123')
c = server.db()
try:
    ridrow = c.execute("SELECT id FROM regions WHERE level='markaz' ORDER BY id LIMIT 1").fetchone() or c.execute("SELECT id FROM regions ORDER BY id LIMIT 1").fetchone()
    rid = ridrow['id']; now = int(time.time()); salt='cd'*16
    uid = c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,?)", ('01033334444','عميل الاختبار',server.hp('password1',salt),salt,'customer',rid,now)).lastrowid
    fid = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (uid,'test.png','image/png',1,now)).lastrowid
    rxid = c.execute("INSERT INTO prescriptions(customer_id,region_id,file_id,note,status,created_at,kind) VALUES(?,?,?,'','pending',?,'rx')", (uid,rid,fid,now)).lastrowid
    for k,v in [('rx_claim_mode','1'),('rx_routing_mode','auto'),('rx_distribution_regions','[]'),('rx_claim_timeout_minutes','10'),('rx_total_timeout_minutes','60')]:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,v))
    c.commit()
    assert server.rx.auto_forward(c, rxid) == 0
    notices = c.execute("SELECT user_id,kind,ref_type,ref_id FROM notifications WHERE kind='rx.no_pharmacy'").fetchall()
    assert len(notices)==1 and tuple(notices[0])==(uid,'rx.no_pharmacy','prescription',rxid), notices
    # Calling the same path again does not duplicate the terminal notice.
    assert server.rx.auto_forward(c, rxid) == 0
    assert c.execute("SELECT COUNT(*) FROM notifications WHERE kind='rx.no_pharmacy' AND ref_id=?",(rxid,)).fetchone()[0] == 1
finally:
    c.close()
print('PASS customer is notified when initial routing has no eligible pharmacy')
print('PASS repeated routing does not duplicate the notification')
