# اختبار مستندات المندوب وفق الواجهة الحالية: التقديم من courier.html المستقلة، وحفظ المستندات عبر API، ومراجعتها من الإدارة.
# لا يفرض وجود نموذج قديم داخل تبويب حساب العميل. قاعدة مؤقتة معزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, subprocess, sqlite3

os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from testutil import apply_docs
from http.server import ThreadingHTTPServer

server.init("01000000000", "AdminPass123")
PORT = 8782
BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.H).serve_forever, daemon=True).start()
time.sleep(.3)

ROOT = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(ROOT, "test_ui_page_harness.js")
COURIER_HTML = os.path.join(ROOT, "static", "courier.html")

def call(method, path, data=None, token=None):
    req = urllib.request.Request(
        BASE + "/api" + path,
        json.dumps(data).encode() if data is not None else None,
        {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})},
        method=method,
    )
    try:
        response = urllib.request.urlopen(req)
        return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())

def ok(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise SystemExit(1)

def user(phone, name):
    call("POST", "/register", {"phone": phone, "name": name, "password": "password1"})
    return call("POST", "/login", {"phone": phone, "password": "password1"})[1]["token"]

def admin_ui(token, steps):
    result = subprocess.run(
        ["node", HARNESS, "admin", BASE, token, json.dumps(steps)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        print(result.stderr[:600])
    return json.loads(result.stdout)

def rows(sql, *args):
    connection = sqlite3.connect(os.environ["LAQINO_DB"])
    try:
        return connection.execute(sql, args).fetchall()
    finally:
        connection.close()

admin = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
applicant = user("01044444444", "متقدم")

# الواجهة الحالية: نموذج الانضمام موجود في لوحة المندوب، وليس في تبويب حساب العميل.
with open(COURIER_HTML, encoding="utf-8") as source_file:
    courier_html = source_file.read()
ok("courier panel owns the current application form", 'function applyView(' in courier_html and 'id="x_f1"' in courier_html and 'id="x_f2"' in courier_html)
ok("front/back ID photos are required and selfie is optional", "id_front_file_id" in courier_html and "id_back_file_id" in courier_html and "selfie_file_id" in courier_html)
ok("application uses current region selector and /couriers/apply endpoint", "rgLevel(null,0)" in courier_html and "'/couriers/apply'" in courier_html)

# لا يوجد طلب قبل التقديم، ثم ينشأ طلب pending بمستندين من خلال المسار الحالي.
status, response = call("GET", "/courier/status", token=applicant)
ok("new applicant is not treated as an existing courier", status == 404 and "لا يوجد طلب انضمام" in str(response))
status, response = apply_docs(call, applicant)
ok("current application API accepts front and back documents", status in (200, 201) and response.get("ok") is not False)
ok("application is pending and exactly two required documents are stored", rows("SELECT status FROM couriers") == [("pending",)] and rows("SELECT COUNT(*) FROM courier_documents")[0][0] == 2)

# مراجعة الإدارة تعرض مستندات الطلب الحالي.
admin_view = admin_ui(admin, [{"js": "tab='couriers';shell()", "wait": 800, "snap": "v"}])
ok("admin page lists both labeled ID documents", "البطاقة — الوجه" in admin_view["v"] and "البطاقة — الظهر" in admin_view["v"] and admin_view["v"].count('id="cd') == 2 and not admin_view["errs"])

# الطلبات القديمة التي لا تحتوي مستندات تظل ظاهرة كحالة تحتاج استكمالًا.
legacy = user("01055555555", "قديم")
legacy_id = call("GET", "/me", token=legacy)[1]["id"]
connection = sqlite3.connect(os.environ["LAQINO_DB"])
connection.execute(
    "INSERT INTO couriers(user_id,region_id,created_at) VALUES(?,?,?)",
    (legacy_id, 3, int(time.time())),
)
connection.commit()
connection.close()
admin_view = admin_ui(admin, [{"js": "tab='couriers';shell()", "wait": 800, "snap": "v"}])
ok("legacy request without documents is flagged", "لا توجد مستندات مرفوعة" in admin_view["v"])
print("ALL PASSED")
