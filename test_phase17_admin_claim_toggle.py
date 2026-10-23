"""Phase 17: admin can explicitly toggle claim routing; it remains off by default and is audited."""
import os,tempfile,threading,time,json,urllib.request,urllib.error,sqlite3
DB=tempfile.mktemp(suffix='.db'); UP=tempfile.mkdtemp(prefix='laqino-p17-')
os.environ['LAQINO_DB']=DB; os.environ['LAQINO_UPLOADS']=UP
import server
from http.server import ThreadingHTTPServer
server.init('01000000000','AdminPass123')
c=server.db(); now=int(time.time())
try:
    reg=c.execute("SELECT id FROM regions WHERE level='markaz' AND is_active=1 ORDER BY id LIMIT 1").fetchone() or c.execute("SELECT id FROM regions ORDER BY id LIMIT 1").fetchone()
    rid=reg['id']; salt='56'*16
    pid=c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,?)",('01077778888','صيدلية',server.hp('password1',salt),salt,'medical_provider',rid,now)).lastrowid
    c.execute("INSERT INTO providers(user_id,name_ar,region_id,address,status,created_at) VALUES(?,?,?,'عنوان','approved',?)",(pid,'صيدلية اختبار',rid,now)); c.commit()
finally:c.close()
srv=ThreadingHTTPServer(('127.0.0.1',0),server.H); threading.Thread(target=srv.serve_forever,daemon=True).start(); base='http://127.0.0.1:%d'%srv.server_address[1]
def call(method,path,data=None,token=None):
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request(base+path,json.dumps(data).encode() if data is not None else None,headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
_,login=call('POST','/api/login',{'phone':'01000000000','password':'AdminPass123'})
token=login['token']
st,r=call('GET','/api/admin/rx/routing-settings',token=token)
assert st==200 and r['settings'].get('rx_claim_mode','0')=='0', (st,r)
st,r=call('POST','/api/admin/rx/routing-settings',{'claim_mode':True,'routing_mode':'direct','direct_provider_id':pid,'claim_timeout_minutes':10,'total_timeout_minutes':60,'distribution_regions':[],'distribution_provider_ids':[]},token)
assert st==200 and r['settings']['rx_claim_mode']=='1', (st,r)
st,r=call('POST','/api/admin/rx/routing-settings',{'claim_mode':'yes','routing_mode':'direct','direct_provider_id':pid,'claim_timeout_minutes':10,'total_timeout_minutes':60,'distribution_regions':[],'distribution_provider_ids':[]},token)
assert st==400, (st,r)
c=server.db()
try:
    assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='settings.rx_routing' AND detail LIKE '%claim_mode%'").fetchone()[0]>=1
finally:c.close()
html=open(os.path.join(os.path.dirname(__file__),'static','admin.html'),encoding='utf-8').read()
assert 'id="rxclaimmode"' in html and 'تحذير: تفعيل النظام سيطبق على الطلبات الجديدة' in html
srv.shutdown();srv.server_close()
print('PASS claim mode remains disabled by default and can be explicitly enabled by admin')
print('PASS invalid claim mode rejected and changes audited')
print('PASS admin UI exposes an explicit confirmation before enabling')
