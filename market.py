"""سوق لاقينو — منطق السوق (المرحلة 2: ترحيل قاعدة البيانات).

بدون مكتبات خارجية. تُستدعى market.migrate(c) من server.init() بعد إنشاء المخطط الأساسي.
الترحيل متكرر بأمان (idempotent): لا يفعل شيئًا إذا كان الجدول بالمخطط الجديد.
"""
import os, sqlite3, time

LISTING_STATUSES = ("pending", "approved", "rejected", "hidden", "deleted")
CONDITIONS = ("new", "used")
CLOSED_KINDS = ("sold", "rented")

# أعمدة الجدول القديم (المرحلة 16 وما قبلها) التي تُنسخ كما هي
_OLD_COLS = "id,user_id,category_id,region_id,title,description,price,data,status,reject_reason,created_at"

_LISTINGS_NEW = """CREATE TABLE listings_new(
 id INTEGER PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES users(id),
 category_id INTEGER NOT NULL REFERENCES categories(id),
 region_id INTEGER NOT NULL REFERENCES regions(id),
 title TEXT NOT NULL, description TEXT, price REAL, data TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','rejected','hidden','deleted')),
 reject_reason TEXT,
 created_at INTEGER NOT NULL,
 condition TEXT CHECK(condition IS NULL OR condition IN('new','used')),
 negotiable INTEGER NOT NULL DEFAULT 0 CHECK(negotiable IN(0,1)),
 closed_kind TEXT CHECK(closed_kind IS NULL OR closed_kind IN('sold','rented')),
 updated_at INTEGER NOT NULL DEFAULT 0,
 reviewed_by INTEGER REFERENCES users(id),
 reviewed_at INTEGER,
 hidden_reason TEXT)"""

_NEW_TABLES = """
CREATE TABLE IF NOT EXISTS listing_images(id INTEGER PRIMARY KEY,
 listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
 file_id INTEGER NOT NULL UNIQUE REFERENCES files(id),
 position INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_listing_images ON listing_images(listing_id,position);
CREATE TABLE IF NOT EXISTS market_files(file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
 user_id INTEGER NOT NULL REFERENCES users(id), created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_market_files_user ON market_files(user_id);
CREATE TABLE IF NOT EXISTS listing_favorites(
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
 created_at INTEGER NOT NULL, PRIMARY KEY(user_id,listing_id));
CREATE INDEX IF NOT EXISTS ix_listing_fav_listing ON listing_favorites(listing_id);
CREATE TABLE IF NOT EXISTS listing_reports(id INTEGER PRIMARY KEY,
 listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
 reporter_id INTEGER NOT NULL REFERENCES users(id),
 reason TEXT NOT NULL, details TEXT,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','resolved','dismissed')),
 handled_by INTEGER REFERENCES users(id), handled_at INTEGER, created_at INTEGER NOT NULL,
 UNIQUE(listing_id,reporter_id));
CREATE INDEX IF NOT EXISTS ix_listing_reports ON listing_reports(status,listing_id);
"""

_LISTING_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_listings ON listings(status,category_id,region_id);
CREATE INDEX IF NOT EXISTS ix_listings_user ON listings(user_id,status);
CREATE INDEX IF NOT EXISTS ix_listings_created ON listings(status,created_at);
CREATE INDEX IF NOT EXISTS ix_listings_price ON listings(status,price);
"""


def _listings_sql(c):
    r = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='listings'").fetchone()
    return r[0] if r else None


def needs_rebuild(c):
    sql = _listings_sql(c)
    return bool(sql) and "'hidden'" not in sql


def _pre_migration_backup(c, db_path):
    """نسخة متسقة من القاعدة قبل إعادة بناء listings (فقط لقاعدة فيها مستخدمون). تُرجع المسار أو None."""
    if not db_path or db_path == ":memory:" or not os.path.exists(db_path): return None
    if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone(): return None
    dst_path = "%s.pre-market-%s.bak" % (db_path, time.strftime("%Y%m%d-%H%M%S"))
    dst = sqlite3.connect(dst_path)
    try: c.backup(dst)
    finally: dst.close()
    return dst_path


def migrate(c, db_path=None):
    """يرحّل القاعدة إلى مخطط السوق الجديد. يُرجع قاموسًا بما تم (للاختبار والتوثيق)."""
    out = {"rebuilt": False, "backup": None, "rows": 0}
    c.commit()
    if needs_rebuild(c):
        out["backup"] = _pre_migration_backup(c, db_path)
        c.commit()
        c.execute("PRAGMA foreign_keys=OFF")  # لا يمكن تغييره داخل معاملة
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DROP TABLE IF EXISTS listings_new")  # بقايا محاولة سابقة منقطعة
            c.execute(_LISTINGS_NEW)
            c.execute("INSERT INTO listings_new(%s,updated_at) SELECT %s,created_at FROM listings" % (_OLD_COLS, _OLD_COLS))
            old_n = c.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            new_n = c.execute("SELECT COUNT(*) FROM listings_new").fetchone()[0]
            if old_n != new_n: raise sqlite3.IntegrityError("listings row count mismatch: %d -> %d" % (old_n, new_n))
            c.execute("DROP TABLE listings")
            c.execute("ALTER TABLE listings_new RENAME TO listings")
            bad = c.execute("PRAGMA foreign_key_check").fetchall()
            if bad: raise sqlite3.IntegrityError("foreign key violations after rebuild: %d" % len(bad))
            c.execute("COMMIT")
            out["rebuilt"], out["rows"] = True, new_n
        except BaseException:
            if c.in_transaction: c.execute("ROLLBACK")
            raise
        finally:
            c.execute("PRAGMA foreign_keys=ON")
    c.executescript(_NEW_TABLES + _LISTING_INDEXES)
    return out


# ───────────── المرحلة 3: التصنيفات (منطق مساعد؛ المسارات الرفيعة في server.py) ─────────────
# قاعدة الظهور: جذر القسم (parent_id IS NULL) لا يدخل في الفحص حتى لا يتغير سلوك قائم؛
# أي تصنيف غير جذري يظهر ويقبل النشر فقط إذا كان هو وكل آبائه غير الجذريين مفعّلين.
VISIBLE_CATEGORIES = ("(WITH RECURSIVE a(id) AS (SELECT id FROM categories WHERE parent_id IS NULL "
                      "UNION SELECT k.id FROM categories k JOIN a ON k.parent_id=a.id WHERE k.is_active=1) SELECT id FROM a)")


def subtree_ids(c, cid):
    """معرّف التصنيف وكل أحفاده."""
    return [r[0] for r in c.execute("WITH RECURSIVE s(id) AS (SELECT ? UNION SELECT k.id FROM categories k JOIN s ON k.parent_id=s.id) SELECT id FROM s", (cid,))]


def listing_counts(c, cid):
    """(غير المحذوفة، الكل بما فيها المحذوفة) داخل التصنيف وأحفاده. الإعلان المحذوف منطقيًا يبقى صفًا يمنع الحذف النهائي."""
    ids = subtree_ids(c, cid); ph = ",".join("?" * len(ids))
    live = c.execute("SELECT COUNT(*) FROM listings WHERE status!='deleted' AND category_id IN (%s)" % ph, ids).fetchone()[0]
    total = c.execute("SELECT COUNT(*) FROM listings WHERE category_id IN (%s)" % ph, ids).fetchone()[0]
    return live, total


def is_visible_category(c, cid):
    return c.execute("SELECT 1 FROM categories WHERE id=? AND id IN " + VISIBLE_CATEGORIES, (cid,)).fetchone() is not None


# ───────────── المرحلة 4: صور الإعلانات ─────────────
MAX_LISTING_IMAGES = 8      # صور لكل إعلان
MAX_MARKET_UPLOADS = 40     # صور سوق مرفوعة لكل مستخدم (سقف مستقل عن سقف الـ20 ملفًا للروشتات والمستندات)


def images_for(c, listing_ids):
    """{listing_id: [file_id, ...]} مرتبة بالموضع."""
    out = {i: [] for i in listing_ids}
    if not listing_ids: return out
    for r in c.execute("SELECT listing_id,file_id FROM listing_images WHERE listing_id IN (%s) ORDER BY listing_id,position,id" % ",".join("?" * len(listing_ids)), list(listing_ids)):
        out[r[0]].append(r[1])
    return out


def file_used_elsewhere(c, fid):
    """هل الملف مستخدم خارج صور الإعلانات (روشتة/مستند مندوب/صورة طبيب أو معمل)؟ إن كان نعم لا يُحذف من القرص."""
    return c.execute("SELECT 1 FROM prescriptions WHERE file_id=? UNION SELECT 1 FROM courier_documents WHERE file_id=? "
                     "UNION SELECT 1 FROM doctors WHERE photo_file_id=? UNION SELECT 1 FROM labs WHERE photo_file_id=?", (fid, fid, fid, fid)).fetchone() is not None
