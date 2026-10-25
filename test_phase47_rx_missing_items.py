"""Phase 47: automatic partial prescription routing, item-level status, and delivery safeguards."""
import os, json, tempfile, threading, urllib.request, urllib.error, sqlite3, time
os.environ['LAQINO_DB'] = tempfile.mktemp(suffix='.db')
os.environ['LAQINO_UPLOADS'] = tempfile.mkdtemp()
import server, rx
from http.server import ThreadingHTTPServer
from imgutil import png
server.init('01000000000', 'AdminPass123')
import sqlite3 as _sq; _m=_sq.connect(os.environ['LAQINO_DB']); _m.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('rx_manual_review','1')"); _m.commit(); _m.close()  # phase-56: تغطية الاعتماد اليدوي (المفتاح الاحتياطي من phase-54)
httpd=ThreadingHTTPServer(('127.0.0.1',0),server.H); threading.Thread(target=httpd.serve_forever,daemon=True).start()
BASE='http://127.0.0.1:%s'%httpd.server_address[1]; DB=os.environ['LAQINO_DB']

def call(method,path,data=None,token=None):
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request(BASE+'/api'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=10) as r: return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: body=json.loads(e.read())
        except Exception: body={}
        return e.code,body

def check(name, cond):
    print(('PASS ' if cond else 'FAIL ')+name)
    if not cond: raise SystemExit(1)

def sql(q,args=()):
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    try: return c.execute(q,args).fetchall()
    finally: c.close()

def add_user(phone,name,role,region_id):
    c=server.db(); salt='ab'*16
    try:
        cur=c.execute('INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) VALUES(?,?,?,?,?,?,?)',(phone,name,server.hp('password1',salt),salt,role,region_id,int(time.time())))
        uid=cur.lastrowid
        if role=='medical_provider': c.execute("INSERT INTO providers(user_id,name_ar,kind,region_id,address,status,created_at,distribution_enabled) VALUES(?,?,'pharmacy',?,'عنوان الاختبار','approved',?,1)",(uid,name,region_id,int(time.time())))
        c.commit(); return uid
    finally: c.close()

try:
    admin=call('POST','/login',{'phone':'01000000000','password':'AdminPass123'})[1]['token']
    c=server.db(); mk=c.execute("SELECT id FROM regions WHERE slug='eg-kfs-riyad'").fetchone(); rid=int(mk['id'])
    for k,v in [('rx_claim_mode','1'),('rx_routing_mode','automatic'),('rx_distribution_regions',json.dumps([rid])),('rx_claim_timeout_minutes','10'),('rx_total_timeout_minutes','60')]:
        c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))
    c.execute('INSERT INTO region_fees(region_id,fee) VALUES(?,20) ON CONFLICT(region_id) DO UPDATE SET fee=excluded.fee',(rid,)); c.commit(); c.close()
    cust_id=add_user('01012345678','عميل الاختبار','customer',rid)
    p1=add_user('01011111111','صيدلية ألف','medical_provider',rid)
    p2=add_user('01022222222','صيدلية باء','medical_provider',rid)
    p3=add_user('01033333333','صيدلية جيم','medical_provider',rid)
    cust=call('POST','/login',{'phone':'01012345678','password':'password1'})[1]['token']
    t1=call('POST','/login',{'phone':'01011111111','password':'password1'})[1]['token']
    t2=call('POST','/login',{'phone':'01022222222','password':'password1'})[1]['token']
    t3=call('POST','/login',{'phone':'01033333333','password':'password1'})[1]['token']
    fid=call('POST','/files',{'data':png()},cust)[1]['id']
    st,created=call('POST','/medical/prescriptions',{'file_ids':[fid],'region_id':rid,'note':'','kind':'rx'},cust)
    check('new prescription is created and initially assigned to the first participating pharmacy',st==201 and sql("SELECT provider_id FROM rx_claims WHERE prescription_id=? AND status='active'",(created.get('id'),))[0]['provider_id']==p1)
    rxid=created['id']
    st,_=call('POST',f'/provider/prescriptions/{rxid}/respond',{'status':'available','price':99},t1)
    check('legacy one-status response cannot bypass item-level confirmation in claim mode',st==409)
    full=[{'name':'دواء أ','qty':1,'unit_price':10,'item_status':'available'},{'name':'دواء ب','qty':1,'unit_price':20,'item_status':'available'},{'name':'دواء ج','qty':1,'unit_price':30,'item_status':'available'},{'name':'دواء د','qty':1,'item_status':'unavailable'},{'name':'دواء هـ','qty':1,'item_status':'unavailable'}]
    all_available=[{'name':x['name'],'qty':1,'unit_price':10,'item_status':'available'} for x in full]
    st,_=call('POST',f'/provider/prescriptions/{rxid}/quote',{'items':all_available,'confirm_all':False},t1)
    check('a pharmacy cannot report full availability without explicit confirmation',st==400)
    st,r=call('POST',f'/provider/prescriptions/{rxid}/quote',{'items':full,'confirm_all':False},t1)
    check('partial response is accepted without claiming all items are available',st==200 and r['status']=='needs_confirmation')
    review_results=[]
    def approve_once(): review_results.append(call('POST',f'/admin/rx/responses/{rxid}/{p1}/review',{'decision':'approve'},admin)[0])
    barrier=threading.Barrier(3)
    def concurrent_approve(): barrier.wait(); approve_once()
    workers=[threading.Thread(target=concurrent_approve) for _ in range(2)]
    [w.start() for w in workers]; barrier.wait(); [w.join() for w in workers]
    active=sql("SELECT provider_id FROM rx_claims WHERE prescription_id=? AND status='active'",(rxid,))
    scope=sql('SELECT name,qty FROM rx_claim_items WHERE prescription_id=? AND provider_id=? ORDER BY line_no',(rxid,p2))
    check('simultaneous admin approvals cannot duplicate redistribution',sorted(review_results)==[200,409] and len(active)==1 and active[0]['provider_id']==p2 and scope==[])  # phase-56: الروشتة كلها بدل الناقص فقط
    st,plist=call('GET','/provider/prescriptions',token=t2)
    row=next((x for x in plist if x['id']==rxid),{})
    check('next pharmacy gets the whole prescription (no missing-item scope) in its work queue',st==200 and row.get('requested_items',[])==[])
    p2items=[{'name':'دواء أ','qty':1,'item_status':'unavailable'},{'name':'دواء ب','qty':1,'item_status':'unavailable'},{'name':'دواء ج','qty':1,'item_status':'unavailable'},{'name':'دواء د','qty':1,'unit_price':8,'item_status':'available'},{'name':'دواء هـ','qty':1,'item_status':'needs_confirmation'}]
    st,r=call('POST',f'/provider/prescriptions/{rxid}/quote',{'items':p2items,'confirm_all':False},t2)
    check('pharmacy can mark an individual item as needing review',st==200 and r['status']=='needs_confirmation')
    call('POST',f'/admin/rx/responses/{rxid}/{p2}/review',{'decision':'approve'},admin)
    active=sql("SELECT provider_id FROM rx_claims WHERE prescription_id=? AND status='active'",(rxid,))
    scope3=sql('SELECT name,qty FROM rx_claim_items WHERE prescription_id=? AND provider_id=? ORDER BY line_no',(rxid,p3))
    check('after the second partial response, the whole prescription goes to the next pharmacy',len(active)==1 and active[0]['provider_id']==p3 and scope3==[])
    st,r=call('POST',f'/provider/prescriptions/{rxid}/quote',{'items':[{'name':'دواء أ','qty':1,'item_status':'unavailable'},{'name':'دواء ب','qty':1,'item_status':'unavailable'},{'name':'دواء ج','qty':1,'item_status':'unavailable'},{'name':'دواء د','qty':1,'item_status':'unavailable'},{'name':'دواء هـ','qty':1,'unit_price':7,'item_status':'available'}],'send_mode':'partial'},t3)
    check('third pharmacy quotes the whole prescription and confirms the last missing item',st==200 and r['status']=='needs_confirmation')
    st,_=call('POST',f'/admin/rx/responses/{rxid}/{p3}/review',{'decision':'approve'},admin)
    data=call('GET',f'/medical/prescriptions/{rxid}/quotes',None,cust)[1]
    listing=call('GET','/medical/prescriptions',None,cust)[1]
    pres=next(x for x in listing if x['id']==rxid)
    active=sql("SELECT provider_id FROM rx_claims WHERE prescription_id=? AND status='active'",(rxid,))
    check('aggregate status becomes complete only after every expected item is approved available',st==200 and pres['aggregate_status']=='complete' and data['aggregate_status']=='complete' and not active)
    check('all previous pharmacy responses remain visible in the customer history',len(data['quotes'])==3 and {x['provider_id'] for x in data['quotes']}=={p1,p2,p3})
    st,delivery=call('POST','/medical/delivery',{'source_type':'prescription','source_id':rxid,'provider_id':p3,'dropoff_text':'شارع البحر'},cust)
    check('a partial quote (not every item confirmed) cannot create a delivery order',st==409 and 'لم تؤكد' in delivery.get('error',''))

    # A single pharmacy's fully confirmed complete quote ends routing immediately and remains eligible for the existing delivery flow.
    fid2=call('POST','/files',{'data':png()},cust)[1]['id']
    st,created2=call('POST','/medical/prescriptions',{'file_ids':[fid2],'region_id':rid,'note':'','kind':'rx'},cust); rx2=created2['id']
    active2=sql("SELECT provider_id FROM rx_claims WHERE prescription_id=? AND status='active'",(rx2,))[0]['provider_id']
    tok={p1:t1,p2:t2,p3:t3}[active2]
    items=[{'name':'دواء كامل','qty':1,'unit_price':12,'item_status':'available'}]
    st,_=call('POST',f'/provider/prescriptions/{rx2}/quote',{'items':items,'confirm_all':True},tok)
    call('POST',f'/admin/rx/responses/{rx2}/{active2}/review',{'decision':'approve'},admin)
    check('single-pharmacy full confirmation stops distribution without assigning another pharmacy',st==200 and not sql("SELECT 1 FROM rx_claims WHERE prescription_id=? AND status='active'",(rx2,)) and len(sql('SELECT provider_id FROM prescription_access WHERE prescription_id=?',(rx2,)))==1)
    st,del2=call('POST','/medical/delivery',{'source_type':'prescription','source_id':rx2,'provider_id':active2,'dropoff_text':'شارع البحر'},cust)
    check('existing delivery flow still accepts a full confirmed quote',st==201 and del2.get('status')=='searching')

    c=server.db(); c.execute('UPDATE providers SET distribution_enabled=0 WHERE user_id IN (?,?)',(p2,p3)); c.commit(); c.close()
    fid3=call('POST','/files',{'data':png()},cust)[1]['id']
    st,created3=call('POST','/medical/prescriptions',{'file_ids':[fid3],'region_id':rid,'note':'','kind':'rx'},cust); rx3=created3['id']
    p1only=sql("SELECT provider_id FROM rx_claims WHERE prescription_id=? AND status='active'",(rx3,))[0]['provider_id']
    st,_=call('POST',f'/provider/prescriptions/{rx3}/quote',{'items':[{'name':'دواء ناقص','qty':1,'item_status':'unavailable'}]},t1)
    call('POST',f'/admin/rx/responses/{rx3}/{p1only}/review',{'decision':'approve'},admin)
    q3=call('GET',f'/medical/prescriptions/{rx3}/quotes',None,cust)[1]
    check('when no eligible pharmacy remains, routing reports exhausted and preserves the partial response',st==200 and q3['routing_state']=='exhausted' and not sql("SELECT 1 FROM rx_claims WHERE prescription_id=? AND status='active'",(rx3,)) and len(q3['quotes'])==1)
finally:
    httpd.shutdown()
