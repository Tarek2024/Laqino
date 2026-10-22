# المرحلة 30 (إصلاح): بحث الإعلانات بفهرس trigram — نفس نتائج LIKE (مطابقة جزء من الكلمة) لكن بفهرس، مع مزامنة الإضافة والتعديل والحذف
import os, json, threading, urllib.request, urllib.parse, tempfile, time, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
ok("FTS5 trigram index is active", server.FTS_OK)
db = sqlite3.connect(server.DB)
uid = db.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
cat = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]; reg = db.execute("SELECT id FROM regions LIMIT 1").fetchone()[0]
def add(title, desc="", status="approved"):
    cur = db.execute("INSERT INTO listings(user_id,category_id,region_id,title,description,price,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (uid, cat, reg, title, desc, 100, status, int(time.time()))); db.commit(); return cur.lastrowid
a = add("ثلاجة سامسونج نظيفة", "حالة ممتازة"); b = add("غسالة اتوماتيك", "ماركة LG ثلاجة صغيرة مجانا"); cc = add("موبايل ايفون", "100% جديد_تماما")
s = ThreadingHTTPServer(("127.0.0.1", 8792), server.H); threading.Thread(target=s.serve_forever, daemon=True).start(); time.sleep(.3)
def search(q):
    r = urllib.request.urlopen("http://127.0.0.1:8792/api/listings?" + urllib.parse.urlencode({"q": q}))
    d = json.loads(r.read()); d = d.get("items", d) if isinstance(d, dict) else d
    return sorted(x["id"] for x in d)
ok("partial Arabic word matches title and description", search("ثلاج") == sorted([a, b]))
ok("match in description only", search("ممتازة") == [a])
ok("English case-insensitive", search("lg ماركة") == [] and search("ماركة lg") == [b])
ok("literal % and _ are not wildcards", search("100%") == [cc] and search("جديد_تما") == [cc] and search("جديدXتما") == [])
ok("quotes in the query do not break the search", search('ثلاجة "x') == [])
ok("2-char query falls back to LIKE", search("ثل") == sorted([a, b]))
db.execute("UPDATE listings SET title='ميكروويف' WHERE id=?", (a,)); db.commit()
ok("update is reflected in the index", search("ميكرو") == [a] and search("سامسونج") == [])
db.execute("DELETE FROM listings WHERE id=?", (b,)); db.commit()
ok("delete is reflected in the index", search("غسال") == [])
add("لابتوب لينوفو", status="pending")
ok("pending listings still hidden from public search", search("لابتوب") == [])
db.execute("INSERT INTO listings_fts(listings_fts) VALUES('delete-all')"); db.commit()
server.init("01000000000", "AdminPass123")
ok("index is rebuilt automatically if it drifted", search("ميكرو") == [a] and server.FTS_OK)
# speed: 30k rows
db = sqlite3.connect(server.DB)
db.executemany("INSERT INTO listings(user_id,category_id,region_id,title,description,price,status,created_at) VALUES(?,?,?,?,?,?,?,?)", [(uid, cat, reg, "إعلان رقم %d منتج مستعمل" % i, "وصف عادي رقم %d للتجربة فقط" % i, 10, "approved", int(time.time())) for i in range(30000)]); db.commit()
c = server.db(); t0 = time.time(); n = c.execute("SELECT COUNT(*) FROM listings l WHERE l.id IN (SELECT rowid FROM listings_fts WHERE listings_fts MATCH ?)", ('"رقم 29999"',)).fetchone()[0]; t_fts = time.time() - t0
t0 = time.time(); m = c.execute("SELECT COUNT(*) FROM listings l WHERE l.title LIKE ? OR l.description LIKE ?", ("%رقم 29999%",) * 2).fetchone()[0]; t_like = time.time() - t0
ok("same count both ways (%d)" % n, n == m == 1)
print("FTS %.1fms vs LIKE %.1fms on 30k rows" % (t_fts * 1000, t_like * 1000))
print("ALL PASSED")
