# المرحلة 16: سلامة الترحيل على قاعدة Phase 15 تحمل بيانات فعلية (مستخدمون، صور، روشتات، أطباء، معامل).
# يعمل على نسخة مؤقتة فقط، ويتحقق أنه لم يضِع صف ولا ملف ولا بايت، وأن الحسابات القديمة تدخل.
import os, tempfile, sqlite3, hashlib, shutil, json, threading, time, urllib.request
_TMP = tempfile.mkdtemp(prefix="laqino-p16mig-")
os.environ["LAQINO_DB"] = os.path.join(_TMP, "test.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "uploads"); os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
from phase16_imgutil import png_bytes
from http.server import ThreadingHTTPServer
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)) and os.path.realpath(server.UP).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))

# 1) ابنِ قاعدة بمخطط Phase 15 (بلا photo_file_id) وفيها بيانات حقيقية الشكل
server.init("01000000000", "AdminPass123")
c = server.db(); now = int(time.time())
for t in ("doctors", "labs"):
    c.execute("ALTER TABLE %s DROP COLUMN photo_file_id" % t)
pw = server.hash_pw("password1") if hasattr(server, "hash_pw") else None
c.execute("INSERT INTO specialties(id,name_ar,name_norm) VALUES(7,'عظام','عظام')")
c.execute("INSERT INTO doctors(id,name_ar,name_norm,specialty_id,region_id,clinic_name,address,schedule,phone,whatsapp,bio,is_published,created_at,updated_at) VALUES(5,'د. أحمد','د. احمد',7,3,'عيادة النيل','ش 1','السبت','0473000009','01012345678','نبذة',1,10,11)")
c.execute("INSERT INTO labs(id,name_ar,name_norm,region_id,address,hours,tests,home_visit,phone,is_published,created_at,updated_at) VALUES(4,'معمل الندى','معمل الندى',3,'ش 2','يوميا','سكر',1,'0473000008',1,10,11)")
uid = c.execute("SELECT id FROM users WHERE phone='01000000000'").fetchone()["id"]
old_files = {}
for i in range(3):  # صور قديمة (روشتات) موجودة فعلًا على القرص
    raw = png_bytes(); name = "old%d" % i; open(os.path.join(server.UP, name), "wb").write(raw)
    fid = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (uid, name, "image/png", len(raw), 100 + i)).lastrowid; old_files[name] = hashlib.sha256(raw).hexdigest()
c.execute("INSERT INTO prescriptions(customer_id,region_id,file_id,note,status,created_at) VALUES(?,3,1,'ملاحظة','pending',200)", (uid,))
c.commit()
cols = lambda t: [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)]
ok("simulated Phase 15 DB has no photo_file_id", "photo_file_id" not in cols("doctors") and "photo_file_id" not in cols("labs"))
def dump(cn):
    out = {}
    for (t,) in cn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        names = [r[1] for r in cn.execute("PRAGMA table_info(%s)" % t) if r[1] != "photo_file_id"]
        out[t] = [tuple(r) for r in cn.execute("SELECT %s FROM %s ORDER BY 1" % (",".join(names), t))]
    return out
before = dump(c); c.close()
shutil.copy(server.DB, os.path.join(_TMP, "backup.db"))  # كما في خطوة النسخ الاحتياطي في README

# 2) رحّل (مرتين)
server.init("01000000000", "AdminPass123"); server.init("01000000000", "AdminPass123")
c = server.db(); after = dump(c)
ok("every pre-existing table has exactly the same rows after migration (all columns)", before == after)
ok("doctors and labs gained photo_file_id = NULL only", all("photo_file_id" in cols(t) for t in ("doctors", "labs")) and c.execute("SELECT photo_file_id FROM doctors WHERE id=5").fetchone()[0] is None and c.execute("SELECT photo_file_id FROM labs WHERE id=4").fetchone()[0] is None)
ok("PRAGMA integrity_check ok and foreign_key_check empty", c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == [])
ok("old uploaded files are byte-identical and still referenced", all(hashlib.sha256(open(os.path.join(server.UP, n), "rb").read()).hexdigest() == h for n, h in old_files.items()) and c.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 3 and c.execute("SELECT file_id FROM prescriptions").fetchone()[0] == 1)
c.close()

# 3) الحسابات والصور القديمة تعمل عبر الـAPI بعد الترحيل
_srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=_srv.serve_forever, daemon=True).start(); time.sleep(.3); BASE = "http://127.0.0.1:%d" % _srv.server_address[1]
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); b = x.read(); return (x.status, b) if raw else (x.status, json.loads(b))
    except urllib.error.HTTPError as e: b = e.read(); return (e.code, b) if raw else (e.code, json.loads(b))
s, r = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"}); ok("existing admin account still logs in", s == 200 and "token" in r); at = r["token"]
ok("old uploaded image still readable through /api/files by its owner", call("GET", "/files/1", None, at, True)[1] == open(os.path.join(server.UP, "old0"), "rb").read())
ok("old published doctor and lab unchanged in public lists", [d["name_ar"] for d in call("GET", "/doctors")[1]] == ["د. أحمد"] and [d["name_ar"] for d in call("GET", "/labs")[1]] == ["معمل الندى"])
ok("old prescription image cannot be hijacked as a doctor photo (409)", call("POST", "/admin/doctors/5", {"photo_file_id": 1}, at)[0] == 409)
ok("old non-photo files are not deleted by photo replacement", (lambda f: call("POST", "/admin/doctors/5", {"photo_file_id": f}, at)[0] == 200 and call("POST", "/admin/doctors/5", {"photo_file_id": None}, at)[0] == 200)(call("POST", "/files", {"data": __import__("base64").b64encode(png_bytes()).decode()}, at)[1]["id"]) and os.path.exists(os.path.join(server.UP, "old0")) and len(os.listdir(server.UP)) == 3)
