# واجهة الإدارة الحقيقية داخل node (DOM وهمي) على خادم حقيقي — إنشاء تصنيف بأب، إضافة حقول، مهلة التوفر. ليس اختبار متصفح.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
PORT = 8779; BASE = f"http://127.0.0.1:{PORT}"
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
cu = user("01022222222", "عميل")
root = q("select id from categories where section='souq' and parent_id is null")[0][0]
S = lambda i, v: f"document.getElementById('{i}').value={json.dumps(v)}"
# --- API validation
ok("customer cannot create a category", call("POST", "/admin/categories", {"section": "souq", "name_ar": "x", "slug": "x1"}, cu)[0] == 403)
ok("parent from another section -> 400", call("POST", "/admin/categories", {"section": "medical", "parent_id": root, "name_ar": "x", "slug": "x2"}, at)[0] == 400)
ok("nonexistent parent -> 400", call("POST", "/admin/categories", {"section": "souq", "parent_id": 9999, "name_ar": "x", "slug": "x3"}, at)[0] == 400)
# --- create the category from the admin UI
r = ui("admin", at, [{"js": "tab='cats';shell()", "wait": 800, "snap": "v"}])
ok("admin page loads without script errors", r["errs"] == [])
ok("categories tab shows parent selector and the souq root", "إضافة تصنيف" in r["v"] and 'id="cp"' in r["v"] and "سوق لاقينو" in r["v"])
r = ui("admin", at, [{"js": "tab='cats';shell()", "wait": 800}, {"js": S("cs", "souq") + ";" + S("cp", str(root)) + ";" + S("cn", "موبايلات") + ";" + S("cl", "mobiles") + ";addC()", "wait": 900, "snap": "v"}])
row = q("select id,parent_id,section,is_active from categories where slug='mobiles'")
ok("UI created the category under the souq root, active", len(row) == 1 and row[0][1] == root and row[0][2] == "souq" and row[0][3] == 1)
cid = row[0][0]
ok("list re-rendered with the new category", "موبايلات" in r["v"])
# --- fields from the UI: a price field and a select field
steps = [{"js": "tab='cats';shell()", "wait": 800}, {"js": f"sf({cid})", "wait": 800, "snap": "v"},
 {"js": S("nfk", "price") + ";" + S("nfl", "السعر") + ";" + S("nft", "price") + ";" + S("nfo", "") + ";document.getElementById('nfr').checked=true;document.getElementById('nfs').checked=false;addF(" + str(cid) + ")", "wait": 900},
 {"js": S("nfk", "color") + ";" + S("nfl", "اللون") + ";" + S("nft", "select") + ";" + S("nfo", "أبيض، أسود, أحمر") + ";document.getElementById('nfr').checked=false;document.getElementById('nfs').checked=true;addF(" + str(cid) + ")", "wait": 900, "snap": "v"}]
r = ui("admin", at, steps)
ok("fields panel opens with the add-field form", "addF(" + str(cid) + ")" in r["v"])
fs = q("select key,type,required,searchable,options from category_fields where category_id=? order by id", cid)
ok("price field stored (required)", fs[0][:4] == ("price", "price", 1, 0))
ok("select field stored with parsed options (Arabic + Latin commas)", fs[1][:4] == ("color", "select", 0, 1) and json.loads(fs[1][4]) == ["أبيض", "أسود", "أحمر"])
ok("panel lists the new fields after adding", "السعر" in r["v"] and "اللون" in r["v"])
ok("admin sees fields of a hidden category via API", (call("POST", f"/admin/categories/{cid}", {"is_active": False}, at)[0] == 200) and len(call("GET", f"/categories/{cid}/fields", None, at)[1]) == 2)
ok("customer gets no fields for a hidden category", call("GET", f"/categories/{cid}/fields", None, cu)[1] == [])
call("POST", f"/admin/categories/{cid}", {"is_active": True}, at)
# --- the full journey: customer posts, admin approves, public sees it with price
r = ui("index", cu, [{"js": "go(1)", "wait": 900, "snap": "v"}])
ok("index posting dropdown lists the admin-made category", "موبايلات" in r["v"] and r["errs"] == [])
st, l = call("POST", "/listings", {"category_id": cid, "region_id": 3, "title": "آيفون مستعمل", "fields": {"price": 5000, "color": "أسود"}}, cu)
ok("customer posts into it (price field drives price)", st == 201)
ok("admin approves", call("POST", f"/admin/listings/{l['id']}/review", {"status": "approved"}, at)[0] == 200)
pub = call("GET", f"/listings?region_id=3&category_id={cid}")[1]
ok("public listing shows with price", len(pub) == 1 and pub[0]["price"] == 5000)
ok("required field enforced on the new category", call("POST", "/listings", {"category_id": cid, "region_id": 3, "title": "بدون سعر"}, cu)[0] == 400)
# --- stock-fresh setting from the settings tab
r = ui("admin", at, [{"js": "tab='settings';shell()", "wait": 900, "snap": "v"}])
ok("settings tab shows the stock-freshness card with default 24", "مدة اعتبار توافر الدواء" in r["v"] and 'id="sh"' in r["v"] and 'value="24"' in r["v"])
r = ui("admin", at, [{"js": "tab='settings';shell()", "wait": 800}, {"js": S("sh", "36") + ";go('/admin/settings/stock-fresh',{hours:+document.getElementById('sh').value})", "wait": 900, "snap": "v"}])
ok("saved from the UI and reflected", q("select value from settings where key='stock_fresh_hours'")[0][0] == "36" and 'value="36"' in r["v"])
print("ALL PASSED")
