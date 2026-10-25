"""Phase 57: شاشة متابعة الروشتات ومفتاح الاعتماد اليدوي في admin.html (متصفح حقيقي)."""
import os, json, threading, tempfile, time, sys, urllib.request

os.environ["LAQINO_DB"]=tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"]=tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
from imgutil import png
server.init("01000000000","AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1",8861),server.H).serve_forever,daemon=True).start(); time.sleep(.3)
B="http://127.0.0.1:8861"
def call(m,p,d=None,t=None):
    r=urllib.request.Request(B+"/api"+p,json.dumps(d).encode() if d is not None else None,{"Content-Type":"application/json",**({"Authorization":"Bearer "+t} if t else {})},method=m); return json.loads(urllib.request.urlopen(r).read())
def user(ph): call("POST","/register",{"phone":ph,"name":"u"+ph[-2:],"password":"password1"}); return call("POST","/login",{"phone":ph,"password":"password1"})["token"]
at=call("POST","/login",{"phone":"01000000000","password":"AdminPass123"})["token"]
cu,pa=user("01012345678"),user("01011111111"); pid=call("GET","/me",None,pa)["id"]
call("POST","/providers/apply",{"name_ar":"صيدلية أ","region_id":3,"address":"x"},pa); call("POST",f"/admin/providers/{pid}/review",{"status":"approved"},at)
rid=call("POST","/medical/prescriptions",{"file_id":call("POST","/files",{"data":png()},cu)["id"],"region_id":3},cu)["id"]
call("POST",f"/admin/prescriptions/{rid}/forward",{"provider_id":pid},at)
call("POST",f"/provider/prescriptions/{rid}/respond",{"status":"available","price":40},pa)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(B+"/admin.html"); pg.fill("#p","01000000000"); pg.fill("#w","AdminPass123"); pg.click("button:has-text('دخول')")
    pg.wait_for_selector("nav"); pg.click("nav button[data-k=rx]"); pg.wait_for_selector("#rxmon .card",timeout=8000)
    t=pg.inner_text("#rxmon"); print(t)
    assert "صيدلية أ" in t and "ردّت" in t
    pg.click("details summary"); pg.check("#rxmr"); pg.wait_for_timeout(500)
    print("manual:",call("GET","/admin/rx/manual-review",None,at))
    print("errors:",errs); assert not errs
    print("PASS admin rx monitor + manual-review toggle"); print("TOTAL OK")
    b.close()
