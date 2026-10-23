"""Phase 14: exercise real deadline processing and both terminal customer notifications."""
import os, tempfile, time, json
DB=tempfile.mktemp(suffix='.db'); UP=tempfile.mkdtemp(prefix='laqino-p14-')
os.environ['LAQINO_DB']=DB; os.environ['LAQINO_UPLOADS']=UP
import server
server.init('01000000000','AdminPass123')
c=server.db(); now=int(time.time())
try:
    reg=c.execute("SELECT id FROM regions WHERE level='markaz' ORDER BY id LIMIT 1").fetchone() or c.execute("SELECT id FROM regions ORDER BY id LIMIT 1").fetchone()
    rid=int(reg['id']); salt='ef'*16
    customer=c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,?)",('01044445555','عميل',server.hp('password1',salt),salt,'customer',rid,now)).lastrowid
    psalt='12'*16
    provider=c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,?)",('01055556666','صيدلية',server.hp('password1',psalt),psalt,'medical_provider',rid,now)).lastrowid
    c.execute("INSERT INTO providers(user_id,name_ar,region_id,address,status,created_at,distribution_enabled) VALUES(?,?,?,'عنوان','approved',?,1)",(provider,'صيدلية الاختبار',rid,now))
    for k,v in [('rx_claim_mode','1'),('rx_routing_mode','auto'),('rx_distribution_regions',json.dumps([rid])),('rx_claim_timeout_minutes','10'),('rx_total_timeout_minutes','60')]:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,v))
    ids=[]
    for n,created in [('total',now-3601),('noalt',now-120)]:
        f=c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)",(customer,n+'.png','image/png',1,now)).lastrowid
        rxid=c.execute("INSERT INTO prescriptions(customer_id,region_id,file_id,note,status,created_at,kind) VALUES(?,?,?,'','forwarded',?,'rx')",(customer,rid,f,created)).lastrowid
        c.execute("INSERT INTO rx_claims(prescription_id,provider_id,claimed_at,expires_at,status) VALUES(?,?,?,?, 'active')",(rxid,provider,now-700,now-1))
        c.execute("INSERT INTO rx_claim_attempts VALUES(?,?,?,'claimed')",(rxid,provider,now-700))
        c.execute("INSERT INTO prescription_access VALUES(?,?)",(rxid,provider))
        ids.append((n,rxid))
    c.commit()
    processed=server.rx.refresh_claims(c,now)
    assert processed==2, processed
    by_kind={r['kind']:r for r in c.execute("SELECT kind,user_id,ref_type,ref_id FROM notifications WHERE ref_type='prescription'").fetchall()}
    total_id=dict(ids)['total']; noalt_id=dict(ids)['noalt']
    assert 'rx.claim_timeout' in by_kind and by_kind['rx.claim_timeout']['user_id']==customer and by_kind['rx.claim_timeout']['ref_id']==total_id, by_kind
    assert 'rx.no_pharmacy' in by_kind and by_kind['rx.no_pharmacy']['user_id']==customer and by_kind['rx.no_pharmacy']['ref_id']==noalt_id, by_kind
    server.rx.refresh_claims(c,now+1)
    assert c.execute("SELECT COUNT(*) FROM notifications WHERE kind IN('rx.claim_timeout','rx.no_pharmacy')").fetchone()[0]==2
finally:
    c.close()
print('PASS total-deadline processing notifies customer once')
print('PASS expired claim with no eligible alternative notifies customer once')
