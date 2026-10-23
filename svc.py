# لاقينو — الخدمات المحلية وطلبات العملاء (المرحلة 5، وُسِّعت في الخطوة 2).
# وحدة مستقلة بنمط chat.py/rx.py: لا تستورد server.py، وتُربط بسطرين.
# الفكرة: العميل يطلب خدمة (نوع + منطقة + وصف + عنوان/وقت/ميزانية/صور اختيارية)، الإدارة ومقدمو الخدمة المطابقون يتابعونه، والعميل يرى الحالة.
#   عميل:  POST /api/service-requests {type_id, region_id, description, address?, preferred_at?, budget_min?, budget_max?}
#          GET  /api/service-requests            (طلباتي)      GET /api/service-requests/<id>   (تفاصيل + سجل الحالات)
#          POST /api/service-requests/<id>/cancel
#          POST /api/service-requests/<id>/images {data:base64}  (حتى 3 صور JPG/PNG، تُنظَّف من EXIF/GPS)
#          GET  /api/service-requests/<id>/images/<file_id>      (صاحب الطلب / الإدارة / المقدم الذي قبل الطلب فقط؛ private/no-store)
#          POST /api/service-requests/<id>/images/<file_id>/delete   (صاحب الطلب، والطلب لم ينتهِ)
#   إدارة: GET  /api/admin/service-requests?status=<أي حالة من الـ11>
#          POST /api/admin/service-requests/<id> {status, note?}   (متابعة: in_progress | done | cancelled)
# الحالات الـ11 (STATUSES) وخريطة الانتقالات (NEXT) مصدر الحقيقة الوحيد:
#   open (جديد) → awaiting_quotes (بانتظار العروض) → quotes_received (وصلت عروض) → provider_selected (اختار العميل مقدمًا)
#   → accepted (قبله المقدم) → on_the_way (في الطريق) → in_progress (قيد التنفيذ) → done (تم)
#   + cancelled (ملغي، ومعه cancelled_by) + expired (انتهى بلا استجابة) + disputed (نزاع).
#   الخطوة 2 تفعّل: open/accepted/on_the_way/in_progress/done/cancelled/expired. الحالات awaiting_quotes/quotes_received/provider_selected
#   جاهزة في الخريطة وتُفعَّل مع عروض الأسعار (الخطوة 3)، و disputed مع النزاعات (الخطوة 6).
# المرحلة 6 — مقدم الخدمة كحساب (إضافة فقط، بلا تغيير في أدوار users):
#   service_providers.owner_user_id يربط مقدمًا بحساب؛ الإدارة تربطه/تفكّه عبر /api/admin/service-owners.
#   مقدم:  GET  /api/my/service-jobs                  (مقدماتي + الطلبات المفتوحة المطابقة + طلباتي المقبولة؛ بلا أرقام/عنوان/صور قبل القبول)
#          POST /api/my/service-jobs/<id>/accept      (حجز ذري: مفتوح -> accepted، يكشف اسم/رقم/عنوان العميل وصوره لقابله فقط)
#          POST /api/my/service-jobs/<id>/progress {status: on_the_way|in_progress|done}   (تقدّم العمل)
#          POST /api/my/service-jobs/<id>/release     (إعادة الطلب للمفتوح)   POST .../<id>/done (إنهاء، يبقى للتوافق)
#   إدارة: GET/POST /api/admin/service-owners {provider_id, phone|null}
# الخطوة 5 — التقييم: تعليق اختياري (≤300 حرف، بلا أرقام هاتف)، تعديل وحذف العميل لتقييمه، بلاغ مقدم الخدمة على تقييم مسيء واعتماد الإدارة (إخفاء/رفض/استرجاع)،
#   والصفحة العامة GET /api/services/<id>/ratings (بلا هوية المقيِّم). التقييم المخفي لا يدخل المتوسط ولا العدد ولا القائمة العلنية.
# المرحلة 6ب — تقييم المقدم: POST /api/service-requests/<id>/rate {stars:1..5} من صاحب طلب منتهٍ (done) قبله مقدم؛ مرة واحدة لكل طلب.
#   المتوسط والعدد (rating_avg, rating_count) علنيان في بطاقة المقدم؛ لا نص حر ولا هوية المقيِّم. المقدم لا يقبل طلب حسابه نفسه (منع تقييم ذاتي).
# الخصوصية: لا تُرجع مسارات العميل أي رقم هاتف أبدًا؛ رقم صاحب الطلب يراه admin/staff ومقدمه القابل فقط.
#   العنوان والصور كذلك: لا يراها مقدم قبل القبول. الميزانية والوقت المفضّل يراهما المقدمون المطابقون (للتقدير).
# الخطوة 3 — عروض أسعار الخدمات (إضافة فقط؛ المسار القديم «مقدم يقبل مباشرة» يعمل كما هو لطلب في حالة open):
#   عميل:  POST /api/service-requests/<id>/request-quotes {provider_ids?:[..]}   (open -> awaiting_quotes، يوزّع الطلب على مقدمين مطابقين لهم حسابات، حتى MAX_INVITES)
#          GET  /api/service-requests/<id>/quotes                                (العروض المعتمدة من الإدارة فقط؛ بلا أرقام)
#          POST /api/service-requests/<id>/select {quote_id}                     (quotes -> provider_selected؛ لا يرى المقدم بيانات العميل بعد)
#          POST /api/service-requests/<id>/dispute {reason}                      (accepted/on_the_way/in_progress أو done خلال DISPUTE_WINDOW_DAYS -> disputed)
#   مقدم:  POST /api/my/service-jobs/<id>/quote {price, note?}                   (المدعو فقط؛ عرض واحد لكل مقدم؛ التعديل يعيده للاعتماد)
#          POST /api/my/service-jobs/<id>/withdraw                                (سحب العرض قبل الاختيار)
#          POST /api/my/service-jobs/<id>/accept                                  (للمقدم المختار: provider_selected -> accepted ويكشف بيانات العميل)
#          POST /api/my/service-jobs/<id>/release                                 (للمختار: اعتذار فيرجع الطلب للعروض)    POST .../<id>/dispute {reason}
#   إدارة: GET /api/admin/service-quotes?status=pending   POST /api/admin/service-quotes/<id> {action: approve|reject, note?}   (العميل لا يرى عرضًا قبل الاعتماد)
#          حسم النزاع: POST /api/admin/service-requests/<id> {status: done|cancelled, note (إلزامي)} على طلب disputed.
#   مهلة تأكيد المقدم المختار: SELECT_TTL_DAYS (كسولة كالانتهاء) ثم يرجع الطلب لحالة العروض والعرض يصير withdrawn.
#   لا يُقبل في نص العرض رقم هاتف (8 أرقام متتالية فأكثر) حتى لا يتجاوز المنصة.
# الانتهاء التلقائي: طلب بلا مقدم (حالات ما قبل القبول) يتجاوز EXPIRE_DAYS يوم يصير expired عند أول طلب API لاحق.
import re, time, json, os, secrets

STATUSES = ("open", "awaiting_quotes", "quotes_received", "provider_selected", "accepted", "on_the_way", "in_progress", "done", "cancelled", "disputed", "expired")
OPEN_SET = ("open", "awaiting_quotes", "quotes_received")        # لا مقدم محجوز بعد، ويمكن لمقدم مطابق قبوله
ASSIGNED = ("accepted", "on_the_way", "in_progress")             # عند مقدم
LIVE = OPEN_SET + ("provider_selected",) + ASSIGNED              # طلب حيّ: يُحسب في الحد ويقبل الإلغاء
ADMIN_SET = ("in_progress", "done", "cancelled")
PROVIDER_PROGRESS = ("on_the_way", "in_progress", "done")
NEXT = {  # من -> الحالات المسموح الانتقال إليها
    "open": ("awaiting_quotes", "accepted", "in_progress", "done", "cancelled", "expired"),
    "awaiting_quotes": ("quotes_received", "provider_selected", "accepted", "in_progress", "cancelled", "expired"),
    "quotes_received": ("awaiting_quotes", "provider_selected", "accepted", "in_progress", "cancelled", "expired"),
    "provider_selected": ("awaiting_quotes", "quotes_received", "accepted", "cancelled", "expired"),
    "accepted": ("on_the_way", "in_progress", "done", "open", "cancelled", "disputed"),
    "on_the_way": ("in_progress", "done", "open", "cancelled", "disputed"),
    "in_progress": ("done", "open", "cancelled", "disputed"),
    "done": ("disputed",), "cancelled": (), "expired": (), "disputed": ("done", "cancelled"),
}
LABELS = {"open": "جديد", "awaiting_quotes": "بانتظار العروض", "quotes_received": "وصلت عروض", "provider_selected": "تم اختيار مقدم", "accepted": "قبله المقدم",
          "on_the_way": "المقدم في الطريق", "in_progress": "قيد التنفيذ", "done": "تم", "cancelled": "ملغي", "disputed": "نزاع", "expired": "انتهى بلا استجابة"}
MIN_DESC, MAX_DESC, MAX_NOTE = 10, 500, 300
MIN_ADDR, MAX_ADDR = 5, 200
MAX_BUDGET = 1_000_000
MAX_AHEAD_DAYS, EXPIRE_DAYS = 90, 14
MAX_IMAGES, MAX_IMAGES_DAY = 3, 30
MAX_ACTIVE, MAX_PER_DAY = 3, 10
MAX_INVITES, MAX_QUOTE_NOTE, MIN_REASON, MAX_REASON = 10, 300, 10, 300
SELECT_TTL_DAYS, DISPUTE_WINDOW_DAYS = 2, 7
QUOTE_STATUSES = ("pending", "approved", "rejected", "selected", "not_selected", "withdrawn")
QLABELS = {"pending": "بانتظار اعتماد الإدارة", "approved": "معتمد", "rejected": "مرفوض", "selected": "تم اختيارك", "not_selected": "لم يُختر", "withdrawn": "مسحوب"}
MAX_JOBS = 10  # أقصى طلبات عند حساب مقدم واحد في آن واحد
UPLOADS = None  # server.py يضبطه: مجلد الرفع نفسه المستخدم لباقي الصور


def _in(t): return "(" + ",".join("'%s'" % x for x in t) + ")"  # ثوابت داخلية فقط، لا مدخلات مستخدم


_STATUS_SQL = ",".join("'%s'" % s for s in STATUSES)
_COLS = ("user_id INTEGER NOT NULL REFERENCES users(id),\n"
         " type_id INTEGER NOT NULL REFERENCES service_types(id), region_id INTEGER NOT NULL REFERENCES regions(id),\n"
         " description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN(%s)),\n"
         " admin_note TEXT, handled_by INTEGER REFERENCES users(id), created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,\n"
         " provider_id INTEGER REFERENCES service_providers(id), accepted_at INTEGER,\n"
         " address TEXT, preferred_at INTEGER, budget_min INTEGER, budget_max INTEGER, cancelled_by TEXT,\n"
         " dispute_reason TEXT, disputed_by TEXT, disputed_at INTEGER" % _STATUS_SQL)
_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_service_requests_user ON service_requests(user_id, id);
CREATE INDEX IF NOT EXISTS ix_service_requests_status ON service_requests(status, id);
CREATE INDEX IF NOT EXISTS ix_service_requests_provider ON service_requests(provider_id, status);
"""
SCHEMA = """
CREATE TABLE IF NOT EXISTS service_requests(id INTEGER PRIMARY KEY,
 %s);
CREATE TABLE IF NOT EXISTS service_ratings(id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL UNIQUE REFERENCES service_requests(id),
 provider_id INTEGER NOT NULL REFERENCES service_providers(id), user_id INTEGER NOT NULL REFERENCES users(id),
 stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5), created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_service_ratings_provider ON service_ratings(provider_id);
CREATE TABLE IF NOT EXISTS service_rating_reports(id INTEGER PRIMARY KEY, rating_id INTEGER NOT NULL, request_id INTEGER NOT NULL, provider_id INTEGER NOT NULL,
 reporter_id INTEGER NOT NULL REFERENCES users(id), reason TEXT NOT NULL, snap_stars INTEGER NOT NULL, snap_comment TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','upheld','dismissed')), admin_note TEXT, decided_by INTEGER REFERENCES users(id), decided_at INTEGER,
 created_at INTEGER NOT NULL, UNIQUE(rating_id, reporter_id));
CREATE INDEX IF NOT EXISTS ix_service_rating_reports_status ON service_rating_reports(status, id);
CREATE TABLE IF NOT EXISTS service_request_images(id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES service_requests(id),
 file_id INTEGER NOT NULL UNIQUE REFERENCES files(id), created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_service_request_images_req ON service_request_images(request_id);
CREATE TABLE IF NOT EXISTS service_request_events(id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES service_requests(id),
 from_status TEXT, to_status TEXT NOT NULL, actor_id INTEGER, actor_role TEXT NOT NULL, note TEXT, at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_service_request_events_req ON service_request_events(request_id, id);
CREATE TABLE IF NOT EXISTS service_request_invites(id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES service_requests(id),
 provider_id INTEGER NOT NULL REFERENCES service_providers(id), created_at INTEGER NOT NULL, UNIQUE(request_id, provider_id));
CREATE INDEX IF NOT EXISTS ix_service_request_invites_prov ON service_request_invites(provider_id, request_id);
CREATE TABLE IF NOT EXISTS service_quotes(id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES service_requests(id),
 provider_id INTEGER NOT NULL REFERENCES service_providers(id), price INTEGER NOT NULL CHECK(price BETWEEN 1 AND 1000000), note TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN(%s)), admin_note TEXT, reviewed_by INTEGER REFERENCES users(id), reviewed_at INTEGER,
 selected_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(request_id, provider_id));
CREATE INDEX IF NOT EXISTS ix_service_quotes_req ON service_quotes(request_id, status);
CREATE INDEX IF NOT EXISTS ix_service_quotes_status ON service_quotes(status, id);
""" % (_COLS, ",".join("'%s'" % x for x in QUOTE_STATUSES))


def _rebuild(c):
    """قاعدة قديمة (4 حالات): قيد CHECK لا يُعدَّل في SQLite، فنعيد بناء الجدول مرة واحدة بالخطوات الرسمية (12 خطوة).
    تُنسخ كل الصفوف كما هي (الحالات القديمة الأربع صالحة في القائمة الجديدة). آمنة لإعادة التشغيل: تُتخطى إن كان الجدول محدَّثًا."""
    sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='service_requests'").fetchone()[0]
    if "on_the_way" in sql: return
    c.commit(); c.execute("PRAGMA foreign_keys=OFF")
    try:
        old = [r[1] for r in c.execute("PRAGMA table_info(service_requests)")]
        new = ["id", "user_id", "type_id", "region_id", "description", "status", "admin_note", "handled_by", "created_at", "updated_at", "provider_id", "accepted_at",
               "address", "preferred_at", "budget_min", "budget_max", "cancelled_by", "dispute_reason", "disputed_by", "disputed_at"]
        keep = ",".join(x for x in new if x in old)
        c.executescript("BEGIN;\nCREATE TABLE service_requests_new(id INTEGER PRIMARY KEY,\n %s);\n"
                        "INSERT INTO service_requests_new(%s) SELECT %s FROM service_requests;\n"
                        "DROP TABLE service_requests;\nALTER TABLE service_requests_new RENAME TO service_requests;\nCOMMIT;" % (_COLS, keep, keep))
        bad = c.execute("PRAGMA foreign_key_check").fetchall()
        if bad: raise RuntimeError("foreign_key_check failed after service_requests rebuild: %r" % (bad[:3],))
    except Exception:
        try: c.rollback()
        except Exception: pass
        raise
    finally:
        c.execute("PRAGMA foreign_keys=ON")


def install(c):
    """متكرر بأمان. بعد إنشاء service_types/regions/users/files."""
    c.executescript(SCHEMA)
    if "owner_user_id" not in [r[1] for r in c.execute("PRAGMA table_info(service_providers)")]:
        c.execute("ALTER TABLE service_providers ADD COLUMN owner_user_id INTEGER REFERENCES users(id)")
    have = [r[1] for r in c.execute("PRAGMA table_info(service_requests)")]  # قواعد أقدم من المرحلة 6 تفتقد هذين العمودين قبل إعادة البناء
    for col, ddl in (("provider_id", "ALTER TABLE service_requests ADD COLUMN provider_id INTEGER REFERENCES service_providers(id)"),
                     ("accepted_at", "ALTER TABLE service_requests ADD COLUMN accepted_at INTEGER")):
        if col not in have: c.execute(ddl)
    c.commit()
    _rebuild(c)
    have = [r[1] for r in c.execute("PRAGMA table_info(service_requests)")]  # قاعدة الخطوة 2: لا إعادة بناء، فنضيف أعمدة النزاع بـALTER
    for col, ty in (("dispute_reason", "TEXT"), ("disputed_by", "TEXT"), ("disputed_at", "INTEGER")):
        if col not in have: c.execute("ALTER TABLE service_requests ADD COLUMN %s %s" % (col, ty))
    have = [r[1] for r in c.execute("PRAGMA table_info(service_ratings)")]  # الخطوة 5: أعمدة بـALTER فقط (بلا إعادة بناء)
    for col, ty in (("comment", "TEXT"), ("updated_at", "INTEGER"), ("hidden", "INTEGER NOT NULL DEFAULT 0")):
        if col not in have: c.execute("ALTER TABLE service_ratings ADD COLUMN %s %s" % (col, ty))
    c.executescript(_INDEXES)
    c.execute("CREATE INDEX IF NOT EXISTS ix_service_providers_owner ON service_providers(owner_user_id)")
    c.commit()


def _riyad_scope_ids(c, region_id):
    """نطاق البحث الموحد لمركز الرياض فقط؛ المناطق الأخرى تحتفظ بسلوك المطابقة القديم."""
    r = c.execute("SELECT slug,level FROM regions WHERE id=? AND is_active=1", (region_id,)).fetchone()
    if not r or r["slug"] != "eg-kfs-riyad" or r["level"] != "markaz": return [region_id]
    return [x[0] for x in c.execute("WITH RECURSIVE tree(id) AS (SELECT ? UNION SELECT g.id FROM regions g JOIN tree t ON g.parent_id=t.id) SELECT id FROM tree", (region_id,)).fetchall()]

def _provider_request_regions(c, provider_region_id):
    """المناطق التي يمكن أن تطابق طلب مقدم الخدمة: منطقته، ومركز الرياض إذا كان تابعًا له."""
    ids = [provider_region_id]; rid = provider_region_id; seen = set()
    while rid and rid not in seen:
        seen.add(rid)
        r = c.execute("SELECT parent_id,level,slug FROM regions WHERE id=?", (rid,)).fetchone()
        if not r: break
        if r["level"] == "markaz" and r["slug"] == "eg-kfs-riyad":
            if rid not in ids: ids.append(rid)
            break
        rid = r["parent_id"]
    return ids

def _matching(c, type_id, region_id):
    """عدد/أسماء مقدمي الخدمة المنشورين المطابقين لنطاق مركز الرياض أو المنطقة المحددة. بلا أي رقم."""
    ids = _riyad_scope_ids(c, region_id)
    return c.execute("SELECT p.id,p.name_ar FROM service_providers p JOIN regions rg ON rg.id=p.region_id "
                     "WHERE p.type_id=? AND p.region_id IN (%s) AND p.is_published=1 AND rg.is_active=1 ORDER BY p.name_ar LIMIT 20" % ",".join("?" * len(ids)), (type_id, *ids)).fetchall()


def _notify(c, user_id, kind, title, body, link, ref_id):
    """أي خطأ هنا لا يُفشل العملية الأساسية."""
    try:
        c.execute("INSERT INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (user_id, kind, title, body, link, "service_request", ref_id, int(time.time())))
    except Exception as e:
        import sys; sys.stderr.write("svc notify failed: %r\n" % (e,))


def _audit(c, actor, action, target, detail):
    try:
        c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (actor, action, str(target), json.dumps(detail, ensure_ascii=False), int(time.time())))
    except Exception as e:
        import sys; sys.stderr.write("svc audit failed: %r\n" % (e,))


def _event(c, rid, frm, to, actor, role, now, note=None):
    c.execute("INSERT INTO service_request_events(request_id,from_status,to_status,actor_id,actor_role,note,at) VALUES(?,?,?,?,?,?,?)", (rid, frm, to, actor, role, note or None, now))


def _can(frm, to): return to in NEXT.get(frm, ())


def _expire(c, now):
    """طلبات لم يقبلها أحد (قبل القبول) وتجاوزت EXPIRE_DAYS يوم تصير expired + إشعار لصاحبها."""
    rows = c.execute("SELECT id,user_id,status,type_id FROM service_requests WHERE status IN%s AND provider_id IS NULL AND created_at<?" % _in(OPEN_SET + ("provider_selected",)), (now - EXPIRE_DAYS * 86400,)).fetchall()
    for r in rows:
        cur = c.execute("UPDATE service_requests SET status='expired',updated_at=? WHERE id=? AND status=? AND provider_id IS NULL", (now, r["id"], r["status"]))
        if cur.rowcount != 1: continue
        _event(c, r["id"], r["status"], "expired", None, "system", now)
        tn = c.execute("SELECT name_ar FROM service_types WHERE id=?", (r["type_id"],)).fetchone()
        _notify(c, r["user_id"], "service_request.expired", "انتهى طلب الخدمة بدون استجابة", (tn[0] if tn else "")[:120], "svc", r["id"])
    if rows: c.commit()
    return len(rows)


def rating_of(c, pid):
    """متوسط وعدد تقييمات مقدم (للعرض العلني). بلا تقييمات: avg=None."""
    r = c.execute("SELECT COUNT(*),AVG(stars) FROM service_ratings WHERE provider_id=? AND hidden=0", (pid,)).fetchone()
    return {"rating_avg": round(r[1], 1) if r[0] else None, "rating_count": r[0]}


PAGE = 20


def public_ratings(c, pid, q):
    """الصفحة العلنية لتقييمات مقدم منشور: توزيع النجوم + آخر التقييمات الظاهرة (نجوم وتعليق وتاريخ فقط، بلا أي هوية). الاستدعاء من server.py بعد التحقق من النشر."""
    try: off = max(0, int((q.get("offset", ["0"])[0] or "0")))
    except (TypeError, ValueError): off = 0
    dist = {str(i): 0 for i in range(1, 6)}
    for st, n in c.execute("SELECT stars,COUNT(*) FROM service_ratings WHERE provider_id=? AND hidden=0 GROUP BY stars", (pid,)): dist[str(st)] = n
    rows = c.execute("SELECT stars,comment,created_at,updated_at FROM service_ratings WHERE provider_id=? AND hidden=0 ORDER BY id DESC LIMIT ? OFFSET ?", (pid, PAGE + 1, off)).fetchall()
    return {**rating_of(c, pid), "distribution": dist, "offset": off, "has_more": len(rows) > PAGE,
            "items": [{"stars": r["stars"], "comment": r["comment"] or "", "at": r["updated_at"] or r["created_at"], "edited": bool(r["updated_at"])} for r in rows[:PAGE]]}


def _comment(d):
    """تعليق اختياري: ≤300 حرف وبلا أرقام هاتف. يرجع (نص أو None، خطأ أو None)."""
    t = d.get("comment")
    if t is None: return None, None
    t = str(t).strip()
    if len(t) > 300: return None, "التعليق أطول من 300 حرف"
    if _phone_in(t): return None, "ممنوع كتابة أرقام تليفون في التعليق"
    return t, None


def _eligible(c, type_id, region_id, exclude_user=None):
    """مقدمون يصلحون لعروض الأسعار داخل النطاق الموحد، مع الحفاظ على مطابقة المناطق الأخرى."""
    ids = _riyad_scope_ids(c, region_id)
    return c.execute("SELECT p.id,p.name_ar,p.owner_user_id FROM service_providers p JOIN regions rg ON rg.id=p.region_id WHERE p.type_id=? AND p.region_id IN (%s) AND p.is_published=1 AND rg.is_active=1 " % ",".join("?" * len(ids)) +
                     "AND p.owner_user_id IS NOT NULL AND p.owner_user_id<>? ORDER BY p.name_ar LIMIT 50", (type_id, *ids, exclude_user or 0)).fetchall()


def _phone_in(text):
    """نص يحوي 8 أرقام متتالية فأكثر (بعد توحيد الأرقام العربية وإزالة الفواصل) يُعدّ رقم هاتف."""
    t = str(text or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    return bool(re.search(r"\d{8,}", re.sub(r"(?<=\d)[\s.\-_/]+(?=\d)", "", t)))


def _sync_quote_status(c, rid, now, actor=None, role="system"):
    """يضبط awaiting_quotes <-> quotes_received حسب وجود عرض معتمد. لا يفعل شيئًا لغير هاتين الحالتين."""
    r = c.execute("SELECT status FROM service_requests WHERE id=?", (rid,)).fetchone()
    if not r or r["status"] not in ("awaiting_quotes", "quotes_received"): return r["status"] if r else None
    n = c.execute("SELECT COUNT(*) FROM service_quotes WHERE request_id=? AND status='approved'", (rid,)).fetchone()[0]
    new = "quotes_received" if n else "awaiting_quotes"
    if new != r["status"]:
        c.execute("UPDATE service_requests SET status=?,updated_at=? WHERE id=? AND status=?", (new, now, rid, r["status"]))
        _event(c, rid, r["status"], new, actor, role, now)
    return new


def _unselect(c, rid, now, actor, role, note):
    """المقدم المختار لم يؤكد (اعتذر/انتهت المهلة/فُكّ ربطه): الطلب يرجع لمرحلة العروض والعرض المختار يصير withdrawn، وباقي العروض كما هي."""
    cur = c.execute("UPDATE service_requests SET status='awaiting_quotes',provider_id=NULL,updated_at=? WHERE id=? AND status='provider_selected'", (now, rid))
    if cur.rowcount != 1: return False
    c.execute("UPDATE service_quotes SET status='withdrawn',updated_at=? WHERE request_id=? AND status='selected'", (now, rid))
    _event(c, rid, "provider_selected", "awaiting_quotes", actor, role, now, note)
    _sync_quote_status(c, rid, now, actor, role)
    return True


def _lapse_selected(c, now):
    """مقدم اختاره العميل ولم يؤكد خلال SELECT_TTL_DAYS: يرجع الطلب لمرحلة العروض ويُبلَّغ العميل."""
    rows = c.execute("SELECT s.id,s.user_id,s.type_id FROM service_requests s JOIN service_quotes q ON q.request_id=s.id AND q.status='selected' "
                     "WHERE s.status='provider_selected' AND q.selected_at<?", (now - SELECT_TTL_DAYS * 86400,)).fetchall()
    n = 0
    for r in rows:
        if _unselect(c, r["id"], now, None, "system", "انتهت مهلة تأكيد المقدم"):
            n += 1
            tn = c.execute("SELECT name_ar FROM service_types WHERE id=?", (r["type_id"],)).fetchone()
            _notify(c, r["user_id"], "service_request.select_lapsed", "المقدم لم يؤكد، اختار عرضًا آخر", (tn[0] if tn else "")[:120], "svc", r["id"])
    if n: c.commit()
    return n


def _myquote(c, rid, pid):
    q = c.execute("SELECT id,price,note,status,admin_note FROM service_quotes WHERE request_id=? AND provider_id=?", (rid, pid)).fetchone()
    return {"id": q["id"], "price": q["price"], "note": q["note"], "status": q["status"], "status_label": QLABELS[q["status"]], "admin_note": q["admin_note"]} if q else None


def _admins(c):
    return [a["id"] for a in c.execute("SELECT id FROM users WHERE role IN('admin','staff')").fetchall()]


def _owner_of(c, pid):
    x = c.execute("SELECT owner_user_id FROM service_providers WHERE id=?", (pid,)).fetchone() if pid else None
    return x[0] if x else None


def _can_dispute(r, now):
    if r["disputed_at"]: return False
    return r["status"] in ASSIGNED or (r["status"] == "done" and r["updated_at"] >= now - DISPUTE_WINDOW_DAYS * 86400)


def _raise_dispute(c, h, r, u, role, now, err):
    """يفتح نزاعًا على طلب: عميل (صاحب الطلب) أو مقدم (الحاصل عليه). السبب إلزامي. يُبلَّغ الإدارة والطرف الآخر."""
    reason = str((h.body() or {}).get("reason") or "").strip()
    if len(reason) < MIN_REASON: return err(400, "اكتب سبب النزاع (%d حروف على الأقل)" % MIN_REASON)
    if len(reason) > MAX_REASON: return err(400, "السبب أطول من %d حرفًا" % MAX_REASON)
    if r["disputed_at"]: return err(409, "سبق فتح نزاع على هذا الطلب")
    if not _can_dispute(r, now): return err(409, "لا يمكن فتح نزاع على الطلب في حالته الحالية")
    cur = c.execute("UPDATE service_requests SET status='disputed',dispute_reason=?,disputed_by=?,disputed_at=?,updated_at=? WHERE id=? AND status=? AND disputed_at IS NULL",
                    (reason, role, now, now, r["id"], r["status"]))
    if cur.rowcount != 1: c.rollback(); return err(409, "تغيّرت حالة الطلب، حاول تاني")
    _event(c, r["id"], r["status"], "disputed", u["id"], role, now, reason)
    _audit(c, u["id"], "service_request.dispute", r["id"], {"by": role})
    tn = c.execute("SELECT name_ar FROM service_types WHERE id=?", (r["type_id"],)).fetchone()
    tname = (tn[0] if tn else "")[:120]
    for a in _admins(c): _notify(c, a, "service_request.disputed", "نزاع جديد على طلب خدمة", tname, "admin:svcreq", r["id"])
    if role == "customer":
        ow = _owner_of(c, r["provider_id"])
        if ow: _notify(c, ow, "service_request.disputed", "العميل فتح نزاعًا على الطلب", tname, "svcjob", r["id"])
    else:
        _notify(c, r["user_id"], "service_request.disputed", "مقدم الخدمة فتح نزاعًا على الطلب", tname, "svc", r["id"])
    c.commit(); h.send(200, {"ok": True, "status": "disputed"}); return True


def _pname(c, pid):
    if not pid: return None
    x = c.execute("SELECT name_ar FROM service_providers WHERE id=?", (pid,)).fetchone()
    return x[0] if x else None


def _rated(c, rid):
    x = c.execute("SELECT stars FROM service_ratings WHERE request_id=?", (rid,)).fetchone()
    return x[0] if x else None


def _my_rating(c, rid):
    x = c.execute("SELECT stars,comment,hidden FROM service_ratings WHERE request_id=?", (rid,)).fetchone()
    return {"stars": x[0], "comment": x[1] or "", "hidden": bool(x[2])} if x else None


def _images(c, rid):
    return [x[0] for x in c.execute("SELECT file_id FROM service_request_images WHERE request_id=? ORDER BY id", (rid,)).fetchall()]


def _mine(r, c):
    prov = _matching(c, r["type_id"], r["region_id"]) if r["status"] in LIVE else []
    now = int(time.time())
    qp = [{"id": p["id"], "name_ar": p["name_ar"], **rating_of(c, p["id"])} for p in _eligible(c, r["type_id"], r["region_id"], r["user_id"])] if r["status"] == "open" else []
    return {"invited_count": c.execute("SELECT COUNT(*) FROM service_request_invites WHERE request_id=?", (r["id"],)).fetchone()[0],
            "quotes_count": c.execute("SELECT COUNT(*) FROM service_quotes WHERE request_id=? AND status IN('approved','selected')", (r["id"],)).fetchone()[0],
            "quote_providers": qp, "can_request_quotes": bool(qp), "can_dispute": _can_dispute(r, now), "disputed_by": r["disputed_by"],
            "dispute_reason": r["dispute_reason"] if r["disputed_by"] == "customer" else None,
            **{"id": r["id"], "type_id": r["type_id"], "type": r["type"], "region_id": r["region_id"], "region_name": r["region_name"],
            "description": r["description"], "status": r["status"], "status_label": LABELS.get(r["status"], r["status"]), "admin_note": r["admin_note"], "created_at": r["created_at"],
            "updated_at": r["updated_at"], "address": r["address"], "preferred_at": r["preferred_at"], "budget_min": r["budget_min"], "budget_max": r["budget_max"],
            "cancelled_by": r["cancelled_by"], "images": _images(c, r["id"]),
            "accepted_by": _pname(c, r["provider_id"]) if r["status"] != "provider_selected" else None, "selected_provider": _pname(c, r["provider_id"]) if r["status"] == "provider_selected" else None, "rated": _rated(c, r["id"]), "rating": _my_rating(c, r["id"]), "can_rate": r["status"] == "done" and bool(r["provider_id"]) and _rated(c, r["id"]) is None,
            "providers": [{"id": p["id"], "name_ar": p["name_ar"]} for p in prov]}}


SEL = ("SELECT s.*,t.name_ar type,rg.name_ar region_name FROM service_requests s JOIN service_types t ON t.id=s.type_id "
       "JOIN regions rg ON rg.id=s.region_id")


def _opt_int(v, what, lo, hi):
    """رقم اختياري: None/"" -> None، وإلا عدد صحيح موجب ضمن الحدود. bool مرفوض."""
    if v is None or v == "": return None
    if isinstance(v, bool): raise ValueError(what)
    try: n = int(float(v)) if not isinstance(v, int) else v
    except (TypeError, ValueError, OverflowError): raise ValueError(what)
    if not lo <= n <= hi: raise ValueError(what)
    return n


def _validate_extra(d, now):
    """يتحقق من العنوان/الوقت/الميزانية الاختيارية. يرجع (address, preferred_at, bmin, bmax) أو يرفع ValueError برسالة عربية."""
    addr = str(d.get("address") or "").strip()
    if addr and len(addr) < MIN_ADDR: raise ValueError("العنوان قصير (%d حروف على الأقل) أو اتركه فارغًا" % MIN_ADDR)
    if len(addr) > MAX_ADDR: raise ValueError("العنوان أطول من %d حرفًا" % MAX_ADDR)
    try: pa = _opt_int(d.get("preferred_at") or None, "الموعد غير صالح", 1, 4_102_444_800)
    except ValueError: raise ValueError("الموعد غير صالح")
    if pa is not None:
        if pa < now - 300: raise ValueError("الموعد المطلوب في الماضي")
        if pa > now + MAX_AHEAD_DAYS * 86400: raise ValueError("الموعد بعيد (الحد %d يومًا)" % MAX_AHEAD_DAYS)
    try:
        bmin = _opt_int(d.get("budget_min"), "الميزانية غير صالحة", 1, MAX_BUDGET); bmax = _opt_int(d.get("budget_max"), "الميزانية غير صالحة", 1, MAX_BUDGET)
    except ValueError: raise ValueError("الميزانية غير صالحة (رقم من 1 إلى %d)" % MAX_BUDGET)
    if bmin is not None and bmax is not None and bmin > bmax: raise ValueError("أقل ميزانية أكبر من أعلاها")
    return addr or None, pa, bmin, bmax


def _can_see_images(c, u, r):
    if u["role"] in ("admin", "staff") or r["user_id"] == u["id"]: return True
    return bool(r["provider_id"]) and r["status"] in ASSIGNED + ("done", "disputed") and \
        c.execute("SELECT 1 FROM service_providers WHERE id=? AND owner_user_id=?", (r["provider_id"], u["id"])).fetchone() is not None


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. الأخطاء تُرجَع مباشرة عبر h.send."""
    if not path.startswith(("/api/service-requests", "/api/admin/service-requests", "/api/admin/service-owners", "/api/admin/service-quotes", "/api/my/service-jobs", "/api/my/service-ratings", "/api/admin/service-rating-reports")): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    now = int(time.time())
    if not u: return err(401, "سجّل الدخول أولًا")
    _expire(c, now); _lapse_selected(c, now)

    # ---------- الخطوة 5: تقييمات المقدم (للمالك) وبلاغات التقييمات (للإدارة) ----------
    if path == "/api/my/service-ratings" and method == "GET":
        rows = c.execute("SELECT g.id,g.provider_id,p.name_ar provider_name,g.stars,g.comment,g.created_at,g.updated_at,g.hidden,t.name_ar type,"
                         "(SELECT status FROM service_rating_reports x WHERE x.rating_id=g.id AND x.reporter_id=?) my_report "
                         "FROM service_ratings g JOIN service_providers p ON p.id=g.provider_id JOIN service_requests s ON s.id=g.request_id JOIN service_types t ON t.id=s.type_id "
                         "WHERE p.owner_user_id=? ORDER BY g.id DESC LIMIT 50", (u["id"], u["id"])).fetchall()
        h.send(200, [{"id": r["id"], "provider_id": r["provider_id"], "provider_name": r["provider_name"], "type": r["type"], "stars": r["stars"], "comment": r["comment"] or "",
                      "at": r["updated_at"] or r["created_at"], "hidden": bool(r["hidden"]), "my_report": r["my_report"]} for r in rows]); return True
    m = re.fullmatch(r"/api/my/service-ratings/(\d+)/report", path)
    if m and method == "POST":
        g = c.execute("SELECT g.*,p.owner_user_id,p.name_ar FROM service_ratings g JOIN service_providers p ON p.id=g.provider_id WHERE g.id=?", (int(m[1]),)).fetchone()
        if not g or g["owner_user_id"] != u["id"]: return err(404, "غير موجود")
        if g["hidden"]: return err(409, "التقييم مخفي بالفعل")
        reason = str((h.body() or {}).get("reason", "")).strip()
        if not 5 <= len(reason) <= 300: return err(400, "اكتب سبب البلاغ (من 5 إلى 300 حرف)")
        try: c.execute("INSERT INTO service_rating_reports(rating_id,request_id,provider_id,reporter_id,reason,snap_stars,snap_comment,created_at) VALUES(?,?,?,?,?,?,?,?)",
                       (g["id"], g["request_id"], g["provider_id"], u["id"], reason, g["stars"], g["comment"], now))
        except Exception: c.rollback(); return err(409, "بلّغت عن هذا التقييم من قبل")
        _audit(c, u["id"], "service_rating.report", g["id"], {"provider_id": g["provider_id"]})
        for a in _admins(c): _notify(c, a, "service_rating.reported", "بلاغ على تقييم خدمة", g["name_ar"][:120], "admin:svcreq", g["request_id"])
        c.commit(); h.send(201, {"ok": True}); return True
    if path == "/api/admin/service-rating-reports" and method == "GET":
        if u["role"] not in ("admin", "staff"): return err(403, "غير مسموح")
        st = (q.get("status", ["pending"])[0] or "pending").strip()
        if st not in ("pending", "upheld", "dismissed"): return err(400, "حالة غير صالحة")
        rows = c.execute("SELECT x.*,p.name_ar provider_name,rp.name reporter_name,g.stars cur_stars,g.comment cur_comment,g.hidden cur_hidden,cu.name customer_name "
                         "FROM service_rating_reports x JOIN service_providers p ON p.id=x.provider_id JOIN users rp ON rp.id=x.reporter_id "
                         "LEFT JOIN service_ratings g ON g.id=x.rating_id LEFT JOIN users cu ON cu.id=g.user_id WHERE x.status=? ORDER BY x.id DESC LIMIT 100", (st,)).fetchall()
        h.send(200, [{"id": r["id"], "rating_id": r["rating_id"], "request_id": r["request_id"], "provider_name": r["provider_name"], "reporter_name": r["reporter_name"], "customer_name": r["customer_name"],
                      "reason": r["reason"], "stars": r["snap_stars"], "comment": r["snap_comment"] or "", "current_stars": r["cur_stars"], "current_comment": r["cur_comment"] or "",
                      "rating_exists": r["cur_stars"] is not None, "hidden": bool(r["cur_hidden"]), "status": r["status"], "admin_note": r["admin_note"], "created_at": r["created_at"]} for r in rows]); return True
    m = re.fullmatch(r"/api/admin/service-rating-reports/(\d+)", path)
    if m and method == "POST":
        if u["role"] not in ("admin", "staff"): return err(403, "غير مسموح")
        x = c.execute("SELECT * FROM service_rating_reports WHERE id=?", (int(m[1]),)).fetchone()
        if not x: return err(404, "غير موجود")
        d = h.body() or {}; act = str(d.get("action", "")); note = str(d.get("note", "")).strip()
        if act not in ("hide", "dismiss", "restore"): return err(400, "إجراء غير صالح")
        if not 5 <= len(note) <= 300: return err(400, "اكتب سببًا من 5 إلى 300 حرف (يصل للطرفين)")
        g = c.execute("SELECT id,user_id FROM service_ratings WHERE id=?", (x["rating_id"],)).fetchone()
        ow = _owner_of(c, x["provider_id"])
        if act == "restore":
            if x["status"] != "upheld" or not g: return err(409, "لا يمكن استرجاع هذا التقييم")
            c.execute("UPDATE service_ratings SET hidden=0 WHERE id=?", (g["id"],))
            c.execute("UPDATE service_rating_reports SET status='dismissed',admin_note=?,decided_by=?,decided_at=? WHERE rating_id=? AND status='upheld'", (note, u["id"], now, g["id"]))
        else:
            if x["status"] != "pending": return err(409, "تم البت في هذا البلاغ")
            if act == "hide":
                if not g: return err(409, "العميل حذف التقييم")
                c.execute("UPDATE service_ratings SET hidden=1 WHERE id=?", (g["id"],))
                c.execute("UPDATE service_rating_reports SET status='upheld',admin_note=?,decided_by=?,decided_at=? WHERE rating_id=? AND status='pending'", (note, u["id"], now, g["id"]))
            else:
                c.execute("UPDATE service_rating_reports SET status='dismissed',admin_note=?,decided_by=?,decided_at=? WHERE id=?", (note, u["id"], now, x["id"]))
        _audit(c, u["id"], "service_rating." + act, x["rating_id"], {"report_id": x["id"], "note": note})
        title = {"hide": "تم إخفاء التقييم بعد مراجعة البلاغ", "dismiss": "تم رفض بلاغك على التقييم", "restore": "تم استرجاع التقييم"}[act]
        if ow: _notify(c, ow, "service_rating." + act, title, note[:120], "svcjob", x["request_id"])
        if g and act in ("hide", "restore"): _notify(c, g["user_id"], "service_rating." + act, "تم إخفاء تقييمك بسبب مخالفته" if act == "hide" else "تم استرجاع تقييمك", note[:120], "svc", x["request_id"])
        c.commit(); h.send(200, {"ok": True}); return True

    # ---------- إدارة: ربط مقدم بحساب ----------
    if path == "/api/admin/service-owners":
        if u["role"] not in ("admin", "staff"): return err(403, "غير مسموح")
        if method == "GET":
            rows = c.execute("SELECT p.id,p.name_ar,p.is_published,p.owner_user_id,o.name owner_name,o.phone owner_phone FROM service_providers p "
                             "LEFT JOIN users o ON o.id=p.owner_user_id ORDER BY p.id DESC LIMIT 200").fetchall()
            h.send(200, [{**dict(r), **rating_of(c, r["id"])} for r in rows]); return True
        if method == "POST":
            if u["role"] != "admin": return err(403, "للمدير فقط")
            d = h.body() or {}
            try: pid = int(d.get("provider_id"))
            except (TypeError, ValueError): return err(400, "مقدم الخدمة غير صالح")
            p = c.execute("SELECT id,name_ar,owner_user_id FROM service_providers WHERE id=?", (pid,)).fetchone()
            if not p: return err(404, "مقدم الخدمة غير موجود")
            ph = str(d.get("phone") or "").strip()
            if not ph:  # فكّ الربط: أي طلب عنده (قبِله ولم ينتهِ) يرجع مفتوحًا
                for r in c.execute("SELECT id FROM service_requests WHERE provider_id=? AND status='provider_selected'", (pid,)).fetchall():
                    _unselect(c, r["id"], now, u["id"], "admin", "فك ربط المقدم")  # مختار لم يؤكد بعد: يرجع لمرحلة العروض
                for r in c.execute("SELECT id,status FROM service_requests WHERE provider_id=? AND status IN%s" % _in(ASSIGNED), (pid,)).fetchall():
                    _event(c, r["id"], r["status"], "open", u["id"], "admin", now, "فك ربط المقدم")
                c.execute("UPDATE service_providers SET owner_user_id=NULL WHERE id=?", (pid,))
                c.execute("UPDATE service_requests SET status='open',provider_id=NULL,accepted_at=NULL,updated_at=? WHERE provider_id=? AND status IN%s" % _in(ASSIGNED), (now, pid))
                _audit(c, u["id"], "service_owner.unlink", pid, {}); c.commit(); h.send(200, {"ok": True, "owner_user_id": None}); return True
            ow = c.execute("SELECT id,role FROM users WHERE phone=?", (ph,)).fetchone()
            if not ow: return err(404, "لا يوجد حساب بهذا الرقم")
            if ow["role"] in ("admin", "staff"): return err(400, "لا يُربط حساب إدارة بمقدم خدمة")
            c.execute("UPDATE service_providers SET owner_user_id=? WHERE id=?", (ow["id"], pid))
            _audit(c, u["id"], "service_owner.link", pid, {"user_id": ow["id"]})
            _notify(c, ow["id"], "service_provider.linked", "تم ربط حسابك بمقدم خدمة", p["name_ar"][:120], "svcjob", pid)
            c.commit(); h.send(200, {"ok": True, "owner_user_id": ow["id"]}); return True
        return err(404, "غير موجود")

    # ---------- مقدم الخدمة ----------
    if path.startswith("/api/my/service-jobs"):
        mine_p = c.execute("SELECT p.id,p.name_ar,p.type_id,p.region_id,p.is_published,t.name_ar type FROM service_providers p JOIN service_types t ON t.id=p.type_id WHERE p.owner_user_id=?", (u["id"],)).fetchall()
        if not mine_p:
            if path == "/api/my/service-jobs" and method == "GET": h.send(200, {"providers": [], "jobs": []}); return True  # 200 لا 403: الواجهة تسأل كل حساب بلا ضوضاء أخطاء
            return err(403, "حسابك غير مربوط بمقدم خدمة")
        live = [p for p in mine_p if p["is_published"]]
        if path == "/api/my/service-jobs" and method == "GET":
            jobs = []
            for p in live:
                request_regions = _provider_request_regions(c, p["region_id"])
                for r in c.execute(SEL + " WHERE s.provider_id IS NULL AND s.type_id=? AND s.region_id IN (%s) AND (s.status='open' OR (s.status IN('awaiting_quotes','quotes_received') AND " % ",".join("?" * len(request_regions)) +
                                   "EXISTS(SELECT 1 FROM service_request_invites i WHERE i.request_id=s.id AND i.provider_id=?))) ORDER BY s.id DESC LIMIT 50", (p["type_id"], *request_regions, p["id"])).fetchall():
                    jobs.append({"quote_mode": r["status"] != "open", "my_quote": _myquote(c, r["id"], p["id"]) if r["status"] != "open" else None, "id": r["id"], "type": r["type"], "region_name": r["region_name"], "description": r["description"], "status": r["status"], "status_label": LABELS[r["status"]],
                                 "created_at": r["created_at"], "preferred_at": r["preferred_at"], "budget_min": r["budget_min"], "budget_max": r["budget_max"],
                                 "image_count": len(_images(c, r["id"])), "provider_id": p["id"], "mine": False})  # بلا عنوان/صور/أرقام قبل القبول
            for r in c.execute(SEL + " WHERE s.provider_id IN(%s) AND s.status='provider_selected' ORDER BY s.id DESC LIMIT 50" % ",".join("?" * len(mine_p)), [p["id"] for p in mine_p]).fetchall():
                jobs.append({"id": r["id"], "type": r["type"], "region_name": r["region_name"], "description": r["description"], "status": r["status"], "status_label": LABELS[r["status"]],
                             "created_at": r["created_at"], "preferred_at": r["preferred_at"], "budget_min": r["budget_min"], "budget_max": r["budget_max"], "image_count": len(_images(c, r["id"])),
                             "provider_id": r["provider_id"], "mine": True, "selected": True, "quote_mode": True, "my_quote": _myquote(c, r["id"], r["provider_id"])})  # اختاره العميل: بلا عنوان/صور/أرقام حتى يؤكد
            for r in c.execute(SEL + " WHERE s.provider_id IN(%s) AND s.status IN%s ORDER BY s.id DESC LIMIT 50" % (",".join("?" * len(mine_p)), _in(ASSIGNED + ("done", "disputed"))), [p["id"] for p in mine_p]).fetchall():
                us = c.execute("SELECT name,phone FROM users WHERE id=?", (r["user_id"],)).fetchone()
                jobs.append({"id": r["id"], "type": r["type"], "region_name": r["region_name"], "description": r["description"], "status": r["status"], "status_label": LABELS[r["status"]],
                             "created_at": r["created_at"], "preferred_at": r["preferred_at"], "budget_min": r["budget_min"], "budget_max": r["budget_max"],
                             "address": r["address"], "images": _images(c, r["id"]), "provider_id": r["provider_id"], "mine": True,
                             "customer_name": us["name"] if us else "", "customer_phone": us["phone"] if us else "", "can_dispute": _can_dispute(r, now), "disputed_by": r["disputed_by"],
                             "dispute_reason": r["dispute_reason"] if r["disputed_by"] == "provider" else None})
            seen = set(); out = [j for j in jobs if not (j["id"] in seen or seen.add(j["id"]))]
            h.send(200, {"providers": [{"id": p["id"], "name_ar": p["name_ar"], "type": p["type"], "is_published": p["is_published"], **rating_of(c, p["id"])} for p in mine_p], "jobs": out}); return True
        m = re.fullmatch(r"/api/my/service-jobs/(\d+)/(accept|release|done|progress|quote|withdraw|dispute)", path)
        if not m or method != "POST": return err(404, "غير موجود")
        jid, act = int(m[1]), m[2]
        r = c.execute(SEL + " WHERE s.id=?", (jid,)).fetchone()
        if not r: return err(404, "غير موجود")
        own = {p["id"] for p in mine_p}
        if act == "quote":
            if r["user_id"] == u["id"]: return err(403, "لا يمكنك تقديم عرض على طلب صادر من حسابك")
            if r["status"] not in ("awaiting_quotes", "quotes_received"): return err(409, "الطلب لا يستقبل عروض أسعار الآن")
            inv = c.execute("SELECT i.provider_id FROM service_request_invites i JOIN service_providers p ON p.id=i.provider_id WHERE i.request_id=? AND p.owner_user_id=? AND p.is_published=1", (jid, u["id"])).fetchone()
            if not inv: return err(403, "لم تُدعَ لتقديم عرض على هذا الطلب")
            d = h.body() or {}
            try: price = _opt_int(d.get("price"), "السعر غير صالح", 1, MAX_BUDGET)
            except ValueError: return err(400, "السعر غير صالح (رقم من 1 إلى %d)" % MAX_BUDGET)
            if price is None: return err(400, "اكتب سعر العرض")
            note = str(d.get("note") or "").strip()
            if len(note) > MAX_QUOTE_NOTE: return err(400, "الملاحظة أطول من %d حرفًا" % MAX_QUOTE_NOTE)
            if _phone_in(note): return err(400, "ممنوع كتابة أرقام هاتف في العرض، التواصل يتم بعد اختيار العميل لك")
            pid = inv["provider_id"]
            ex = c.execute("SELECT id,status FROM service_quotes WHERE request_id=? AND provider_id=?", (jid, pid)).fetchone()
            if ex and ex["status"] in ("selected", "not_selected"): return err(409, "لا يمكن تعديل هذا العرض")
            if ex:
                c.execute("UPDATE service_quotes SET price=?,note=?,status='pending',admin_note=NULL,reviewed_by=NULL,reviewed_at=NULL,updated_at=? WHERE id=?", (price, note or None, now, ex["id"]))
                qid, was = ex["id"], ex["status"]
            else:
                qid = c.execute("INSERT INTO service_quotes(request_id,provider_id,price,note,created_at,updated_at) VALUES(?,?,?,?,?,?)", (jid, pid, price, note or None, now, now)).lastrowid; was = None
            _sync_quote_status(c, jid, now, u["id"], "provider")
            _audit(c, u["id"], "service_quote.submit", qid, {"request_id": jid, "price": price})
            if was != "pending":
                for a in _admins(c): _notify(c, a, "service_quote.pending", "عرض سعر جديد بانتظار الاعتماد", (r["type"] + " — " + str(price) + " ج")[:120], "admin:svcreq", jid)
            c.commit(); h.send(200, {"ok": True, "quote": _myquote(c, jid, pid)}); return True
        if act == "withdraw":
            q = c.execute("SELECT q.id,q.status FROM service_quotes q WHERE q.request_id=? AND q.provider_id IN(%s)" % ",".join("?" * len(mine_p)), [jid] + [p["id"] for p in mine_p]).fetchone()
            if not q: return err(404, "لا يوجد عرض لك على هذا الطلب")
            if q["status"] not in ("pending", "approved") or r["status"] not in ("awaiting_quotes", "quotes_received"): return err(409, "لا يمكن سحب العرض في حالته الحالية")
            c.execute("UPDATE service_quotes SET status='withdrawn',updated_at=? WHERE id=?", (now, q["id"]))
            _sync_quote_status(c, jid, now, u["id"], "provider"); _audit(c, u["id"], "service_quote.withdraw", q["id"], {"request_id": jid})
            c.commit(); h.send(200, {"ok": True}); return True
        if act == "dispute":
            if r["provider_id"] not in own: return err(404, "غير موجود")
            return _raise_dispute(c, h, r, u, "provider", now, err)
        if act in ("accept", "release") and r["status"] == "provider_selected":
            if r["provider_id"] not in own: return err(409, "الطلب لم يعد متاحًا")
            q = c.execute("SELECT id FROM service_quotes WHERE request_id=? AND status='selected'", (jid,)).fetchone()
            if act == "release":
                if not _unselect(c, jid, now, u["id"], "provider", "اعتذر المقدم المختار"): c.rollback(); return err(409, "الطلب لم يعد متاحًا")
                _audit(c, u["id"], "service_quote.decline", q["id"] if q else 0, {"request_id": jid})
                _notify(c, r["user_id"], "service_request.select_declined", "المقدم اعتذر، اختار عرضًا آخر", r["type"][:120], "svc", jid)
                c.commit(); h.send(200, {"ok": True, "status": c.execute("SELECT status FROM service_requests WHERE id=?", (jid,)).fetchone()[0]}); return True
            if c.execute("SELECT COUNT(*) FROM service_requests WHERE provider_id IN(%s) AND status IN%s" % (",".join("?" * len(mine_p)), _in(ASSIGNED)), [p["id"] for p in mine_p]).fetchone()[0] >= MAX_JOBS:
                return err(429, "عندك %d طلبات قيد التنفيذ، أنهِ واحدًا أولًا" % MAX_JOBS)
            cur = c.execute("UPDATE service_requests SET status='accepted',accepted_at=?,updated_at=? WHERE id=? AND status='provider_selected' AND provider_id=?", (now, now, jid, r["provider_id"]))
            if cur.rowcount != 1: c.rollback(); return err(409, "الطلب لم يعد متاحًا")
            _event(c, jid, "provider_selected", "accepted", u["id"], "provider", now)
            others = c.execute("SELECT id,provider_id FROM service_quotes WHERE request_id=? AND status IN('pending','approved')", (jid,)).fetchall()
            c.execute("UPDATE service_quotes SET status='not_selected',updated_at=? WHERE request_id=? AND status IN('pending','approved')", (now, jid))
            for o in others:
                ow = _owner_of(c, o["provider_id"])
                if ow: _notify(c, ow, "service_quote.not_selected", "تم اختيار مقدم آخر للطلب", r["type"][:120], "svcjob", jid)
            _audit(c, u["id"], "service_request.accept", jid, {"provider_id": r["provider_id"], "via": "quote"})
            _notify(c, r["user_id"], "service_request.accepted", "المقدم أكّد قبول طلبك", (_pname(c, r["provider_id"]) + " — " + r["type"])[:120], "svc", jid)
            us = c.execute("SELECT name,phone FROM users WHERE id=?", (r["user_id"],)).fetchone()
            c.commit(); h.send(200, {"ok": True, "status": "accepted", "customer_name": us["name"] if us else "", "customer_phone": us["phone"] if us else "",
                                     "address": r["address"], "images": _images(c, jid)}); return True
        if act == "accept":
            if r["user_id"] == u["id"]: return err(403, "لا يمكنك قبول طلب صادر من حسابك")
            if r["status"] in ("awaiting_quotes", "quotes_received"): return err(409, "الطلب بنظام عروض الأسعار، قدّم عرضك بدل القبول المباشر")
            cand = [p for p in live if p["type_id"] == r["type_id"] and p["region_id"] in _riyad_scope_ids(c, r["region_id"])]
            if not cand: return err(403, "هذا الطلب لا يطابق نوع ومنطقة خدمتك المنشورة")
            if c.execute("SELECT COUNT(*) FROM service_requests WHERE provider_id IN(%s) AND status IN%s" % (",".join("?" * len(mine_p)), _in(ASSIGNED)), [p["id"] for p in mine_p]).fetchone()[0] >= MAX_JOBS:
                return err(429, "عندك %d طلبات قيد التنفيذ، أنهِ واحدًا أولًا" % MAX_JOBS)
            cur = c.execute("UPDATE service_requests SET status='accepted',provider_id=?,accepted_at=?,updated_at=? WHERE id=? AND status='open' AND provider_id IS NULL", (cand[0]["id"], now, now, jid))
            if cur.rowcount != 1: c.rollback(); return err(409, "الطلب لم يعد متاحًا")
            _event(c, jid, r["status"], "accepted", u["id"], "provider", now)
            _audit(c, u["id"], "service_request.accept", jid, {"provider_id": cand[0]["id"]})
            _notify(c, r["user_id"], "service_request.accepted", "مقدم خدمة قبل طلبك", (cand[0]["name_ar"] + " — " + r["type"])[:120], "svc", jid)
            us = c.execute("SELECT name,phone FROM users WHERE id=?", (r["user_id"],)).fetchone()
            c.commit(); h.send(200, {"ok": True, "status": "accepted", "customer_name": us["name"] if us else "", "customer_phone": us["phone"] if us else "",
                                     "address": r["address"], "images": _images(c, jid)}); return True
        if r["provider_id"] not in own: return err(404, "غير موجود")
        if r["status"] not in ASSIGNED: return err(409, "الطلب ليس عندك قيد التنفيذ")
        if act == "release":
            c.execute("UPDATE service_requests SET status='open',provider_id=NULL,accepted_at=NULL,updated_at=? WHERE id=? AND status IN%s" % _in(ASSIGNED), (now, jid))
            _event(c, jid, r["status"], "open", u["id"], "provider", now, "أعاد المقدم الطلب")
            _audit(c, u["id"], "service_request.release", jid, {})
            _notify(c, r["user_id"], "service_request.released", "عاد طلبك للانتظار", r["type"][:120], "svc", jid)
            c.commit(); h.send(200, {"ok": True, "status": "open"}); return True
        if act == "progress":
            to = (h.body() or {}).get("status")
            if to not in PROVIDER_PROGRESS: return err(400, "حالة غير صالحة")
        else: to = "done"
        if to == r["status"]: return err(409, "الطلب بهذه الحالة بالفعل")
        if not _can(r["status"], to): return err(409, "لا يمكن الانتقال من هذه الحالة")
        c.execute("UPDATE service_requests SET status=?,updated_at=? WHERE id=? AND status=?", (to, now, jid, r["status"]))
        _event(c, jid, r["status"], to, u["id"], "provider", now)
        _audit(c, u["id"], "service_request.provider_" + to, jid, {})
        title = {"on_the_way": "المقدم في الطريق إليك", "in_progress": "بدأ تنفيذ طلب الخدمة", "done": "تم إنجاز طلب الخدمة"}[to]
        _notify(c, r["user_id"], "service_request." + to, title, r["type"][:120], "svc", jid)
        c.commit(); h.send(200, {"ok": True, "status": to}); return True

    # ---------- إدارة ----------
    if path.startswith("/api/admin/"):
        if u["role"] not in ("admin", "staff"): return err(403, "غير مسموح")
        if path == "/api/admin/service-requests" and method == "GET":
            st = (q.get("status", [""])[0] or "").strip()
            if st and st not in STATUSES: return err(400, "حالة غير صالحة")
            rows = c.execute(SEL + " WHERE (?1='' OR s.status=?1) ORDER BY CASE WHEN s.status IN%s THEN 0 WHEN s.status IN%s THEN 1 ELSE 2 END, s.id DESC LIMIT 200" % (_in(OPEN_SET), _in(ASSIGNED + ("provider_selected",))), (st,)).fetchall()
            out = []
            for r in rows:
                us = c.execute("SELECT name,phone FROM users WHERE id=?", (r["user_id"],)).fetchone()
                d = _mine(r, c); d.update({"user_name": us["name"] if us else "", "user_phone": us["phone"] if us else "", "handled_by": r["handled_by"], "dispute_reason": r["dispute_reason"], "disputed_by": r["disputed_by"],
                                           "pending_quotes": c.execute("SELECT COUNT(*) FROM service_quotes WHERE request_id=? AND status='pending'", (r["id"],)).fetchone()[0]}); out.append(d)
            h.send(200, out); return True
        if path == "/api/admin/service-quotes" and method == "GET":
            st = (q.get("status", ["pending"])[0] or "pending").strip()
            if st not in QUOTE_STATUSES: return err(400, "حالة غير صالحة")
            rows = c.execute("SELECT q.*,p.name_ar provider_name,t.name_ar type,rg.name_ar region_name,s.description,s.status req_status,s.budget_min,s.budget_max FROM service_quotes q "
                             "JOIN service_providers p ON p.id=q.provider_id JOIN service_requests s ON s.id=q.request_id JOIN service_types t ON t.id=s.type_id JOIN regions rg ON rg.id=s.region_id "
                             "WHERE q.status=? AND (?<>'pending' OR s.status IN('awaiting_quotes','quotes_received')) ORDER BY q.id DESC LIMIT 200", (st, st)).fetchall()
            h.send(200, [{"id": r["id"], "request_id": r["request_id"], "provider_id": r["provider_id"], "provider_name": r["provider_name"], **rating_of(c, r["provider_id"]), "type": r["type"],
                          "region_name": r["region_name"], "description": r["description"], "request_status": r["req_status"], "budget_min": r["budget_min"], "budget_max": r["budget_max"],
                          "price": r["price"], "note": r["note"], "status": r["status"], "status_label": QLABELS[r["status"]], "admin_note": r["admin_note"], "created_at": r["created_at"]} for r in rows]); return True
        m = re.fullmatch(r"/api/admin/service-quotes/(\d+)", path)
        if m and method == "POST":
            qr = c.execute("SELECT q.*,s.status req_status,s.user_id cust,t.name_ar type FROM service_quotes q JOIN service_requests s ON s.id=q.request_id JOIN service_types t ON t.id=s.type_id WHERE q.id=?", (int(m[1]),)).fetchone()
            if not qr: return err(404, "غير موجود")
            d = h.body() or {}; act = d.get("action"); note = str(d.get("note") or "").strip()[:MAX_NOTE]
            if act not in ("approve", "reject"): return err(400, "إجراء غير صالح")
            if qr["req_status"] not in ("awaiting_quotes", "quotes_received"): return err(409, "الطلب لا يستقبل عروضًا الآن")
            if act == "approve" and qr["status"] != "pending": return err(409, "العرض ليس بانتظار الاعتماد")
            if act == "reject":
                if qr["status"] not in ("pending", "approved"): return err(409, "لا يمكن رفض العرض في حالته الحالية")
                if len(note) < 3: return err(400, "اكتب سبب الرفض")
            new = "approved" if act == "approve" else "rejected"
            c.execute("UPDATE service_quotes SET status=?,admin_note=?,reviewed_by=?,reviewed_at=?,updated_at=? WHERE id=? AND status=?", (new, note or None, u["id"], now, now, qr["id"], qr["status"]))
            _sync_quote_status(c, qr["request_id"], now, u["id"], "admin")
            _audit(c, u["id"], "service_quote." + new, qr["id"], {"request_id": qr["request_id"], "note": note})
            if act == "approve": _notify(c, qr["cust"], "service_quote.received", "وصلك عرض سعر على طلبك", (qr["type"] + " — " + str(qr["price"]) + " ج")[:120], "svc", qr["request_id"])
            ow = _owner_of(c, qr["provider_id"])
            if ow: _notify(c, ow, "service_quote." + new, "تم اعتماد عرضك" if act == "approve" else "تم رفض عرضك", (qr["type"] + (" — " + note if note else ""))[:120], "svcjob", qr["request_id"])
            c.commit(); h.send(200, {"ok": True, "status": new}); return True
        m = re.fullmatch(r"/api/admin/service-requests/(\d+)", path)
        if m and method == "POST":
            r = c.execute(SEL + " WHERE s.id=?", (int(m[1]),)).fetchone()
            if not r: return err(404, "غير موجود")
            d = h.body() or {}; st = d.get("status"); note = str(d.get("note") or "").strip()[:MAX_NOTE]
            if st not in ADMIN_SET: return err(400, "حالة غير صالحة")
            if r["status"] in ("done", "cancelled", "expired"): return err(409, "الطلب منتهٍ ولا يمكن تغييره")
            if r["status"] == "disputed":  # حسم النزاع: تم أو ملغي فقط وبسبب مكتوب
                if st not in ("done", "cancelled"): return err(400, "حسم النزاع يكون بـ«تم» أو «ملغي» فقط")
                if len(note) < 5: return err(400, "اكتب سبب القرار (5 حروف على الأقل)")
            if r["status"] == st and not note: return err(409, "الطلب بهذه الحالة بالفعل")
            if r["status"] != st and not _can(r["status"], st): return err(409, "لا يمكن الانتقال من هذه الحالة")
            c.execute("UPDATE service_requests SET status=?,admin_note=?,handled_by=?,cancelled_by=CASE WHEN ?='cancelled' THEN 'admin' ELSE cancelled_by END,updated_at=? WHERE id=?",
                      (st, note or r["admin_note"], u["id"], st, now, r["id"]))
            if r["status"] != st or note: _event(c, r["id"], r["status"], st, u["id"], "admin", now, note)
            _audit(c, u["id"], "service_request." + st, r["id"], {"note": note})
            title = {"in_progress": "طلب الخدمة قيد المتابعة", "done": "تم إنجاز طلب الخدمة", "cancelled": "تم إلغاء طلب الخدمة"}[st]
            if r["status"] == "disputed":
                title = "تم حسم النزاع: " + ("اعتُمد الطلب منجزًا" if st == "done" else "أُلغي الطلب")
                ow = _owner_of(c, r["provider_id"])
                if ow: _notify(c, ow, "service_request.dispute_resolved", title, (r["type"] + " — " + note)[:120], "svcjob", r["id"])
            _notify(c, r["user_id"], "service_request." + st, title, (r["type"] + (" — " + note if note else ""))[:120], "svc", r["id"])
            c.commit(); h.send(200, {"ok": True, "status": st}); return True
        return err(404, "غير موجود")

    # ---------- عميل ----------
    if path == "/api/service-requests":
        if method == "GET":
            rows = c.execute(SEL + " WHERE s.user_id=? ORDER BY s.id DESC LIMIT 50", (u["id"],)).fetchall()
            h.send(200, [_mine(r, c) for r in rows]); return True
        if method != "POST": return err(404, "غير موجود")
        d = h.body() or {}
        try: tid, rid = int(d.get("type_id")), int(d.get("region_id"))
        except (TypeError, ValueError): return err(400, "اختار نوع الخدمة والمنطقة")
        desc = str(d.get("description") or "").strip()
        if len(desc) < MIN_DESC: return err(400, "اكتب وصفًا للطلب (%d حروف على الأقل)" % MIN_DESC)
        if len(desc) > MAX_DESC: return err(400, "الوصف أطول من %d حرفًا" % MAX_DESC)
        try: addr, pa, bmin, bmax = _validate_extra(d, now)
        except ValueError as e: return err(400, str(e))
        if not c.execute("SELECT 1 FROM service_types WHERE id=? AND is_active=1", (tid,)).fetchone(): return err(400, "نوع الخدمة غير متاح")
        if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone(): return err(400, "المنطقة غير متاحة")
        if c.execute("SELECT COUNT(*) FROM service_requests WHERE user_id=? AND status IN%s" % _in(LIVE), (u["id"],)).fetchone()[0] >= MAX_ACTIVE:
            return err(429, "عندك %d طلبات مفتوحة، انتظر معالجتها أو ألغِ واحدًا" % MAX_ACTIVE)
        if c.execute("SELECT COUNT(*) FROM service_requests WHERE user_id=? AND created_at>?", (u["id"], now - 86400)).fetchone()[0] >= MAX_PER_DAY:
            return err(429, "تجاوزت الحد اليومي للطلبات، حاول لاحقًا")
        cur = c.execute("INSERT INTO service_requests(user_id,type_id,region_id,description,created_at,updated_at,address,preferred_at,budget_min,budget_max) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (u["id"], tid, rid, desc, now, now, addr, pa, bmin, bmax))
        _event(c, cur.lastrowid, None, "open", u["id"], "customer", now)
        tname = c.execute("SELECT name_ar FROM service_types WHERE id=?", (tid,)).fetchone()[0]
        for a in c.execute("SELECT id FROM users WHERE role IN('admin','staff')").fetchall():
            _notify(c, a["id"], "service_request.new", "طلب خدمة جديد", tname, "admin:svcreq", cur.lastrowid)
        request_regions = _riyad_scope_ids(c, rid)
        for o in c.execute("SELECT DISTINCT p.owner_user_id FROM service_providers p JOIN regions rg ON rg.id=p.region_id WHERE p.owner_user_id IS NOT NULL AND p.is_published=1 AND rg.is_active=1 AND p.type_id=? AND p.region_id IN (%s) AND p.owner_user_id<>?" % ",".join("?" * len(request_regions)), (tid, *request_regions, u["id"])).fetchall():
            _notify(c, o[0], "service_request.job", "طلب خدمة جديد في منطقتك", tname[:120], "svcjob", cur.lastrowid)
        c.commit(); h.send(201, {"id": cur.lastrowid, "status": "open"}); return True

    m = re.fullmatch(r"/api/service-requests/(\d+)", path)
    if m and method == "GET":
        r = c.execute(SEL + " WHERE s.id=? AND s.user_id=?", (int(m[1]), u["id"])).fetchone()
        if not r: return err(404, "غير موجود")
        d = _mine(r, c)
        d["history"] = [{"from": x["from_status"], "to": x["to_status"], "label": LABELS.get(x["to_status"], x["to_status"]), "by": x["actor_role"], "at": x["at"]}
                        for x in c.execute("SELECT * FROM service_request_events WHERE request_id=? ORDER BY id", (r["id"],)).fetchall()]
        h.send(200, d); return True

    # ---------- عروض الأسعار (عميل) ----------
    m = re.fullmatch(r"/api/service-requests/(\d+)/(request-quotes|quotes|select|dispute)", path)
    if m:
        act = m[2]
        if (act == "quotes") != (method == "GET"): return err(404, "غير موجود")
        r = c.execute("SELECT * FROM service_requests WHERE id=? AND user_id=?", (int(m[1]), u["id"])).fetchone()
        if not r: return err(404, "غير موجود")
        if act == "dispute": return _raise_dispute(c, h, r, u, "customer", now, err)
        if act == "quotes":
            rows = c.execute("SELECT q.id,q.provider_id,q.price,q.note,q.status,q.created_at,p.name_ar FROM service_quotes q JOIN service_providers p ON p.id=q.provider_id "
                             "WHERE q.request_id=? AND q.status IN('approved','selected') ORDER BY q.price,q.id", (r["id"],)).fetchall()
            h.send(200, {"request_status": r["status"], "can_select": r["status"] in ("awaiting_quotes", "quotes_received"),
                         "invited_count": c.execute("SELECT COUNT(*) FROM service_request_invites WHERE request_id=?", (r["id"],)).fetchone()[0],
                         "quotes": [{"id": x["id"], "provider_id": x["provider_id"], "provider_name": x["name_ar"], **rating_of(c, x["provider_id"]), "price": x["price"], "note": x["note"],
                                     "selected": x["status"] == "selected", "created_at": x["created_at"]} for x in rows]}); return True
        if act == "request-quotes":
            if r["status"] != "open": return err(409, "الطلب مش في حالة «جديد»، مينفعش تطلب عروض أسعار دلوقتي")
            pool = _eligible(c, r["type_id"], r["region_id"], u["id"])
            ids = (h.body() or {}).get("provider_ids")
            if ids is not None:
                try:
                    if not isinstance(ids, list) or not ids or any(isinstance(x, bool) for x in ids): raise ValueError
                    want = {int(x) for x in ids}
                except (TypeError, ValueError): return err(400, "اختار مقدمًا واحدًا على الأقل")
                pick = [p for p in pool if p["id"] in want]
                if len(pick) != len(want): return err(400, "من المقدمين المختارين من لا يصلح لهذا الطلب")
            else: pick = pool[:MAX_INVITES]
            if not pick: return err(409, "مفيش مقدمين متاحين لعروض الأسعار في منطقتك حاليًا")
            if len(pick) > MAX_INVITES: return err(400, "الحد الأقصى %d مقدمين للطلب الواحد" % MAX_INVITES)
            cur = c.execute("UPDATE service_requests SET status='awaiting_quotes',updated_at=? WHERE id=? AND status='open' AND provider_id IS NULL", (now, r["id"]))
            if cur.rowcount != 1: c.rollback(); return err(409, "تغيّرت حالة الطلب، حاول تاني")
            for p in pick: c.execute("INSERT OR IGNORE INTO service_request_invites(request_id,provider_id,created_at) VALUES(?,?,?)", (r["id"], p["id"], now))
            _event(c, r["id"], "open", "awaiting_quotes", u["id"], "customer", now)
            tn = c.execute("SELECT name_ar FROM service_types WHERE id=?", (r["type_id"],)).fetchone()
            for ow in {p["owner_user_id"] for p in pick}: _notify(c, ow, "service_request.invite", "مطلوب منك عرض سعر على طلب خدمة", (tn[0] if tn else "")[:120], "svcjob", r["id"])
            c.commit(); h.send(200, {"ok": True, "status": "awaiting_quotes", "invited": len(pick)}); return True
        if act == "select":
            if method != "POST": return err(404, "غير موجود")
            if r["status"] not in ("awaiting_quotes", "quotes_received"): return err(409, "الطلب لا يقبل اختيار مقدم الآن")
            try: qid = int((h.body() or {}).get("quote_id"))
            except (TypeError, ValueError): return err(400, "اختار عرضًا")
            qr = c.execute("SELECT q.*,p.is_published,p.owner_user_id,p.name_ar FROM service_quotes q JOIN service_providers p ON p.id=q.provider_id WHERE q.id=? AND q.request_id=?", (qid, r["id"])).fetchone()
            if not qr or qr["status"] != "approved": return err(404, "العرض غير متاح")
            if not qr["is_published"] or not qr["owner_user_id"]: return err(409, "المقدم لم يعد متاحًا")
            cur = c.execute("UPDATE service_requests SET status='provider_selected',provider_id=?,updated_at=? WHERE id=? AND status IN('awaiting_quotes','quotes_received') AND provider_id IS NULL", (qr["provider_id"], now, r["id"]))
            if cur.rowcount != 1: c.rollback(); return err(409, "الطلب لم يعد متاحًا")
            c.execute("UPDATE service_quotes SET status='selected',selected_at=?,updated_at=? WHERE id=? AND status='approved'", (now, now, qr["id"]))
            _event(c, r["id"], r["status"], "provider_selected", u["id"], "customer", now)
            _audit(c, u["id"], "service_quote.select", qr["id"], {"request_id": r["id"], "provider_id": qr["provider_id"]})
            tn = c.execute("SELECT name_ar FROM service_types WHERE id=?", (r["type_id"],)).fetchone()
            _notify(c, qr["owner_user_id"], "service_quote.selected", "العميل اختار عرضك، أكّد قبولك", (tn[0] if tn else "")[:120], "svcjob", r["id"])
            c.commit(); h.send(200, {"ok": True, "status": "provider_selected", "provider_name": qr["name_ar"]}); return True

    # ---------- صور الطلب ----------
    m = re.fullmatch(r"/api/service-requests/(\d+)/images", path)
    if m and method == "POST":
        r = c.execute("SELECT id,status,user_id FROM service_requests WHERE id=? AND user_id=?", (int(m[1]), u["id"])).fetchone()
        if not r: return err(404, "غير موجود")
        if r["status"] not in LIVE: return err(409, "الطلب منتهٍ، لا يمكن إضافة صور")
        if not UPLOADS: return err(503, "رفع الصور غير مفعّل")
        if c.execute("SELECT COUNT(*) FROM service_request_images WHERE request_id=?", (r["id"],)).fetchone()[0] >= MAX_IMAGES: return err(409, "الحد الأقصى %d صور للطلب" % MAX_IMAGES)
        if c.execute("SELECT COUNT(*) FROM service_request_images i JOIN files f ON f.id=i.file_id WHERE f.owner_id=? AND i.created_at>?", (u["id"], now - 86400)).fetchone()[0] >= MAX_IMAGES_DAY:
            return err(429, "وصلت للحد اليومي لرفع الصور، حاول لاحقًا")
        raw, mime = h.read_image()  # يتحقق من الصيغة والحجم وينظّف EXIF/GPS (نفس مسار باقي الصور)
        os.makedirs(UPLOADS, exist_ok=True); name = secrets.token_hex(16)
        with open(os.path.join(UPLOADS, name), "wb") as fh: fh.write(raw)
        fid = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (u["id"], name, mime, len(raw), now)).lastrowid
        c.execute("INSERT INTO service_request_images(request_id,file_id,created_at) VALUES(?,?,?)", (r["id"], fid, now)); c.commit()
        h.send(201, {"id": fid, "images": _images(c, r["id"])}); return True
    m = re.fullmatch(r"/api/service-requests/(\d+)/images/(\d+)(/delete)?", path)
    if m:
        r = c.execute("SELECT s.id,s.status,s.user_id,s.provider_id,f.path,f.mime FROM service_requests s JOIN service_request_images i ON i.request_id=s.id JOIN files f ON f.id=i.file_id "
                      "WHERE s.id=? AND i.file_id=?", (int(m[1]), int(m[2]))).fetchone()
        if not r or not _can_see_images(c, u, r): return err(404, "غير موجود")
        if method == "GET" and not m[3]:
            try: raw = open(os.path.join(UPLOADS, r["path"]), "rb").read()
            except (OSError, TypeError): return err(404, "غير موجود")
            h.send(200, None, r["mime"], raw, {"Cache-Control": "private, no-store"}); return True
        if method == "POST" and m[3]:
            if r["user_id"] != u["id"]: return err(404, "غير موجود")
            if r["status"] not in LIVE: return err(409, "الطلب منتهٍ، لا يمكن حذف الصور")
            c.execute("DELETE FROM service_request_images WHERE file_id=?", (int(m[2]),)); c.execute("DELETE FROM files WHERE id=?", (int(m[2]),)); c.commit()
            try: os.remove(os.path.join(UPLOADS, r["path"]))
            except OSError: pass
            h.send(200, {"ok": True, "images": _images(c, r["id"])}); return True
        return err(404, "غير موجود")

    m = re.fullmatch(r"/api/service-requests/(\d+)/rate(?:/(update|delete))?", path)
    if m and method == "POST":
        r = c.execute("SELECT id,status,provider_id,type_id FROM service_requests WHERE id=? AND user_id=?", (int(m[1]), u["id"])).fetchone()
        if not r: return err(404, "غير موجود")
        d = h.body() or {}; act = m[2]
        cur = c.execute("SELECT id,stars,comment,hidden FROM service_ratings WHERE request_id=?", (r["id"],)).fetchone()
        ow = c.execute("SELECT owner_user_id FROM service_providers WHERE id=?", (r["provider_id"],)).fetchone() if r["provider_id"] else None
        if act == "delete":
            if not cur: return err(404, "لا يوجد تقييم لحذفه")
            c.execute("DELETE FROM service_ratings WHERE id=?", (cur["id"],))
            c.execute("UPDATE service_rating_reports SET status='dismissed',admin_note='حذف العميل التقييم',decided_at=? WHERE rating_id=? AND status='pending'", (now, cur["id"]))
            _audit(c, u["id"], "service_rating.delete", cur["id"], {"request_id": r["id"], "stars": cur["stars"]})
            c.commit(); h.send(200, {"ok": True, **rating_of(c, r["provider_id"])}); return True
        st = None
        if act == "update" and "stars" not in d: st = cur["stars"] if cur else None
        else:
            try: st = int(d.get("stars"))
            except (TypeError, ValueError): return err(400, "اختار من 1 إلى 5 نجوم")
            if not 1 <= st <= 5: return err(400, "اختار من 1 إلى 5 نجوم")
        txt, e = _comment(d)
        if e: return err(400, e)
        if act == "update":
            if not cur: return err(404, "لا يوجد تقييم لتعديله")
            if cur["hidden"]: return err(409, "الإدارة أخفت تقييمك، لا يمكن تعديله (يمكنك حذفه)")
            c.execute("UPDATE service_ratings SET stars=?,comment=?,updated_at=? WHERE id=?", (st, cur["comment"] if txt is None else txt, now, cur["id"]))
            _audit(c, u["id"], "service_rating.update", cur["id"], {"request_id": r["id"], "stars": st})
            if ow and ow[0]: _notify(c, ow[0], "service_request.rating_updated", "العميل عدّل تقييمه", "%d من 5" % st, "svcjob", r["id"])
            c.commit(); h.send(200, {"ok": True, "stars": st, **rating_of(c, r["provider_id"])}); return True
        if r["status"] != "done" or not r["provider_id"]: return err(409, "التقييم متاح بعد إنجاز طلب قبله مقدم خدمة")
        try: c.execute("INSERT INTO service_ratings(request_id,provider_id,user_id,stars,created_at,comment) VALUES(?,?,?,?,?,?)", (r["id"], r["provider_id"], u["id"], st, now, txt or None))
        except Exception: c.rollback(); return err(409, "قيّمت هذا الطلب من قبل")
        if ow and ow[0]: _notify(c, ow[0], "service_request.rated", "حصلت على تقييم جديد", "%d من 5" % st, "svcjob", r["id"])
        c.commit(); h.send(200, {"ok": True, "stars": st, **rating_of(c, r["provider_id"])}); return True

    m = re.fullmatch(r"/api/service-requests/(\d+)/cancel", path)
    if m and method == "POST":
        r = c.execute("SELECT id,status,provider_id,type_id FROM service_requests WHERE id=? AND user_id=?", (int(m[1]), u["id"])).fetchone()
        if not r: return err(404, "غير موجود")
        if r["status"] not in LIVE: return err(409, "الطلب منتهٍ بالفعل")
        c.execute("UPDATE service_requests SET status='cancelled',cancelled_by='customer',updated_at=? WHERE id=?", (now, r["id"]))
        _event(c, r["id"], r["status"], "cancelled", u["id"], "customer", now)
        if r["provider_id"]:  # لو كان عند مقدم: يُبلَّغ حساب المقدم
            ow = c.execute("SELECT owner_user_id FROM service_providers WHERE id=?", (r["provider_id"],)).fetchone()
            tn = c.execute("SELECT name_ar FROM service_types WHERE id=?", (r["type_id"],)).fetchone()
            if ow and ow[0]: _notify(c, ow[0], "service_request.cancelled", "ألغى العميل الطلب", (tn[0] if tn else "")[:120], "svcjob", r["id"])
        c.commit(); h.send(200, {"ok": True, "status": "cancelled"}); return True
    return err(404, "غير موجود")
