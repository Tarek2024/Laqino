# المرحلة 11 / A-6: التصنيفات من قاعدة البيانات فقط؛ التصفح يخفي الفارغ والمعطّل، والنشر يرى كل المفعّل. fake-DOM في node، ليس متصفحًا.
import os, json, threading, urllib.request, urllib.error, urllib.parse, tempfile, time, subprocess, re
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8789), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:8789"; D = os.path.dirname(os.path.abspath(__file__)); HN = os.path.join(D, "test_ui_page_harness.js")
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + urllib.parse.quote(p, safe="/?=&"), json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def page(tok, steps):
    o = subprocess.run(["node", HN, "index", BASE, tok, json.dumps(steps)], capture_output=True, text=True, timeout=60); return json.loads(o.stdout)
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]; cu = user("01012345678"); sel = user("01022222222")
def cat(slug, name, **k): return call("POST", "/admin/categories", {"parent_id": 2, "section": "souq", "slug": slug, "name_ar": name, "is_active": True, **k}, at)[1]["id"]
c_full, c_empty, c_off = cat("furn", "أثاث"), cat("toys", "ألعاب"), cat("old", "قديم", is_active=False)
call("POST", f"/admin/categories/{c_full}/fields", {"key": "price", "label_ar": "السعر", "type": "price", "required": True}, at)
l = call("POST", "/listings", {"category_id": c_full, "region_id": 3, "title": "كنبة ثلاثية", "description": "ممتازة", "fields": {"price": 3500}}, sel)[1]["id"]
call("POST", "/listings", {"category_id": c_full, "region_id": 3, "title": "كنبة معلقة", "fields": {"price": 1}}, sel)  # قيد المراجعة
names = lambda r: [x["name_ar"] for x in r if x["parent_id"]]
ok("before approval: browse shows no subcategory (pending listings don't count)", names(call("GET", "/categories?section=souq&browse=1")[1]) == [])
call("POST", f"/admin/listings/{l}/review", {"status": "approved"}, at)
ok("browse hides empty and inactive subcategories", names(call("GET", "/categories?section=souq&browse=1")[1]) == ["أثاث"])
ok("posting list (no browse) shows every ACTIVE category, not the inactive one", sorted(names(call("GET", "/categories?section=souq")[1])) == sorted(["أثاث", "ألعاب"]))
ok("admin all=1 sees everything including inactive", sorted(names(call("GET", "/categories?section=souq&all=1", None, at)[1])) == sorted(["أثاث", "ألعاب", "قديم"]))
ok("customers cannot use all=1 to see inactive ones", "قديم" not in names(call("GET", "/categories?section=souq&all=1", None, cu)[1]))
rx = call("POST", "/admin/regions", {"parent_id": 1, "level": "governorate", "slug": "other", "name_ar": "محافظة أخرى للاختبار", "is_active": True}, at)[1]["id"]
ok("region-aware: a category with listings only elsewhere is hidden for this region", names(call("GET", f"/categories?section=souq&browse=1&region_id={rx}")[1]) == [] and names(call("GET", "/categories?section=souq&browse=1&region_id=3")[1]) == ["أثاث"] and names(call("GET", "/categories?section=souq&browse=1&region_id=2")[1]) == ["أثاث"])
ok("bad region value is a 400", call("GET", "/categories?section=souq&browse=1&region_id=x")[0] == 400)
lt = call("POST", "/listings", {"category_id": c_empty, "region_id": 3, "title": "لعبة", "fields": {}}, sel)[1].get("id"); call("POST", f"/admin/listings/{lt}/review", {"status": "rejected", "reason": "x"}, at)
ok("a rejected/pending listing does not make its category visible", names(call("GET", "/categories?section=souq&browse=1")[1]) == ["أثاث"])
# --- الواجهة
r = page(cu, [{"js": "go(1)", "snap": "v", "wait": 1200}])
chips = re.search(r'<div class="chips">(.*?)</div>', r["v"], re.S)
ok("market chips: only the non-empty category + 'الكل'", not r["errs"] and chips and "أثاث" in chips.group(1) and "ألعاب" not in chips.group(1) and "قديم" not in chips.group(1))
ok("publish form still offers every active category (can post into an empty one), never the inactive one", r["v"].count('<option value="') >= 2 and "ألعاب" in r["v"] and "قديم" not in r["v"])
print("ALL PASSED")
