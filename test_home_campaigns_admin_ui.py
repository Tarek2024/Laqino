"""Exercise the real admin campaign screen through the repository's DOM harness."""
import os, tempfile, threading, time, json, urllib.request, urllib.error, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1",0),server.H)
threading.Thread(target=srv.serve_forever,daemon=True).start()
BASE="http://127.0.0.1:%d" % srv.server_address[1]
ROOT=os.path.dirname(os.path.abspath(__file__))
def call(method,path,data=None,token=None):
    req=urllib.request.Request(BASE+"/api"+path,json.dumps(data).encode() if data is not None else None,{"Content-Type":"application/json",**({"Authorization":"Bearer "+token} if token else {})},method=method)
    try:
        with urllib.request.urlopen(req,timeout=8) as r:return r.status,json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read() or b"{}")
def check(name,condition):
    print(("PASS " if condition else "FAIL ")+name)
    if not condition:raise AssertionError(name)
admin=call("POST","/login",{"phone":"01000000000","password":"AdminPass123"})[1]["token"]
harness=os.path.join(ROOT,"test_ui_page_harness.js")
def ui(steps):
    p=subprocess.run(["node",harness,"admin",BASE,admin,json.dumps(steps)],capture_output=True,text=True,timeout=20)
    if p.returncode:raise AssertionError(p.stderr[-1000:])
    return json.loads(p.stdout)
r=ui([{"js":"tab='homecampaigns';shell()","wait":900,"snap":"v"}])
check("admin screen loads dedicated homepage-campaigns section without JS errors",not r["errs"] and "إعلانات الصفحة الرئيسية" in r["v"])
check("admin UI clearly separates homepage campaigns from user market ads","الإعلانات هنا مستقلة عن إعلانات السوق" in r["v"])
check("admin UI exposes campaign title, destination, schedule, order, and active controls",all(x in r["v"] for x in ('id="hc-title"','id="hc-type"','id="hc-start"','id="hc-end"','id="hc-order"','id="hc-active"')))
r=ui([
 {"js":"tab='homecampaigns';shell()","wait":800},
 {"js":"document.getElementById('hc-title').value='حملة من لوحة الإدارة';document.getElementById('hc-desc').value='رسالة إدارية';document.getElementById('hc-type').value='home';document.getElementById('hc-target').value='';document.getElementById('hc-order').value='1';document.getElementById('hc-active').checked=true;saveHomeCampaign()","wait":900,"snap":"v"}
])
st,feed=call("GET","/home-campaigns")
item=next((x for x in feed if x["title"]=="حملة من لوحة الإدارة"),None)
check("admin UI creates an active campaign and public feed serves it",bool(item and item["href"]=="/"))
check("saved campaign is shown in the admin campaign list","حملة من لوحة الإدارة" in r["v"])
print("ALL HOMEPAGE CAMPAIGN ADMIN UI CHECKS PASSED")
