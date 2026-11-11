# واجهتا طلب انضمام المندوب (index) ومراجعة المستندات (admin) داخل node بـ DOM وهمي على خادم حقيقي. ليس اختبار متصفح.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs, png
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8782; BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))

def user(ph, nm):
    call("POST", "/register", {"phone": ph, "name": nm, "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def ui(page, token, steps):
    r = subprocess.run(["node", H, page, BASE, token, json.dumps(steps)], capture_output=True, text=True, timeout=60)
    if r.returncode: print(r.stderr[:600])
    return json.loads(r.stdout)
q = lambda sql, *a: sqlite3.connect(os.environ["LAQINO_DB"]).execute(sql, a).fetchall()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
cu = user("01044444444", "متقدم")
FR = "FileReader=class{readAsDataURL(f){this.result='data:image/png;base64,'+f.b64;setTimeout(()=>this.onload(),0)}}"
NOS = {"js": "document.getElementById('cs').files=[]"}  # a real <input type=file> always has .files; the fake DOM does not
fl = lambda i, n=10: f"document.getElementById('{i}').files=[{{size:{n},b64:'{png()}'}}]"
# Phase 69 moved courier applications from the customer account tab to courier.html.
r = ui("courier", cu, [{"js": "document.getElementById('x_rg').querySelectorAll=()=>[{value:'3'}]", "snap": "m"}])
ok("courier page shows the three upload inputs", all(x in r["m"] for x in ('id="x_f1"', 'id="x_f2"', 'id="x_f3"')))
r = ui("courier", cu, [{"js": "document.getElementById('x_rg').querySelectorAll=()=>[{value:'3'}]"}, {"js": "sendApply()", "snap": "m"}])
ok("no files -> asks for ID photos, nothing created", "ارفع صورة البطاقة" in r["m"] and not q("SELECT * FROM couriers"))
r = ui("courier", cu, [{"js": "document.getElementById('x_rg').querySelectorAll=()=>[{value:'3'}]"}, {"js": fl("x_f1")}, {"js": "sendApply()", "snap": "m"}])
ok("only front -> asked for back, nothing created", "ارفع صورة البطاقة" in r["m"] and not q("SELECT * FROM couriers"))
r = ui("courier", cu, [{"js": "document.getElementById('x_rg').querySelectorAll=()=>[{value:'3'}]"}, {"js": fl("x_f1", 5_000_000)}, {"js": fl("x_f2")}, {"js": "sendApply()", "snap": "x_err"}])
ok("oversize photo rejected client-side", "كبيرة" in r["x_err"] and not q("SELECT * FROM couriers"))
r = ui("courier", cu, [{"js": FR}, {"js": "document.getElementById('x_rg').querySelectorAll=()=>[{value:'3'}]"}, {"js": fl("x_f1")}, {"js": fl("x_f2")}, {"js": "sendApply()", "snap": "m"}])
ok("front+back submit -> pending courier with 2 documents", q("SELECT status FROM couriers") == [("pending",)] and q("SELECT COUNT(*) FROM courier_documents")[0][0] == 2 and not r["errs"])
ok("application status shown after submit", "قيد مراجعة الإدارة" in r["m"])
r = ui("admin", at, [{"js": "tab='couriers';shell()", "wait": 4000, "snap": "v"}])
doc_ids=[x[0] for x in q("SELECT file_id FROM courier_documents")]
ok("admin page lists the documents with labels", "البطاقة — الوجه" in r["v"] and "البطاقة — الظهر" in r["v"] and len(doc_ids)==2 and all(f'id="cd{fid}"' in r["v"] for fid in doc_ids) and not r["errs"])
cu2 = user("01055555555", "قديم")
sqlite3.connect(os.environ["LAQINO_DB"]).execute("INSERT INTO couriers(user_id,region_id,created_at) VALUES(?,?,?)", (call("GET", "/me", None, cu2)[1]["id"], 3, int(time.time()))).connection.commit()
r = ui("admin", at, [{"js": "tab='couriers';shell()", "wait": 4000, "snap": "v"}])
ok("legacy request without documents is flagged", "لا توجد مستندات مرفوعة" in r["v"])
print("ALL PASSED")
