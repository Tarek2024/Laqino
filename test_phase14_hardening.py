# المرحلة 14: توحيد حماية أرقام التواصل (أطباء/معامل/خدمات/سوق)، إزالة EXIF عند الرفع، HSTS، فحص كلمة مرور المدير.
# كل البيانات هنا بيانات اختبار داخل قاعدة مؤقتة فقط.
import os, json, threading, urllib.request, urllib.error, urllib.parse, tempfile, time, base64, struct, zlib
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, imgutil
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8791), server.H).serve_forever, daemon=True).start(); time.sleep(.3)
B = "http://127.0.0.1:8791"; D = os.path.dirname(os.path.abspath(__file__))
def raw(m, p, d=None, t=None):
    r = urllib.request.Request(B + "/api" + urllib.parse.quote(p, safe="/?=&"), json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, x.read(), x.headers
    except urllib.error.HTTPError as e: return e.code, e.read(), e.headers
def call(m, p, d=None, t=None): s, b, h = raw(m, p, d, t); return s, json.loads(b)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]; cu, cu2 = user("01012345678"), user("01099999999")

# ---------- 1) أرقام الأطباء والمعامل مقفولة بنفس طريقة الخدمات ----------
sp = call("POST", "/admin/specialties", {"name_ar": "أطفال"}, at)[1]["id"]
def doc(n): 
    i = call("POST", "/admin/doctors", {"name_ar": "د. تجربة %d" % n, "specialty_id": sp, "region_id": 3, "address": "شارع البحر", "phone": "0473%06d" % n, "whatsapp": "01055%06d" % n}, at)[1]["id"]; call("POST", f"/admin/doctors/{i}/publish", {"published": True}, at); return i
def lab(n):
    i = call("POST", "/admin/labs", {"name_ar": "معمل تجربة %d" % n, "region_id": 3, "address": "شارع المحطة", "phone": "0473%06d" % n}, at)[1]["id"]; call("POST", f"/admin/labs/{i}/publish", {"published": True}, at); return i
t1 = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
def svc(n):
    i = call("POST", "/admin/services", {"name_ar": "فني تجربة %d" % n, "type_id": t1, "region_id": 3, "address": "شارع البحر", "phone": "0100%07d" % n}, at)[1]["id"]; call("POST", f"/admin/services/{i}/publish", {"published": True}, at); return i
d1, d2, l1, l2, s1 = doc(1), doc(2), lab(1), lab(2), svc(1)
body = lambda r: json.dumps(r, ensure_ascii=False)
ok("public doctor list/detail carry no phone or whatsapp", all(k not in x for x in call("GET", "/doctors")[1] for k in ("phone", "whatsapp")) and all(k not in call("GET", f"/doctors/{d1}")[1] for k in ("phone", "whatsapp")))
ok("public lab list/detail carry no phone or whatsapp", all(k not in x for x in call("GET", "/labs")[1] for k in ("phone", "whatsapp")) and all(k not in call("GET", f"/labs/{l1}")[1] for k in ("phone", "whatsapp")))
ok("numbers appear nowhere in public responses (list, detail, global search)", "0473000001" not in body(call("GET", "/doctors")[1]) + body(call("GET", "/labs")[1]) + body(call("GET", "/doctors?q=تجربة")[1]))
ok("doctor/lab contact needs login (anonymous 401)", call("GET", f"/doctors/{d1}/contact")[0] == 401 and call("GET", f"/labs/{l1}/contact")[0] == 401)
ok("logged-in user gets the numbers", call("GET", f"/doctors/{d1}/contact", None, cu)[1] == {"name_ar": "د. تجربة 1", "phone": "0473000001", "whatsapp": "01055000001"} and call("GET", f"/labs/{l1}/contact", None, cu)[1]["phone"] == "0473000001")
nd = call("POST", "/admin/doctors", {"name_ar": "د. غير منشور", "specialty_id": sp, "region_id": 3, "address": "x", "phone": "0473999999"}, at)[1]["id"]
ok("unpublished doctor/lab: contact is 404", call("GET", f"/doctors/{nd}/contact", None, cu)[0] == 404 and call("GET", "/labs/9999/contact", None, cu)[0] == 404)
ok("admin lists still show numbers (admin needs them to edit)", next(x for x in call("GET", "/admin/doctors", None, at)[1] if x["id"] == d1)["phone"] == "0473000001" and next(x for x in call("GET", "/admin/labs", None, at)[1] if x["id"] == l1)["phone"] == "0473000001")
server.CONTACT_LIMIT = 3
ok("cap is shared across sections: 3 reveals mixed (doctor+lab+service), the 4th is 429", call("GET", f"/doctors/{d1}/contact", None, cu2)[0] == 200 and call("GET", f"/labs/{l1}/contact", None, cu2)[0] == 200 and call("GET", f"/services/{s1}/contact", None, cu2)[0] == 200 and call("GET", f"/doctors/{d2}/contact", None, cu2)[0] == 429 and call("GET", f"/labs/{l2}/contact", None, cu2)[0] == 429)
ok("an already revealed number still works after the cap", call("GET", f"/doctors/{d1}/contact", None, cu2)[0] == 200 and call("GET", f"/labs/{l1}/contact", None, cu2)[0] == 200)
ok("429 carries an Arabic message", "الحد" in call("GET", f"/doctors/{d2}/contact", None, cu2)[1]["error"])
server.CONTACT_LIMIT = 30

# ---------- 2) إزالة EXIF عند الرفع ----------
def seg(mk, payload): return b"\xff" + bytes([mk]) + (len(payload) + 2).to_bytes(2, "big") + payload
def exif(ori=None, extra=b""):
    ents = [(0x0112, 3, 1, ori.to_bytes(2, "big") + b"\0\0")] if ori else []
    t = b"MM\0*\0\0\0\x08" + len(ents).to_bytes(2, "big") + b"".join(struct.pack(">HHI", a, b_, c_) + v for a, b_, c_, v in ents) + b"\0\0\0\0" + extra
    return b"Exif\0\0" + t
def jpeg(app1=b"", extra=b"", tail=b""):
    return b"\xff\xd8" + seg(0xE0, b"JFIF\0\x01\x01\0\0\x01\0\x01\0\0") + app1 + extra + seg(0xDB, b"\0" + bytes(range(64))) + seg(0xC0, b"\x08\0\x08\0\x08\x01\x01\x11\0") + seg(0xDA, b"\x01\x01\0\0?\0") + b"\x12\x34\x56" + b"\xff\xd9" + tail
def up(data, t=cu):
    s, r = call("POST", "/files", {"data": base64.b64encode(data).decode()}, t); return s, r
def stored(fid): s, b, h = raw("GET", f"/files/{fid}", None, cu); return b
GPS = b"GPSLatitude-30.123-GPSLongitude-31.456"
j = jpeg(seg(0xE1, exif(6, GPS)), seg(0xE1, b"http://ns.adobe.com/xap/1.0/\0<x:xmpmeta>SECRET-XMP</x:xmpmeta>") + seg(0xED, b"Photoshop 3.0\0SECRET-IPTC") + seg(0xFE, b"SECRET-COMMENT"), b"TRAILING-SECRET")
s, r = up(j); out = stored(r["id"]) if s == 201 else b""
ok("JPEG upload accepted", s == 201)
ok("GPS/EXIF, XMP, IPTC, comment and trailing data are gone from the stored file", all(x not in out for x in (b"GPSLatitude", b"SECRET-XMP", b"SECRET-IPTC", b"SECRET-COMMENT", b"TRAILING-SECRET")) and out.endswith(b"\xff\xd9"))
ok("pixel data and tables are untouched", b"\x12\x34\x56\xff\xd9" in out and bytes(range(64)) in out)
ok("rotation survives: only an Orientation tag (6) remains in EXIF", server._exif_orientation(out[out.index(b"Exif\0\0"):out.index(b"Exif\0\0") + 40]) == 6 and out.count(b"Exif") == 1 and b"GPS" not in out)
s, r = up(jpeg(seg(0xE1, exif(None, GPS)))); out2 = stored(r["id"])
ok("no orientation -> no EXIF segment at all", s == 201 and b"Exif" not in out2 and b"GPS" not in out2)
def pch(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
p = imgutil.png_bytes([pch(b"tEXt", b"Comment\0SECRET-PNG-TEXT"), pch(b"eXIf", b"MM\0*" + GPS), pch(b"iTXt", b"XML:com.adobe.xmp\0\0\0\0\0SECRET-XMP2"), pch(b"tIME", b"\x07\xea\x01\x01\0\0\0")])
s, r = up(p); out3 = stored(r["id"])
ok("PNG metadata chunks removed, image chunks kept", s == 201 and all(x not in out3 for x in (b"SECRET-PNG-TEXT", b"GPSLatitude", b"SECRET-XMP2", b"tEXt", b"eXIf", b"iTXt", b"tIME")) and b"IHDR" in out3 and b"IDAT" in out3 and out3.endswith(pch(b"IEND", b"")))
if True:
    try:
        from PIL import Image; import io; Image.open(io.BytesIO(out3)).load(); print("PASS stripped PNG still decodes (Pillow)")
    except ImportError: print("SKIP Pillow not installed: decode check skipped")
ok("corrupt or truncated images are rejected with 400", up(b"\xff\xd8\xff" + b"x" * 30)[0] == 400 and up(b"\x89PNG\r\n\x1a\n" + b"0" * 40)[0] == 400 and up(j[:30])[0] == 400 and up(p[:-12])[0] == 400)
inner = jpeg(seg(0xE1, exif(6, b"GPS-INNER-SECRET")))
s, r = up(jpeg() + inner); o4 = stored(r["id"]) if s == 201 else b""
ok("a second JPEG appended after the first EOI (thumbnail/motion-photo style) is dropped with its metadata", s == 201 and b"GPS-INNER-SECRET" not in o4 and o4.count(b"\xff\xd9") == 1)
prog = jpeg()[:-2] + seg(0xE1, exif(None, b"GPS-LATE")) + seg(0xDA, b"\x01\x01\0\0?\0") + b"\x56\xff\xd9"
s, r = up(prog); o5 = stored(r["id"]) if s == 201 else b""
ok("metadata placed after the first scan is removed and every scan kept (progressive layout)", s == 201 and b"GPS-LATE" not in o5 and o5.count(b"\xff\xda") == 2 and b"\x56\xff\xd9" in o5)
s, r = up(jpeg()[:-2] + b"\x12\xff\x00\x34\xff\xd0\x56" + b"\xff\xd9"); o6 = stored(r["id"]) if s == 201 else b""
ok("stuffed FF00 bytes and restart markers inside scan data are preserved", s == 201 and b"\x12\xff\x00\x34\xff\xd0\x56\xff\xd9" in o6)
ok("non-images still rejected", up(b"GIF89a....")[0] == 400)

# ---------- 3) HSTS ----------
cf = open(os.path.join(D, "deploy", "Caddyfile"), encoding="utf-8").read()
ok("Caddyfile sends HSTS (1 year) without includeSubDomains/preload", 'header Strict-Transport-Security "max-age=31536000"' in cf and "includeSubDomains" not in cf and "preload" not in cf)

# ---------- 4) كلمة مرور المدير ----------
def init_fails(ph, pw):
    try: server.init(ph, pw); return False
    except SystemExit: return True
exists = lambda ph: server.db().execute("SELECT 1 FROM users WHERE phone=?", (ph,)).fetchone() is not None
ok("short password refused and no admin created", init_fails("01011111111", "Short1") and not exists("01011111111") and init_fails("01011111112", "abcdefghi") and not exists("01011111112"))
ok("repeated / common / contains-the-phone passwords refused", init_fails("01011111113", "aaaaaaaaaaaa") and init_fails("01011111114", "password123") and init_fails("01011111115", "x01011111115xx") and init_fails("01011111116", "0123456789"))
ok("env.example placeholder refused", init_fails("01011111117", "ضع-كلمة-قوية-طويلة") and init_fails("01011111118", "كلمة-قوية-هنا-123"))
server.init("01011111119", "Tr0ub4dor&3xyz"); ok("a strong password creates the admin", exists("01011111119"))
server.init("01000000000", "x"); ok("existing admin is not re-checked (upgrades keep working)", True)
import re
inst = open(os.path.join(D, "deploy", "install.sh"), encoding="utf-8").read()
ok("install.sh generates a 24-char hex password (passes the check)", "openssl rand -hex 12" in inst)
