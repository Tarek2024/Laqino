"""Phase 18: persistence and validation of homepage section settings using a temporary DB."""
import os, tempfile, threading, time, json, sqlite3, urllib.request, urllib.error
os.environ['LAQINO_DB'] = tempfile.mktemp(suffix='.db')
os.environ['LAQINO_UPLOADS'] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
PORT=8791
server.init('01000000000','AdminPass123')
# Simulate settings saved by the previous build, which had a separate products card.
legacy = [
 {'key':'med','name':'الخدمات الطبية','description':'أدوية وصيدليات وأطباء ومعامل','visible':True,'order':1},
 {'key':'prod','name':'المنتجات','description':'منتجات طبية وعروض الصيدليات','visible':True,'order':2},
 {'key':'souq','name':'سوق لاقينو','description':'بيع واشتري جنب بيتك','visible':True,'order':3},
 {'key':'svc','name':'الخدمات المحلية','description':'مقدّمو خدمات في منطقتك','visible':True,'order':4},
 {'key':'dlv','name':'التوصيل','description':'ابعت أي حاجة والمندوب يوصلها','visible':True,'order':5},
]
with sqlite3.connect(os.environ['LAQINO_DB']) as db:
    db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('home_sections_v1',?)", (json.dumps(legacy, ensure_ascii=False),))
threading.Thread(target=ThreadingHTTPServer(('127.0.0.1',PORT),server.H).serve_forever,daemon=True).start();time.sleep(.25)
BASE=f'http://127.0.0.1:{PORT}/api'
def call(method,path,data=None,token=None):
    req=urllib.request.Request(BASE+path,json.dumps(data).encode() if data is not None else None,{'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})},method=method)
    try:
        with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
def check(c,m):
    if not c:raise AssertionError(m)
    print('PASS',m)
st,initial=call('GET','/home-sections');check(st==200 and len(initial)==4 and {x['key'] for x in initial}=={'med','souq','svc','dlv'},'legacy settings migrate to four homepage sections; products remain inside medical')
check([x['order'] for x in initial]==[1,2,3,4],'legacy order values are compacted after removing the products card')
st,login=call('POST','/login',{'phone':'01000000000','password':'AdminPass123'});check(st==200,'admin login on temporary database')
tok=login['token']; changed=[]
for x in initial: changed.append({**x,'name':x['name']+' معدّل' if x['key']=='med' else x['name'],'visible':False if x['key']=='souq' else x['visible'],'order':6-x['order']})
st,res=call('POST','/home-sections',{'sections':changed},tok);check(st==200 and res['ok'],'admin saves names, visibility, and ordering')
st,after=call('GET','/home-sections');check(st==200 and next(x for x in after if x['key']=='med')['name'].endswith('معدّل'),'saved names persist after reload')
check(next(x for x in after if x['key']=='souq')['visible'] is False,'hidden section persists after reload')
check([x['order'] for x in after]==sorted(x['order'] for x in after),'public config is sorted by configured order')
bad=[dict(x) for x in after];bad[0]['order']=bad[1]['order']
st,_=call('POST','/home-sections',{'sections':bad},tok);check(st==400,'duplicate order is rejected without changing settings')
print('ALL PASSED')
