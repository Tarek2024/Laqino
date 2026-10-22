# المرحلة 16: صور الأطباء والمعامل — الترحيل، الرفع، التغيير، الإزالة، العرض العام، الصلاحيات، الأنواع الممنوعة.
# كل البيانات هنا داخل قاعدة مؤقتة ومجلد رفع مؤقت فقط.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, base64, io
_TMP = tempfile.mkdtemp(prefix="laqino-p16-")  # كل شيء هنا مؤقت ومعزول؛ لا يُلمس laqino.db الحقيقي ولا uploads الحقيقي
os.environ["LAQINO_DB"] = os.path.join(_TMP, "test.db"); os.environ["LAQINO_UPLOADS"] = os.path.join(_TMP, "uploads"); os.makedirs(os.environ["LAQINO_UPLOADS"])
import server
from phase16_imgutil import png_bytes
assert os.path.realpath(server.DB).startswith(os.path.realpath(_TMP)) and os.path.realpath(server.UP).startswith(os.path.realpath(_TMP)), "ISOLATION BROKEN: refusing to run"
from http.server import ThreadingHTTPServer
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))

# ---------- 1) ترحيل قاعدة قديمة (Phase 15: بلا عمود الصورة) تحمل أطباء ومعامل فعلية ----------
old = sqlite3.connect(server.DB); old.executescript(server.SCHEMA)
old.execute("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(3,NULL,'markaz','m','مركز الرياض',1)")
old.execute("INSERT INTO specialties(id,name_ar,name_norm) VALUES(1,'أطفال','اطفال')")
old.execute("INSERT INTO doctors(id,name_ar,name_norm,specialty_id,region_id,clinic_name,address,schedule,phone,bio,is_published,created_at,updated_at) VALUES(1,'د. قديم','د. قديم',1,3,'عيادة قديمة','شارع 1','السبت','0473000001','نبذة',1,1,1)")
old.execute("INSERT INTO labs(id,name_ar,name_norm,region_id,address,hours,tests,home_visit,phone,is_published,created_at,updated_at) VALUES(1,'معمل قديم','معمل قديم',3,'شارع 2','يوميا','سكر',1,'0473000002',1,1,1)")
old.commit(); cols = [r[1] for r in old.execute("PRAGMA table_info(doctors)")]; old.close()
ok("old database really lacks photo_file_id before migration", "photo_file_id" not in cols)
server.init("01000000000", "AdminPass123"); server.init("01000000000", "AdminPass123")  # twice: idempotent
c = server.db()
ok("migration adds photo_file_id to doctors and labs (idempotent)", all("photo_file_id" in [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)] for t in ("doctors", "labs")))
ok("old rows survive untouched with NULL photo", c.execute("SELECT name_ar,clinic_name,phone,is_published,photo_file_id FROM doctors WHERE id=1").fetchone()[:] == ("د. قديم", "عيادة قديمة", "0473000001", 1, None) and c.execute("SELECT name_ar,tests,photo_file_id FROM labs WHERE id=1").fetchone()[:] == ("معمل قديم", "سكر", None))
c.close()

_srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=_srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % _srv.server_address[1]  # منفذ حر تلقائي
def call(m, p, d=None, t=None, raw=False):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try:
        x = urllib.request.urlopen(r); b = x.read(); return (x.status, b, x.headers) if raw else (x.status, json.loads(b))
    except urllib.error.HTTPError as e:
        b = e.read(); return (e.code, b, e.headers) if raw else (e.code, json.loads(b))
b64 = lambda b: base64.b64encode(b).decode()
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
call("POST", "/register", {"phone": "01012345678", "name": "cust", "password": "password1"}); cu = call("POST", "/login", {"phone": "01012345678", "password": "password1"})[1]["token"]
up = lambda tok, data: call("POST", "/files", {"data": b64(data)}, tok)
files_on_disk = lambda: set(os.listdir(server.UP))

# ---------- 2) السجلات القديمة بلا صور ----------
pl = call("GET", "/doctors")[1]; ok("old doctor listed publicly with photo_url null", len(pl) == 1 and pl[0]["photo_url"] is None and "photo_file_id" not in pl[0] and "phone" not in pl[0])
ok("old doctor has no public photo (404)", call("GET", "/doctors/1/photo", None, None, True)[0] == 404)
ok("old lab listed publicly with photo_url null", call("GET", "/labs")[1][0]["photo_url"] is None and call("GET", "/labs/1/photo", None, None, True)[0] == 404)
ok("old doctor can still be edited without touching photo", call("POST", "/admin/doctors/1", {"bio": "نبذة جديدة"}, at)[0] == 200 and call("GET", "/doctors/1")[1]["bio"] == "نبذة جديدة")

# ---------- 3) طبيب بصورة: إضافة -> تعديل الصورة -> عرض للمستخدم ----------
sp = call("POST", "/admin/specialties", {"name_ar": "جلدية"}, at)[1]["id"]
img1 = png_bytes(); s, f1 = up(at, img1); f1 = f1["id"]; ok("admin uploads a photo", s == 201)
s, r = call("POST", "/admin/doctors", {"name_ar": "د. سارة عبد الرحمن", "specialty_id": sp, "region_id": 3, "clinic_name": "عيادة الشفاء", "address": "شارع الجمهورية", "phone": "0473123456", "photo_file_id": f1}, at)
did = r["id"]; ok("doctor created with a photo (unpublished)", s == 201 and r["is_published"] == 0)
adm = [x for x in call("GET", "/admin/doctors", None, at)[1] if x["id"] == did][0]
ok("admin row exposes photo_file_id and photo_url", adm["photo_file_id"] == f1 and adm["photo_url"] == "/api/doctors/%d/photo?v=%d" % (did, f1))
ok("unpublished doctor's photo is not public", call("GET", f"/doctors/{did}/photo", None, None, True)[0] == 404)
ok("admin can preview the unpublished photo through /files", call("GET", f"/files/{f1}", None, at, True)[0] == 200)
ok("publish works with a photo", call("POST", f"/admin/doctors/{did}/publish", {"published": True}, at)[0] == 200)
s, body, h = call("GET", f"/doctors/{did}/photo", None, None, True)
ok("published photo is public (no login) and is an image", s == 200 and h["Content-Type"] == "image/png" and body[:4] == b"\x89PNG" and "max-age" in h["Cache-Control"] and h["X-Content-Type-Options"] == "nosniff")
pub = call("GET", "/doctors?q=" + urllib.request.quote("سارة"))[1]; det = call("GET", f"/doctors/{did}")[1]
ok("Arabic search returns the doctor with photo_url; no secrets leak", len(pub) == 1 and pub[0]["photo_url"] == adm["photo_url"] and det["photo_url"] == adm["photo_url"] and not ({"phone", "whatsapp", "photo_file_id", "is_published"} & set(det)))
# تعديل بيانات فقط: الصورة تبقى
ok("text-only edit keeps the photo", call("POST", f"/admin/doctors/{did}", {"clinic_name": "عيادة الشفاء الجديدة"}, at)[0] == 200 and call("GET", f"/doctors/{did}")[1]["photo_url"] == adm["photo_url"])
# تغيير الصورة
img2 = png_bytes(); f2 = up(at, img2)[1]["id"]; before = files_on_disk()
ok("photo replaced", call("POST", f"/admin/doctors/{did}", {"photo_file_id": f2}, at)[0] == 200)
det = call("GET", f"/doctors/{did}")[1]; s, body, h = call("GET", f"/doctors/{did}/photo", None, None, True)
ok("new photo is served and the URL changes (cache busting)", det["photo_url"].endswith("v=%d" % f2) and body == img2)
ok("old photo row and file were removed", server.db().execute("SELECT 1 FROM files WHERE id=?", (f1,)).fetchone() is None and len(files_on_disk()) == len(before) - 1)
ok("other doctor fields untouched by the photo change", det["clinic_name"] == "عيادة الشفاء الجديدة" and det["name_ar"] == "د. سارة عبد الرحمن")
# إزالة الصورة
ok("photo removed with null", call("POST", f"/admin/doctors/{did}", {"photo_file_id": None}, at)[0] == 200 and call("GET", f"/doctors/{did}")[1]["photo_url"] is None and call("GET", f"/doctors/{did}/photo", None, None, True)[0] == 404)
ok("removed photo file deleted from disk and table", server.db().execute("SELECT 1 FROM files WHERE id=?", (f2,)).fetchone() is None)

# ---------- 4) معمل بصورة ----------
imgL = png_bytes(); fl = up(at, imgL)[1]["id"]
s, r = call("POST", "/admin/labs", {"name_ar": "معمل الأمل للتحاليل", "region_id": 3, "address": "ش المحطة", "phone": "0473555555", "tests": "سكر، صورة دم", "photo_file_id": fl}, at); lid = r["id"]
ok("lab created with a photo/logo", s == 201 and call("GET", "/admin/labs", None, at)[1][0]["photo_file_id"] == fl)
ok("unpublished lab photo not public", call("GET", f"/labs/{lid}/photo", None, None, True)[0] == 404)
call("POST", f"/admin/labs/{lid}/publish", {"published": True}, at)
s, body, h = call("GET", f"/labs/{lid}/photo", None, None, True); ok("published lab photo is public", s == 200 and body == imgL and h["Content-Type"] == "image/png")
lp = [x for x in call("GET", "/labs")[1] if x["id"] == lid][0]; ok("lab list has photo_url, no number", lp["photo_url"].startswith(f"/api/labs/{lid}/photo?v=") and "phone" not in lp)
ok("lab text-only edit keeps photo", call("POST", f"/admin/labs/{lid}", {"hours": "9-5"}, at)[0] == 200 and [x for x in call("GET", "/labs")[1] if x["id"] == lid][0]["photo_url"] == lp["photo_url"])
imgL2 = png_bytes(); fl2 = up(at, imgL2)[1]["id"]
ok("lab photo replaced and old removed", call("POST", f"/admin/labs/{lid}", {"photo_file_id": fl2}, at)[0] == 200 and call("GET", f"/labs/{lid}/photo", None, None, True)[1] == imgL2 and server.db().execute("SELECT 1 FROM files WHERE id=?", (fl,)).fetchone() is None)
ok("lab photo removed", call("POST", f"/admin/labs/{lid}", {"photo_file_id": ""}, at)[0] == 200 and call("GET", f"/labs/{lid}/photo", None, None, True)[0] == 404)

# ---------- 5) الصلاحيات والتحقق ----------
ok("customer cannot add/edit doctors or labs with photos (403)", all(call("POST", p, {"name_ar": "xxxx", "photo_file_id": 1}, cu)[0] == 403 for p in ("/admin/doctors", f"/admin/doctors/{did}", "/admin/labs", f"/admin/labs/{lid}")))
ok("anonymous cannot either", call("POST", "/admin/doctors", {"name_ar": "xxxx"})[0] in (401, 403))
fc = up(cu, png_bytes())[1]["id"]
ok("admin cannot attach another user's file", call("POST", f"/admin/doctors/{did}", {"photo_file_id": fc}, at)[0] == 400)
fa = up(at, png_bytes())[1]["id"]; call("POST", f"/admin/doctors/{did}", {"photo_file_id": fa}, at)
ok("same photo cannot be reused by a second record (409)", call("POST", f"/admin/labs/{lid}", {"photo_file_id": fa}, at)[0] == 409)
ok("a photo in use cannot be deleted through /files (409)", call("POST", f"/files/{fa}/delete", {}, at)[0] == 409)
ok("unknown / non-numeric photo ids rejected", call("POST", f"/admin/doctors/{did}", {"photo_file_id": 999999}, at)[0] == 400 and call("POST", f"/admin/doctors/{did}", {"photo_file_id": "abc"}, at)[0] == 400)
ok("failed photo change leaves the old photo", call("GET", f"/doctors/{did}")[1]["photo_url"].endswith("v=%d" % fa))
ok("bad input on create does not create a record", call("POST", "/admin/doctors", {"name_ar": "د. بدون تخصص", "specialty_id": 9999, "region_id": 3, "photo_file_id": up(at, png_bytes())[1]["id"]}, at)[0] == 400)
# أنواع غير مسموحة
gif = b"GIF89a" + b"\x01\x00\x01\x00" + b"\x00" * 20; svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'; html = b"<html><script>alert(1)</script></html>"
ok("GIF / SVG / HTML / text rejected by upload", all(up(at, x)[0] == 400 for x in (gif, svg, html, b"hello")))
ok("PNG header with garbage body rejected", up(at, b"\x89PNG\r\n\x1a\n" + b"junk" * 10)[0] == 400)
ok("oversize image rejected (413)", up(at, b"\x89PNG\r\n\x1a\n" + b"\x00" * 4_100_000)[0] == 413)
ok("admin uploads are not blocked by the per-customer file cap (22 uploads)", all(up(at, png_bytes())[0] == 201 for _ in range(22)))
n = 0
for _ in range(25):
    if up(cu, png_bytes())[0] == 201: n += 1
ok("customers are still capped at 20 files", n == 19)  # one already uploaded above
if True:
    try:
        from PIL import Image
        bio = io.BytesIO(); Image.new("RGB", (60, 40), (200, 30, 30)).save(bio, "JPEG", quality=80); jb = bio.getvalue()
        fj = up(at, jb); ok("real JPEG accepted", fj[0] == 201)
        call("POST", f"/admin/labs/{lid}", {"photo_file_id": fj[1]["id"]}, at); s, body, h = call("GET", f"/labs/{lid}/photo", None, None, True)
        ok("JPEG served as image/jpeg", s == 200 and h["Content-Type"] == "image/jpeg" and body[:3] == b"\xff\xd8\xff")
    except ImportError:
        print("SKIP JPEG checks (Pillow not installed)")
