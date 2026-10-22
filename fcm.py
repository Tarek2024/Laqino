# لاقينو — إشعارات تطبيق أندرويد عبر FCM (المرحلة 8، الدفعة الأولى: جهة السيرفر).
# وحدة مستقلة بنمط notif.py/chat.py/svc.py: لا تستورد server.py، وتُربط به بأسطر قليلة. مقفولة افتراضيًا.
#   مستخدم مسجّل:  POST /api/fcm/register   {token, platform?}   (يحفظ توكن الجهاز؛ 503 إن كان FCM غير مفعّل على السيرفر)
#                  POST /api/fcm/unregister {token}                (يحذف توكن الجهاز إن كان له)
#   إدارة/موظف:   GET  /api/admin/fcm/status                      (enabled + عدد الأجهزة المسجلة؛ أرقام فقط)
# التفعيل: ضع مسار ملف حساب الخدمة (Service Account JSON من Firebase) في LAQINO_FCM_SERVICE_ACCOUNT. بدونه لا شيء يُرسل ولا شبكة تُلمس.
# الرسالة عامة بلا بيانات (مثل Web Push الحالي): عنوان ثابت ونص عام حسب النوع (order/chat) فقط، لا أسماء ولا أرقام ولا عناوين.
# إضافة فقط: جدول fcm_tokens. مفتاح التوقيع RS256 عبر مكتبة cryptography (نفسها المستخدمة لمفاتيح VAPID).
import base64, json, os, re, sys, threading, time, urllib.error, urllib.parse, urllib.request

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
MAX_PER_USER = 5
TOKEN_RE = re.compile(r"^[A-Za-z0-9_:\-\.]{20,4096}$")
TEXTS = {"order": "طلب توصيل جديد في منطقتك", "chat": "عندك رسالة جديدة"}
TITLE = "لاقينو"
CHANNEL = "laqino_alerts"   # يجب أن تنشئه نسخة الأندرويد (native.js يفعل ذلك)

SCHEMA = """
CREATE TABLE IF NOT EXISTS fcm_tokens(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 platform TEXT NOT NULL DEFAULT 'android', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_fcm_tokens_user ON fcm_tokens(user_id);
"""

_lock = threading.Lock()
_cache = {"sa_path": None, "sa": None, "tok": None, "exp": 0}


def install(c):
    c.executescript(SCHEMA)


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _allow_any():
    return os.environ.get("LAQINO_FCM_ALLOW_ANY") == "1"   # للاختبارات فقط: يسمح بخادم وهمي محلي


def _host_ok(url, suffix):
    try:
        p = urllib.parse.urlparse(url)
        return p.scheme == "https" and (p.hostname == suffix or (p.hostname or "").endswith("." + suffix))
    except Exception:
        return False


def service_account():
    """يقرأ ملف حساب الخدمة (مع تخزين مؤقت). None إن لم يُضبط أو كان غير صالح."""
    path = os.environ.get("LAQINO_FCM_SERVICE_ACCOUNT", "").strip()
    if not path:
        return None
    try:
        mt = os.path.getmtime(path)
        if _cache["sa_path"] == (path, mt):
            return _cache["sa"]
        with open(path, encoding="utf8") as f:
            sa = json.load(f)
        if not all(isinstance(sa.get(k), str) and sa.get(k) for k in ("client_email", "private_key", "project_id")):
            raise ValueError("missing fields")
        sa.setdefault("token_uri", "https://oauth2.googleapis.com/token")
        if not _allow_any() and not _host_ok(sa["token_uri"], "googleapis.com"):
            raise ValueError("token_uri not allowed")
        _cache.update(sa_path=(path, mt), sa=sa, tok=None, exp=0)
        return sa
    except Exception as e:
        sys.stderr.write("fcm: service account unusable: %r\n" % (e,))
        return None


def enabled():
    return service_account() is not None


def make_jwt(sa, now=None):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    now = int(now or time.time())
    head = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64u(json.dumps({"iss": sa["client_email"], "scope": SCOPE, "aud": sa["token_uri"], "iat": now, "exp": now + 3600}, separators=(",", ":")).encode())
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    sig = key.sign((head + "." + body).encode(), padding.PKCS1v15(), hashes.SHA256())
    return head + "." + body + "." + _b64u(sig)


def access_token(sa):
    with _lock:
        if _cache["tok"] and _cache["exp"] > time.time() + 120:
            return _cache["tok"]
    data = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": make_jwt(sa)}).encode()
    rq = urllib.request.Request(sa["token_uri"], data, {"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(rq, timeout=10) as r:
        j = json.loads(r.read())
    with _lock:
        _cache["tok"] = j["access_token"]; _cache["exp"] = time.time() + int(j.get("expires_in", 3600))
    return j["access_token"]


def _base():
    b = os.environ.get("LAQINO_FCM_BASE", "") if _allow_any() else ""
    return b.rstrip("/") or "https://fcm.googleapis.com"


def build_message(token, kind, ttl):
    kind = kind if kind in TEXTS else "order"
    return {"message": {"token": token, "notification": {"title": TITLE, "body": TEXTS[kind]}, "data": {"kind": kind},
                        "android": {"priority": "HIGH", "ttl": "%ds" % max(30, min(int(ttl), 3600)), "collapse_key": kind,
                                    "notification": {"tag": kind, "channel_id": CHANNEL}}}}


def send_one(sa, token, kind, ttl):
    """يرجع (status, dead): dead=True إن كان التوكن لم يعد صالحًا (يُحذف). لا يرمي."""
    try:
        at = access_token(sa)
        rq = urllib.request.Request("%s/v1/projects/%s/messages:send" % (_base(), urllib.parse.quote(sa["project_id"], safe="")),
                                    json.dumps(build_message(token, kind, ttl)).encode(),
                                    {"Authorization": "Bearer " + at, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(rq, timeout=10) as r:
            return r.status, False
    except urllib.error.HTTPError as e:
        dead = e.code == 404
        try:
            if "UNREGISTERED" in e.read().decode("utf8", "ignore"):
                dead = True
        except Exception:
            pass
        if e.code == 401:
            with _lock:
                _cache["tok"] = None   # توكن الوصول انتهى/رُفض: يُجدَّد في المرة القادمة
        return e.code, dead
    except Exception as e:
        sys.stderr.write("fcm send error: %r\n" % (e,))
        return 0, False


def has_tokens(c, uid):
    return bool(c.execute("SELECT 1 FROM fcm_tokens WHERE user_id=?", (uid,)).fetchone())


def send(c, uids, ttl=300, kind="order"):
    """يوقظ أجهزة أندرويد المستخدمين. يرجع عدد الرسائل المقبولة. لا يرمي أبدًا، ولا يفعل شيئًا إن كان FCM غير مفعّل."""
    try:
        sa = service_account()
        if not sa:
            return 0
        n = 0
        for uid in uids:
            for r in c.execute("SELECT token FROM fcm_tokens WHERE user_id=?", (uid,)).fetchall():
                st, dead = send_one(sa, r["token"], kind, ttl)
                if dead:
                    c.execute("DELETE FROM fcm_tokens WHERE token=?", (r["token"],)); c.commit()
                elif 200 <= st < 300:
                    n += 1
        return n
    except Exception as e:
        sys.stderr.write("fcm send failed: %r\n" % (e,))
        return 0


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب."""
    if path not in ("/api/fcm/register", "/api/fcm/unregister", "/api/admin/fcm/status"):
        return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    if not u:
        return err(401, "سجّل الدخول أولًا")
    now = int(time.time())
    if path == "/api/admin/fcm/status":
        if u["role"] not in ("admin", "staff"):
            return err(403, "غير مسموح")
        if method != "GET":
            return err(404, "غير موجود")
        h.send(200, {"enabled": enabled(), "devices": c.execute("SELECT COUNT(*) FROM fcm_tokens").fetchone()[0]}); return True
    if method != "POST":
        return err(404, "غير موجود")
    b = h.body()
    tok = str(b.get("token", "")).strip()
    if not TOKEN_RE.match(tok):
        return err(400, "توكن الجهاز غير صالح")
    if path == "/api/fcm/unregister":
        c.execute("DELETE FROM fcm_tokens WHERE token=? AND user_id=?", (tok, u["id"])); c.commit()
        h.send(200, {"ok": True}); return True
    if not enabled():
        return err(503, "إشعارات التطبيق غير مفعّلة على السيرفر")
    c.execute("INSERT INTO fcm_tokens(token,user_id,platform,created_at,updated_at) VALUES(?,?,'android',?,?) "
              "ON CONFLICT(token) DO UPDATE SET user_id=excluded.user_id, updated_at=excluded.updated_at", (tok, u["id"], now, now))
    # لا نرفض التسجيل عند تجاوز الحد (إعادة تثبيت التطبيق تولّد توكنات جديدة): نُبقي الأحدث 5 فقط
    c.execute("DELETE FROM fcm_tokens WHERE user_id=? AND token NOT IN (SELECT token FROM fcm_tokens WHERE user_id=? ORDER BY updated_at DESC, rowid DESC LIMIT ?)",
              (u["id"], u["id"], MAX_PER_USER))
    c.commit()
    h.send(200, {"ok": True}); return True
