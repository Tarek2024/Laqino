import base64, sqlite3, json, os, secrets, hashlib, hmac, sys, time, mimetypes, re, threading, ipaddress
import notif, account
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
import market
import gsearch, products, provider_delivery, rx, chat, svc, overview, fcm, exchange, lsocial, bulk_import
DB = os.environ.get("LAQINO_DB", "laqino.db")
UP = os.environ.get("LAQINO_UPLOADS", "uploads")
ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"))
MIME = {".webmanifest": "application/manifest+json", ".js": "text/javascript", ".png": "image/png", ".webp": "image/webp"}
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS regions(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES regions(id),
 level TEXT NOT NULL CHECK(level IN('country','governorate','markaz','village','zone')),
 slug TEXT UNIQUE NOT NULL, name_ar TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 0, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, phone TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 pw_hash TEXT NOT NULL, salt TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'customer' CHECK(role IN('customer','seller','medical_provider','courier','staff','admin')),
 region_id INTEGER REFERENCES regions(id), created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS throttle(k TEXT NOT NULL, ts INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_throttle_k ON throttle(k,ts);
CREATE INDEX IF NOT EXISTS ix_throttle_ts ON throttle(ts);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT NOT NULL, target TEXT, detail TEXT, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES categories(id),
 section TEXT NOT NULL CHECK(section IN('medical','souq','delivery','services')), slug TEXT UNIQUE NOT NULL, name_ar TEXT NOT NULL,
 sort INTEGER DEFAULT 0, is_active INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS category_fields(id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
 key TEXT NOT NULL, label_ar TEXT NOT NULL, type TEXT NOT NULL CHECK(type IN('text','price','number','image','date','select','location')),
 required INTEGER NOT NULL DEFAULT 0, searchable INTEGER NOT NULL DEFAULT 0, options TEXT, sort INTEGER DEFAULT 0, UNIQUE(category_id,key));
CREATE TABLE IF NOT EXISTS listings(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), category_id INTEGER NOT NULL REFERENCES categories(id),
 region_id INTEGER NOT NULL REFERENCES regions(id), title TEXT NOT NULL, description TEXT, price REAL, data TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','rejected','deleted')), reject_reason TEXT, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_listings ON listings(status,category_id,region_id);
CREATE TABLE IF NOT EXISTS couriers(user_id INTEGER PRIMARY KEY REFERENCES users(id), status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','suspended','rejected')),
 region_id INTEGER NOT NULL REFERENCES regions(id), is_available INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS region_fees(region_id INTEGER PRIMARY KEY REFERENCES regions(id), fee REAL NOT NULL CHECK(fee>=0));
CREATE TABLE IF NOT EXISTS password_resets(user_id INTEGER PRIMARY KEY REFERENCES users(id), code_hash TEXT NOT NULL, salt TEXT NOT NULL, expires INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, issued_by INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS push_subs(endpoint TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS push_keys(id INTEGER PRIMARY KEY CHECK(id=1), priv TEXT NOT NULL, pub TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS delivery_orders(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES users(id), region_id INTEGER NOT NULL REFERENCES regions(id),
 pickup_text TEXT NOT NULL, dropoff_text TEXT NOT NULL, details TEXT, fee REAL NOT NULL, courier_id INTEGER REFERENCES users(id),
 status TEXT NOT NULL DEFAULT 'searching' CHECK(status IN('searching','assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation','completed','cancelled','disputed')),
 commission REAL NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS order_events(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, actor_id INTEGER, from_status TEXT, to_status TEXT NOT NULL, at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_orders ON delivery_orders(status,region_id);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wallet_entries(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), kind TEXT NOT NULL CHECK(kind IN('topup','commission','reversal')),
 amount REAL NOT NULL, ref_type TEXT NOT NULL, ref_id INTEGER NOT NULL, created_at INTEGER NOT NULL, UNIQUE(kind,ref_type,ref_id));
CREATE TABLE IF NOT EXISTS topup_requests(id INTEGER PRIMARY KEY, courier_id INTEGER NOT NULL REFERENCES users(id), amount REAL NOT NULL CHECK(amount>0),
 transfer_ref TEXT NOT NULL UNIQUE, note TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','rejected')), reason TEXT, reviewed_by INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS wallet_adjustments(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), amount REAL NOT NULL CHECK(amount!=0), reason TEXT NOT NULL,
 admin_id INTEGER NOT NULL REFERENCES users(id), request_key TEXT, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_wadj_user ON wallet_adjustments(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wadj_key ON wallet_adjustments(admin_id,request_key) WHERE request_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS ratings(order_id INTEGER PRIMARY KEY REFERENCES delivery_orders(id), customer_id INTEGER NOT NULL, courier_id INTEGER NOT NULL,
 stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5), comment TEXT, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS providers(user_id INTEGER PRIMARY KEY REFERENCES users(id), name_ar TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'pharmacy' CHECK(kind IN('pharmacy')),
 region_id INTEGER NOT NULL REFERENCES regions(id), address TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','suspended','rejected')), created_at INTEGER NOT NULL,
 lat REAL, lng REAL, distribution_enabled INTEGER NOT NULL DEFAULT 0 CHECK(distribution_enabled IN(0,1)));
CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), path TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS provider_stock(provider_id INTEGER NOT NULL REFERENCES providers(user_id), name_norm TEXT NOT NULL, medicine_name TEXT NOT NULL, available INTEGER NOT NULL, price REAL, confirmed_at INTEGER NOT NULL, PRIMARY KEY(provider_id,name_norm));
CREATE TABLE IF NOT EXISTS medicine_inquiries(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES users(id), region_id INTEGER NOT NULL REFERENCES regions(id), medicine_name TEXT NOT NULL, note TEXT,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','cancelled')), created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS inquiry_responses(inquiry_id INTEGER NOT NULL REFERENCES medicine_inquiries(id), provider_id INTEGER NOT NULL REFERENCES providers(user_id),
 status TEXT NOT NULL CHECK(status IN('available','unavailable','needs_confirmation')), price REAL, note TEXT, updated_at INTEGER NOT NULL, PRIMARY KEY(inquiry_id,provider_id));
CREATE TABLE IF NOT EXISTS prescriptions(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES users(id), region_id INTEGER NOT NULL REFERENCES regions(id), file_id INTEGER REFERENCES files(id), note TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','forwarded','closed')), created_at INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'rx' CHECK(kind IN('rx','item')));
CREATE TABLE IF NOT EXISTS prescription_access(prescription_id INTEGER NOT NULL REFERENCES prescriptions(id), provider_id INTEGER NOT NULL REFERENCES providers(user_id), PRIMARY KEY(prescription_id,provider_id));
CREATE TABLE IF NOT EXISTS prescription_responses(prescription_id INTEGER NOT NULL REFERENCES prescriptions(id), provider_id INTEGER NOT NULL REFERENCES providers(user_id),
 status TEXT NOT NULL CHECK(status IN('available','unavailable','needs_confirmation')), price REAL, note TEXT, updated_at INTEGER NOT NULL, PRIMARY KEY(prescription_id,provider_id));
CREATE TABLE IF NOT EXISTS medical_delivery_links(order_id INTEGER PRIMARY KEY REFERENCES delivery_orders(id), source_type TEXT NOT NULL CHECK(source_type IN('inquiry','prescription')), source_id INTEGER NOT NULL, provider_id INTEGER NOT NULL REFERENCES providers(user_id), created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_mdl ON medical_delivery_links(source_type,source_id,provider_id);
CREATE INDEX IF NOT EXISTS ix_cat_section ON categories(section,parent_id);
CREATE INDEX IF NOT EXISTS ix_regions_parent ON regions(parent_id);
CREATE TABLE IF NOT EXISTS order_offers(order_id INTEGER NOT NULL REFERENCES delivery_orders(id), courier_id INTEGER NOT NULL REFERENCES users(id),
 status TEXT NOT NULL DEFAULT 'offered' CHECK(status IN('offered','rejected','expired','accepted','lost')), offered_at INTEGER NOT NULL, responded_at INTEGER, rounds INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(order_id,courier_id));
CREATE TABLE IF NOT EXISTS specialties(id INTEGER PRIMARY KEY, name_ar TEXT NOT NULL UNIQUE, name_norm TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY, name_ar TEXT NOT NULL, name_norm TEXT NOT NULL, specialty_id INTEGER NOT NULL REFERENCES specialties(id), region_id INTEGER NOT NULL REFERENCES regions(id),
 clinic_name TEXT, address TEXT, schedule TEXT, phone TEXT, whatsapp TEXT, bio TEXT, is_published INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_doctors ON doctors(is_published,specialty_id,region_id);
CREATE TABLE IF NOT EXISTS service_types(id INTEGER PRIMARY KEY, name_ar TEXT NOT NULL UNIQUE, name_norm TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS service_providers(id INTEGER PRIMARY KEY, name_ar TEXT NOT NULL, name_norm TEXT NOT NULL, type_id INTEGER NOT NULL REFERENCES service_types(id), region_id INTEGER NOT NULL REFERENCES regions(id),
 description TEXT, address TEXT, phone TEXT, whatsapp TEXT, is_published INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_service_providers ON service_providers(is_published,type_id,region_id);
CREATE TABLE IF NOT EXISTS labs(id INTEGER PRIMARY KEY, name_ar TEXT NOT NULL, name_norm TEXT NOT NULL, region_id INTEGER NOT NULL REFERENCES regions(id), address TEXT, hours TEXT, tests TEXT, home_visit INTEGER NOT NULL DEFAULT 0,
 phone TEXT, whatsapp TEXT, is_published INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_labs ON labs(is_published,region_id);
CREATE TABLE IF NOT EXISTS courier_documents(courier_id INTEGER NOT NULL REFERENCES couriers(user_id), kind TEXT NOT NULL CHECK(kind IN('id_front','id_back','selfie')), file_id INTEGER NOT NULL REFERENCES files(id), created_at INTEGER NOT NULL, PRIMARY KEY(courier_id,kind));
CREATE TABLE IF NOT EXISTS phone_verifications(phone TEXT NOT NULL, purpose TEXT NOT NULL CHECK(purpose IN('register','reset')), code TEXT NOT NULL, expires INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, verified_at INTEGER, created_at INTEGER NOT NULL, PRIMARY KEY(phone,purpose));
"""
def db():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA busy_timeout=10000")
    if not getattr(db, "wal", False):
        try: c.execute("PRAGMA journal_mode=WAL"); db.wal = True  # concurrent readers during writes; persists in the db file
        except sqlite3.Error: pass
    return c
def hp(pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
def audit(c, actor, action, target=None, detail=None):
    c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (actor, action, target, json.dumps(detail, ensure_ascii=False), int(time.time())))
def charge_commission(c, oid):
    """Idempotent: UNIQUE(kind,ref_type,ref_id) + INSERT OR IGNORE guarantee a single commission per order."""
    r = c.execute("SELECT courier_id,commission FROM delivery_orders WHERE id=?", (oid,)).fetchone()
    if r and r["courier_id"] and r["commission"] > 0:
        c.execute("INSERT OR IGNORE INTO wallet_entries(user_id,kind,amount,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?)", (r["courier_id"], "commission", -r["commission"], "order", oid, int(time.time())))
def sweep(c):
    """Lazy auto-confirm: orders left in awaiting_confirmation longer than auto_confirm_hours (default 24) complete and the commission is charged once."""
    try:
        hrs = float(({r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}).get("auto_confirm_hours", 24)); now = int(time.time()); cut = now - int(hrs * 3600)
        for r in c.execute("SELECT id FROM delivery_orders WHERE status='awaiting_confirmation' AND updated_at<=?", (cut,)).fetchall():
            if c.execute("UPDATE delivery_orders SET status='completed',updated_at=? WHERE id=? AND status='awaiting_confirmation' AND updated_at<=?", (now, r["id"], cut)).rowcount:
                c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,NULL,'awaiting_confirmation','completed',?)", (r["id"], now))
                charge_commission(c, r["id"]); audit(c, None, "order.auto_confirm", str(r["id"]), {"hours": hrs})
        c.commit()
    except (sqlite3.Error, ValueError): c.rollback()
# ---- الموقع الموحد (المرحلة 22) ----
# السيرفر لا يخزّن موقع المستخدم أبدًا إلا إذا أرفقه صراحةً بطلب توصيل (يراه المندوب بعد قبول الطلب فقط).
RESOLVE_RADIUS_KM = (("village", 10.0), ("zone", 10.0), ("markaz", 40.0))  # المناطق الفرعية تُطابق جغرافيًا، لكن فروع مركز الرياض تُحوّل إلى المركز الموحد
def geo_pair(lat, lng, required=False):
    """يتحقق من زوج إحداثيات ويعيد (lat, lng) أو (None, None) إن لم يُرسَل؛ خطأ 400 لقيمة غير صالحة أو زوج ناقص."""
    if lat in (None, "") and lng in (None, ""):
        if required: raise E(400, "إحداثيات الموقع مطلوبة")
        return None, None
    try: la, ln = float(lat), float(lng)
    except (TypeError, ValueError): raise E(400, "إحداثيات الموقع غير صالحة")
    if not (-90 <= la <= 90 and -180 <= ln <= 180) or la != la or ln != ln: raise E(400, "إحداثيات الموقع غير صالحة")
    return round(la, 6), round(ln, 6)
def haversine_km(la1, ln1, la2, ln2):
    import math
    p1, p2 = math.radians(la1), math.radians(la2); dp, dl = p2 - p1, math.radians(ln2 - ln1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))
def resolve_region(c, lat, lng):
    """يرجع (المنطقة، المسافة، الحالة). لا يختار تلقائيًا عند تعادل مرشحين قريبين؛ حينها يطلب اختيارًا يدويًا."""
    rows = c.execute("SELECT id,parent_id,level,name_ar,lat,lng FROM regions WHERE is_active=1 AND lat IS NOT NULL AND lng IS NOT NULL AND level IN ('village','zone','markaz')").fetchall()
    for lv, rad in RESOLVE_RADIUS_KM:
        matches = []
        for r in rows:
            if r["level"] != lv: continue
            d = haversine_km(lat, lng, r["lat"], r["lng"])
            if d <= rad: matches.append((r, d))
        if not matches: continue
        matches.sort(key=lambda x: x[1])
        nearest, distance = matches[0]
        # لاقينو يعتمد مركز الرياض كنطاق خدمة موحد: أي نقطة تُطابق قرية/منطقة فرعية
        # تابعة له تُرجع المركز بدل اسم القرية. بيانات الفروع تظل محفوظة للطلبات القديمة.
        if lv in ("village", "zone"):
            rid, seen = nearest["id"], set()
            while rid and rid not in seen:
                seen.add(rid)
                anc = c.execute("SELECT * FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone()
                if not anc: break
                if anc["level"] == "markaz" and "slug" in anc.keys() and anc["slug"] == "eg-kfs-riyad":
                    dist = haversine_km(lat, lng, anc["lat"], anc["lng"]) if anc["lat"] is not None and anc["lng"] is not None else distance
                    return anc, round(dist, 2), "clear"
                rid = anc["parent_id"]
        # إن كان أقرب مرشحين من المستوى نفسه متقاربين جدًا في المسافة، لا نخمن المنطقة.
        if len(matches) > 1 and matches[0][1] <= 2.0 and matches[1][1] <= 2.0 and (matches[1][1] - matches[0][1]) <= 0.75:
            return None, round(matches[0][1], 2), 'ambiguous'
        return nearest, round(distance, 2), 'clear'
    return None, None, 'unspecified'

def region_path(c, rid):
    out, seen = [], set()
    while rid and rid not in seen:
        seen.add(rid); r = c.execute("SELECT parent_id,name_ar,level FROM regions WHERE id=?", (rid,)).fetchone()
        if not r: break
        if r["level"] != "country": out.append(r["name_ar"])
        rid = r["parent_id"]
    return list(reversed(out))
# مناطق مركز الرياض الثابتة (المرحلة 25): (slug, الاسم، الأجرة الافتراضية، الحد الأدنى، الحد الأقصى). الإدارة تعدّل الأسعار والحدود من لوحة التحكم.
RIYAD_ZONES = (("fargh-kobra-koum", "فرج الكبرى / الكوم", 15, 10, 20), ("mothalath-bariya", "المثلث / البرية (عزبة البط)", 25, 20, 30),
               ("hasafa-thabet", "الحصفة / الثابت", 35, 30, 45), ("abu-mostafa", "أبو مصطفى", 40, 30, 50), ("manshaat-salama", "منشأة سلامة", 45, 35, 55),
               ("dabaa-raseef", "الضبعة / الرصيف", 50, 40, 65), ("wazaria", "الوزارية", 60, 50, 75), ("aqoula", "العاقولة", 90, 70, 115),
               ("baqloula-omran", "بقلولة / العمران", 100, 80, 125), ("majd-55", "المجد 55", 120, 95, 150))
def seed_riyad_zones(c):
    """يزرع المناطق العشر تحت مركز الرياض مرة واحدة: لا يكرّر منطقة موجودة (بالاسم أو الـslug) ولا يكتب فوق أي أجرة/حد عدّلته الإدارة ولا يعيد تفعيل منطقة عطّلتها."""
    mk = c.execute("SELECT id FROM regions WHERE slug='eg-kfs-riyad'").fetchone()
    if not mk: return
    for i, (slug, name, fee, lo, hi) in enumerate(RIYAD_ZONES):
        r = c.execute("SELECT id FROM regions WHERE slug=? OR (parent_id=? AND name_ar=?)", ("eg-kfs-riyad-" + slug, mk[0], name)).fetchone()
        rid = r[0] if r else c.execute("INSERT INTO regions(parent_id,level,slug,name_ar,is_active,sort) VALUES(?,'zone',?,?,1,?)", (mk[0], "eg-kfs-riyad-" + slug, name, i + 1)).lastrowid
        c.execute("INSERT OR IGNORE INTO region_fees(region_id,fee,min_fee,max_fee) VALUES(?,?,?,?)", (rid, fee, lo, hi))
FTS_OK = False
def ensure_fts(c):
    """Trigram full-text index over listings(title, description). Same substring semantics as LIKE '%q%' for queries of 3+ chars, but indexed
    (no full scan). Optional: if this SQLite lacks FTS5/trigram, FTS_OK stays False and search keeps using LIKE. Idempotent; triggers keep it in sync."""
    global FTS_OK
    FTS_OK = False
    try:
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS listings_fts USING fts5(title, description, content='listings', content_rowid='id', tokenize='trigram')")
        c.execute("CREATE TRIGGER IF NOT EXISTS listings_fts_ai AFTER INSERT ON listings BEGIN INSERT INTO listings_fts(rowid,title,description) VALUES(new.id,new.title,new.description); END")
        c.execute("CREATE TRIGGER IF NOT EXISTS listings_fts_ad AFTER DELETE ON listings BEGIN INSERT INTO listings_fts(listings_fts,rowid,title,description) VALUES('delete',old.id,old.title,old.description); END")
        c.execute("CREATE TRIGGER IF NOT EXISTS listings_fts_au AFTER UPDATE OF title,description ON listings BEGIN INSERT INTO listings_fts(listings_fts,rowid,title,description) VALUES('delete',old.id,old.title,old.description); INSERT INTO listings_fts(rowid,title,description) VALUES(new.id,new.title,new.description); END")
        n_l = c.execute("SELECT COUNT(*) FROM listings").fetchone()[0]; n_f = c.execute("SELECT COUNT(*) FROM listings_fts_docsize").fetchone()[0]
        if n_l != n_f: c.execute("INSERT INTO listings_fts(listings_fts) VALUES('rebuild')")  # first run on an existing DB, or drift after a table rebuild
        c.commit(); FTS_OK = True
    except sqlite3.OperationalError as e:
        c.rollback(); print("FTS5 trigram unavailable, search uses LIKE:", e)
def auto_backup(keep=5):
    """نسخة احتياطية متسقة (sqlite backup API) قبل أي ترحيل تلقائي للمخطط. لا تعمل إن لم توجد قاعدة، أو إن LAQINO_AUTO_BACKUP=0.
    تُحفظ في مجلد backups بجوار القاعدة، ويُبقى آخر keep نسخ فقط. فشل النسخ لا يوقف الخادم (يُطبع تحذير)."""
    if os.environ.get("LAQINO_AUTO_BACKUP", "1") == "0" or not os.path.isfile(DB) or os.path.getsize(DB) == 0: return None
    try:
        d = os.path.join(os.path.dirname(os.path.abspath(DB)), "backups"); os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, "pre-start-%s.db" % time.strftime("%Y%m%d-%H%M%S"))
        src = sqlite3.connect(DB, timeout=10); out = sqlite3.connect(dst)
        try: src.backup(out)
        finally: out.close(); src.close()
        old = sorted(f for f in os.listdir(d) if f.startswith("pre-start-") and f.endswith(".db"))
        for f in old[:-keep]: os.remove(os.path.join(d, f))
        return dst
    except Exception as e: print("AUTO BACKUP WARNING:", e, file=sys.stderr); return None
def init(admin_phone=None, admin_pw=None):
    bk = auto_backup()
    if bk: print("auto-backup:", bk)
    if os.environ.get("LAQINO_WA_VERIFY", "0") != "1": print("WARNING: LAQINO_WA_VERIFY!=1 — التسجيل بدون تحقق من الهاتف (للإنتاج فعّله)", file=sys.stderr)
    c = db(); c.executescript(SCHEMA)
    for ddl in ('ALTER TABLE delivery_orders ADD COLUMN commission REAL NOT NULL DEFAULT 0', 'ALTER TABLE couriers ADD COLUMN last_seen INTEGER NOT NULL DEFAULT 0', 'ALTER TABLE couriers ADD COLUMN review_reason TEXT', 'ALTER TABLE couriers ADD COLUMN avatar_file_id INTEGER REFERENCES files(id)',
                'ALTER TABLE delivery_orders ADD COLUMN search_started_at INTEGER NOT NULL DEFAULT 0', 'ALTER TABLE delivery_orders ADD COLUMN delivery_code TEXT', 'ALTER TABLE delivery_orders ADD COLUMN request_key TEXT',
                'ALTER TABLE doctors ADD COLUMN photo_file_id INTEGER REFERENCES files(id)', 'ALTER TABLE labs ADD COLUMN photo_file_id INTEGER REFERENCES files(id)',
                "ALTER TABLE categories ADD COLUMN description TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE categories ADD COLUMN icon TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE categories ADD COLUMN display_mode TEXT NOT NULL DEFAULT 'auto'",
                # الموقع الموحد (المرحلة 22): إحداثيات اختيارية للمناطق (تحدّدها الإدارة) وموقع تسليم اختياري على طلب التوصيل
                'ALTER TABLE regions ADD COLUMN lat REAL', 'ALTER TABLE regions ADD COLUMN lng REAL',
                'ALTER TABLE delivery_orders ADD COLUMN dropoff_lat REAL', 'ALTER TABLE delivery_orders ADD COLUMN dropoff_lng REAL',
                # الأجرة التفاوضية (المرحلة 25): حدود أدنى/أقصى لكل منطقة + حالة الأجرة على الطلب. الطلبات القديمة تُعتبر «approved» فلا يتغير سلوكها
                'ALTER TABLE region_fees ADD COLUMN min_fee REAL', 'ALTER TABLE delivery_orders ADD COLUMN comm_type TEXT', 'ALTER TABLE delivery_orders ADD COLUMN comm_value REAL', 'ALTER TABLE region_fees ADD COLUMN max_fee REAL',
                "ALTER TABLE delivery_orders ADD COLUMN fare_status TEXT NOT NULL DEFAULT 'approved'",
                'ALTER TABLE delivery_orders ADD COLUMN offer_fee REAL'):  # المرحلة 27: أجرة يقترحها العميل (اختيارية)
        try: c.execute(ddl)
        except sqlite3.OperationalError: pass
    # Phase 1 / ج1: safe additive schema migrations. Existing rows remain rx and excluded from pharmacy distribution until explicitly enabled.
    for ddl in (
        "ALTER TABLE prescriptions ADD COLUMN kind TEXT NOT NULL DEFAULT 'rx' CHECK(kind IN('rx','item'))",
        'ALTER TABLE providers ADD COLUMN lat REAL',
        'ALTER TABLE providers ADD COLUMN lng REAL',
        'ALTER TABLE providers ADD COLUMN distribution_enabled INTEGER NOT NULL DEFAULT 0 CHECK(distribution_enabled IN(0,1))'
    ):
        try: c.execute(ddl)
        except sqlite3.OperationalError as e:
            if 'duplicate column name' not in str(e).lower(): raise
    # Administrative settings are additive and disabled by default; no existing live request is rewritten.
    for key, value in (("rx_claim_mode", "0"), ("rx_routing_mode", "direct"),
                       ("rx_direct_provider_id", ""), ("rx_claim_timeout_minutes", "10"),
                       ("rx_total_timeout_minutes", "60")):
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (key, value))
    c.execute('CREATE INDEX IF NOT EXISTS ix_providers_region_distribution ON providers(region_id,status,distribution_enabled)')
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_order_reqkey ON delivery_orders(customer_id,request_key) WHERE request_key IS NOT NULL')
    market.migrate(c, DB)  # Phase 2: market schema (listing statuses/columns, images, favorites, reports); idempotent
    if not c.execute("SELECT 1 FROM regions").fetchone():
        # geographic structure only; coverage is activated explicitly by admin
        c.execute("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(1,NULL,'country','eg','مصر',1)")
        c.execute("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(2,1,'governorate','eg-kfs','كفر الشيخ',1)")
        c.execute("INSERT INTO regions(id,parent_id,level,slug,name_ar,is_active) VALUES(3,2,'markaz','eg-kfs-riyad','مركز الرياض',1)")
    # إحداثيات مركز الرياض (كفر الشيخ) للتحديد التلقائي بالـGPS؛ تُملأ فقط لو فارغة (لا تكتب فوق تعديل الإدارة)
    c.execute("UPDATE regions SET lat=31.314810,lng=30.928087 WHERE slug='eg-kfs-riyad' AND lat IS NULL AND lng IS NULL")
    seed_riyad_zones(c)
    c.commit()
    if not c.execute("SELECT 1 FROM categories").fetchone():
        # section roots only; hidden until the admin activates them
        for sec, nm in (("medical", "الطبي"), ("souq", "سوق لاقينو"), ("delivery", "دليفري ومشاوير"), ("services", "الخدمات")):
            c.execute("INSERT INTO categories(section,slug,name_ar,is_active) VALUES(?,?,?,0)", (sec, sec, nm))
    if admin_phone and admin_pw and not c.execute("SELECT 1 FROM users WHERE phone=?", (admin_phone,)).fetchone():
        check_admin_password(admin_pw, admin_phone); s = secrets.token_hex(16)
        c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?,?)", (admin_phone, "مدير النظام", hp(admin_pw, s), s, "admin", int(time.time())))
    c.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))  # purge expired sessions at startup
    account.ensure_column(c)  # حذف الحساب (Google Play): users.deleted_at
    notif.install(c)
    exchange.install(c)  # سوق الصيدليات (إضافة بعد الخطوة 7): exchange_deals/images/reports (idempotent)
    provider_delivery.bind(push_new_order, audit, default_delivery_region, COUNT_SQL["orders"]); provider_delivery.install(c)  # Phase 40: زر «اطلب دليفري» للصيدليات
    products.install(c)  # Phase 2: product_offers + medical sub-categories (idempotent)
    rx.install(c)  # RX schema extensions (idempotent, additive migrations)
    try: c.execute("ALTER TABLE listings ADD COLUMN featured_until INTEGER")  # المرحلة 30: تمييز الإعلان حتى تاريخ (NULL = غير مميز). بعد market.migrate لأنه قد يعيد بناء الجدول
    except sqlite3.OperationalError: pass
    ensure_fts(c)  # المرحلة 30: فهرس بحث trigram للإعلانات (اختياري)
    chat.install(c)  # Phase 4: chat_* tables + listings.contact_mode (idempotent; after market.migrate)
    svc.install(c)  # Phase 5: service_requests (idempotent)
    fcm.install(c)  # Phase 8: fcm_tokens (Android push; idempotent, inert until LAQINO_FCM_SERVICE_ACCOUNT is set)
    c.commit(); c.close()
def listing_clean_fields(c, cat_id, vals):
    """يتحقق من حقول التصنيف ويعيد (البيانات النظيفة، السعر). نفس قواعد النشر القديمة حرفيًا."""
    if not isinstance(vals, dict): raise E(400, "الحقول غير صالحة")
    clean, price = {}, None
    for f in c.execute("SELECT * FROM category_fields WHERE category_id=?", (cat_id,)):
        v = vals.get(f["key"])
        if v in (None, ""):
            if f["required"]: raise E(400, "الحقل مطلوب: " + f["label_ar"])
            continue
        if f["type"] in ("price", "number"):
            try: v = float(v)
            except (TypeError, ValueError): raise E(400, "قيمة غير صحيحة: " + f["label_ar"])
            if v < 0: raise E(400, "قيمة غير صحيحة: " + f["label_ar"])
            if f["type"] == "price": price = v
        elif f["type"] == "select" and v not in json.loads(f["options"]): raise E(400, "اختيار غير صالح: " + f["label_ar"])
        elif f["type"] in ("text", "date") and len(str(v)) > 1000: raise E(400, "النص طويل: " + f["label_ar"])
        clean[f["key"]] = v
    return clean, price
def listing_flags(d, cur_cond=None, cur_neg=0):
    cond = d["condition"] if "condition" in d else cur_cond
    if cond not in (None, "new", "used"): raise E(400, "حالة المنتج: new أو used")
    neg = d["negotiable"] if "negotiable" in d else cur_neg
    if neg is None: neg = 0
    if neg not in (0, 1, True, False): raise E(400, "قابل للتفاوض: true أو false")
    return cond, int(neg)
def listing_image_ids(c, uid, raw, listing_id=None):
    """يتحقق من قائمة صور: ≤8، بلا تكرار، كلها مرفوعة بواسطة هذا المستخدم عبر مسار السوق، وغير مرتبطة بإعلان آخر."""
    if raw is None: return []
    if not isinstance(raw, list) or len(raw) > market.MAX_LISTING_IMAGES or len(set(map(repr, raw))) != len(raw) or not all(isinstance(i, int) and not isinstance(i, bool) for i in raw):
        raise E(400, "قائمة الصور غير صالحة (حتى %d صور بلا تكرار)" % market.MAX_LISTING_IMAGES)
    for fid in raw:
        r = c.execute("SELECT f.owner_id,li.listing_id FROM files f JOIN market_files mf ON mf.file_id=f.id LEFT JOIN listing_images li ON li.file_id=f.id WHERE f.id=?", (fid,)).fetchone()
        if not r or r["owner_id"] != uid or (r["listing_id"] is not None and r["listing_id"] != listing_id): raise E(400, "صورة غير صالحة")
    return raw
def rm_upload(path):
    try: os.remove(os.path.join(UP, path))
    except OSError: pass
class E(Exception):
    def __init__(s, code, msg): s.code, s.msg = code, msg
ACTIVE = "('assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation')"  # phones are shared between the two parties only while an order is in these states
CONTACT_LIMIT = 30  # distinct phone numbers (listings + services + doctors + labs combined) one user may reveal per hour
CONTACT_ACTIONS = ("listing.contact", "service.contact", "doctor.contact", "lab.contact")
def contact_guard(c, u, action, target, msg="تجاوزت الحد المسموح لعرض الأرقام، حاول لاحقًا"):
    """Every public phone number sits behind login + one shared hourly cap, so no section is an easier scraping target than another."""
    cut = int(time.time()) - 3600; t = str(target)
    if c.execute("SELECT 1 FROM audit_log WHERE actor_id=? AND action=? AND target=? AND at>?", (u["id"], action, t, cut)).fetchone(): return
    n = c.execute("SELECT COUNT(DISTINCT action||':'||target) FROM audit_log WHERE actor_id=? AND action IN (%s) AND at>?" % ",".join("?" * len(CONTACT_ACTIONS)), (u["id"],) + CONTACT_ACTIONS + (cut,)).fetchone()[0]
    if n >= CONTACT_LIMIT: raise E(429, msg)
    audit(c, u["id"], action, t); c.commit()
WEAK_ADMIN_PW = {"password", "password1", "password123", "admin123", "admin12345", "adminadmin", "12345678", "123456789", "1234567890", "0123456789", "qwertyuiop", "1q2w3e4r5t", "letmein123", "changeme123", "laqino123", "laqino12345"}
def check_admin_password(pw, phone=""):
    pw = str(pw)
    if len(pw) < 10: raise SystemExit("كلمة مرور المدير قصيرة: الحد الأدنى 10 أحرف (يُنصح بـ 12 فأكثر).")
    if len(set(pw)) < 4 or pw.lower() in WEAK_ADMIN_PW or pw == phone or phone and phone in pw: raise SystemExit("كلمة مرور المدير ضعيفة (متكررة أو شائعة أو تحتوي رقم الهاتف). اختر كلمة أخرى.")
    if pw.startswith("ضع-") or "كلمة-قوية" in pw or pw.startswith("XXXX"): raise SystemExit("كلمة مرور المدير ما زالت النص التوضيحي من env.example. اكتب كلمة حقيقية.")
LIMITS = {"orders": 5, "inquiries": 10, "prescriptions": 5, "files": 20}  # per-user caps on open items (server-side abuse guard)
OPEN_ORDERS = "('searching','assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation')"
COUNT_SQL = {
    "orders": "SELECT COUNT(*) FROM delivery_orders WHERE customer_id=? AND status IN " + OPEN_ORDERS,
    "inquiries": "SELECT COUNT(*) FROM medicine_inquiries WHERE customer_id=? AND status='open'",
    "prescriptions": "SELECT COUNT(*) FROM prescriptions WHERE customer_id=? AND status!='closed'",
    # Count only standalone/unattached uploads against the temporary 20-file quota.
    # Once a file is attached to a feature, that feature's own quota/policy applies.
    # This deliberately excludes courier verification documents and avatars too;
    # those were missing here and could permanently exhaust the generic quota.
    "files": "SELECT COUNT(*) FROM files WHERE owner_id=?"
        " AND id NOT IN (SELECT file_id FROM market_files)"
        " AND id NOT IN (SELECT file_id FROM listing_images)"
        " AND id NOT IN (SELECT file_id FROM chat_messages WHERE file_id IS NOT NULL)"
        " AND id NOT IN (SELECT file_id FROM service_request_images)"
        " AND id NOT IN (SELECT file_id FROM prescriptions WHERE file_id IS NOT NULL)"
        " AND id NOT IN (SELECT file_id FROM rx_images)"
        " AND id NOT IN (SELECT file_id FROM courier_documents)"
        " AND id NOT IN (SELECT avatar_file_id FROM couriers WHERE avatar_file_id IS NOT NULL)"
        " AND id NOT IN (SELECT photo_file_id FROM doctors WHERE photo_file_id IS NOT NULL)"
        " AND id NOT IN (SELECT photo_file_id FROM labs WHERE photo_file_id IS NOT NULL)"
        " AND id NOT IN (SELECT file_id FROM product_images)"
        " AND id NOT IN (SELECT file_id FROM exchange_images)"
}
def _exif_orientation(seg):
    """Read only the Orientation tag (1-8) from an APP1 'Exif' payload; None when absent or malformed."""
    try:
        if seg[:6] != b"Exif\0\0": return None
        t = seg[6:]; bo = {b"II": "little", b"MM": "big"}[t[:2]]; i4 = lambda o: int.from_bytes(t[o:o + 4], bo); i2 = lambda o: int.from_bytes(t[o:o + 2], bo)
        if i2(2) != 42: return None
        ifd = i4(4); n = i2(ifd)
        for k in range(min(n, 64)):
            e = ifd + 2 + 12 * k
            if i2(e) == 0x0112 and i2(e + 2) == 3 and i4(e + 4) == 1:
                v = i2(e + 8); return v if 2 <= v <= 8 else None
    except Exception: return None
def strip_image_metadata(raw):
    """Remove EXIF/GPS, XMP, IPTC, comments and trailing data from uploaded JPEG/PNG without re-encoding pixels.
    JPEG keeps ICC/Adobe colour segments and, if the photo was rotated, a minimal EXIF holding only Orientation (so phone photos don't turn sideways).
    Raises ValueError on a malformed file."""
    if raw[:3] == b"\xff\xd8\xff":
        out = bytearray(b"\xff\xd8"); i = 2; n = len(raw); ori = None; keep = []; scans = 0
        while True:
            if i >= n or raw[i] != 0xFF: raise ValueError("jpeg: bad marker")
            while i < n and raw[i] == 0xFF: i += 1  # fill bytes
            if i >= n: raise ValueError("jpeg: truncated")
            mk = raw[i]; i += 1
            if mk == 0xD9:  # EOI: everything after it (appended thumbnails, second images, junk) is discarded
                if not scans: raise ValueError("jpeg: EOI before SOS")
                for k in keep: out += k
                if ori:  # minimal big-endian TIFF: one IFD0 entry, Orientation
                    ex = b"Exif\0\0MM\0*\0\0\0\x08\0\x01\x01\x12\0\x03\0\0\0\x01" + ori.to_bytes(2, "big") + b"\0\0\0\0\0\0"
                    out[2:2] = b"\xff\xe1" + (len(ex) + 2).to_bytes(2, "big") + ex
                return bytes(out + b"\xff\xd9")
            if mk == 0xD8 or 0xD0 <= mk <= 0xD7 or mk == 0x01: continue
            if i + 2 > n: raise ValueError("jpeg: truncated")
            ln = int.from_bytes(raw[i:i + 2], "big")
            if ln < 2 or i + ln > n: raise ValueError("jpeg: bad length")
            seg = raw[i + 2:i + ln]; i += ln
            if mk == 0xE1:
                o = _exif_orientation(seg); ori = o if o else ori
            elif mk in (0xE0, 0xEE) or (mk == 0xE2 and seg[:12] == b"ICC_PROFILE\0") or not 0xE0 <= mk <= 0xFE:  # JFIF, Adobe, ICC, and every non-APPn/COM marker (tables, frame, scan)
                keep.append(bytes([0xFF, mk]) + ln.to_bytes(2, "big") + seg)
            if mk == 0xDA:  # entropy-coded data runs until the next real marker (FF00 is a stuffed byte, FFD0-D7 are restarts); progressive files have several scans
                scans += 1; j = i
                while True:
                    j = raw.find(b"\xff", j)
                    if j < 0 or j + 1 >= n: raise ValueError("jpeg: no EOI")
                    if raw[j + 1] == 0 or 0xD0 <= raw[j + 1] <= 0xD7 or raw[j + 1] == 0xFF: j += 1 if raw[j + 1] == 0xFF else 2; continue
                    break
                keep.append(raw[i:j]); i = j
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        out = bytearray(raw[:8]); i = 8; n = len(raw); first = True
        while i < n:
            if i + 12 > n: raise ValueError("png: truncated chunk")
            ln = int.from_bytes(raw[i:i + 4], "big"); ty = raw[i + 4:i + 8]
            if ln > n or i + 12 + ln > n: raise ValueError("png: bad length")
            if first and ty != b"IHDR": raise ValueError("png: no IHDR")
            first = False
            if ty not in (b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"): out += raw[i:i + 12 + ln]  # drop metadata chunks, keep everything needed to render
            i += 12 + ln
            if ty == b"IEND": return bytes(out)
        raise ValueError("png: no IEND")
    raise ValueError("unsupported")
def check_limit(c, what, uid, msg):
    if c.execute(COUNT_SQL[what], (uid,)).fetchone()[0] >= LIMITS[what]: raise E(429, msg)
PHONE = re.compile(r"^01[0125]\d{8}$")
LOGIN_MAX, LOGIN_WINDOW = 5, 900
REG_PER_IP, REG_PER_IP_WINDOW = int(os.environ.get("LAQINO_REG_PER_HOUR", 5)), 3600
REG_GLOBAL, REG_GLOBAL_WINDOW = int(os.environ.get("LAQINO_REG_PER_DAY", 200)), 86400
# Throttle state lives in SQLite (table `throttle`) so it survives restarts. Keys: "login|ip|phone", "reg|ip", "reg|*".
def throttled(c, key, mx=None, window=None):
    mx = LOGIN_MAX if mx is None else mx; window = LOGIN_WINDOW if window is None else window
    return c.execute("SELECT COUNT(*) FROM throttle WHERE k=? AND ts>?", (key, int(time.time()) - window)).fetchone()[0] >= mx
def note_fail(c, key):
    now = int(time.time())
    c.execute("DELETE FROM throttle WHERE ts<?", (now - 86400,))  # bound table size: nothing is ever counted past 24h
    c.execute("INSERT INTO throttle(k,ts) VALUES(?,?)", (key, now)); c.commit()
def throttle_reset(c, key): c.execute("DELETE FROM throttle WHERE k=?", (key,)); c.commit()
def throttle_clear(c=None):
    own = c is None; c = c or db(); c.execute("DELETE FROM throttle"); c.commit()
    if own: c.close()
PRESENCE_ENFORCED = True  # production default: a courier counts as online only with a fresh heartbeat (legacy tests switch this off via testutil)
def cfg(c, key, default):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    try: return float(r[0]) if r else default
    except ValueError: return default
def is_online(c, cr):
    if not cr["is_available"]: return False
    return (not PRESENCE_ENFORCED) or cr["last_seen"] >= int(time.time()) - int(cfg(c, "heartbeat_ttl", 45))
def default_delivery_region(c):
    """المنطقة الداخلية لطلب التوصيل (المرحلة 28): مركز الرياض إن وُجد وكان مفعّلًا، وإلا أول مركز مفعّل، وإلا None."""
    r = c.execute("SELECT id FROM regions WHERE slug='eg-kfs-riyad' AND is_active=1").fetchone() or c.execute("SELECT id FROM regions WHERE level='markaz' AND is_active=1 ORDER BY id LIMIT 1").fetchone()
    return r[0] if r else None
def region_fee(c, rid):
    """أجرة التوصيل الافتراضية لمنطقة (مع حدّيها min/max): المنطقة نفسها ثم أقرب منطقة أعلى منها لها أجرة (قرية/حي ← مركز ← محافظة).
    كانت المطابقة تامة فقط، فالعميل الذي يختار قرية تابعة لمركز مسعَّر يرى «الدليفري غير متاح» رغم أن المندوب (تغطيته تشمل التابعات) متصل.
    المنطقة المطلوبة يجب أن تكون مفعّلة. يرجع {"fee": ..} أو None."""
    try: n = int(rid)
    except (TypeError, ValueError): return None
    r = c.execute("SELECT is_active FROM regions WHERE id=?", (n,)).fetchone()
    if not r or not r[0]: return None
    for _ in range(8):
        f = c.execute("SELECT rf.fee,r.parent_id,rf.min_fee,rf.max_fee FROM regions r LEFT JOIN region_fees rf ON rf.region_id=r.id WHERE r.id=?", (n,)).fetchone()
        if not f: return None
        if f[0] is not None: return {"fee": f[0], "min": f[2] if f[2] is not None else f[0], "max": f[3] if f[3] is not None else f[0]}  # بلا حدود مخزّنة = أجرة ثابتة لا يعدّلها المندوب
        if f[1] is None: return None
        n = f[1]
    return None
def commission_for(c, fee, ct=None, cv=None):
    """عمولة لاقينو لأجرة معيّنة بنفس معادلة النظام الحالي (ثابتة أو نسبة). نوع/قيمة العمولة تُثبَّتان على الطلب عند إنشائه (comm_type/comm_value) فلا يغيّرهما تعديل الإعدادات لاحقًا؛
    الطلبات القديمة بلا لقطة تستعمل الإعدادات الحالية. تُحسب عند الاقتراح وتُخصم مرة واحدة فقط عند الإغلاق عبر charge_commission."""
    if ct is None:
        cm = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; ct, cv = cm.get("commission_type"), cm.get("commission_value", 0)
    return round(float(cv) * (fee / 100 if ct == "percent" else 1), 2)
COVER = "(WITH RECURSIVE r(id) AS (SELECT ? UNION SELECT g.id FROM regions g JOIN r ON g.parent_id=r.id) SELECT id FROM r)"
LEDGER_SQL = ("SELECT kind,amount,ref_type,ref_id,created_at,NULL reason FROM wallet_entries WHERE user_id=? UNION ALL SELECT 'adjustment',amount,'adjustment',id,created_at,reason FROM wallet_adjustments WHERE user_id=? "
              "ORDER BY created_at DESC, ref_id DESC LIMIT %d")  # one merged ledger: ordinary entries + admin adjustments
def wallet_free(c, uid):
    bal = c.execute("SELECT (SELECT COALESCE(SUM(amount),0) FROM wallet_entries WHERE user_id=?)+(SELECT COALESCE(SUM(amount),0) FROM wallet_adjustments WHERE user_id=?)", (uid, uid)).fetchone()[0]
    held = c.execute("SELECT COALESCE(SUM(commission),0) FROM delivery_orders o WHERE courier_id=? AND status NOT IN('completed','cancelled','disputed') AND NOT EXISTS(SELECT 1 FROM wallet_entries w WHERE w.kind='commission' AND w.ref_type='order' AND w.ref_id=o.id)", (uid,)).fetchone()[0]  # المرحلة 28: العمولة المخصومة فعلًا (عند التسليم) لا تُحجز مرة ثانية
    return bal, bal - held
# ---- Web Push (VAPID, no payload): wakes a courier's device when a new order appears. The push carries NO data; the app fetches orders itself after login.
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com")  # known push services only (SSRF guard)
def _b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def push_endpoint_ok(url):
    from urllib.parse import urlparse as _up
    try: p = _up(url)
    except ValueError: return False
    if len(url) > 600 or not p.hostname: return False
    if os.environ.get("LAQINO_PUSH_ALLOW_ANY") == "1": return p.scheme in ("http", "https")  # tests only
    return p.scheme == "https" and any(p.hostname == h or p.hostname.endswith("." + h) for h in PUSH_HOSTS)
def vapid_keys(c):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization as ser
    r = c.execute("SELECT priv,pub FROM push_keys WHERE id=1").fetchone()
    if r: return r["priv"], r["pub"]
    k = ec.generate_private_key(ec.SECP256R1())
    priv = _b64u(k.private_numbers().private_value.to_bytes(32, "big")); pub = _b64u(k.public_key().public_bytes(ser.Encoding.X962, ser.PublicFormat.UncompressedPoint))
    c.execute("INSERT OR IGNORE INTO push_keys VALUES(1,?,?)", (priv, pub)); c.commit()
    r = c.execute("SELECT priv,pub FROM push_keys WHERE id=1").fetchone(); return r["priv"], r["pub"]
def vapid_header(priv, pub, endpoint):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from urllib.parse import urlparse as _up
    pr = _up(endpoint); aud = pr.scheme + "://" + pr.netloc
    head = _b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode()); body = _b64u(json.dumps({"aud": aud, "exp": int(time.time()) + 12 * 3600, "sub": os.environ.get("LAQINO_VAPID_SUBJECT", "mailto:admin@example.com")}, separators=(",", ":")).encode())
    key = ec.derive_private_key(int.from_bytes(base64.urlsafe_b64decode(priv + "=="), "big"), ec.SECP256R1())
    r, s_ = decode_dss_signature(key.sign((head + "." + body).encode(), ec.ECDSA(hashes.SHA256())))
    return "vapid t=%s.%s.%s, k=%s" % (head, body, _b64u(r.to_bytes(32, "big") + s_.to_bytes(32, "big")), pub)
def push_send(endpoint, priv, pub, ttl):
    import urllib.request, urllib.error
    rq = urllib.request.Request(endpoint, b"", {"Authorization": vapid_header(priv, pub, endpoint), "TTL": str(int(ttl)), "Urgency": "high", "Content-Length": "0"}, method="POST")
    try:
        with urllib.request.urlopen(rq, timeout=6) as r: return r.status
    except urllib.error.HTTPError as e: return e.code
    except Exception: return 0
def push_targets(c, oid):
    """Couriers to wake for an order: approved, covering the region, chose 'online' recently (heartbeat may be stale because the app is closed), enough wallet for the commission, not the customer, not already rejected it. Waking is NOT dispatch: offers/accept still require a fresh heartbeat."""
    o = c.execute("SELECT customer_id,region_id,commission FROM delivery_orders WHERE id=? AND status='searching'", (oid,)).fetchone()
    if not o: return []
    reach = int(time.time()) - int(cfg(c, "push_reach_hours", 12)) * 3600; out = []
    for r in c.execute("SELECT cr.user_id FROM couriers cr WHERE cr.status='approved' AND cr.is_available=1 AND cr.last_seen>=? AND cr.user_id!=? AND (cr.region_id IN " + COVER_REV + " OR cr.region_id IN " + COVER + ") AND (EXISTS(SELECT 1 FROM push_subs p WHERE p.user_id=cr.user_id) OR EXISTS(SELECT 1 FROM fcm_tokens ft WHERE ft.user_id=cr.user_id)) AND NOT EXISTS(SELECT 1 FROM order_offers f WHERE f.order_id=? AND f.courier_id=cr.user_id AND f.status IN('rejected','lost'))", (reach, o["customer_id"], o["region_id"], o["region_id"], oid)).fetchall():
        if wallet_free(c, r["user_id"])[1] >= o["commission"]: out.append(r["user_id"])
    return out
COVER_REV = "(WITH RECURSIVE r(id) AS (SELECT ? UNION SELECT g.parent_id FROM regions g JOIN r ON g.id=r.id WHERE g.parent_id IS NOT NULL) SELECT id FROM r)"  # courier region must be the order region or one of its ancestors
# ---- Repeating push (phase 17): the wake-up push is re-sent every `push_repeat_secs` (default 25s; 0 = off) while the order is still searching,
# then ONE final "sweep" push when it is accepted / cancelled / expired so devices drop the alert. The push still carries NO data:
# sw.js asks /api/push/state how many orders are still waiting for that device's courier and shows or clears the alert accordingly.
PUSH_MIN_GAP = 5          # seconds, floor for push_repeat_secs (lowered only by tests)
PUSH_MAX_ROUNDS = 20      # hard cap of repeats per order
_PUSH_LOOPS, _PUSH_LOCK = {}, threading.Lock()
def push_pending(c, uid):
    """How many searching orders are currently waiting for this courier (same eligibility as push_targets). Count only, never order data."""
    cr = c.execute("SELECT region_id,last_seen FROM couriers WHERE user_id=? AND status='approved' AND is_available=1", (uid,)).fetchone()
    now = int(time.time())
    if not cr or cr["last_seen"] < now - int(cfg(c, "push_reach_hours", 12)) * 3600: return 0
    win = int(cfg(c, "search_timeout", 300)); free = wallet_free(c, uid)[1]; n = 0
    for o in c.execute("SELECT o.commission FROM delivery_orders o WHERE o.status='searching' AND o.courier_id IS NULL AND o.customer_id!=? AND (o.region_id IN " + COVER + " OR o.region_id IN " + COVER_REV + ") AND (CASE WHEN o.search_started_at>0 THEN o.search_started_at ELSE o.created_at END)>? AND NOT EXISTS(SELECT 1 FROM order_offers f WHERE f.order_id=o.id AND f.courier_id=? AND f.status IN('rejected','lost'))", (uid, cr["region_id"], cr["region_id"], now - win, uid)).fetchall():
        if free >= o["commission"]: n += 1
    return n
def _push_to_users(c, uids, ttl, native=True, kind="order"):
    """Web Push (data-less) to every subscribed device, then (Phase 8) FCM to the user's Android app tokens. native=False for the final sweep: a generic FCM notification cannot be withdrawn."""
    priv, pub = vapid_keys(c); n = 0
    for uid in uids:
        for sub in c.execute("SELECT endpoint FROM push_subs WHERE user_id=?", (uid,)).fetchall():
            st = push_send(sub["endpoint"], priv, pub, ttl)
            if st in (404, 410): c.execute("DELETE FROM push_subs WHERE endpoint=?", (sub["endpoint"],)); c.commit()
            elif 200 <= st < 300: n += 1
    if native: n += fcm.send(c, uids, ttl, kind)
    return n
def medical_push(uid, kind="rx.update"):
    """Wake the user's devices for an unread medical notification. Push payload is generic and contains no request details."""
    def run():
        try:
            time.sleep(0.25)  # allow the transaction that inserted the notification to commit before devices re-check counts
            c = db()
            try:
                if c.execute("SELECT 1 FROM push_subs WHERE user_id=?", (uid,)).fetchone() or fcm.has_tokens(c, uid):
                    _push_to_users(c, [uid], 3600, kind="medical")
            finally: c.close()
        except Exception as e: print("medical push failed:", e, file=sys.stderr)
    threading.Thread(target=run, daemon=True).start()
rx.push_hook = medical_push


def chat_push(uid):
    """Phase 4: wakes the recipient's devices for a new chat message. Data-less like the courier push: sw.js asks /api/push/state for the unread COUNT. Best effort, background thread."""
    def run():
        try:
            c = db()
            try:
                if c.execute("SELECT 1 FROM push_subs WHERE user_id=?", (uid,)).fetchone() or fcm.has_tokens(c, uid): _push_to_users(c, [uid], 3600, kind="chat")
            finally: c.close()
        except Exception: pass
    threading.Thread(target=run, daemon=True).start()
chat.push_hook = chat_push
chat.UPLOADS = UP  # صور المحادثة تُحفظ في مجلد الرفع نفسه
exchange.UP = UP
svc.UPLOADS = UP  # صور طلبات الخدمة (الخطوة 2) في مجلد الرفع نفسه
def push_stop_order(oid):
    """Called right after an order is accepted / cancelled by the customer: wakes the repeat loop so it sends the final sweep immediately."""
    with _PUSH_LOCK: st = _PUSH_LOOPS.get(oid)
    if st: st["stop"] = True; st["evt"].set()
def push_new_order(oid):
    def run():
        st = gen = None
        try:
            c = db(); targets = push_targets(c, oid)
            if not targets: c.close(); return  # nothing to send: avoid any DB write that could contend with request handlers
            ttl = int(cfg(c, "search_timeout", 300)); gap = float(cfg(c, "push_repeat_secs", 25)); n = _push_to_users(c, targets, ttl)
            audit(c, None, "push.order", str(oid), {"sent": n}); c.commit(); c.close()
            if gap <= 0: return  # repeating switched off: behaves exactly like phase 10 (one wake-up push)
            gap = max(gap, PUSH_MIN_GAP)
            with _PUSH_LOCK:  # a retry-search while a loop is alive takes the loop over (the old one exits silently)
                st = _PUSH_LOOPS.get(oid)
                if st: st["gen"] += 1; st["evt"].set(); st["evt"] = threading.Event(); st["stop"] = False
                else: st = _PUSH_LOOPS[oid] = {"gen": 0, "notified": set(), "evt": threading.Event(), "stop": False}
                gen, evt = st["gen"], st["evt"]; st["notified"].update(targets)
            rounds = 0
            while rounds < PUSH_MAX_ROUNDS:
                evt.wait(gap)
                with _PUSH_LOCK: superseded = _PUSH_LOOPS.get(oid) is not st or st["gen"] != gen
                if superseded: return
                c = db()
                try:
                    o = c.execute("SELECT status,created_at,search_started_at FROM delivery_orders WHERE id=?", (oid,)).fetchone(); now = int(time.time()); win = int(cfg(c, "search_timeout", 300))
                    if not o: break
                    left = (o["search_started_at"] if o["search_started_at"] > 0 else o["created_at"]) + win - now
                    if o["status"] != "searching" or st["stop"] or left <= 0: break
                    tg = push_targets(c, oid)  # re-evaluated every round: a courier who went offline / rejected / ran out of balance is no longer woken
                    if tg: _push_to_users(c, tg, max(30, left)); st["notified"].update(tg)
                finally: c.close()
                rounds += 1
            c = db()
            try:
                n = _push_to_users(c, sorted(st["notified"]), 60, native=False); audit(c, None, "push.stop", str(oid), {"rounds": rounds, "swept": n}); c.commit()
            finally: c.close()
        except Exception as e: print("PUSH ERR", e, file=sys.stderr)
        finally:
            if st is not None:
                with _PUSH_LOCK:
                    if _PUSH_LOOPS.get(oid) is st and st["gen"] == gen: del _PUSH_LOOPS[oid]
    threading.Thread(target=run, daemon=True).start()
_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})
def norm_ar(t):
    t = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", str(t or "")).translate(_AR).lower()
    t = re.sub(r"^(دكتور|دكتوره|د\.|د)\s+", "", re.sub(r"\s+", " ", t).strip())
    return t.strip()
bulk_import.norm_ar, bulk_import.audit = norm_ar, audit  # حقن تطبيع الاسم وسجل التدقيق (المرحلة 23)
def toint(v, default=0):
    try: return int(v)
    except (TypeError, ValueError): raise E(400, "قيمة رقمية غير صحيحة")
# ---- WhatsApp reverse verification: the CUSTOMER sends a message containing a one-time code to Laqino's WhatsApp number; the sender's number (authenticated by WhatsApp) proves ownership. Free: no outbound messages.
WA_NUMBER = os.environ.get("LAQINO_WA_NUMBER", "01017011170")  # Laqino's WhatsApp number (local format)
WA_CODE_TTL, WA_DONE_TTL, WA_MAX_TRIES = 600, 1800, 5  # code valid 10 min; a verified phone may register/reset within 30 min
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
def wa_required(): return os.environ.get("LAQINO_WA_VERIFY", "0") == "1"  # off by default so dev/tests work; set LAQINO_WA_VERIFY=1 in production
def wa_to_local(wa_id):
    """WhatsApp sender id (e.g. 201012345678) -> local Egyptian mobile (01012345678), or None."""
    d = re.sub(r"\D", "", str(wa_id or "").translate(AR_DIGITS))
    if d.startswith("20") and len(d) == 12: d = "0" + d[2:]
    return d if PHONE.match(d) else None
def wa_codes(text): return re.findall(r"(?<!\d)\d{6}(?!\d)", str(text or "").translate(AR_DIGITS))  # Arabic-Indic digits accepted
def wa_link(code): return "https://wa.me/20%s?text=%s" % (WA_NUMBER.lstrip("0"), quote("كود التحقق من لاقينو: " + code))
def wa_ingest(c, wa_from, text):
    """An incoming WhatsApp text from `wa_from`: marks matching pending verifications of THAT sender's number as verified. Returns True if something was verified."""
    ph = wa_to_local(wa_from); codes = wa_codes(text)
    if not ph or not codes: return False
    now = int(time.time()); hit = False
    for r in c.execute("SELECT purpose,code FROM phone_verifications WHERE phone=? AND verified_at IS NULL AND expires>? AND attempts<?", (ph, now, WA_MAX_TRIES)).fetchall():
        if any(hmac.compare_digest(x, r["code"]) for x in codes):
            if c.execute("UPDATE phone_verifications SET verified_at=? WHERE phone=? AND purpose=? AND verified_at IS NULL", (now, ph, r["purpose"])).rowcount: hit = True; audit(c, None, "phone.verified", ph, {"purpose": r["purpose"], "via": "whatsapp"})
        else: c.execute("UPDATE phone_verifications SET attempts=attempts+1 WHERE phone=? AND purpose=?", (ph, r["purpose"]))
    c.commit(); return hit
def wa_ingest_manual(c, ph, purpose, code):
    r = c.execute("SELECT code FROM phone_verifications WHERE phone=? AND purpose=? AND verified_at IS NULL AND expires>? AND attempts<?", (ph, purpose, int(time.time()), WA_MAX_TRIES)).fetchone()
    if not r: return False
    if not hmac.compare_digest(code, r["code"]): c.execute("UPDATE phone_verifications SET attempts=attempts+1 WHERE phone=? AND purpose=?", (ph, purpose)); c.commit(); return False
    return bool(c.execute("UPDATE phone_verifications SET verified_at=? WHERE phone=? AND purpose=? AND verified_at IS NULL", (int(time.time()), ph, purpose)).rowcount)
def wa_is_verified(c, ph, purpose): return bool(c.execute("SELECT 1 FROM phone_verifications WHERE phone=? AND purpose=? AND verified_at>?", (ph, purpose, int(time.time()) - WA_DONE_TTL)).fetchone())
# Content-Security-Policy: pages use inline scripts/handlers, so script-src keeps 'unsafe-inline'; the policy still blocks
# foreign script hosts, plugins, base-tag hijack, cross-site form posts, framing and any request leaving our own origin.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; "
       "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
LEGAL_PAGES = {"/privacy": "privacy.html", "/terms": "terms.html", "/delete-account": "delete-account.html", "/contact": "contact.html"}
def LEGAL_VARS(): return {"CONTACT_NAME": os.environ.get("LAQINO_CONTACT_NAME", "Laqino"), "SUPPORT_EMAIL": os.environ.get("LAQINO_SUPPORT_EMAIL", "Laqino100@gmail.com"), "SUPPORT_WA": WA_NUMBER, "UPDATED": "أكتوبر 2026"}
class H(BaseHTTPRequestHandler):
    server_version, sys_version = "Laqino", ""  # do not advertise the Python/BaseHTTP version in the Server header
    timeout = 30  # seconds: an idle/slow-loris connection is dropped instead of holding a thread forever
    def send(self, code, obj, ctype="application/json", raw=None, extra=None):
        b = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "text" in ctype else ""))
        self.send_header("Content-Length", str(len(b))); self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "DENY"); self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", CSP)
        if extra:
            for k, v in extra.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def real_ip(self):
        """Client address. X-Forwarded-For is honoured only when the TCP peer is a local/private proxy (Caddy).
        Returns None for a direct loopback connection (local dev/tests): there is no remote client to limit."""
        peer = self.client_address[0]
        try: pip = ipaddress.ip_address(peer)
        except ValueError: return peer
        if not (pip.is_loopback or pip.is_private): return peer
        xff = (self.headers.get("X-Forwarded-For") or "").split(",")[-1].strip()
        try: return str(ipaddress.ip_address(xff)) if xff else (None if pip.is_loopback else peer)
        except ValueError: return peer
    def lip(self):
        """IP used in throttle keys: the real client behind the proxy (XFF from a private peer only), else the TCP peer (local dev/tests)."""
        return self.real_ip() or self.client_address[0]
    def body(self, lim=100_000):
        try: n = int(self.headers.get("Content-Length") or 0)
        except ValueError: raise E(400, "بيانات غير صالحة")
        if n < 0: raise E(400, "بيانات غير صالحة")
        if n > lim: raise E(413, "الطلب كبير جدًا")
        try: d = json.loads(self.rfile.read(n) or b"{}")
        except Exception: raise E(400, "بيانات غير صالحة")
        if not isinstance(d, dict): raise E(400, "بيانات غير صالحة")  # قائمة/نص/null كانت تسبب خطأ 500 داخل المسارات
        return d
    def user(self, c):
        tok = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        if not tok: return None
        r = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?", (hashlib.sha256(tok.encode()).hexdigest(), int(time.time()))).fetchone()
        return r
    def need(self, u, *roles):
        if not u: raise E(401, "سجّل الدخول أولًا")
        if roles and u["role"] not in roles: raise E(403, "ليس لديك صلاحية")
        return u
    def read_image(self):
        d = self.body(6_000_000); self.last_body = d  # last_body: يقرأ منه chat.py حقل text المرافق للصورة (الجسم يُقرأ مرة واحدة)
        try: raw = base64.b64decode(str(d.get("data", "")), validate=True)
        except Exception: raise E(400, "ملف غير صالح")
        mime = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/png" if raw[:4] == b"\x89PNG" else None
        if not mime: raise E(400, "الصيغة المدعومة: JPG أو PNG")
        if len(raw) > 4_000_000: raise E(413, "الصورة كبيرة (الحد 4 ميجابايت)")
        try: raw = strip_image_metadata(raw)
        except ValueError: raise E(400, "الصورة تالفة أو غير مدعومة، جرّب صورة أخرى")
        return raw, mime
    def route(self, method):
        p = urlparse(self.path); q = parse_qs(p.query); path = p.path
        if not path.startswith("/api/"):
            if path == "/healthz":
                try: c = db(); c.execute("SELECT 1").fetchone(); c.close()
                except sqlite3.Error: return self.send(503, {"ok": False})
                return self.send(200, {"ok": True})
            if path in LEGAL_PAGES:  # صفحات قانونية عامة (Google Play): تُقدَّم بدون تسجيل دخول مع استبدال اسم/إيميل التواصل من الإعدادات
                try: html = open(os.path.join(ROOT, LEGAL_PAGES[path]), encoding="utf-8").read()
                except OSError: return self.send(404, {"error": "غير موجود"})
                for k, v in LEGAL_VARS().items(): html = html.replace("{{" + k + "}}", v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
                return self.send(200, None, "text/html", html.encode("utf-8"), {"Cache-Control": "no-cache"})
            f = os.path.realpath(os.path.join(ROOT, "index.html" if path == "/" else path.lstrip("/")))
            if os.path.commonpath([f, ROOT]) != ROOT or not os.path.isfile(f): return self.send(404, {"error": "غير موجود"})
            # the service worker and the html shell must always revalidate so updates reach installed apps; assets may be cached briefly
            cc = "no-cache" if f.endswith((".js", ".html", ".css", ".webmanifest")) else "public, max-age=3600"
            return self.send(200, None, MIME.get(os.path.splitext(f)[1]) or mimetypes.guess_type(f)[0] or "application/octet-stream", open(f, "rb").read(), {"Cache-Control": cc})
        c = db()
        try:
            u = self.user(c)
            if notif.handle(self, c, u, method, path, q): return
            if gsearch.handle(self, c, u, method, path, q): return
            if products.handle(self, c, u, method, path, q): return
            if provider_delivery.handle(self, c, u, method, path, q): return
            if exchange.handle(self, c, u, method, path, q): return
            if rx.handle(self, c, u, method, path, q): return
            if chat.handle(self, c, u, method, path, q): return
            if svc.handle(self, c, u, method, path, q): return
            if overview.handle(self, c, u, method, path, q): return
            if fcm.handle(self, c, u, method, path, q): return
            if lsocial.handle(self, c, u, method, path, q): return
            if bulk_import.handle(self, c, u, method, path, q): return
            if method == "GET" and path == "/api/regions":
                pid = q.get("parent_id", [None])[0]; act = q.get("all", ["0"])[0] == "1" and u and u["role"] in ("admin", "staff")
                sql = "SELECT id,parent_id,level,slug,name_ar,is_active,lat,lng FROM regions WHERE " + ("parent_id IS ?" if pid is None else "parent_id=?") + ("" if act else " AND is_active=1") + " ORDER BY sort,name_ar"
                return self.send(200, [dict(r) for r in c.execute(sql, (pid,))])
            if method == "POST" and path == "/api/verify/start":  # customer asks for a code to send to Laqino's WhatsApp
                d = self.body(); ph, purpose = str(d.get("phone", "")), str(d.get("purpose", "register"))
                if not PHONE.match(ph) or purpose not in ("register", "reset"): raise E(400, "رقم الهاتف غير صحيح")
                rip = self.real_ip(); ks = ["wav|" + ph] + (["wav|ip|" + rip] if rip is not None else [])
                if throttled(c, ks[0], 5, 3600) or (len(ks) > 1 and throttled(c, ks[1], 20, 3600)): raise E(429, "محاولات كثيرة، حاول لاحقًا")
                if purpose == "register" and c.execute("SELECT 1 FROM users WHERE phone=?", (ph,)).fetchone(): raise E(409, "الرقم مسجّل بالفعل")
                for k in ks: note_fail(c, k)
                code = "%06d" % secrets.randbelow(10 ** 6); now = int(time.time())  # reset: identical answer whether or not the phone has an account (no enumeration)
                c.execute("INSERT INTO phone_verifications(phone,purpose,code,expires,attempts,verified_at,created_at) VALUES(?,?,?,?,0,NULL,?) ON CONFLICT(phone,purpose) DO UPDATE SET code=excluded.code,expires=excluded.expires,attempts=0,verified_at=NULL,created_at=excluded.created_at", (ph, purpose, code, now + WA_CODE_TTL, now)); c.commit()
                return self.send(200, {"code": code, "wa_number": WA_NUMBER, "wa_link": wa_link(code), "expires_in": WA_CODE_TTL})
            if method == "POST" and path == "/api/verify/status":
                d = self.body(); ph, purpose = str(d.get("phone", "")), str(d.get("purpose", "register"))
                if not PHONE.match(ph) or purpose not in ("register", "reset"): raise E(400, "رقم الهاتف غير صحيح")
                return self.send(200, {"verified": wa_is_verified(c, ph, purpose)})
            if method == "GET" and path == "/api/wa/webhook":  # Meta Cloud API subscription handshake
                tok = os.environ.get("LAQINO_WA_VERIFY_TOKEN", "")
                if tok and q.get("hub.mode", [""])[0] == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", [""])[0], tok): return self.send(200, None, "text/plain", q.get("hub.challenge", [""])[0].encode())
                raise E(403, "مرفوض")
            if method == "POST" and path == "/api/wa/webhook":  # incoming WhatsApp messages (Meta Cloud API); HMAC-signed with the app secret
                try: n = int(self.headers.get("Content-Length") or 0)
                except ValueError: raise E(400, "بيانات غير صالحة")
                if n < 0 or n > 1_000_000: raise E(413, "الطلب كبير جدًا")
                raw = self.rfile.read(n); sec = os.environ.get("LAQINO_WA_APP_SECRET", "")
                sig = (self.headers.get("X-Hub-Signature-256") or "").removeprefix("sha256=")
                if not sec or not hmac.compare_digest(hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest(), sig): raise E(403, "توقيع غير صحيح")
                try: data = json.loads(raw or b"{}")
                except ValueError: raise E(400, "بيانات غير صالحة")
                for en in data.get("entry", []) if isinstance(data, dict) else []:
                    for ch in en.get("changes", []) if isinstance(en, dict) else []:
                        for m in ((ch.get("value") or {}).get("messages") or []) if isinstance(ch, dict) else []:
                            if isinstance(m, dict) and m.get("type") == "text": wa_ingest(c, m.get("from"), (m.get("text") or {}).get("body"))
                return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/register":
                d = self.body(); ph, nm, pw = str(d.get("phone", "")), str(d.get("name", "")).strip(), str(d.get("password", ""))
                if not PHONE.match(ph): raise E(400, "رقم الهاتف غير صحيح")
                if not nm or len(pw) < 8: raise E(400, "الاسم مطلوب وكلمة المرور 8 أحرف على الأقل")
                if wa_required() and not wa_is_verified(c, ph, "register"): raise E(403, "تحقق من رقمك عبر واتساب أولًا")
                rip = self.real_ip()
                if rip is not None:
                    if throttled(c, "reg|" + rip, REG_PER_IP, REG_PER_IP_WINDOW) or throttled(c, "reg|*", REG_GLOBAL, REG_GLOBAL_WINDOW): raise E(429, "محاولات تسجيل كثيرة، حاول لاحقًا")
                    note_fail(c, "reg|" + rip); note_fail(c, "reg|*")
                s = secrets.token_hex(16)
                try: c.execute("INSERT INTO users(phone,name,pw_hash,salt,created_at) VALUES(?,?,?,?,?)", (ph, nm, hp(pw, s), s, int(time.time())))
                except sqlite3.IntegrityError: raise E(409, "الرقم مسجّل بالفعل")
                c.execute("DELETE FROM phone_verifications WHERE phone=? AND purpose='register'", (ph,)); c.commit(); return self.send(201, {"ok": True})
            if method == "POST" and path == "/api/login":
                d = self.body(); key = "login|%s|%s" % (self.lip(), d.get("phone", "")); gkey = "loginp|" + str(d.get("phone", ""))[:32]  # per-IP+phone limit stops one client; the looser per-phone limit stops distributed guessing without letting one stranger lock a victim out
                rip_ = self.real_ip(); ikey = ("loginip|" + rip_) if rip_ is not None else None  # per-IP cap across ALL phones (password spraying); skipped for direct loopback (dev/tests)
                if throttled(c, key) or throttled(c, gkey, 25) or (ikey and throttled(c, ikey, 40)): raise E(429, "محاولات كثيرة، حاول بعد 15 دقيقة")
                r = c.execute("SELECT * FROM users WHERE phone=?", (str(d.get("phone", "")),)).fetchone()
                ok = r and hmac.compare_digest(hp(str(d.get("password", "")), r["salt"]), r["pw_hash"])
                if not ok: note_fail(c, key); note_fail(c, gkey); (ikey and note_fail(c, ikey)); raise E(401, "بيانات الدخول غير صحيحة")
                throttle_reset(c, key); throttle_reset(c, gkey)
                tok = secrets.token_urlsafe(32)
                c.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(tok.encode()).hexdigest(), r["id"], int(time.time()) + 30 * 86400)); c.commit()
                return self.send(200, {"token": tok})
            if method == "POST" and path == "/api/password/reset":  # public: phone + one-time code issued by an admin after identity check
                d = self.body(); ph, code, npw = str(d.get("phone", "")).strip(), str(d.get("code", "")).strip(), str(d.get("new_password", ""))
                if len(npw) < 8: raise E(400, "كلمة المرور 8 أحرف على الأقل")
                keys = ("pwr|%s|%s" % (self.lip(), ph), "pwr|" + ph)
                if throttled(c, keys[0], 5, 900) or throttled(c, keys[1], 10, 3600): raise E(429, "محاولات كثيرة، حاول لاحقًا أو تواصل مع الإدارة")
                bad = E(400, "الكود غير صحيح أو منتهي، اطلب كودًا جديدًا من الإدارة")
                if d.get("wa") in (1, True):  # self-service: the phone proved ownership by messaging Laqino on WhatsApp (admin accounts excluded, as with admin codes)
                    t = c.execute("SELECT u.id FROM users u WHERE u.phone=? AND u.role!='admin' AND EXISTS(SELECT 1 FROM phone_verifications v WHERE v.phone=u.phone AND v.purpose='reset' AND v.verified_at>?)", (ph, int(time.time()) - WA_DONE_TTL)).fetchone()
                    if not t: [note_fail(c, k) for k in keys]; raise E(400, "لم يتم التحقق من الرقم عبر واتساب أو انتهت صلاحيته")
                    sl = secrets.token_hex(16); c.execute("UPDATE users SET pw_hash=?,salt=? WHERE id=?", (hp(npw, sl), sl, t["id"])); c.execute("DELETE FROM sessions WHERE user_id=?", (t["id"],)); c.execute("DELETE FROM phone_verifications WHERE phone=? AND purpose='reset'", (ph,))
                    audit(c, t["id"], "password.reset", str(t["id"]), {"via": "whatsapp"}); c.commit(); [throttle_reset(c, k) for k in keys]; throttle_reset(c, "login|%s|%s" % (self.lip(), ph)); return self.send(200, {"ok": True})
                r = c.execute("SELECT p.*,u.id uid FROM users u JOIN password_resets p ON p.user_id=u.id WHERE u.phone=?", (ph,)).fetchone()
                if not r: hp(code, "00" * 16); [note_fail(c, k) for k in keys]; raise bad  # dummy hash: same timing whether or not the phone exists
                if r["expires"] < int(time.time()) or r["attempts"] >= 5: c.execute("DELETE FROM password_resets WHERE user_id=?", (r["uid"],)); c.commit(); raise bad
                if not hmac.compare_digest(hp(code, r["salt"]), r["code_hash"]):
                    c.execute("UPDATE password_resets SET attempts=attempts+1 WHERE user_id=?", (r["uid"],)); [note_fail(c, k) for k in keys]; raise bad
                if not c.execute("DELETE FROM password_resets WHERE user_id=? AND code_hash=?", (r["uid"], r["code_hash"])).rowcount: raise bad  # one-time: a concurrent second use loses
                sl = secrets.token_hex(16); c.execute("UPDATE users SET pw_hash=?,salt=? WHERE id=?", (hp(npw, sl), sl, r["uid"])); c.execute("DELETE FROM sessions WHERE user_id=?", (r["uid"],))
                audit(c, r["uid"], "password.reset", str(r["uid"])); c.commit(); [throttle_reset(c, k) for k in keys]; throttle_reset(c, "login|%s|%s" % (self.lip(), ph)); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/logout":
                self.need(u); c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256((self.headers.get("Authorization") or "").removeprefix("Bearer ").encode()).hexdigest(),)); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/me":
                self.need(u); return self.send(200, {k: u[k] for k in ("id", "name", "phone", "role", "region_id")})
            if method == "POST" and path == "/api/me/password":
                self.need(u); d = self.body(); key = "chg|%d" % u["id"]
                if throttled(c, key, 5, 900): raise E(429, "محاولات كثيرة، حاول بعد 15 دقيقة")
                old, npw = str(d.get("old_password", "")), str(d.get("new_password", ""))
                if not hmac.compare_digest(hp(old, u["salt"]), u["pw_hash"]): note_fail(c, key); raise E(403, "كلمة المرور الحالية غير صحيحة")
                if len(npw) < 8 or npw == old: raise E(400, "كلمة المرور الجديدة 8 أحرف على الأقل ومختلفة عن الحالية")
                sl = secrets.token_hex(16); cur = hashlib.sha256((self.headers.get("Authorization") or "").removeprefix("Bearer ").encode()).hexdigest()
                c.execute("UPDATE users SET pw_hash=?,salt=? WHERE id=?", (hp(npw, sl), sl, u["id"])); c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (u["id"], cur))  # other devices are logged out
                audit(c, u["id"], "password.change", str(u["id"])); c.commit(); throttle_reset(c, key); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/me/delete":  # حذف الحساب بإخفاء الهوية (يتطلب كلمة المرور)
                self.need(u); d = self.body(); key = "del|%d" % u["id"]
                if throttled(c, key, 5, 900): raise E(429, "محاولات كثيرة، حاول بعد 15 دقيقة")
                if not hmac.compare_digest(hp(str(d.get("password", "")), u["salt"]), u["pw_hash"]): note_fail(c, key); raise E(403, "كلمة المرور غير صحيحة")
                try: account.check_allowed(c, u)
                except account.Blocked as e: raise E(e.code, e.msg)
                paths = account.delete_account(c, u["id"], UP)
                audit(c, u["id"], "account.delete", str(u["id"])); c.commit(); throttle_reset(c, key); account.remove_files(paths)
                return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/me/region":
                self.need(u); rid = self.body().get("region_id")
                if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone(): raise E(400, "المنطقة غير مفعّلة")
                c.execute("UPDATE users SET region_id=? WHERE id=?", (rid, u["id"])); c.commit(); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/location/resolve":  # بلا تسجيل دخول (التطبيق يطلب الموقع عند الفتح)؛ لا يُخزَّن شيء ولا يُسجَّل في audit_log
                d = self.body(); la, ln = geo_pair(d.get("lat"), d.get("lng"), required=True)
                r, dist, state = resolve_region(c, la, ln)
                return self.send(200, {"region": ({"id": r["id"], "name_ar": r["name_ar"], "level": r["level"], "path": region_path(c, r["id"])} if r else None), "distance_km": dist, "state": state})
            if method == "POST" and re.fullmatch(r"/api/admin/regions/\d+/coords", path):
                self.need(u, "admin"); rid = int(path.split("/")[4]); d = self.body(); la, ln = geo_pair(d.get("lat"), d.get("lng"))  # null/null = مسح الإحداثيات
                if not c.execute("SELECT 1 FROM regions WHERE id=?", (rid,)).fetchone(): raise E(404, "غير موجود")
                c.execute("UPDATE regions SET lat=?,lng=? WHERE id=?", (la, ln, rid)); audit(c, u["id"], "region.coords", str(rid), {"lat": la, "lng": ln}); c.commit(); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/admin/regions":
                self.need(u, "admin"); d = self.body(); la, ln = geo_pair(d.get("lat"), d.get("lng"))
                try: cur = c.execute("INSERT INTO regions(parent_id,level,slug,name_ar,is_active,lat,lng) VALUES(?,?,?,?,?,?,?)", (d.get("parent_id"), d.get("level"), d.get("slug"), d.get("name_ar"), int(bool(d.get("is_active"))), la, ln))
                except sqlite3.Error: raise E(400, "بيانات المنطقة غير صالحة")
                audit(c, u["id"], "region.create", str(cur.lastrowid), d); c.commit(); return self.send(201, {"id": cur.lastrowid})
            m = re.fullmatch(r"/api/admin/regions/(\d+)", path)
            if method == "POST" and m:
                self.need(u, "admin"); rid = int(m[1]); d = self.body()
                old = c.execute('SELECT * FROM regions WHERE id=?', (rid,)).fetchone()
                if not old: raise E(404, "المنطقة غير موجودة")
                name = str(d.get('name_ar', old['name_ar'])).strip()
                slug = str(d.get('slug', old['slug'])).strip()
                level = str(d.get('level', old['level']))
                parent = d.get('parent_id', old['parent_id'])
                if not name or not slug or level not in ('country','governorate','markaz','village','zone'): raise E(400, "بيانات المنطقة غير صالحة")
                if parent is not None:
                    pr = c.execute('SELECT level FROM regions WHERE id=?', (parent,)).fetchone()
                    if not pr or parent == rid: raise E(400, "المنطقة الأب غير صالحة")
                    if level == 'governorate' and pr['level'] != 'country' or level == 'markaz' and pr['level'] != 'governorate': raise E(400, "مستوى المنطقة لا يتوافق مع المنطقة الأب")
                    if c.execute('WITH RECURSIVE tree(id) AS (SELECT ? UNION ALL SELECT r.id FROM regions r JOIN tree t ON r.parent_id=t.id) SELECT 1 FROM tree WHERE id=?', (rid, parent)).fetchone(): raise E(400, "لا يمكن نقل المنطقة إلى أحد فروعها")
                try: c.execute('UPDATE regions SET name_ar=?,slug=?,level=?,parent_id=? WHERE id=?', (name, slug, level, parent, rid))
                except sqlite3.IntegrityError: raise E(409, "المعرّف مستخدم بالفعل")
                audit(c, u['id'], 'region.update', str(rid), {'name_ar':name,'slug':slug,'level':level,'parent_id':parent}); c.commit(); return self.send(200, {'ok':True})
            if method == "POST" and re.fullmatch(r"/api/admin/regions/\d+/active", path):
                self.need(u, "admin"); rid = int(path.split("/")[4]); a = int(bool(self.body().get("is_active")))
                c.execute("UPDATE regions SET is_active=? WHERE id=?", (a, rid)); audit(c, u["id"], "region.active", str(rid), {"is_active": a}); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/categories":
                sec = q.get("section", [None])[0]; allv = q.get("all", ["0"])[0] == "1" and u and u["role"] in ("admin", "staff")
                sql = "SELECT id,parent_id,section,slug,name_ar,description,icon,display_mode,sort,is_active FROM categories WHERE (?1 IS NULL OR section=?1)" + ("" if allv else " AND is_active=1 AND id IN " + market.VISIBLE_CATEGORIES) + " ORDER BY sort,id"
                rows = [dict(r) for r in c.execute(sql, (sec,))]
                if q.get("browse", ["0"])[0] == "1" and not allv:  # browsing view: hide categories with no approved listing (in the user's region if given); posting still sees every active category
                    rid = toint(q.get("region_id", [0])[0])
                    have = {r[0] for r in c.execute("SELECT DISTINCT l.category_id FROM listings l JOIN regions rg ON rg.id=l.region_id WHERE l.status='approved' AND rg.is_active=1" + (" AND l.region_id IN " + COVER if rid else ""), (rid,) if rid else ())}
                    rows = [r for r in rows if r["parent_id"] is None or r["id"] in have]
                return self.send(200, rows)
            m = re.fullmatch(r"/api/categories/(\d+)/fields", path)
            if method == "GET" and m:
                adm = int(bool(u and u["role"] in ("admin", "staff")))  # admins also see the fields of hidden categories
                return self.send(200, [dict(r) for r in c.execute("SELECT f.* FROM category_fields f JOIN categories k ON k.id=f.category_id WHERE f.category_id=? AND (k.is_active=1 OR ?) ORDER BY f.sort,f.id", (int(m[1]), adm))])
            if method == "POST" and path == "/api/admin/categories":
                self.need(u, "admin"); d = self.body()
                if d.get("parent_id") is not None:
                    par = c.execute("SELECT section FROM categories WHERE id=?", (d.get("parent_id"),)).fetchone()
                    if not par or par["section"] != d.get("section"): raise E(400, "التصنيف الأب غير موجود أو من قسم مختلف")
                try: cur = c.execute("INSERT INTO categories(parent_id,section,slug,name_ar,description,icon,display_mode,sort,is_active) VALUES(?,?,?,?,?,?,?,?,?)", (d.get("parent_id"), d.get("section"), d.get("slug"), d.get("name_ar"), str(d.get("description") or "")[:500], str(d.get("icon") or "")[:40], d.get("display_mode") if d.get("display_mode") in ("auto","categories","content","both") else "auto", int(d.get("sort") or 0), int(bool(d.get("is_active")))))
                except sqlite3.Error: raise E(400, "بيانات التصنيف غير صالحة")
                audit(c, u["id"], "category.create", str(cur.lastrowid), d); c.commit(); return self.send(201, {"id": cur.lastrowid})
            if method == "POST" and path == "/api/admin/categories/reorder":  # {"ids":[...]} — كلها أبناء أب واحد؛ الترتيب = ترتيب القائمة
                self.need(u, "admin"); ids = self.body().get("ids")
                if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids): raise E(400, "قائمة الترتيب غير صالحة")
                rows = c.execute("SELECT id,parent_id,section FROM categories WHERE id IN (%s)" % ",".join("?" * len(ids)), ids).fetchall()
                if len(rows) != len(ids): raise E(404, "تصنيف غير موجود")
                if len({(r["parent_id"], r["section"]) for r in rows}) != 1: raise E(400, "الترتيب يكون بين تصنيفات أب واحد فقط")
                for i, cid in enumerate(ids): c.execute("UPDATE categories SET sort=? WHERE id=?", ((i + 1) * 10, cid))
                audit(c, u["id"], "category.reorder", None, {"ids": ids}); c.commit(); return self.send(200, {"ok": True})
            m = re.fullmatch(r"/api/admin/categories/(\d+)/delete", path)
            if method == "POST" and m:  # حذف نهائي محمي: يُرفض (409) إن وُجدت إعلانات (حتى المحذوفة منطقيًا) أو تصنيفات فرعية أو كان جذر قسم
                self.need(u, "admin"); cid = int(m[1]); cat = c.execute("SELECT id,parent_id FROM categories WHERE id=?", (cid,)).fetchone()
                if not cat: raise E(404, "التصنيف غير موجود")
                if cat["parent_id"] is None: raise E(409, "لا يمكن حذف جذر القسم")
                if c.execute("SELECT 1 FROM categories WHERE parent_id=?", (cid,)).fetchone(): raise E(409, "التصنيف فيه تصنيفات فرعية؛ احذفها أو انقلها أولًا")
                live, total = market.listing_counts(c, cid)
                if total: raise E(409, "عليه %d إعلان (%d منها غير محذوف)؛ لا يُحذف نهائيًا، عطّله بدلًا من ذلك" % (total, live))
                c.execute("DELETE FROM categories WHERE id=?", (cid,)); audit(c, u["id"], "category.delete", str(cid)); c.commit(); return self.send(200, {"ok": True})
            m = re.fullmatch(r"/api/admin/categories/(\d+)", path)
            if method == "POST" and m:
                self.need(u, "admin"); d = self.body(); cid = int(m[1]); ch = {k: d[k] for k in ("name_ar", "description", "icon", "display_mode", "sort", "is_active") if k in d}
                cat = c.execute("SELECT id,parent_id,section FROM categories WHERE id=?", (cid,)).fetchone()
                if not cat: raise E(404, "التصنيف غير موجود")
                if not ch and "parent_id" not in d: raise E(400, "لا توجد تعديلات")
                if "description" in ch: ch["description"] = str(ch["description"] or "")[:500]
                if "icon" in ch: ch["icon"] = str(ch["icon"] or "")[:40]
                if "display_mode" in ch and ch["display_mode"] not in ("auto", "categories", "content", "both"): raise E(400, "طريقة العرض غير صالحة")
                if "name_ar" in ch:
                    ch["name_ar"] = str(ch["name_ar"] or "").strip()
                    if not 2 <= len(ch["name_ar"]) <= 60: raise E(400, "اسم التصنيف من 2 إلى 60 حرفًا")
                if "sort" in ch:
                    if isinstance(ch["sort"], bool) or not isinstance(ch["sort"], int): raise E(400, "الترتيب رقم صحيح")
                if "is_active" in ch: ch["is_active"] = int(bool(ch["is_active"]))
                if "parent_id" in d:  # نقل: داخل نفس القسم، بلا حلقات، وبقرار صريح (confirm) إن كان فيه إعلانات
                    npar = d["parent_id"]
                    if cat["parent_id"] is None: raise E(400, "لا يُنقل جذر القسم")
                    if isinstance(npar, bool) or not isinstance(npar, int): raise E(400, "التصنيف الأب غير صالح")
                    par = c.execute("SELECT section FROM categories WHERE id=?", (npar,)).fetchone()
                    if not par or par["section"] != cat["section"]: raise E(400, "التصنيف الأب غير موجود أو من قسم مختلف")
                    if npar in market.subtree_ids(c, cid): raise E(400, "لا يمكن نقل التصنيف داخل نفسه أو أحد فروعه")
                    if npar != cat["parent_id"]:
                        live, total = market.listing_counts(c, cid)
                        if live and d.get("confirm") is not True: raise E(409, "في التصنيف %d إعلان؛ أعد الطلب مع confirm=true لتأكيد النقل" % live)
                        ch["parent_id"] = npar
                if not ch: raise E(400, "لا توجد تعديلات")
                c.execute("UPDATE categories SET " + ",".join(k + "=?" for k in ch) + " WHERE id=?", (*ch.values(), cid))
                live, _ = market.listing_counts(c, cid)
                audit(c, u["id"], "category.update", m[1], ch); c.commit(); return self.send(200, {"ok": True, "affected_listings": live})
            m = re.fullmatch(r"/api/admin/categories/(\d+)/fields", path)
            if method == "POST" and m:
                self.need(u, "admin"); d = self.body()
                try:
                    opts = json.dumps(d["options"], ensure_ascii=False) if d.get("options") else None
                    if d.get("type") == "select" and not opts: raise E(400, "حقل الاختيار يحتاج قائمة خيارات")
                    cur = c.execute("INSERT INTO category_fields(category_id,key,label_ar,type,required,searchable,options,sort) VALUES(?,?,?,?,?,?,?,?)", (int(m[1]), d.get("key"), d.get("label_ar"), d.get("type"), int(bool(d.get("required"))), int(bool(d.get("searchable"))), opts, int(d.get("sort") or 0)))
                except sqlite3.Error: raise E(400, "بيانات الحقل غير صالحة أو مكررة")
                audit(c, u["id"], "field.create", str(cur.lastrowid), d); c.commit(); return self.send(201, {"id": cur.lastrowid})
            if method == "POST" and path == "/api/listings":
                self.need(u); d = self.body(); title = str(d.get("title", "")).strip()
                cat = c.execute("SELECT id FROM categories WHERE id=? AND section='souq' AND is_active=1 AND id IN " + market.VISIBLE_CATEGORIES, (d.get("category_id"),)).fetchone()
                if not cat: raise E(400, "التصنيف غير متاح")
                if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (d.get("region_id"),)).fetchone(): raise E(400, "المنطقة غير مفعّلة")
                if not 3 <= len(title) <= 120: raise E(400, "العنوان من 3 إلى 120 حرفًا")
                clean, price = listing_clean_fields(c, cat["id"], d.get("fields") or {})
                if d.get("contact_mode") is not None and d.get("contact_mode") not in chat.MODES: raise E(400, "طريقة التواصل غير صالحة")
                cond, neg = listing_flags(d); img_ids = listing_image_ids(c, u["id"], d.get("image_file_ids"))
                now = int(time.time())
                cur = c.execute("INSERT INTO listings(user_id,category_id,region_id,title,description,price,data,created_at,updated_at,condition,negotiable) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (u["id"], cat["id"], d["region_id"], title, str(d.get("description", ""))[:2000], price, json.dumps(clean, ensure_ascii=False), now, now, cond, neg))
                for i, fid in enumerate(img_ids): c.execute("INSERT INTO listing_images(listing_id,file_id,position,created_at) VALUES(?,?,?,?)", (cur.lastrowid, fid, i, now))
                chat.set_mode(c, cur.lastrowid, d.get("contact_mode") or "both"); c.commit(); return self.send(201, {"id": cur.lastrowid, "status": "pending", "images": img_ids})
            if method == "POST" and path == "/api/listings/images":  # رفع صورة إعلان: سقف مستقل (MAX_MARKET_UPLOADS) عن سقف الـ20 ملفًا
                self.need(u); raw, mime = self.read_image()
                if u["role"] not in ("admin", "staff") and c.execute("SELECT COUNT(*) FROM market_files WHERE user_id=?", (u["id"],)).fetchone()[0] >= market.MAX_MARKET_UPLOADS: raise E(429, "وصلت للحد الأقصى من صور الإعلانات، احذف صورًا غير مستخدمة")
                os.makedirs(UP, exist_ok=True); name = secrets.token_hex(16); open(os.path.join(UP, name), "wb").write(raw)
                cur = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (u["id"], name, mime, len(raw), int(time.time())))
                c.execute("INSERT INTO market_files(file_id,user_id,created_at) VALUES(?,?,?)", (cur.lastrowid, u["id"], int(time.time()))); c.commit(); return self.send(201, {"id": cur.lastrowid})
            m = re.fullmatch(r"/api/listings/(\d+)/images/(\d+)", path)
            if method == "GET" and m:  # عام للإعلان المنشور فقط؛ غير المنشور لصاحبه والإدارة فقط (404 لغيرهم دون كشف وجوده)
                r = c.execute("SELECT l.status,l.user_id,l.category_id,f.path,f.mime FROM listing_images li JOIN listings l ON l.id=li.listing_id JOIN files f ON f.id=li.file_id WHERE li.listing_id=? AND li.file_id=?", (int(m[1]), int(m[2]))).fetchone()
                if not r: raise E(404, "غير موجود")
                public = r["status"] == "approved" and market.is_visible_category(c, r["category_id"])
                if not public and not (u and (u["id"] == r["user_id"] or u["role"] in ("admin", "staff"))): raise E(404, "غير موجود")
                try: raw = open(os.path.join(UP, r["path"]), "rb").read()
                except OSError: raise E(404, "غير موجود")
                return self.send(200, None, r["mime"], raw, {"Cache-Control": "public, max-age=3600" if public else "private, no-store"})
            m = re.fullmatch(r"/api/listings/(\d+)/edit", path)
            if method == "POST" and m:  # تعديل بواسطة المالك: أي تعديل يعيد الإعلان للمراجعة (pending) ويمسح سبب الرفض
                self.need(u); lid = int(m[1]); r = c.execute("SELECT * FROM listings WHERE id=? AND user_id=? AND status!='deleted'", (lid, u["id"])).fetchone()
                if not r: raise E(404, "غير موجود")
                if r["status"] == "hidden": raise E(409, "الإعلان مخفي بقرار إداري؛ تواصل مع الإدارة")
                d = self.body(); keys = ("title", "description", "region_id", "category_id", "fields", "condition", "negotiable", "image_file_ids")
                if not any(k in d for k in keys): raise E(400, "لا توجد تعديلات")
                cat_id = d["category_id"] if "category_id" in d else r["category_id"]
                if not c.execute("SELECT 1 FROM categories WHERE id=? AND section='souq' AND is_active=1 AND id IN " + market.VISIBLE_CATEGORIES, (cat_id,)).fetchone(): raise E(400, "التصنيف غير متاح")
                region = r["region_id"]
                if "region_id" in d:
                    region = d["region_id"]
                    if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (region,)).fetchone(): raise E(400, "المنطقة غير مفعّلة")
                title = str(d["title"]).strip() if "title" in d else r["title"]
                if not 3 <= len(title) <= 120: raise E(400, "العنوان من 3 إلى 120 حرفًا")
                desc = str(d.get("description", ""))[:2000] if "description" in d else r["description"]
                data, price = r["data"], r["price"]
                if "fields" in d or cat_id != r["category_id"]:
                    clean, price = listing_clean_fields(c, cat_id, d.get("fields") or {}); data = json.dumps(clean, ensure_ascii=False)
                cond, neg = listing_flags(d, r["condition"], r["negotiable"])
                new_imgs = listing_image_ids(c, u["id"], d["image_file_ids"], lid) if "image_file_ids" in d else None
                now = int(time.time()); drop = []
                c.execute("UPDATE listings SET category_id=?,region_id=?,title=?,description=?,price=?,data=?,condition=?,negotiable=?,status='pending',reject_reason=NULL,reviewed_by=NULL,reviewed_at=NULL,updated_at=? WHERE id=?", (cat_id, region, title, desc, price, data, cond, neg, now, lid))
                if new_imgs is not None:
                    old = market.images_for(c, [lid])[lid]; c.execute("DELETE FROM listing_images WHERE listing_id=?", (lid,))
                    for i, fid in enumerate(new_imgs): c.execute("INSERT INTO listing_images(listing_id,file_id,position,created_at) VALUES(?,?,?,?)", (lid, fid, i, now))
                    for fid in old:  # الصور المزالة فقط، ولا تُحذف إن كانت مستخدمة في مكان آخر
                        if fid in new_imgs or market.file_used_elsewhere(c, fid): continue
                        f = c.execute("SELECT path FROM files WHERE id=? AND owner_id=?", (fid, u["id"])).fetchone()
                        if f: c.execute("DELETE FROM files WHERE id=?", (fid,)); drop.append(f["path"])
                audit(c, u["id"], "listing.edit", str(lid), {k: d[k] for k in keys if k in d and k != "fields"}); c.commit()
                for p_ in drop: rm_upload(p_)
                return self.send(200, {"ok": True, "status": "pending", "images": market.images_for(c, [lid])[lid]})
            m = re.fullmatch(r"/api/my/listings/(\d+)", path)
            if method == "GET" and m:
                self.need(u); r = c.execute("SELECT * FROM listings WHERE id=? AND user_id=? AND status!='deleted'", (int(m[1]), u["id"])).fetchone()
                if not r: raise E(404, "غير موجود")
                out = dict(r); out["images"] = market.images_for(c, [r["id"]])[r["id"]]; return self.send(200, out)
            if method == "GET" and path == "/api/listings":
                sql_w, args, ctes, cargs = ["l.status='approved'", "l.category_id IN " + market.VISIBLE_CATEGORIES], [], [], []
                def num(name):
                    try: v = float(q[name][0])
                    except (TypeError, ValueError): raise E(400, "قيمة غير صحيحة: " + name)
                    if v != v or v in (float("inf"), float("-inf")): raise E(400, "قيمة غير صحيحة: " + name)
                    return v
                if q.get("category_id"):  # التصنيف الأب يشمل فروعه
                    ctes.append("s(id) AS (SELECT ? UNION SELECT k.id FROM categories k JOIN s ON k.parent_id=s.id)"); cargs.append(toint(q["category_id"][0])); sql_w.append("l.category_id IN (SELECT id FROM s)")
                if q.get("region_id"):
                    ctes.append("r(id) AS (SELECT ? UNION SELECT g.id FROM regions g JOIN r ON g.parent_id=r.id)"); cargs.append(toint(q["region_id"][0])); sql_w.append("l.region_id IN (SELECT id FROM r)")
                if q.get("q") and q["q"][0].strip():
                    qt = q["q"][0].strip()[:100]
                    if FTS_OK and len(qt) >= 3: sql_w.append("l.id IN (SELECT rowid FROM listings_fts WHERE listings_fts MATCH ?)"); args.append('"' + qt.replace('"', '""') + '"')  # indexed substring match (trigram), same results as the LIKE below
                    else:
                        t = "%" + qt.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"; sql_w.append("(l.title LIKE ? ESCAPE '\\' OR l.description LIKE ? ESCAPE '\\')"); args += [t, t]
                if q.get("min_price"): sql_w.append("l.price>=?"); args.append(num("min_price"))
                if q.get("max_price"): sql_w.append("l.price<=?"); args.append(num("max_price"))
                if q.get("condition"):
                    if q["condition"][0] not in ("new", "used"): raise E(400, "حالة المنتج: new أو used")
                    sql_w.append("l.condition=?"); args.append(q["condition"][0])
                if q.get("negotiable", ["0"])[0] == "1": sql_w.append("l.negotiable=1")
                if q.get("exclude_closed", ["0"])[0] == "1": sql_w.append("l.closed_kind IS NULL")
                only_feat = q.get("featured", ["0"])[0] == "1"
                if only_feat: sql_w.append("l.featured_until>%d" % int(time.time()))  # المرحلة 30: المميز الساري فقط
                ffs = {k[2:]: v[0] for k, v in q.items() if k.startswith("f_")}  # فلتر على حقول التصنيف القابلة للبحث: f_<key>=<value> (يتطلب category_id)
                if ffs:
                    if not q.get("category_id"): raise E(400, "فلاتر الحقول تتطلب category_id")
                    for key, val in ffs.items():
                        fd = c.execute("SELECT type FROM category_fields WHERE key=? AND searchable=1 AND category_id IN (WITH RECURSIVE s(id) AS (SELECT ? UNION SELECT k.id FROM categories k JOIN s ON k.parent_id=s.id) SELECT id FROM s) LIMIT 1", (key, toint(q["category_id"][0]))).fetchone()
                        if not fd: raise E(400, "حقل غير قابل للبحث: " + key)
                        if fd["type"] in ("number", "price"):
                            try: val = float(val)
                            except ValueError: raise E(400, "قيمة غير صحيحة: " + key)
                        sql_w.append("json_extract(l.data, ?)=?"); args += ['$."%s"' % key.replace('"', ""), val]
                SORTS = {"newest": "l.created_at DESC,l.id DESC", "oldest": "l.created_at ASC,l.id ASC", "price_asc": "(l.price IS NULL),l.price ASC,l.id DESC", "price_desc": "(l.price IS NULL),l.price DESC,l.id DESC"}
                srt = q.get("sort", ["newest"])[0]
                if srt not in SORTS: raise E(400, "ترتيب غير مدعوم")
                lim = max(1, min(toint(q.get("limit", ["20"])[0]), 50)); off = max(0, toint(q.get("offset", ["0"])[0]))
                pre = ("WITH RECURSIVE " + ",".join(ctes) + " ") if ctes else ""; where = " AND ".join(sql_w)
                total = c.execute(pre + "SELECT COUNT(*) FROM listings l WHERE " + where, (*cargs, *args)).fetchone()[0]
                rows = [dict(r) for r in c.execute(pre + "SELECT l.id,l.title,l.description,l.price,l.data,l.category_id,l.region_id,l.condition,l.negotiable,l.contact_mode,l.closed_kind,l.created_at,CASE WHEN l.featured_until>" + str(int(time.time())) + " THEN 1 ELSE 0 END featured,u.name seller FROM listings l JOIN users u ON u.id=l.user_id WHERE " + where + " ORDER BY " + ("l.featured_until DESC,l.id DESC" if only_feat else SORTS[srt]) + " LIMIT ? OFFSET ?", (*cargs, *args, lim, off)).fetchall()]
                imgs = market.images_for(c, [r["id"] for r in rows])
                for r in rows: r["images"] = imgs[r["id"]]
                return self.send(200, rows, extra={"X-Total-Count": str(total)})
            m = re.fullmatch(r"/api/listings/(\d+)", path)
            if method == "GET" and m:  # تفاصيل إعلان: عام للمنشور فقط؛ غير ذلك لصاحبه (غير المحذوف) والإدارة؛ 404 لغيرهم
                r = c.execute("SELECT l.*,u.name seller FROM listings l JOIN users u ON u.id=l.user_id WHERE l.id=?", (int(m[1]),)).fetchone()
                if not r: raise E(404, "غير موجود")
                public = r["status"] == "approved" and market.is_visible_category(c, r["category_id"])
                own = bool(u and u["id"] == r["user_id"] and r["status"] != "deleted"); adm = bool(u and u["role"] in ("admin", "staff"))
                if not (public or own or adm): raise E(404, "غير موجود")
                try: data = json.loads(r["data"] or "{}")
                except ValueError: data = {}
                fields = [{"key": f["key"], "label": f["label_ar"], "type": f["type"], "value": data[f["key"]]} for f in c.execute("SELECT * FROM category_fields WHERE category_id=? ORDER BY sort,id", (r["category_id"],)) if f["key"] in data]
                def chain(table, rid):
                    out = []
                    while rid is not None and len(out) < 10:
                        n = c.execute("SELECT id,parent_id,name_ar FROM %s WHERE id=?" % table, (rid,)).fetchone()
                        if not n: break
                        out.append({"id": n["id"], "name": n["name_ar"]}); rid = n["parent_id"]
                    return list(reversed(out))
                out = {"id": r["id"], "title": r["title"], "description": r["description"], "price": r["price"], "condition": r["condition"], "negotiable": r["negotiable"],
                       "closed_kind": r["closed_kind"], "created_at": r["created_at"], "updated_at": r["updated_at"], "seller": r["seller"], "fields": fields,
                       "category": chain("categories", r["category_id"]), "region": chain("regions", r["region_id"]), "images": market.images_for(c, [r["id"]])[r["id"]], "is_owner": own, "contact_mode": r["contact_mode"], "featured": bool(r["featured_until"] and r["featured_until"] > time.time())}
                if own or adm: out["status"] = r["status"]; out["reject_reason"] = r["reject_reason"] if own else None
                out.update(lsocial.flags(c, u, r["id"]))  # is_favorite / reported للمسجّل فقط
                return self.send(200, out)
            if method == "GET" and path == "/api/my/listings":
                self.need(u); rows = [dict(r) for r in c.execute("SELECT id,title,price,status,reject_reason,created_at,contact_mode FROM listings WHERE user_id=? AND status!='deleted' ORDER BY id DESC", (u["id"],))]; imgs = market.images_for(c, [r["id"] for r in rows])
                for r in rows: r["images"] = imgs[r["id"]]
                return self.send(200, rows)
            m = re.fullmatch(r"/api/listings/(\d+)/contact", path)
            if method == "GET" and m:
                self.need(u); lid = m[1]
                r = c.execute("SELECT l.user_id,u.name,u.phone FROM listings l JOIN users u ON u.id=l.user_id WHERE l.id=? AND l.status='approved'", (int(lid),)).fetchone()
                if not r: raise E(404, "غير موجود")
                if r["user_id"] != u["id"]: contact_guard(c, u, "listing.contact", lid, "تجاوزت الحد المسموح لعرض أرقام البائعين، حاول لاحقًا")
                return self.send(200, {"seller": r["name"], "phone": r["phone"]})
            m = re.fullmatch(r"/api/listings/(\d+)/delete", path)
            if method == "POST" and m:
                self.need(u); r = c.execute("SELECT user_id FROM listings WHERE id=?", (int(m[1]),)).fetchone()
                if not r or (r["user_id"] != u["id"] and u["role"] != "admin"): raise E(404, "غير موجود")
                c.execute("UPDATE listings SET status='deleted' WHERE id=?", (int(m[1]),)); audit(c, u["id"], "listing.delete", m[1]); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/admin/featured":  # المرحلة 30: المميز الحالي + آخر المنشور القابل للتمييز + الحد الأقصى
                self.need(u, "admin", "staff"); now = int(time.time())
                fe = [dict(r) for r in c.execute("SELECT l.id,l.title,l.featured_until,u.name seller FROM listings l JOIN users u ON u.id=l.user_id WHERE l.status='approved' AND l.featured_until>? ORDER BY l.featured_until DESC", (now,))]
                rc = [dict(r) for r in c.execute("SELECT l.id,l.title,u.name seller FROM listings l JOIN users u ON u.id=l.user_id WHERE l.status='approved' AND l.closed_kind IS NULL AND (l.featured_until IS NULL OR l.featured_until<=?) ORDER BY l.id DESC LIMIT 40", (now,))]
                return self.send(200, {"max": int(cfg(c, "featured_max", 6)), "featured": fe, "recent": rc})
            if method == "POST" and path == "/api/admin/featured/settings":
                self.need(u, "admin")
                try: mx = int(self.body().get("max"))
                except (TypeError, ValueError): raise E(400, "الحد الأقصى غير صالح")
                if not 1 <= mx <= 12: raise E(400, "الحد الأقصى من 1 إلى 12")
                c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("featured_max", str(mx))); audit(c, u["id"], "settings.featured_max", None, {"max": mx}); c.commit(); return self.send(200, {"max": mx})
            m = re.fullmatch(r"/api/admin/listings/(\d+)/feature", path)
            if method == "POST" and m:  # تمييز إعلان منشور لعدد أيام (0 = إلغاء)؛ يُنتهي وحده، بحد أقصى للمميز المتزامن
                self.need(u, "admin", "staff"); lid = int(m[1])
                try: days = int(self.body().get("days"))
                except (TypeError, ValueError): raise E(400, "عدد الأيام غير صالح")
                if not 0 <= days <= 30: raise E(400, "عدد الأيام من 0 إلى 30")
                c.commit(); c.execute("BEGIN IMMEDIATE")
                try:
                    r = c.execute("SELECT status,closed_kind FROM listings WHERE id=?", (lid,)).fetchone(); now = int(time.time())
                    if not r: raise E(404, "غير موجود")
                    if days == 0:
                        c.execute("UPDATE listings SET featured_until=NULL WHERE id=?", (lid,)); audit(c, u["id"], "listing.unfeature", str(lid)); c.commit(); return self.send(200, {"featured": False})
                    if r["status"] != "approved" or r["closed_kind"]: raise E(409, "يمكن تمييز الإعلانات المنشورة المفتوحة فقط")
                    mx = int(cfg(c, "featured_max", 6))
                    if c.execute("SELECT COUNT(*) FROM listings WHERE status='approved' AND featured_until>? AND id!=?", (now, lid)).fetchone()[0] >= mx: raise E(409, "وصلت للحد الأقصى للإعلانات المميزة (%d)" % mx)
                    until = now + days * 86400; c.execute("UPDATE listings SET featured_until=? WHERE id=?", (until, lid)); audit(c, u["id"], "listing.feature", str(lid), {"days": days}); c.commit()
                    return self.send(200, {"featured": True, "featured_until": until})
                except E: c.rollback() if c.in_transaction else None; raise
            if method == "GET" and path == "/api/admin/listings":
                self.need(u, "admin", "staff"); return self.send(200, [dict(r) for r in c.execute("SELECT l.*,u.name seller,u.phone seller_phone FROM listings l JOIN users u ON u.id=l.user_id WHERE l.status=? ORDER BY l.id", (q.get("status", ["pending"])[0],))])
            m = re.fullmatch(r"/api/admin/listings/(\d+)/review", path)
            if method == "POST" and m:
                self.need(u, "admin", "staff"); d = self.body(); st = d.get("status")
                if st not in ("approved", "rejected"): raise E(400, "حالة غير صالحة")
                if st == "rejected" and not d.get("reason"): raise E(400, "اذكر سبب الرفض")
                n = c.execute("UPDATE listings SET status=?,reject_reason=? WHERE id=? AND status='pending'", (st, d.get("reason"), int(m[1]))).rowcount
                if not n: raise E(409, "الإعلان غير قيد المراجعة")
                audit(c, u["id"], "listing." + st, m[1], d); c.commit(); return self.send(200, {"ok": True})
            sweep(c)
            NEXT = {"assigned": "heading_pickup", "heading_pickup": "picked_up", "picked_up": "heading_customer", "heading_customer": "arrived", "arrived": "awaiting_confirmation"}
            def ev(oid, frm, to): c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, u["id"], frm, to, int(time.time())))
            def courier():
                self.need(u); r = c.execute("SELECT * FROM couriers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone()
                if not r: raise E(403, "حساب المندوب غير معتمد")
                return r
            if method == "POST" and path == "/api/couriers/apply":
                self.need(u); d = self.body(); rid = d.get("region_id")
                if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone(): raise E(400, "المنطقة غير مفعّلة")
                docs = {}
                for kind, key in (("id_front", "id_front_file_id"), ("id_back", "id_back_file_id"), ("selfie", "selfie_file_id")):
                    if d.get(key) in (None, ""):
                        if kind != "selfie": raise E(400, "صورة البطاقة (الوجه والظهر) مطلوبة")
                        continue
                    fid = toint(d.get(key))
                    if not c.execute("SELECT 1 FROM files WHERE id=? AND owner_id=?", (fid, u["id"])).fetchone(): raise E(400, "ارفع المستند أولًا")
                    docs[kind] = fid
                if len(set(docs.values())) != len(docs): raise E(400, "كل مستند يحتاج صورة مختلفة")
                ex = c.execute("SELECT status,(SELECT COUNT(*) FROM courier_documents WHERE courier_id=couriers.user_id) nd FROM couriers WHERE user_id=?", (u["id"],)).fetchone(); now = int(time.time())
                if ex and not (ex["status"] == "rejected" or (ex["status"] == "pending" and not ex["nd"])): raise E(409, "طلبك مقدّم بالفعل")  # re-submission only after rejection, or to add missing documents to an old pending request
                if ex:
                    c.execute("UPDATE couriers SET status='pending',region_id=?,review_reason=NULL WHERE user_id=?", (rid, u["id"])); c.execute("DELETE FROM courier_documents WHERE courier_id=?", (u["id"],))
                else: c.execute("INSERT INTO couriers(user_id,region_id,created_at) VALUES(?,?,?)", (u["id"], rid, now))
                for kind, fid in docs.items(): c.execute("INSERT INTO courier_documents VALUES(?,?,?,?)", (u["id"], kind, fid, now))
                audit(c, u["id"], "courier.apply", str(u["id"]), {"documents": sorted(docs)}); c.commit(); return self.send(201, {"status": "pending"})
            if method == "GET" and path == "/api/admin/couriers":
                self.need(u, "admin", "staff"); rows = [dict(r) for r in c.execute("SELECT c.*,u.name,u.phone FROM couriers c JOIN users u ON u.id=c.user_id WHERE c.status=?", (q.get("status", ["pending"])[0],))]
                for r in rows: r["documents"] = [dict(x) for x in c.execute("SELECT kind,file_id FROM courier_documents WHERE courier_id=? ORDER BY kind", (r["user_id"],))]
                return self.send(200, rows)
            m = re.fullmatch(r"/api/admin/couriers/(\d+)/review", path)
            if method == "POST" and m:
                self.need(u, "admin"); rd = self.body(); st = rd.get("status")
                if st not in ("approved", "suspended", "rejected"): raise E(400, "حالة غير صالحة")
                if st == "approved" and c.execute("SELECT COUNT(*) FROM courier_documents WHERE courier_id=? AND kind IN('id_front','id_back')", (int(m[1]),)).fetchone()[0] < 2: raise E(409, "لا يمكن الاعتماد قبل رفع صورة البطاقة (الوجه والظهر)")
                why = str(rd.get("reason", "")).strip()[:300] if st in ("rejected", "suspended") else ""  # optional note shown to the courier; cleared on approval
                if not c.execute("UPDATE couriers SET status=?,review_reason=? WHERE user_id=?", (st, why or None, int(m[1]))).rowcount: raise E(404, "غير موجود")
                c.execute("UPDATE users SET role=? WHERE id=? AND role IN('customer','courier')", ("courier" if st == "approved" else "customer", int(m[1])))
                audit(c, u["id"], "courier." + st, m[1], {"reason": why} if why else None); c.commit(); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/admin/region-fees":
                self.need(u, "admin"); d = self.body()
                try:
                    fee = float(d.get("fee"))
                    if not (0 <= fee <= 100000): raise ValueError  # rejects NaN/inf/negative/absurd values
                    c.execute("INSERT INTO region_fees(region_id,fee) VALUES(?,?) ON CONFLICT(region_id) DO UPDATE SET fee=excluded.fee", (d.get("region_id"), fee))
                except (sqlite3.Error, TypeError, ValueError): raise E(400, "بيانات الرسوم غير صالحة")
                audit(c, u["id"], "fee.set", str(d.get("region_id")), d); c.commit(); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/delivery/orders":
                self.need(u); d = self.body(); rid = d.get("region_id")
                if not (rid and c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone()): rid = default_delivery_region(c)  # المرحلة 28: العميل لا يختار منطقة؛ المنطقة داخلية (مركز الرياض) ولا تُستعمل لتسعير الطلب
                if not rid: raise E(400, "الدليفري غير متاح حاليًا")
                pk, dr = str(d.get("pickup_text", "")).strip(), str(d.get("dropoff_text", "")).strip()
                if len(pk) < 3 or len(dr) < 3: raise E(400, "عنوان الاستلام والتسليم مطلوبان")
                check_limit(c, "orders", u["id"], "لديك طلبات توصيل مفتوحة كثيرة، أكمل أو ألغِ بعضها أولًا")
                of = d.get("offer_fee")  # المرحلة 27: أجرة مقترحة من العميل — اختيارية؛ فارغ = التدفق القديم (المندوب يقترح بعد القبول)
                if of is None or (isinstance(of, str) and not of.strip()): of = None
                else:
                    try: of = round(float(of), 2)
                    except (TypeError, ValueError): raise E(400, "أجرة غير صالحة")
                    if not (0 < of <= 100000): raise E(400, "أجرة غير صالحة")  # يرفض NaN/inf/صفر/سالب/مبالغ فيه
                now = int(time.time()); cm = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; comm = float(cm.get("commission_value", 0)) * ((of if of is not None else 0) / 100 if cm.get("commission_type") == "percent" else 1)  # بلا أجرة افتراضية: العمولة النسبية تُحسب عند اقتراح الأجرة
                det = str(d.get("details", ""))[:1000]
                rk = str(d.get("request_key", "")).strip()[:64] or None  # client-generated per form submit: a retry or double-tap with the same key returns the same order
                if rk:
                    dup = c.execute("SELECT id,status,delivery_code FROM delivery_orders WHERE customer_id=? AND request_key=?", (u["id"], rk)).fetchone()
                    if dup: return self.send(200, {"id": dup["id"], "status": dup["status"], "delivery_code": dup["delivery_code"], "duplicate": True})
                code = "%06d" % secrets.randbelow(10 ** 6); dla, dln = geo_pair(d.get("dropoff_lat"), d.get("dropoff_lng"))  # موقع التسليم اختياري (من GPS)؛ يراه المندوب بعد قبول الطلب فقط
                cur = c.execute("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,details,fee,commission,created_at,updated_at,search_started_at,delivery_code,request_key,dropoff_lat,dropoff_lng,fare_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'none')", (u["id"], rid, pk, dr, det, of if of is not None else 0, round(comm, 2), now, now, now, code, rk, dla, dln))
                c.execute("UPDATE delivery_orders SET comm_type=?,comm_value=?,offer_fee=? WHERE id=?", (cm.get("commission_type", "fixed"), float(cm.get("commission_value", 0)), of, cur.lastrowid))
                ev(cur.lastrowid, None, "searching"); c.commit(); push_new_order(cur.lastrowid); return self.send(201, {"id": cur.lastrowid, "status": "searching", "delivery_code": code})  # لا سعر للعميل: الأجرة يقترحها المندوب بعد القبول
            if method == "GET" and path == "/api/delivery/orders":
                self.need(u); win = int(cfg(c, "search_timeout", 300)); rows = [dict(r, search_window=win) for r in c.execute("SELECT o.id,o.pickup_text,o.dropoff_text,CASE WHEN o.fare_status IN('proposed','approved') THEN o.fee END fee,o.offer_fee,o.fare_status,o.status,o.created_at,CASE WHEN o.search_started_at>0 THEN o.search_started_at ELSE o.created_at END search_started_at,CASE WHEN o.status IN " + ACTIVE + " THEN o.delivery_code END delivery_code,CASE WHEN o.fare_status IN('proposed','approved') THEN o.courier_id END courier_id,CASE WHEN o.fare_status IN('proposed','approved') THEN cu.name END courier_name,CASE WHEN o.status IN " + ACTIVE + " AND o.fare_status='approved' THEN cu.phone END courier_phone,EXISTS(SELECT 1 FROM ratings r WHERE r.order_id=o.id) rated FROM delivery_orders o LEFT JOIN users cu ON cu.id=o.courier_id WHERE o.customer_id=? ORDER BY o.id DESC", (u["id"],))]; return self.send(200, rows)
            m = re.fullmatch(r"/api/delivery/orders/(\d+)/fare/(approve|reject)", path)
            if method == "POST" and m:  # موافقة العميل على أجرة المندوب (شرط لبدء التوصيل) أو رفضها (يعود الطلب لباقي المناديب ولا يُعرض مجددًا لهذا المندوب)
                self.need(u); oid, act = int(m[1]), m[2]; d = self.body(); c.commit(); c.execute("BEGIN IMMEDIATE"); now = int(time.time())
                try:
                    o = c.execute("SELECT status,fare_status,fee,courier_id FROM delivery_orders WHERE id=? AND customer_id=?", (oid, u["id"])).fetchone()
                    if not o: raise E(404, "غير موجود")
                    if o["status"] != "assigned" or o["fare_status"] != "proposed": raise E(409, "لا توجد أجرة مقترحة بانتظار ردّك")
                    if act == "approve":
                        try: seen = float(d.get("fee"))
                        except (TypeError, ValueError): raise E(400, "أرسل الأجرة التي وافقت عليها")
                        if abs(seen - o["fee"]) > 0.001: raise E(409, "تغيّرت الأجرة المقترحة، راجعها ثم وافق من جديد")  # المندوب عدّلها أثناء مراجعتك
                        if not c.execute("UPDATE delivery_orders SET fare_status='approved',updated_at=? WHERE id=? AND customer_id=? AND status='assigned' AND fare_status='proposed' AND fee=?", (now, oid, u["id"], o["fee"])).rowcount: raise E(409, "تغيّرت حالة الطلب، حدّث الصفحة")
                        audit(c, u["id"], "order.fare_approved", str(oid), {"fee": o["fee"], "courier_id": o["courier_id"]}); c.commit(); return self.send(200, {"fare_status": "approved", "fee": o["fee"]})
                    cid_ = o["courier_id"]
                    if not c.execute("UPDATE delivery_orders SET status='searching',courier_id=NULL,fare_status='none',updated_at=?,search_started_at=? WHERE id=? AND customer_id=? AND status='assigned' AND fare_status='proposed'", (now, now, oid, u["id"])).rowcount: raise E(409, "تغيّرت حالة الطلب، حدّث الصفحة")
                    c.execute("UPDATE order_offers SET status='rejected',responded_at=? WHERE order_id=? AND courier_id=?", (now, oid, cid_))  # يستبعده من كل مسارات العرض والتنبيه
                    c.execute("DELETE FROM order_offers WHERE order_id=? AND courier_id!=? AND status IN('lost','offered','expired')", (oid, cid_))  # باقي المناديب يرون الطلب من جديد
                    ev(oid, "assigned", "searching"); audit(c, u["id"], "order.fare_rejected", str(oid), {"fee": o["fee"], "courier_id": cid_}); c.commit(); push_new_order(oid); return self.send(200, {"status": "searching"})
                except E: c.rollback() if c.in_transaction else None; raise
            m = re.fullmatch(r"/api/delivery/orders/(\d+)/(cancel|confirm)", path)
            if method == "POST" and m:
                self.need(u); oid, act = int(m[1]), m[2]; o = c.execute("SELECT * FROM delivery_orders WHERE id=? AND customer_id=?", (oid, u["id"])).fetchone()
                if not o: raise E(404, "غير موجود")
                ok_from, to = (("searching", "assigned", "heading_pickup"), "cancelled") if act == "cancel" else (("awaiting_confirmation",), "completed")
                if not c.execute("UPDATE delivery_orders SET status=?,updated_at=? WHERE id=? AND status IN (%s)" % ",".join("?" * len(ok_from)), (to, int(time.time()), oid, *ok_from)).rowcount: raise E(409, "لا يمكن تنفيذ ذلك في الحالة الحالية")
                ev(oid, o["status"], to)
                if act == "confirm" and o["commission"] > 0: c.execute("INSERT OR IGNORE INTO wallet_entries(user_id,kind,amount,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?)", (o["courier_id"], "commission", -o["commission"], "order", oid, int(time.time())))
                c.commit();
                if act == "cancel": push_stop_order(oid)
                return self.send(200, {"status": to})
            if method == "POST" and path in ("/api/courier/heartbeat", "/api/courier/online"):
                cr = courier(); now = int(time.time()); bd = self.body(); on = bd.get("online") if path.endswith("online") else None
                if path.endswith("online") and not isinstance(on, bool): raise E(400, "حدد الاتصال true أو false")
                resume = path.endswith("heartbeat") and bd.get("resume") is True  # app just opened (e.g. from a push): resume presence ONLY if the courier explicitly chose online within the reach window; never auto-connect someone who never pressed connect
                if on is None and resume and not (cr["last_seen"] > 0 and cr["last_seen"] >= now - int(cfg(c, "push_reach_hours", 12)) * 3600): c.commit(); return self.send(200, {"online": is_online(c, cr)})
                if on is None: c.execute("UPDATE couriers SET last_seen=? WHERE user_id=?", (now, u["id"]))
                else:
                    c.execute("UPDATE couriers SET is_available=?,last_seen=? WHERE user_id=?", (1 if on else 0, now, u["id"]))
                    if not on: c.execute("UPDATE order_offers SET status='expired',responded_at=? WHERE courier_id=? AND status='offered'", (now, u["id"]))
                    audit(c, u["id"], "courier.online" if on else "courier.offline", str(u["id"]))
                c.commit(); return self.send(200, {"online": bool(on) if on is not None else bool(cr["is_available"])})
            if method == "POST" and path == "/api/push/state":  # public on purpose: sw.js cannot read the login token. Keyed by the device's own push endpoint; answers with a COUNT only
                ep = str(self.body().get("endpoint", "")).strip(); r = c.execute("SELECT user_id FROM push_subs WHERE endpoint=?", (ep,)).fetchone() if 0 < len(ep) <= 600 else None
                medical = c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL AND kind LIKE 'rx.%'", (r["user_id"],)).fetchone()[0] if r else 0
                return self.send(200, {"pending": push_pending(c, r["user_id"]) if r else 0, "chat": chat.unread_total(c, r["user_id"]) if r else 0,
                                       "medical": medical, "courier": bool(r and c.execute("SELECT 1 FROM couriers WHERE user_id=? AND status='approved'", (r["user_id"],)).fetchone())})  # counts/flags only, never data
            if method == "GET" and path == "/api/push/key":  # Phase 4: any logged-in user (chat wake-ups); same VAPID key as the courier route
                self.need(u); return self.send(200, {"key": vapid_keys(c)[1]})
            if method == "POST" and path == "/api/push/subscribe":
                self.need(u); ep = str(self.body().get("endpoint", "")).strip()
                if not push_endpoint_ok(ep): raise E(400, "عنوان الإشعارات غير صالح")
                if c.execute("SELECT COUNT(*) FROM push_subs WHERE user_id=? AND endpoint!=?", (u["id"], ep)).fetchone()[0] >= 5: raise E(400, "عدد الأجهزة المسجلة للإشعارات كبير")
                c.execute("INSERT INTO push_subs VALUES(?,?,?) ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id", (ep, u["id"], int(time.time()))); c.commit(); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/push/unsubscribe":
                self.need(u); c.execute("DELETE FROM push_subs WHERE endpoint=? AND user_id=?", (str(self.body().get("endpoint", "")), u["id"])); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/courier/push/key":
                courier(); return self.send(200, {"key": vapid_keys(c)[1]})
            if method == "POST" and path == "/api/courier/push/subscribe":
                courier(); ep = str(self.body().get("endpoint", "")).strip()
                if not push_endpoint_ok(ep): raise E(400, "عنوان الإشعارات غير صالح")
                if c.execute("SELECT COUNT(*) FROM push_subs WHERE user_id=? AND endpoint!=?", (u["id"], ep)).fetchone()[0] >= 5: raise E(400, "عدد الأجهزة المسجلة للإشعارات كبير")
                c.execute("INSERT INTO push_subs VALUES(?,?,?) ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id", (ep, u["id"], int(time.time()))); c.commit(); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/courier/push/unsubscribe":
                courier(); c.execute("DELETE FROM push_subs WHERE endpoint=? AND user_id=?", (str(self.body().get("endpoint", "")), u["id"])); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/courier/status":
                self.need(u); cr = c.execute("SELECT * FROM couriers WHERE user_id=?", (u["id"],)).fetchone()
                if not cr: raise E(404, "لا يوجد طلب انضمام")
                bal, free = wallet_free(c, u["id"]); why = []
                if cr["status"] != "approved": why.append({"pending": "حسابك قيد المراجعة", "suspended": "حسابك موقوف", "rejected": "طلب انضمامك مرفوض"}[cr["status"]])
                else:
                    if not cr["is_available"]: why.append("أنت في وضع غير متصل")
                    elif not is_online(c, cr): why.append("لا توجد إشارة اتصال حديثة من التطبيق")
                    cs = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; need = float(cs.get("commission_value", 0)) if cs.get("commission_type") != "percent" else 0
                    if need > 0 and free < need: why.append("رصيدك غير كافٍ لعمولة الطلبات")
                    if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (cr["region_id"],)).fetchone(): why.append("منطقة تغطيتك غير مفعّلة")
                return self.send(200, {"status": cr["status"], "online": cr["status"] == "approved" and is_online(c, cr), "balance": bal, "available_balance": free, "reasons": why, "region_id": cr["region_id"],
                    "review_reason": cr["review_reason"] if cr["status"] in ("rejected", "suspended") else None, "user_id": u["id"], "has_avatar": bool(cr["avatar_file_id"]),
                    "has_documents": c.execute("SELECT COUNT(*) FROM courier_documents WHERE courier_id=? AND kind IN('id_front','id_back')", (u["id"],)).fetchone()[0] >= 2})
            if method == "GET" and path == "/api/courier/available":
                cr = courier(); now = int(time.time())
                if not is_online(c, cr): c.commit(); return self.send(200, [])
                ttl, win = int(cfg(c, "offer_timeout", 30)), int(cfg(c, "search_timeout", 300)); fresh = "(CASE WHEN o.search_started_at>0 THEN o.search_started_at ELSE o.created_at END)>?"
                c.execute("UPDATE order_offers SET status='expired',responded_at=? WHERE status='offered' AND offered_at<=?", (now, now - ttl))
                c.execute("UPDATE order_offers SET status='offered',offered_at=?,responded_at=NULL,rounds=rounds+1 WHERE courier_id=? AND status='expired' AND order_id IN (SELECT o.id FROM delivery_orders o WHERE o.status='searching' AND " + fresh + ")", (now, u["id"], now - win))  # re-search: unanswered offers are re-offered until the search window ends
                bal, free = wallet_free(c, u["id"])
                for o in c.execute("SELECT o.id,o.commission FROM delivery_orders o WHERE o.status='searching' AND o.customer_id!=? AND (o.region_id IN " + COVER + " OR o.region_id IN " + COVER_REV + ") AND " + fresh + " AND o.id NOT IN (SELECT order_id FROM order_offers WHERE courier_id=?)", (u["id"], cr["region_id"], cr["region_id"], now - win, u["id"])).fetchall():
                    if free >= o["commission"]: c.execute("INSERT OR IGNORE INTO order_offers(order_id,courier_id,status,offered_at) VALUES(?,?,'offered',?)", (o["id"], u["id"], now))
                c.commit()
                rows = [dict(r) for r in c.execute("SELECT o.id,o.origin_type,o.region_id,rg.name_ar region_name,o.offer_fee,o.created_at,f.offered_at+? - ? expires_in,0 taken FROM order_offers f JOIN delivery_orders o ON o.id=f.order_id JOIN regions rg ON rg.id=o.region_id WHERE f.courier_id=? AND f.status='offered' AND o.status='searching' ORDER BY o.id", (ttl, now, u["id"]))]
                rows += [dict(r) for r in c.execute("SELECT o.id,o.region_id,rg.name_ar region_name,NULL offer_fee,o.created_at,0 expires_in,1 taken FROM order_offers f JOIN delivery_orders o ON o.id=f.order_id JOIN regions rg ON rg.id=o.region_id WHERE f.courier_id=? AND f.status='lost' AND f.responded_at>?", (u["id"], now - 60))]
                for r in rows:
                    if r.get("origin_type") is None: r.pop("origin_type", None)
                return self.send(200, rows)
            m = re.fullmatch(r"/api/courier/orders/(\d+)/accept", path)
            if method == "POST" and m:
                courier(); oid = int(m[1]); d_acc = self.body(); counter = bool(d_acc.get("counter")); c.commit(); c.execute("BEGIN IMMEDIATE"); now = int(time.time())  # one writer at a time: the first successful UPDATE wins
                try:
                    cr = c.execute("SELECT * FROM couriers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone()  # re-checked inside the lock
                    if not cr: raise E(403, "حساب المندوب غير معتمد")
                    if not is_online(c, cr): raise E(403, "أنت غير متصل حاليًا")
                    bal, free = wallet_free(c, u["id"])
                    need_ = c.execute("SELECT commission,customer_id,region_id,comm_type,comm_value,offer_fee,origin_type FROM delivery_orders WHERE id=?", (oid,)).fetchone()
                    if not need_: raise E(404, "غير موجود")
                    dflt = region_fee(c, need_["region_id"]); cm_ = commission_for(c, dflt["fee"], need_["comm_type"], need_["comm_value"]) if dflt else need_["commission"]
                    if need_["offer_fee"] is not None: dflt = {"fee": need_["offer_fee"]}; cm_ = commission_for(c, need_["offer_fee"], need_["comm_type"], need_["comm_value"])  # المرحلة 27: السعر المرجعي هو سعر العميل لا الافتراضي  # الأجرة الافتراضية الحالية للمنطقة (الإدارة قد تكون عدّلتها بعد إنشاء الطلب)
                    pk_ = need_["origin_type"] == provider_delivery.KIND
                    if pk_: dflt = None; cm_ = need_["commission"]
                    if need_["customer_id"] == u["id"]: raise E(403, "لا يمكنك قبول طلب أنشأته بنفسك")
                    if free < cm_: raise E(402, "رصيدك غير كافٍ لقبول هذا الطلب")
                    mine = c.execute("SELECT status FROM order_offers WHERE order_id=? AND courier_id=?", (oid, u["id"])).fetchone()
                    if mine and mine[0] == "rejected": raise E(409, "رفضت هذا الطلب سابقًا")
                    n = c.execute("UPDATE delivery_orders SET status='assigned',courier_id=?,updated_at=? WHERE id=? AND status='searching' AND courier_id IS NULL AND (region_id IN " + COVER + " OR region_id IN " + COVER_REV + ")", (u["id"], now, oid, cr["region_id"], cr["region_id"])).rowcount
                    if not n:
                        c.execute("UPDATE order_offers SET status='lost',responded_at=? WHERE order_id=? AND courier_id=? AND status IN('offered','expired')", (now, oid, u["id"])); c.commit(); raise E(409, "الطلب لم يعد متاحًا")
                    c.execute("INSERT INTO order_offers(order_id,courier_id,status,offered_at,responded_at) VALUES(?,?,'accepted',?,?) ON CONFLICT(order_id,courier_id) DO UPDATE SET status='accepted',responded_at=excluded.responded_at", (oid, u["id"], now, now))
                    c.execute("UPDATE order_offers SET status='lost',responded_at=? WHERE order_id=? AND courier_id!=? AND status IN('offered','expired')", (now, oid, u["id"]))
                    if dflt: c.execute("UPDATE delivery_orders SET fee=?,commission=? WHERE id=?", (dflt["fee"], cm_, oid))
                    direct = pk_ or (need_["offer_fee"] is not None and not counter)  # طلب الصيدلية يُقبل مباشرة بلا تفاوض أجرة
                    c.execute("UPDATE delivery_orders SET fare_status=? WHERE id=?", ("approved" if direct else "draft", oid))  # draft: المندوب يرى الأجرة المرجعية ويعدّلها ثم يرسلها للعميل
                    if direct: audit(c, u["id"], "order.fare_accepted_offer", str(oid), {"fee": need_["offer_fee"]})
                    ev(oid, "searching", "assigned"); c.commit(); push_stop_order(oid); return self.send(200, {"ok": True, "fee": dflt["fee"] if dflt else None, "fare_status": "approved" if direct else "draft"})
                except E: c.rollback() if c.in_transaction else None; raise
            m = re.fullmatch(r"/api/courier/orders/(\d+)/reject", path)
            if method == "POST" and m:
                courier(); oid = int(m[1]); now = int(time.time())
                if not c.execute("SELECT 1 FROM delivery_orders WHERE id=? AND status='searching'", (oid,)).fetchone(): raise E(409, "الطلب لم يعد متاحًا")
                c.execute("INSERT INTO order_offers(order_id,courier_id,status,offered_at,responded_at) VALUES(?,?,'rejected',?,?) ON CONFLICT(order_id,courier_id) DO UPDATE SET status='rejected',responded_at=excluded.responded_at WHERE status IN('offered','expired')", (oid, u["id"], now, now))
                c.commit(); return self.send(200, {"ok": True})  # the order stays searching for every other eligible courier
            m = re.fullmatch(r"/api/courier/orders/(\d+)/handover", path)
            if method == "POST" and m:
                courier(); oid = int(m[1]); o = c.execute("SELECT status,delivery_code FROM delivery_orders WHERE id=? AND courier_id=?", (oid, u["id"])).fetchone()
                if not o: raise E(404, "غير موجود")
                if o["status"] != "awaiting_confirmation": raise E(409, "الطلب ليس بانتظار التأكيد")
                key = "otp|%d" % oid
                if throttled(c, key, 5, 900): raise E(429, "محاولات كثيرة، اطلب من العميل التأكيد من تطبيقه")
                if not o["delivery_code"] or not secrets.compare_digest(str(self.body().get("code", "")).strip(), o["delivery_code"]): note_fail(c, key); raise E(403, "رمز التسليم غير صحيح")
                if not c.execute("UPDATE delivery_orders SET status='completed',updated_at=? WHERE id=? AND status='awaiting_confirmation'", (int(time.time()), oid)).rowcount: raise E(409, "تم إغلاق الطلب")
                ev(oid, "awaiting_confirmation", "completed"); charge_commission(c, oid); audit(c, u["id"], "order.otp_complete", str(oid)); c.commit(); return self.send(200, {"status": "completed"})
            m = re.fullmatch(r"/api/delivery/orders/(\d+)/retry", path)
            if method == "POST" and m:
                self.need(u); oid = int(m[1]); now = int(time.time())
                if not c.execute("UPDATE delivery_orders SET search_started_at=?,updated_at=? WHERE id=? AND customer_id=? AND status='searching'", (now, now, oid, u["id"])).rowcount: raise E(409, "لا يمكن إعادة البحث لهذا الطلب")
                c.execute("DELETE FROM order_offers WHERE order_id=?", (oid,)); audit(c, u["id"], "order.retry_search", str(oid)); c.commit(); push_new_order(oid); return self.send(200, {"status": "searching"})
            if method == "GET" and path == "/api/courier/orders":
                courier(); rows = [dict(r) for r in c.execute("SELECT o.origin_type,o.region_id,o.fare_status,o.offer_fee,o.id,o.pickup_text,o.dropoff_text,o.details,o.fee,o.status,CASE WHEN o.status IN " + ACTIVE + " THEN cu.name END customer_name,CASE WHEN o.status IN " + ACTIVE + " THEN cu.phone END customer_phone,CASE WHEN o.status IN " + ACTIVE + " THEN o.dropoff_lat END dropoff_lat,CASE WHEN o.status IN " + ACTIVE + " THEN o.dropoff_lng END dropoff_lng FROM delivery_orders o JOIN users cu ON cu.id=o.customer_id WHERE o.courier_id=? ORDER BY o.id DESC", (u["id"],))]
                for r in rows:
                    if r.get("origin_type") is None: r.pop("origin_type", None)
                    f = region_fee(c, r.pop("region_id"))
                    if r["fare_status"] != "approved": r["customer_name"] = r["customer_phone"] = r["dropoff_lat"] = r["dropoff_lng"] = None  # بيانات العميل لا تُكشف قبل موافقته على الأجرة
                return self.send(200, rows)
            m = re.fullmatch(r"/api/courier/orders/(\d+)/fare", path)
            if method == "POST" and m:  # المندوب يرسل الأجرة للعميل (الافتراضية أو معدّلة ضمن حدّي المنطقة). الحدود تُفحص هنا على الخادم دائمًا.
                courier(); oid = int(m[1]); d = self.body()
                try: fee = round(float(d.get("fee")), 2)
                except (TypeError, ValueError): raise E(400, "أجرة غير صالحة")
                c.commit(); c.execute("BEGIN IMMEDIATE")
                try:
                    o = c.execute("SELECT region_id,status,fare_status,commission,comm_type,comm_value FROM delivery_orders WHERE id=? AND courier_id=?", (oid, u["id"])).fetchone()
                    if not o: raise E(404, "غير موجود")
                    if o["status"] != "assigned" or o["fare_status"] not in ("draft", "proposed"): raise E(409, "لا يمكن تعديل الأجرة في الحالة الحالية")
                    if not (0 < fee <= 100000): raise E(400, "أجرة غير صالحة")  # بلا حدود أدنى/أقصى لكل منطقة (مناطق غير مضافة)؛ العميل هو من يوافق أو يرفض
                    comm = commission_for(c, fee, o["comm_type"], o["comm_value"]); free = wallet_free(c, u["id"])[1]  # free يخصم عمولة هذا الطلب القديمة المحجوزة، فنضيفها قبل المقارنة
                    if free + o["commission"] < comm: raise E(402, "رصيدك غير كافٍ لعمولة هذه الأجرة")
                    if not c.execute("UPDATE delivery_orders SET fee=?,commission=?,fare_status='proposed',updated_at=? WHERE id=? AND courier_id=? AND status='assigned' AND fare_status IN('draft','proposed')", (fee, comm, int(time.time()), oid, u["id"])).rowcount: raise E(409, "تغيّرت حالة الطلب، حدّث الصفحة")
                    audit(c, u["id"], "order.fare_propose", str(oid), {"fee": fee}); c.commit(); return self.send(200, {"fee": fee, "fare_status": "proposed"})
                except E: c.rollback() if c.in_transaction else None; raise
            m = re.fullmatch(r"/api/courier/orders/(\d+)/(status|release)", path)
            if method == "POST" and m:
                courier(); oid = int(m[1]); o = c.execute("SELECT status,fare_status,origin_type FROM delivery_orders WHERE id=? AND courier_id=?", (oid, u["id"])).fetchone()
                if not o: raise E(404, "غير موجود")
                if m[2] == "release":
                    if o["status"] not in ("assigned", "heading_pickup"): raise E(409, "لا يمكن التخلي عن الطلب بعد الاستلام")
                    now = int(time.time())
                    if not c.execute("UPDATE delivery_orders SET status='searching',courier_id=NULL,fare_status='none',updated_at=?,search_started_at=? WHERE id=? AND courier_id=? AND status IN('assigned','heading_pickup')", (now, now, oid, u["id"])).rowcount: raise E(409, "تغيّرت حالة الطلب، حدّث الصفحة")  # لا نُحيي طلبًا ألغاه العميل في نفس اللحظة
                    c.execute("DELETE FROM order_offers WHERE order_id=?", (oid,)); ev(oid, o["status"], "searching"); c.commit(); push_new_order(oid); return self.send(200, {"status": "searching"})  # push: وإلا لا يعلم بقية المناديب بالطلب المُعاد
                to = (provider_delivery.NEXT if o["origin_type"] == provider_delivery.KIND else NEXT).get(o["status"])
                if not to or self.body().get("to") != to: raise E(409, "انتقال غير مسموح")
                if o["fare_status"] != "approved": raise E(409, "لا يمكن بدء التوصيل قبل موافقة العميل على الأجرة")
                if not c.execute("UPDATE delivery_orders SET status=?,updated_at=? WHERE id=? AND courier_id=? AND status=?", (to, int(time.time()), oid, u["id"], o["status"])).rowcount: raise E(409, "تغيّرت حالة الطلب، حدّث الصفحة")  # لا نكتب فوق إلغاء/اعتراض حدث بالتوازي
                ev(oid, o["status"], to)
                if to in ("awaiting_confirmation", "completed"): charge_commission(c, oid)  # الطلبات العادية تُحصّل عند التأكيد؛ طلب الصيدلية عند الاستلام
                c.commit(); return self.send(200, {"status": to})
            if method == "GET" and path == "/api/features":  # أعلام عامة للواجهة (المنتجات مطفية افتراضيًا عند الإطلاق)
                return self.send(200, {"products": products.enabled(c)})
            if method == "POST" and path == "/api/admin/features":
                self.need(u, "admin"); d = self.body()
                if not isinstance(d.get("products"), bool): raise E(400, "قيمة غير صالحة")
                c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("products_enabled", "1" if d["products"] else "0"))
                audit(c, u["id"], "settings.products_enabled", None, {"products": d["products"]}); c.commit(); return self.send(200, {"products": d["products"]})
            if path == "/api/home-sections":
                defaults = [
                    {"key":"med","name":"الخدمات الطبية","description":"أدوية وصيدليات وأطباء ومعامل","visible":True,"order":1},
                    {"key":"souq","name":"سوق لاقينو","description":"بيع واشتري جنب بيتك","visible":True,"order":2},
                    {"key":"svc","name":"الخدمات المحلية","description":"مقدّمو خدمات في منطقتك","visible":True,"order":3},
                    {"key":"dlv","name":"التوصيل","description":"ابعت أي حاجة والمندوب يوصلها","visible":True,"order":4},
                ]
                row = c.execute("SELECT value FROM settings WHERE key='home_sections_v1'").fetchone()
                try:
                    saved = json.loads(row[0]) if row else None
                except (ValueError, TypeError):
                    saved = None
                by_key = {x.get('key'): x for x in saved if isinstance(x, dict)} if isinstance(saved, list) else {}
                sections = [{**d, **{k: by_key.get(d['key'], {}).get(k, d[k]) for k in ('name','description','visible','order')}} for d in defaults]
                # Older settings included a standalone products card. Ignore that legacy key
                # and compact the remaining order values so the four current cards remain valid.
                sections = sorted(sections, key=lambda x: (int(x['order']) if str(x['order']).isdigit() else 999, x['key']))
                for index, section in enumerate(sections, 1):
                    section['order'] = index
                if method == "GET":
                    return self.send(200, sections)
                if method == "POST":
                    self.need(u, "admin")
                    data = self.body().get('sections')
                    if not isinstance(data, list) or len(data) != len(defaults): raise E(400, "إعدادات الأقسام غير مكتملة")
                    allowed = {x['key'] for x in defaults}; normalized=[]; seen=set()
                    for item in data:
                        if not isinstance(item, dict) or item.get('key') not in allowed or item['key'] in seen: raise E(400, "معرّف قسم غير صالح أو مكرر")
                        seen.add(item['key']); name=str(item.get('name','')).strip(); desc=str(item.get('description','')).strip()
                        if not name or len(name)>60 or len(desc)>160: raise E(400, "تحقق من الاسم والوصف (الاسم حتى 60 حرفًا والوصف حتى 160)")
                        try: order=int(item.get('order'))
                        except (ValueError, TypeError): raise E(400, "ترتيب القسم غير صالح")
                        if not 1<=order<=20: raise E(400, "الترتيب يجب أن يكون بين 1 و20")
                        normalized.append({"key":item['key'],"name":name,"description":desc,"visible":bool(item.get('visible')),"order":order})
                    if len({x['order'] for x in normalized}) != len(normalized): raise E(400, "لا تكرر رقم الترتيب")
                    c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("home_sections_v1", json.dumps(normalized, ensure_ascii=False)))
                    audit(c, u['id'], "settings.home_sections", None, {"count":len(normalized)}); c.commit()
                    return self.send(200, {"ok":True,"sections":sorted(normalized,key=lambda x:x['order'])})
                raise E(405, "طريقة غير مدعومة")
            if method == "POST" and path == "/api/admin/settings":
                self.need(u, "admin"); d = self.body()
                if d.get("commission_type") not in ("fixed", "percent"): raise E(400, "نوع العمولة غير صالح")
                try: v = float(d.get("commission_value"))
                except (TypeError, ValueError): raise E(400, "قيمة العمولة غير صالحة")
                if v < 0 or (d["commission_type"] == "percent" and v > 100): raise E(400, "قيمة العمولة غير صالحة")
                for k, x in (("commission_type", d["commission_type"]), ("commission_value", v)): c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(x)))
                audit(c, u["id"], "settings.commission", None, d); c.commit(); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/courier/topups":
                courier(); d = self.body(); ref = str(d.get("transfer_ref", "")).strip()
                try: amt = float(d.get("amount"))
                except (TypeError, ValueError): amt = 0
                if amt <= 0 or len(ref) < 4: raise E(400, "المبلغ ومرجع التحويل مطلوبان")
                if c.execute("SELECT COUNT(*) FROM topup_requests WHERE courier_id=? AND status='pending'", (u["id"],)).fetchone()[0] >= int(cfg(c, "topup_max_pending", 3)): raise E(429, "لديك طلبات شحن قيد المراجعة كثيرة، انتظر مراجعتها أولًا")
                tk = "topup|%d" % u["id"]
                if throttled(c, tk, 10, 3600): raise E(429, "محاولات شحن كثيرة، حاول لاحقًا")
                note_fail(c, tk)
                try: cur = c.execute("INSERT INTO topup_requests(courier_id,amount,transfer_ref,note,created_at) VALUES(?,?,?,?,?)", (u["id"], amt, ref, str(d.get("note", ""))[:300], int(time.time())))
                except sqlite3.IntegrityError: raise E(409, "مرجع التحويل مستخدم من قبل")
                c.commit(); return self.send(201, {"id": cur.lastrowid, "status": "pending"})
            if method == "GET" and path == "/api/courier/wallet":
                courier(); _bal, _free = wallet_free(c, u["id"]); return self.send(200, {"balance": _bal, "available": _free, "held": round(_bal - _free, 2),
                    "entries": [dict(r) for r in c.execute(LEDGER_SQL % 50, (u["id"], u["id"]))],
                    "topups": [dict(r) for r in c.execute("SELECT id,amount,transfer_ref,status,reason,created_at FROM topup_requests WHERE courier_id=? ORDER BY id DESC LIMIT 20", (u["id"],))],
                    "topup_instructions": (c.execute("SELECT value FROM settings WHERE key='topup_instructions'").fetchone() or [""])[0]})
            if path == "/api/admin/topup-settings":  # transfer instructions shown to couriers + cap on pending top-up requests per courier
                self.need(u, "admin")
                if method == "GET":
                    ins = c.execute("SELECT value FROM settings WHERE key='topup_instructions'").fetchone()
                    return self.send(200, {"instructions": ins[0] if ins else "", "max_pending": int(cfg(c, "topup_max_pending", 3))})
                d = self.body()
                if "instructions" in d:
                    ins = str(d["instructions"]).strip()
                    if len(ins) > 500: raise E(400, "التعليمات يجب ألا تتجاوز 500 حرف")
                    c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("topup_instructions", ins))
                if "max_pending" in d:
                    try: mp = int(d["max_pending"])
                    except (TypeError, ValueError): raise E(400, "قيمة غير صالحة: max_pending")
                    if not 1 <= mp <= 20: raise E(400, "الحد يجب أن يكون بين 1 و20")
                    c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("topup_max_pending", str(mp)))
                audit(c, u["id"], "settings.topup", None, {k: d[k] for k in ("instructions", "max_pending") if k in d}); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/admin/topups":
                self.need(u, "admin"); return self.send(200, [dict(r) for r in c.execute("SELECT t.*,u.name,u.phone FROM topup_requests t JOIN users u ON u.id=t.courier_id WHERE t.status=? ORDER BY t.id", (q.get("status", ["pending"])[0],))])
            m = re.fullmatch(r"/api/admin/topups/(\d+)/review", path)
            if method == "POST" and m:
                self.need(u, "admin"); d = self.body(); st = d.get("status"); tid = int(m[1])
                if st not in ("approved", "rejected"): raise E(400, "حالة غير صالحة")
                if st == "rejected" and not d.get("reason"): raise E(400, "اذكر سبب الرفض")
                t = c.execute("SELECT * FROM topup_requests WHERE id=?", (tid,)).fetchone()
                if not t or not c.execute("UPDATE topup_requests SET status=?,reason=?,reviewed_by=? WHERE id=? AND status='pending'", (st, d.get("reason"), u["id"], tid)).rowcount: raise E(409, "الطلب غير قيد المراجعة")
                if st == "approved": c.execute("INSERT INTO wallet_entries(user_id,kind,amount,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?)", (t["courier_id"], "topup", t["amount"], "topup", tid, int(time.time())))
                audit(c, u["id"], "topup." + st, str(tid), d); c.commit(); return self.send(200, {"ok": True})
            m = re.fullmatch(r"/api/delivery/orders/(\d+)/rate", path)
            if method == "POST" and m:
                self.need(u); d = self.body(); o = c.execute("SELECT courier_id FROM delivery_orders WHERE id=? AND customer_id=? AND status='completed'", (int(m[1]), u["id"])).fetchone()
                if not o: raise E(404, "لا يمكن تقييم هذا الطلب")
                if d.get("stars") not in (1, 2, 3, 4, 5): raise E(400, "التقييم من 1 إلى 5")
                try: c.execute("INSERT INTO ratings VALUES(?,?,?,?,?,?)", (int(m[1]), u["id"], o["courier_id"], d["stars"], str(d.get("comment", ""))[:300], int(time.time())))
                except sqlite3.IntegrityError: raise E(409, "قيّمت هذا الطلب من قبل")
                c.commit(); return self.send(201, {"ok": True})
            if method == "GET" and path == "/api/courier/stats":
                courier(); me = u["id"]; one = lambda sql, *a: c.execute(sql, a).fetchone()[0]
                acc = one("SELECT COUNT(*) FROM order_events WHERE actor_id=? AND to_status='assigned'", me)
                done = one("SELECT COUNT(*) FROM delivery_orders WHERE courier_id=? AND status='completed'", me)
                rel = one("SELECT COUNT(*) FROM order_events WHERE actor_id=? AND to_status='searching' AND from_status IN('assigned','heading_pickup')", me)
                rc, ra = c.execute("SELECT COUNT(*),AVG(stars) FROM ratings WHERE courier_id=?", (me,)).fetchone()
                at_ = one("SELECT AVG(e.at-o.created_at) FROM order_events e JOIN delivery_orders o ON o.id=e.order_id WHERE e.actor_id=? AND e.to_status='assigned'", me)
                return self.send(200, {"accepted": acc, "completed": done, "released": rel, "completion_rate": round(done / acc, 3) if acc else None, "release_rate": round(rel / acc, 3) if acc else None,
                    "rating_avg": round(ra, 2) if rc else None, "rating_count": rc, "avg_accept_seconds": round(at_) if at_ is not None else None})
            if method == "GET" and path == "/api/courier/ratings":
                courier(); return self.send(200, [dict(r) for r in c.execute("SELECT order_id,stars,comment,created_at FROM ratings WHERE courier_id=? ORDER BY created_at DESC LIMIT 20", (u["id"],))])
            # ---- بروفايل المندوب (المرحلة 38): صورة شخصية يضبطها المندوب نفسه + صفحة بيانات فعلية يراها العميل قبل الموافقة على الأجرة ----
            if method == "POST" and path == "/api/courier/avatar":
                cr = courier(); fid = toint(self.body().get("file_id")); old = cr["avatar_file_id"]
                f = c.execute("SELECT * FROM files WHERE id=? AND owner_id=?", (fid, u["id"])).fetchone() if fid else None
                if not f: raise E(400, "الصورة غير موجودة، ارفعها أولًا")
                if c.execute("SELECT 1 FROM courier_documents WHERE file_id=?", (fid,)).fetchone(): raise E(409, "لا يمكن استخدام صورة مستند التحقق كصورة بروفايل")
                c.execute("UPDATE couriers SET avatar_file_id=? WHERE user_id=?", (fid, u["id"]))
                if old and old != fid:  # الصورة القديمة تُحذف بعد الاستبدال (لا يشير إليها شيء آخر)
                    of = c.execute("SELECT * FROM files WHERE id=? AND owner_id=?", (old, u["id"])).fetchone()
                    if of and not c.execute("SELECT 1 FROM courier_documents WHERE file_id=?", (old,)).fetchone():
                        c.execute("DELETE FROM files WHERE id=?", (old,))
                        try: os.remove(os.path.join(UP, of["path"]))
                        except OSError: pass
                audit(c, u["id"], "courier.avatar_set", str(fid)); c.commit(); return self.send(200, {"ok": True, "has_avatar": True})
            m = re.fullmatch(r"/api/couriers/(\d+)/(profile|photo)", path)
            if method == "GET" and m:
                self.need(u); cid = int(m[1])
                cr = c.execute("SELECT * FROM couriers WHERE user_id=? AND status='approved'", (cid,)).fetchone()
                # يراه: المندوب نفسه، الإدارة، أو عميل مندوبه هذا (أجرة مقترحة/موافَق عليها) — لا كشف عام لبيانات المناديب
                if not cr or not (cid == u["id"] or u["role"] in ("admin", "staff") or c.execute("SELECT 1 FROM delivery_orders WHERE customer_id=? AND courier_id=? AND fare_status IN('proposed','approved')", (u["id"], cid)).fetchone()): raise E(404, "غير موجود")
                if m[2] == "photo":
                    f = c.execute("SELECT * FROM files WHERE id=?", (cr["avatar_file_id"],)).fetchone() if cr["avatar_file_id"] else None
                    if not f: raise E(404, "لا توجد صورة")
                    try: raw = open(os.path.join(UP, f["path"]), "rb").read()
                    except OSError: raise E(404, "لا توجد صورة")
                    return self.send(200, None, f["mime"], raw, {"Cache-Control": "private, max-age=300"})
                one = lambda sql, *a: c.execute(sql, a).fetchone()[0]
                acc = one("SELECT COUNT(*) FROM order_events WHERE actor_id=? AND to_status='assigned'", cid)
                done = one("SELECT COUNT(*) FROM delivery_orders WHERE courier_id=? AND status='completed'", cid)
                rc, ra = c.execute("SELECT COUNT(*),AVG(stars) FROM ratings WHERE courier_id=?", (cid,)).fetchone()
                cm = [{"stars": r["stars"], "comment": r["comment"], "created_at": r["created_at"], "customer": (str(r["name"]).split() or ["عميل"])[0]}  # الاسم الأول فقط
                      for r in c.execute("SELECT r.stars,r.comment,r.created_at,cu.name FROM ratings r JOIN users cu ON cu.id=r.customer_id WHERE r.courier_id=? AND r.comment IS NOT NULL AND TRIM(r.comment)!='' ORDER BY r.created_at DESC LIMIT 30", (cid,))]
                nm = one("SELECT name FROM users WHERE id=?", cid)
                return self.send(200, {"id": cid, "name": nm, "has_photo": bool(cr["avatar_file_id"]), "available": bool(is_online(c, cr)), "member_since": cr["created_at"],
                    "rating_avg": round(ra, 2) if rc else None, "rating_count": rc, "completed": done,
                    "completion_rate": round(min(done / acc, 1), 3) if acc else None, "comments": cm})
            if method == "GET" and path == "/api/admin/settings":
                self.need(u, "admin"); return self.send(200, {"settings": {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")},
                    "fees": [dict(r) for r in c.execute("SELECT f.region_id,r.name_ar,f.fee FROM region_fees f JOIN regions r ON r.id=f.region_id ORDER BY r.parent_id,r.sort,r.id")]})
            if path == "/api/admin/delivery-settings":
                self.need(u, "admin")
                if method == "GET": return self.send(200, {"offer_timeout": int(cfg(c, "offer_timeout", 30)), "search_timeout": int(cfg(c, "search_timeout", 300)), "heartbeat_ttl": int(cfg(c, "heartbeat_ttl", 45)), "auto_confirm_hours": cfg(c, "auto_confirm_hours", 24)})
                d = self.body(); lim = {"offer_timeout": (10, 300), "search_timeout": (60, 3600), "heartbeat_ttl": (15, 300)}
                for k, (lo, hi) in lim.items():
                    if k in d:
                        try: v = int(d[k])
                        except (TypeError, ValueError): raise E(400, "قيمة غير صالحة: " + k)
                        if not lo <= v <= hi: raise E(400, "%s يجب أن تكون بين %d و%d" % (k, lo, hi))
                        c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
                audit(c, u["id"], "settings.delivery", None, d); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/admin/couriers/online":
                self.need(u, "admin", "staff"); out = []
                for r in c.execute("SELECT c.*,u.name,u.phone FROM couriers c JOIN users u ON u.id=c.user_id WHERE c.status='approved' ORDER BY c.last_seen DESC").fetchall():
                    out.append({"user_id": r["user_id"], "name": r["name"], "phone": r["phone"], "region_id": r["region_id"], "is_available": r["is_available"], "last_seen": r["last_seen"], "online": is_online(c, r), "available_balance": wallet_free(c, r["user_id"])[1]})
                return self.send(200, out)
            m = re.fullmatch(r"/api/admin/couriers/(\d+)/wallet", path)
            if method == "GET" and m:  # read-only: one courier's balance, held commission and ledger (admin only)
                self.need(u, "admin"); cid = int(m[1])
                cr = c.execute("SELECT c.status,c.region_id,u.name,u.phone FROM couriers c JOIN users u ON u.id=c.user_id WHERE c.user_id=?", (cid,)).fetchone()
                if not cr: raise E(404, "المندوب غير موجود")
                bal, free = wallet_free(c, cid)
                return self.send(200, {"user_id": cid, "name": cr["name"], "phone": cr["phone"], "status": cr["status"], "balance": bal, "held": round(bal - free, 2), "available_balance": free,
                    "entries": [dict(r) for r in c.execute(LEDGER_SQL % 100, (cid, cid))],
                    "topups": [dict(r) for r in c.execute("SELECT id,amount,transfer_ref,status,reason,created_at FROM topup_requests WHERE courier_id=? ORDER BY id DESC LIMIT 50", (cid,))]})
            m = re.fullmatch(r"/api/admin/couriers/(\d+)/wallet-adjust", path)
            if method == "POST" and m:  # manual credit/debit by an admin: mandatory reason, audited, never pushes the AVAILABLE balance below zero (held commissions stay covered)
                self.need(u, "admin"); cid = int(m[1]); d = self.body(); why = str(d.get("reason", "")).strip(); rk = str(d.get("request_key", "")).strip()[:64] or None
                try: amt = round(float(d.get("amount")), 2)
                except (TypeError, ValueError): amt = 0
                if not (amt == amt and amt != 0 and abs(amt) <= 100000): raise E(400, "المبلغ غير صالح (غير صفري وحتى 100000)")
                if len(why) < 3 or len(why) > 300: raise E(400, "السبب مطلوب (3 إلى 300 حرفًا)")
                if not c.execute("SELECT 1 FROM couriers WHERE user_id=?", (cid,)).fetchone(): raise E(404, "المندوب غير موجود")
                c.commit(); c.execute("BEGIN IMMEDIATE")  # balance check and insert under one write lock: no race with accepts or commissions
                try:
                    if rk:
                        dup = c.execute("SELECT id,amount FROM wallet_adjustments WHERE admin_id=? AND request_key=?", (u["id"], rk)).fetchone()
                        if dup: c.rollback(); bal, free = wallet_free(c, cid); return self.send(200, {"id": dup["id"], "amount": dup["amount"], "balance": bal, "available_balance": free, "duplicate": True})
                    bal, free = wallet_free(c, cid)
                    if free + amt < 0: raise E(409, "الرصيد المتاح (%s ج) لا يكفي للخصم؛ جزء منه محجوز لطلبات جارية" % round(free, 2))
                    cur = c.execute("INSERT INTO wallet_adjustments(user_id,amount,reason,admin_id,request_key,created_at) VALUES(?,?,?,?,?,?)", (cid, amt, why, u["id"], rk, int(time.time())))
                    audit(c, u["id"], "wallet.adjust", str(cid), {"amount": amt, "reason": why, "adjustment_id": cur.lastrowid}); c.commit()
                except E: c.rollback() if c.in_transaction else None; raise
                bal, free = wallet_free(c, cid); return self.send(201, {"id": cur.lastrowid, "amount": amt, "balance": bal, "available_balance": free})
            m = re.fullmatch(r"/api/admin/orders/(\d+)/offers", path)
            if method == "GET" and m:
                self.need(u, "admin", "staff")
                return self.send(200, [dict(r) for r in c.execute("SELECT f.courier_id,cu.name,f.status,f.offered_at,f.responded_at,f.rounds FROM order_offers f JOIN users cu ON cu.id=f.courier_id WHERE f.order_id=? ORDER BY f.offered_at", (int(m[1]),))])
            # ---------- doctors & specialties ----------
            def doc_row(r, full=True):
                d = {k: r[k] for k in ("id", "name_ar", "specialty_id", "specialty", "region_id", "region_name", "clinic_name", "address", "schedule", "bio") if k in r.keys()}
                d["photo_url"] = "/api/doctors/%d/photo?v=%d" % (r["id"], r["photo_file_id"]) if r["photo_file_id"] else None  # public, published-only endpoint; ?v= busts the cache when the photo changes
                if full:  # numbers only in the admin view; the public gets them from /api/doctors/<id>/contact (login + hourly cap)
                    d.update(phone=r["phone"], whatsapp=r["whatsapp"], photo_file_id=r["photo_file_id"])
                    if "is_published" in r.keys(): d["is_published"] = r["is_published"]
                return d
            DSEL = "SELECT d.*,s.name_ar specialty,rg.name_ar region_name FROM doctors d JOIN specialties s ON s.id=d.specialty_id JOIN regions rg ON rg.id=d.region_id"
            PUBW = " d.is_published=1 AND s.is_active=1 AND rg.is_active=1"
            def doc_clean(d, cur=None):
                g = lambda k: str(d.get(k, cur[k] if cur is not None and k in cur.keys() and cur[k] is not None else "") if k in d or cur is not None else "").strip()
                v = {k: g(k) for k in ("name_ar", "clinic_name", "address", "schedule", "phone", "whatsapp", "bio")}
                v["specialty_id"] = d.get("specialty_id", cur["specialty_id"] if cur is not None else None); v["region_id"] = d.get("region_id", cur["region_id"] if cur is not None else None)
                if len(v["name_ar"]) < 3: raise E(400, "اسم الطبيب مطلوب")
                if not c.execute("SELECT 1 FROM specialties WHERE id=?", (v["specialty_id"],)).fetchone(): raise E(400, "التخصص غير موجود")
                if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (v["region_id"],)).fetchone(): raise E(400, "المنطقة غير مفعّلة")
                for k in ("phone", "whatsapp"):
                    if v[k] and not re.fullmatch(r"\+?\d{7,15}", v[k]): raise E(400, "رقم غير صالح: " + k)
                for k, n in (("name_ar", 120), ("clinic_name", 120), ("address", 300), ("schedule", 500), ("bio", 1000)): v[k] = v[k][:n]
                return v
            def doc_complete(v):
                if not (v["address"] or v["clinic_name"]): raise E(409, "أدخل عنوان العيادة أو اسمها قبل النشر")
                if not (v["phone"] or v["whatsapp"] or v["schedule"]): raise E(409, "أدخل وسيلة تواصل أو مواعيد قبل النشر")
            def photo_arg(d, cur, tbl):
                """Photo change requested by the admin form. Returns (changed, file_id|None). Key absent => photo untouched (editing text never drops it)."""
                if "photo_file_id" not in d: return False, None
                pid = d["photo_file_id"]
                if pid in (None, "", 0, False): return True, None
                pid = toint(pid)
                if cur is not None and cur["photo_file_id"] == pid: return False, None
                f = c.execute("SELECT * FROM files WHERE id=?", (pid,)).fetchone()
                if not f or f["owner_id"] != u["id"]: raise E(400, "الصورة غير موجودة، ارفعها من جديد")
                if f["mime"] not in ("image/jpeg", "image/png"): raise E(400, "الصيغة المدعومة: JPG أو PNG")
                if (c.execute("SELECT 1 FROM courier_documents WHERE file_id=?", (pid,)).fetchone() or c.execute("SELECT 1 FROM prescriptions WHERE file_id=?", (pid,)).fetchone() or c.execute("SELECT 1 FROM rx_images WHERE file_id=?", (pid,)).fetchone()
                        or c.execute("SELECT 1 FROM doctors WHERE photo_file_id=?", (pid,)).fetchone() or c.execute("SELECT 1 FROM labs WHERE photo_file_id=?", (pid,)).fetchone()):
                    raise E(409, "هذه الصورة مستخدمة في موضع آخر")
                return True, pid
            def drop_photo(fid):
                """Remove a replaced/cleared photo (row + file on disk) once nothing references it."""
                if not fid: return
                f = c.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
                if not f or c.execute("SELECT 1 FROM doctors WHERE photo_file_id=?", (fid,)).fetchone() or c.execute("SELECT 1 FROM labs WHERE photo_file_id=?", (fid,)).fetchone(): return
                c.execute("DELETE FROM files WHERE id=?", (fid,)); c.commit()
                try: os.remove(os.path.join(UP, f["path"]))
                except OSError: pass
            def send_photo(r):
                f = c.execute("SELECT * FROM files WHERE id=?", (r["photo_file_id"],)).fetchone() if r["photo_file_id"] else None
                if not f: raise E(404, "لا توجد صورة")
                try: raw = open(os.path.join(UP, f["path"]), "rb").read()
                except OSError: raise E(404, "لا توجد صورة")
                return self.send(200, None, f["mime"], raw, {"Cache-Control": "public, max-age=604800, immutable"})
            if method == "GET" and path == "/api/specialties":
                adm = q.get("all", [""])[0] == "1"
                if adm: self.need(u, "admin", "staff")
                return self.send(200, [dict(r) for r in c.execute("SELECT s.id,s.name_ar,s.is_active,(SELECT COUNT(*) FROM doctors d JOIN regions rg ON rg.id=d.region_id WHERE d.specialty_id=s.id AND d.is_published=1 AND rg.is_active=1) published FROM specialties s WHERE ?1 OR (s.is_active=1 AND EXISTS(SELECT 1 FROM doctors d JOIN regions rg ON rg.id=d.region_id WHERE d.specialty_id=s.id AND d.is_published=1 AND rg.is_active=1)) ORDER BY s.name_ar", (1 if adm else 0,))])
            if method == "POST" and path == "/api/admin/specialties":
                self.need(u, "admin"); nm = str(self.body().get("name_ar", "")).strip()[:60]
                if len(nm) < 2: raise E(400, "اسم التخصص مطلوب")
                try: cur = c.execute("INSERT INTO specialties(name_ar,name_norm) VALUES(?,?)", (nm, norm_ar(nm)))
                except sqlite3.IntegrityError: raise E(409, "التخصص موجود")
                audit(c, u["id"], "specialty.add", str(cur.lastrowid), {"name": nm}); c.commit(); return self.send(201, {"id": cur.lastrowid})
            m = re.fullmatch(r"/api/admin/specialties/(\d+)", path)
            if method == "POST" and m:
                self.need(u, "admin"); d = self.body(); sp = c.execute("SELECT * FROM specialties WHERE id=?", (int(m[1]),)).fetchone()
                if not sp: raise E(404, "غير موجود")
                nm = str(d.get("name_ar", sp["name_ar"])).strip()[:60]; act = 1 if d.get("is_active", sp["is_active"]) in (1, True) else 0
                if len(nm) < 2: raise E(400, "اسم التخصص مطلوب")
                try: c.execute("UPDATE specialties SET name_ar=?,name_norm=?,is_active=? WHERE id=?", (nm, norm_ar(nm), act, sp["id"]))
                except sqlite3.IntegrityError: raise E(409, "التخصص موجود")
                audit(c, u["id"], "specialty.update", m[1], {"name": nm, "is_active": act}); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/doctors":
                qq = norm_ar(q.get("q", [""])[0]); toks = qq.split(); sid = toint(q.get("specialty_id", [0])[0]); rid = toint(q.get("region_id", [0])[0])
                sql = DSEL + " WHERE" + PUBW; args = []
                if sid: sql += " AND d.specialty_id=?"; args.append(sid)
                if rid: sql += " AND d.region_id IN " + COVER; args.append(rid)
                rows = c.execute(sql, args).fetchall(); out = []
                for r in rows:
                    hay = " ".join((r["name_norm"], norm_ar(r["specialty"]), norm_ar(r["clinic_name"])))
                    if all(t in hay for t in toks): out.append((0 if toks and r["name_norm"].startswith(toks[0]) else 1, r["name_norm"], r))
                out.sort(key=lambda x: x[:2]); return self.send(200, [doc_row(r, False) for _, _, r in out[:50]])
            m = re.fullmatch(r"/api/doctors/(\d+)/photo", path)
            if method == "GET" and m:  # public, but only for published doctors; unpublished photos stay admin-only (via /api/files)
                r = c.execute(DSEL + " WHERE d.id=? AND" + PUBW, (int(m[1]),)).fetchone()
                if not r: raise E(404, "لا توجد صورة")
                return send_photo(r)
            m = re.fullmatch(r"/api/doctors/(\d+)(/contact)?", path)
            if method == "GET" and m:
                r = c.execute(DSEL + " WHERE d.id=? AND" + PUBW, (int(m[1]),)).fetchone()
                if not r: raise E(404, "الطبيب غير موجود")
                if not m[2]: return self.send(200, doc_row(r, False))
                self.need(u); contact_guard(c, u, "doctor.contact", m[1])
                return self.send(200, {"name_ar": r["name_ar"], "phone": r["phone"], "whatsapp": r["whatsapp"]})
            if method == "GET" and path == "/api/admin/doctors":
                self.need(u, "admin", "staff"); return self.send(200, [doc_row(r) for r in c.execute(DSEL + " ORDER BY d.id DESC LIMIT 200")])
            if method == "POST" and path == "/api/admin/doctors":
                self.need(u, "admin"); d = self.body(); v = doc_clean(d); now = int(time.time()); _, ph = photo_arg(d, None, "doctors")
                cur = c.execute("INSERT INTO doctors(name_ar,name_norm,specialty_id,region_id,clinic_name,address,schedule,phone,whatsapp,bio,photo_file_id,is_published,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,?,?)", (v["name_ar"], norm_ar(v["name_ar"]), v["specialty_id"], v["region_id"], v["clinic_name"], v["address"], v["schedule"], v["phone"], v["whatsapp"], v["bio"], ph, now, now))
                audit(c, u["id"], "doctor.add", str(cur.lastrowid)); c.commit(); return self.send(201, {"id": cur.lastrowid, "is_published": 0})  # always created unpublished
            m = re.fullmatch(r"/api/admin/doctors/(\d+)(/publish)?", path)
            if method == "POST" and m:
                self.need(u, "admin"); cur = c.execute("SELECT * FROM doctors WHERE id=?", (int(m[1]),)).fetchone()
                if not cur: raise E(404, "غير موجود")
                d = self.body()
                if m[2]:
                    pub = 1 if d.get("published") in (1, True) else 0
                    if pub: doc_complete(doc_clean({}, cur))
                    c.execute("UPDATE doctors SET is_published=?,updated_at=? WHERE id=?", (pub, int(time.time()), cur["id"])); audit(c, u["id"], "doctor.publish" if pub else "doctor.unpublish", m[1]); c.commit(); return self.send(200, {"is_published": pub})
                v = doc_clean(d, cur)
                if cur["is_published"]: doc_complete(v)  # a published profile can't be edited into an incomplete one
                chg, ph = photo_arg(d, cur, "doctors"); ph = ph if chg else cur["photo_file_id"]
                c.execute("UPDATE doctors SET name_ar=?,name_norm=?,specialty_id=?,region_id=?,clinic_name=?,address=?,schedule=?,phone=?,whatsapp=?,bio=?,photo_file_id=?,updated_at=? WHERE id=?", (v["name_ar"], norm_ar(v["name_ar"]), v["specialty_id"], v["region_id"], v["clinic_name"], v["address"], v["schedule"], v["phone"], v["whatsapp"], v["bio"], ph, int(time.time()), cur["id"]))
                audit(c, u["id"], "doctor.update", m[1], {"photo": "changed" if chg else "kept"}); c.commit()
                if chg and cur["photo_file_id"] != ph: drop_photo(cur["photo_file_id"])
                return self.send(200, {"ok": True})
            # ---- الخدمات المحلية: الأنواع تُدار من لوحة الإدارة، والمقدّمون يُضافون يدويًا من الإدارة ويُنشرون بعد اكتمال بيانات التواصل؛ الأرقام لا تظهر إلا بعد تسجيل الدخول وبحد يومي
            SSEL = "SELECT p.*,t.name_ar type,rg.name_ar region_name FROM service_providers p JOIN service_types t ON t.id=p.type_id JOIN regions rg ON rg.id=p.region_id"
            SPUB = " p.is_published=1 AND t.is_active=1 AND rg.is_active=1"
            def svc_row(r, admin=False):
                d = {k: r[k] for k in ("id", "name_ar", "type_id", "type", "region_id", "region_name", "description", "address")}
                if admin: d.update(phone=r["phone"], whatsapp=r["whatsapp"], is_published=r["is_published"])
                d.update(svc.rating_of(c, r["id"]))  # Phase 6b
                return d
            def svc_clean(d, cur=None):
                g = lambda k: str(d.get(k, cur[k] if cur is not None and cur[k] is not None else "") if k in d or cur is not None else "").strip()
                v = {k: g(k) for k in ("name_ar", "description", "address", "phone", "whatsapp")}
                v["type_id"] = d.get("type_id", cur["type_id"] if cur is not None else None); v["region_id"] = d.get("region_id", cur["region_id"] if cur is not None else None)
                if len(v["name_ar"]) < 3: raise E(400, "اسم مقدّم الخدمة مطلوب")
                if not c.execute("SELECT 1 FROM service_types WHERE id=?", (v["type_id"],)).fetchone(): raise E(400, "نوع الخدمة غير موجود")
                if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (v["region_id"],)).fetchone(): raise E(400, "المنطقة غير مفعّلة")
                for k in ("phone", "whatsapp"):
                    if v[k] and not re.fullmatch(r"\+?\d{7,15}", v[k]): raise E(400, "رقم غير صالح: " + k)
                for k, n in (("name_ar", 120), ("description", 500), ("address", 300)): v[k] = v[k][:n]
                return v
            def svc_complete(v):
                if not (v["phone"] or v["whatsapp"]): raise E(409, "أدخل رقم هاتف أو واتساب قبل النشر")
            if method == "GET" and path == "/api/service-types":
                adm = q.get("all", [""])[0] == "1"
                if adm: self.need(u, "admin", "staff")
                return self.send(200, [dict(r) for r in c.execute("SELECT t.id,t.name_ar,t.is_active,(SELECT COUNT(*) FROM service_providers p JOIN regions rg ON rg.id=p.region_id WHERE p.type_id=t.id AND p.is_published=1 AND rg.is_active=1) published FROM service_types t WHERE ?1 OR (t.is_active=1 AND EXISTS(SELECT 1 FROM service_providers p JOIN regions rg ON rg.id=p.region_id WHERE p.type_id=t.id AND p.is_published=1 AND rg.is_active=1)) ORDER BY t.name_ar", (1 if adm else 0,))])
            if method == "POST" and path == "/api/admin/service-types":
                self.need(u, "admin"); nm = str(self.body().get("name_ar", "")).strip()[:60]
                if len(nm) < 2: raise E(400, "اسم نوع الخدمة مطلوب")
                try: cur = c.execute("INSERT INTO service_types(name_ar,name_norm) VALUES(?,?)", (nm, norm_ar(nm)))
                except sqlite3.IntegrityError: raise E(409, "النوع موجود")
                audit(c, u["id"], "service_type.add", str(cur.lastrowid), {"name": nm}); c.commit(); return self.send(201, {"id": cur.lastrowid})
            m = re.fullmatch(r"/api/admin/service-types/(\d+)", path)
            if method == "POST" and m:
                self.need(u, "admin"); d = self.body(); t = c.execute("SELECT * FROM service_types WHERE id=?", (int(m[1]),)).fetchone()
                if not t: raise E(404, "غير موجود")
                nm = str(d.get("name_ar", t["name_ar"])).strip()[:60]
                if len(nm) < 2: raise E(400, "اسم نوع الخدمة مطلوب")
                act = 1 if d.get("is_active", t["is_active"]) in (1, True) else 0
                try: c.execute("UPDATE service_types SET name_ar=?,name_norm=?,is_active=? WHERE id=?", (nm, norm_ar(nm), act, t["id"]))
                except sqlite3.IntegrityError: raise E(409, "النوع موجود")
                audit(c, u["id"], "service_type.update", m[1], {"name": nm, "active": act}); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/services":
                toks = norm_ar(q.get("q", [""])[0]).split(); tid = toint(q.get("type_id", [0])[0]); rid = toint(q.get("region_id", [0])[0])
                sql = SSEL + " WHERE" + SPUB; args = []
                if tid: sql += " AND p.type_id=?"; args.append(tid)
                if rid: sql += " AND p.region_id IN " + COVER; args.append(rid)
                out = []
                for r in c.execute(sql, args).fetchall():
                    hay = " ".join((r["name_norm"], norm_ar(r["type"]), norm_ar(r["description"])))
                    if all(t in hay for t in toks): out.append((0 if toks and r["name_norm"].startswith(toks[0]) else 1, r["name_norm"], r))
                out.sort(key=lambda x: x[:2]); return self.send(200, [svc_row(r) for _, _, r in out[:50]])
            m = re.fullmatch(r"/api/services/(\d+)/ratings", path)  # الخطوة 5: صفحة التقييمات العلنية (منشور فقط، بلا هوية)
            if method == "GET" and m:
                r = c.execute(SSEL + " WHERE p.id=? AND" + SPUB, (int(m[1]),)).fetchone()
                if not r: raise E(404, "مقدّم الخدمة غير موجود")
                return self.send(200, svc.public_ratings(c, r["id"], q))
            m = re.fullmatch(r"/api/services/(\d+)(/contact)?", path)
            if method == "GET" and m:
                r = c.execute(SSEL + " WHERE p.id=? AND" + SPUB, (int(m[1]),)).fetchone()
                if not r: raise E(404, "مقدّم الخدمة غير موجود")
                if not m[2]: return self.send(200, svc_row(r))
                self.need(u); contact_guard(c, u, "service.contact", m[1])
                return self.send(200, {"name_ar": r["name_ar"], "phone": r["phone"], "whatsapp": r["whatsapp"]})
            if method == "GET" and path == "/api/admin/services":
                self.need(u, "admin", "staff"); return self.send(200, [svc_row(r, True) for r in c.execute(SSEL + " ORDER BY p.id DESC LIMIT 200")])
            if method == "POST" and path == "/api/admin/services":
                self.need(u, "admin"); v = svc_clean(self.body()); now = int(time.time())
                cur = c.execute("INSERT INTO service_providers(name_ar,name_norm,type_id,region_id,description,address,phone,whatsapp,is_published,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,0,?,?)", (v["name_ar"], norm_ar(v["name_ar"]), v["type_id"], v["region_id"], v["description"], v["address"], v["phone"], v["whatsapp"], now, now))
                audit(c, u["id"], "service.add", str(cur.lastrowid)); c.commit(); return self.send(201, {"id": cur.lastrowid, "is_published": 0})  # always created unpublished
            m = re.fullmatch(r"/api/admin/services/(\d+)(/publish)?", path)
            if method == "POST" and m:
                self.need(u, "admin"); cur = c.execute("SELECT * FROM service_providers WHERE id=?", (int(m[1]),)).fetchone()
                if not cur: raise E(404, "غير موجود")
                d = self.body()
                if m[2]:
                    pub = 1 if d.get("published") in (1, True) else 0
                    if pub: svc_complete(svc_clean({}, cur))
                    c.execute("UPDATE service_providers SET is_published=?,updated_at=? WHERE id=?", (pub, int(time.time()), cur["id"])); audit(c, u["id"], "service.publish" if pub else "service.unpublish", m[1]); c.commit(); return self.send(200, {"is_published": pub})
                v = svc_clean(d, cur)
                if cur["is_published"]: svc_complete(v)  # a published profile can't be edited into an incomplete one
                c.execute("UPDATE service_providers SET name_ar=?,name_norm=?,type_id=?,region_id=?,description=?,address=?,phone=?,whatsapp=?,updated_at=? WHERE id=?", (v["name_ar"], norm_ar(v["name_ar"]), v["type_id"], v["region_id"], v["description"], v["address"], v["phone"], v["whatsapp"], int(time.time()), cur["id"]))
                audit(c, u["id"], "service.update", m[1]); c.commit(); return self.send(200, {"ok": True})
            # ---- معامل التحاليل: تُضاف يدويًا من الإدارة وتُنشر بعد اكتمال العنوان ووسيلة التواصل؛ بيانات نشاط تجاري فتُعرض أرقامها كالعيادات
            LSEL = "SELECT l.*,rg.name_ar region_name FROM labs l JOIN regions rg ON rg.id=l.region_id"
            LPUB = " l.is_published=1 AND rg.is_active=1"
            def lab_row(r, admin=False):
                d = {k: r[k] for k in ("id", "name_ar", "region_id", "region_name", "address", "hours", "tests", "home_visit")}
                d["photo_url"] = "/api/labs/%d/photo?v=%d" % (r["id"], r["photo_file_id"]) if r["photo_file_id"] else None
                if admin: d.update(phone=r["phone"], whatsapp=r["whatsapp"], is_published=r["is_published"], photo_file_id=r["photo_file_id"])  # public numbers: /api/labs/<id>/contact
                return d
            def lab_clean(d, cur=None):
                g = lambda k: str(d.get(k, cur[k] if cur is not None and cur[k] is not None else "") if k in d or cur is not None else "").strip()
                v = {k: g(k) for k in ("name_ar", "address", "hours", "tests", "phone", "whatsapp")}
                v["region_id"] = d.get("region_id", cur["region_id"] if cur is not None else None)
                v["home_visit"] = 1 if d.get("home_visit", cur["home_visit"] if cur is not None else 0) in (1, True) else 0
                if len(v["name_ar"]) < 3: raise E(400, "اسم المعمل مطلوب")
                if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (v["region_id"],)).fetchone(): raise E(400, "المنطقة غير مفعّلة")
                for k in ("phone", "whatsapp"):
                    if v[k] and not re.fullmatch(r"\+?\d{7,15}", v[k]): raise E(400, "رقم غير صالح: " + k)
                for k, n in (("name_ar", 120), ("address", 300), ("hours", 500), ("tests", 1000)): v[k] = v[k][:n]
                return v
            def lab_complete(v):
                if not v["address"]: raise E(409, "أدخل عنوان المعمل قبل النشر")
                if not (v["phone"] or v["whatsapp"]): raise E(409, "أدخل رقم هاتف أو واتساب قبل النشر")
            if method == "GET" and path == "/api/labs":
                toks = norm_ar(q.get("q", [""])[0]).split(); rid = toint(q.get("region_id", [0])[0]); lim = min(max(toint(q.get("limit", [50])[0], 50), 1), 50)
                sql = LSEL + " WHERE" + LPUB; args = []
                if rid: sql += " AND l.region_id IN " + COVER; args.append(rid)
                out = []
                for r in c.execute(sql, args).fetchall():
                    hay = " ".join((r["name_norm"], norm_ar(r["tests"])))
                    if all(t in hay for t in toks): out.append((0 if toks and r["name_norm"].startswith(toks[0]) else 1, r["name_norm"], r))
                out.sort(key=lambda x: x[:2]); return self.send(200, [lab_row(r) for _, _, r in out[:lim]])
            m = re.fullmatch(r"/api/labs/(\d+)/photo", path)
            if method == "GET" and m:
                r = c.execute(LSEL + " WHERE l.id=? AND" + LPUB, (int(m[1]),)).fetchone()
                if not r: raise E(404, "لا توجد صورة")
                return send_photo(r)
            m = re.fullmatch(r"/api/labs/(\d+)(/contact)?", path)
            if method == "GET" and m:
                r = c.execute(LSEL + " WHERE l.id=? AND" + LPUB, (int(m[1]),)).fetchone()
                if not r: raise E(404, "المعمل غير موجود")
                if not m[2]: return self.send(200, lab_row(r))
                self.need(u); contact_guard(c, u, "lab.contact", m[1])
                return self.send(200, {"name_ar": r["name_ar"], "phone": r["phone"], "whatsapp": r["whatsapp"]})
            if method == "GET" and path == "/api/admin/labs":
                self.need(u, "admin", "staff"); return self.send(200, [lab_row(r, True) for r in c.execute(LSEL + " ORDER BY l.id DESC LIMIT 200")])
            if method == "POST" and path == "/api/admin/labs":
                self.need(u, "admin"); d = self.body(); v = lab_clean(d); now = int(time.time()); _, ph = photo_arg(d, None, "labs")
                cur = c.execute("INSERT INTO labs(name_ar,name_norm,region_id,address,hours,tests,home_visit,phone,whatsapp,photo_file_id,is_published,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,0,?,?)", (v["name_ar"], norm_ar(v["name_ar"]), v["region_id"], v["address"], v["hours"], v["tests"], v["home_visit"], v["phone"], v["whatsapp"], ph, now, now))
                audit(c, u["id"], "lab.add", str(cur.lastrowid)); c.commit(); return self.send(201, {"id": cur.lastrowid, "is_published": 0})  # always created unpublished
            m = re.fullmatch(r"/api/admin/labs/(\d+)(/publish)?", path)
            if method == "POST" and m:
                self.need(u, "admin"); cur = c.execute("SELECT * FROM labs WHERE id=?", (int(m[1]),)).fetchone()
                if not cur: raise E(404, "غير موجود")
                d = self.body()
                if m[2]:
                    pub = 1 if d.get("published") in (1, True) else 0
                    if pub: lab_complete(lab_clean({}, cur))
                    c.execute("UPDATE labs SET is_published=?,updated_at=? WHERE id=?", (pub, int(time.time()), cur["id"])); audit(c, u["id"], "lab.publish" if pub else "lab.unpublish", m[1]); c.commit(); return self.send(200, {"is_published": pub})
                v = lab_clean(d, cur)
                if cur["is_published"]: lab_complete(v)  # a published profile can't be edited into an incomplete one
                chg, ph = photo_arg(d, cur, "labs"); ph = ph if chg else cur["photo_file_id"]
                c.execute("UPDATE labs SET name_ar=?,name_norm=?,region_id=?,address=?,hours=?,tests=?,home_visit=?,phone=?,whatsapp=?,photo_file_id=?,updated_at=? WHERE id=?", (v["name_ar"], norm_ar(v["name_ar"]), v["region_id"], v["address"], v["hours"], v["tests"], v["home_visit"], v["phone"], v["whatsapp"], ph, int(time.time()), cur["id"]))
                audit(c, u["id"], "lab.update", m[1], {"photo": "changed" if chg else "kept"}); c.commit()
                if chg and cur["photo_file_id"] != ph: drop_photo(cur["photo_file_id"])
                return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/admin/orders":
                self.need(u, "admin", "staff"); st = q.get("status", [None])[0]
                return self.send(200, [dict(r) for r in c.execute("SELECT o.id,o.status,o.fee,o.commission,o.pickup_text,o.dropoff_text,o.created_at,cu.name customer,co.name courier,(SELECT detail FROM audit_log WHERE action='order.dispute' AND target=CAST(o.id AS TEXT) ORDER BY id DESC LIMIT 1) dispute FROM delivery_orders o JOIN users cu ON cu.id=o.customer_id LEFT JOIN users co ON co.id=o.courier_id WHERE (?1 IS NULL OR o.status=?1) ORDER BY o.id DESC LIMIT 100", (st,))])
            if method == "GET" and path == "/api/admin/users":
                self.need(u, "admin"); t = "%" + q.get("q", [""])[0] + "%"
                return self.send(200, [dict(r) for r in c.execute("SELECT id,name,phone,role,created_at FROM users WHERE name LIKE ? OR phone LIKE ? ORDER BY id DESC LIMIT 50", (t, t))])
            if method == "GET" and path == "/api/admin/verifications":  # pending requests; the code itself is NOT shown: the admin must read it from the WhatsApp message
                self.need(u, "admin", "staff")
                return self.send(200, [dict(r) for r in c.execute("SELECT phone,purpose,created_at,expires FROM phone_verifications WHERE verified_at IS NULL AND expires>? ORDER BY created_at DESC LIMIT 100", (int(time.time()),))])
            if method == "POST" and path == "/api/admin/verifications/confirm":  # manual mode: the admin saw a WhatsApp message from this phone containing this code
                self.need(u, "admin", "staff"); d = self.body(); ph, code, purpose = str(d.get("phone", "")), str(d.get("code", "")).translate(AR_DIGITS).strip(), str(d.get("purpose", "register"))
                if not PHONE.match(ph) or purpose not in ("register", "reset"): raise E(400, "بيانات غير صحيحة")
                if not wa_ingest_manual(c, ph, purpose, code): raise E(400, "الكود غير مطابق أو منتهي")
                audit(c, u["id"], "phone.verified", ph, {"purpose": purpose, "via": "admin"}); c.commit(); return self.send(200, {"ok": True})
            m = re.fullmatch(r"/api/admin/users/(\d+)/reset-code", path)
            if method == "POST" and m:  # admin issues a one-time code AFTER verifying the user's identity out-of-band; the code is shown once and stored hashed
                self.need(u, "admin"); uid = int(m[1]); t = c.execute("SELECT role,phone FROM users WHERE id=?", (uid,)).fetchone()
                if not t: raise E(404, "المستخدم غير موجود")
                if uid == u["id"] or t["role"] == "admin": raise E(409, "لا يمكن إصدار كود لحساب مدير")
                code = "%08d" % secrets.randbelow(10 ** 8); sl = secrets.token_hex(16); now = int(time.time())
                c.execute("INSERT INTO password_resets(user_id,code_hash,salt,expires,attempts,issued_by,created_at) VALUES(?,?,?,?,0,?,?) ON CONFLICT(user_id) DO UPDATE SET code_hash=excluded.code_hash,salt=excluded.salt,expires=excluded.expires,attempts=0,issued_by=excluded.issued_by,created_at=excluded.created_at", (uid, hp(code, sl), sl, now + 1800, u["id"], now))
                audit(c, u["id"], "password.reset_code", str(uid)); c.commit(); return self.send(200, {"code": code, "expires_in": 1800, "phone": t["phone"]})
            m = re.fullmatch(r"/api/admin/users/(\d+)/role", path)
            if method == "POST" and m:
                self.need(u, "admin"); role = self.body().get("role"); uid = int(m[1])
                if role not in ("customer", "seller", "medical_provider", "staff"): raise E(400, "دور غير مسموح (المندوب يُعتمد من طلبات الانضمام)")
                t = c.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
                if not t or uid == u["id"] or t["role"] in ("admin", "courier"): raise E(409, "لا يمكن تغيير دور هذا الحساب")
                c.execute("UPDATE users SET role=? WHERE id=?", (role, uid)); audit(c, u["id"], "user.role", str(uid), {"from": t["role"], "to": role}); c.commit(); return self.send(200, {"ok": True})
            m = re.fullmatch(r"/api/admin/orders/(\d+)/(cancel|reassign)", path)
            if method == "POST" and m:
                self.need(u, "admin"); oid = int(m[1]); o = c.execute("SELECT status FROM delivery_orders WHERE id=?", (oid,)).fetchone()
                if not o: raise E(404, "غير موجود")
                frm, to, ccl = (("searching", "assigned", "heading_pickup", "picked_up", "heading_customer", "arrived", "awaiting_confirmation", "disputed"), "cancelled", "") if m[2] == "cancel" else (("assigned", "heading_pickup"), "searching", ",courier_id=NULL,fare_status='none'")
                now = int(time.time()); ccl += ",search_started_at=%d" % now if m[2] == "reassign" else ""  # إعادة التعيين = بحث جديد كامل (نافذة بحث جديدة)
                if not c.execute("UPDATE delivery_orders SET status=?,updated_at=?" + ccl + " WHERE id=? AND status IN (%s)" % ",".join("?" * len(frm)), (to, now, oid, *frm)).rowcount: raise E(409, "لا يمكن تنفيذ ذلك في الحالة الحالية")
                if m[2] == "reassign": c.execute("DELETE FROM order_offers WHERE order_id=?", (oid,))  # وإلا لا يرى الطلب كل مندوب سبق أن عُرض عليه (صفوف lost/accepted القديمة)
                ev(oid, o["status"], to); audit(c, u["id"], "order." + m[2], str(oid), None)
                if m[2] == "cancel":  # المرحلة 28: العمولة تُخصم عند التسليم، فإلغاء الإدارة بعدها يعكسها تلقائيًا (مرة واحدة) كما كان الإلغاء = لا عمولة
                    ent = c.execute("SELECT user_id,amount FROM wallet_entries WHERE kind='commission' AND ref_type='order' AND ref_id=?", (oid,)).fetchone()
                    if ent and c.execute("INSERT OR IGNORE INTO wallet_entries(user_id,kind,amount,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?)", (ent["user_id"], "reversal", -ent["amount"], "order", oid, now)).rowcount: audit(c, u["id"], "order.reverse_commission", str(oid), {"reason": "إلغاء إداري", "amount": -ent["amount"], "auto": True})
                c.commit()
                if m[2] == "reassign": push_new_order(oid)  # نبّه المناديب مثل الطلب الجديد
                return self.send(200, {"status": to})
            m = re.fullmatch(r"/api/delivery/orders/(\d+)/dispute", path)
            if method == "POST" and m:
                self.need(u); oid = int(m[1]); why = str(self.body().get("reason", "")).strip()
                if len(why) < 3: raise E(400, "اذكر سبب الاعتراض")
                if not c.execute("SELECT 1 FROM delivery_orders WHERE id=? AND customer_id=?", (oid, u["id"])).fetchone(): raise E(404, "غير موجود")
                if not c.execute("UPDATE delivery_orders SET status='disputed',updated_at=? WHERE id=? AND status='awaiting_confirmation'", (int(time.time()), oid)).rowcount: raise E(409, "لا يمكن الاعتراض في الحالة الحالية")
                ev(oid, "awaiting_confirmation", "disputed"); audit(c, u["id"], "order.dispute", str(oid), {"reason": why[:500]}); c.commit(); return self.send(200, {"status": "disputed"})
            m = re.fullmatch(r"/api/admin/orders/(\d+)/(complete|reverse-commission)", path)
            if method == "POST" and m:
                self.need(u, "admin"); oid = int(m[1]); why = str(self.body().get("reason", "")).strip()
                if len(why) < 3: raise E(400, "اذكر السبب")
                o = c.execute("SELECT status FROM delivery_orders WHERE id=?", (oid,)).fetchone()
                if not o: raise E(404, "غير موجود")
                if m[2] == "complete":
                    if not c.execute("UPDATE delivery_orders SET status='completed',updated_at=? WHERE id=? AND status IN('awaiting_confirmation','disputed')", (int(time.time()), oid)).rowcount: raise E(409, "لا يمكن الإكمال في الحالة الحالية")
                    ev(oid, o["status"], "completed"); charge_commission(c, oid); audit(c, u["id"], "order.admin_complete", str(oid), {"reason": why[:500]}); c.commit(); return self.send(200, {"status": "completed"})
                ent = c.execute("SELECT user_id,amount FROM wallet_entries WHERE kind='commission' AND ref_type='order' AND ref_id=?", (oid,)).fetchone()
                if o["status"] not in ("completed", "awaiting_confirmation", "disputed", "cancelled") or not ent: raise E(409, "لا توجد عمولة مخصومة لهذا الطلب")
                try: c.execute("INSERT INTO wallet_entries(user_id,kind,amount,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?)", (ent["user_id"], "reversal", -ent["amount"], "order", oid, int(time.time())))
                except sqlite3.IntegrityError: c.rollback(); raise E(409, "سبق عكس هذه العمولة")
                audit(c, u["id"], "order.reverse_commission", str(oid), {"reason": why[:500], "amount": -ent["amount"]}); c.commit(); return self.send(200, {"reversed": -ent["amount"]})
            if method == "POST" and path == "/api/admin/settings/auto-confirm":
                self.need(u, "admin")
                try: h = int(self.body().get("hours"))
                except (TypeError, ValueError): h = 0
                if not 1 <= h <= 720: raise E(400, "المدة بين 1 و720 ساعة")
                c.execute("INSERT INTO settings VALUES('auto_confirm_hours',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(h),)); audit(c, u["id"], "settings.auto_confirm", None, {"hours": h}); c.commit(); return self.send(200, {"hours": h})
            if method == "POST" and path == "/api/admin/settings/stock-fresh":
                self.need(u, "admin")
                try: h = int(self.body().get("hours"))
                except (TypeError, ValueError): h = 0
                if not 1 <= h <= 720: raise E(400, "المدة بين 1 و720 ساعة")
                c.execute("INSERT INTO settings VALUES('stock_fresh_hours',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(h),)); audit(c, u["id"], "settings.stock_fresh", None, {"hours": h}); c.commit(); return self.send(200, {"hours": h})
            if method == "GET" and path == "/api/admin/audit":
                self.need(u, "admin"); return self.send(200, [dict(r) for r in c.execute("SELECT a.id,a.action,a.target,a.detail,a.at,u.name actor FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 100")])
            if method == "GET" and path == "/api/admin/reports":
                self.need(u, "admin"); one = lambda sql: c.execute(sql).fetchone()[0]; rows = lambda sql: [dict(r) for r in c.execute(sql)]
                return self.send(200, {"orders_by_status": rows("SELECT status,COUNT(*) n FROM delivery_orders GROUP BY status"),
                    "completed_fees": one("SELECT COALESCE(SUM(fee),0) FROM delivery_orders WHERE status='completed'"), "commission_collected": one("SELECT COALESCE(-SUM(amount),0) FROM wallet_entries WHERE kind='commission'"),
                    "topups_credited": one("SELECT COALESCE(SUM(amount),0) FROM wallet_entries WHERE kind='topup'"), "adjustments_net": one("SELECT COALESCE(SUM(amount),0) FROM wallet_adjustments"), "pending_topups": one("SELECT COUNT(*) FROM topup_requests WHERE status='pending'"),
                    "listings_by_status": rows("SELECT status,COUNT(*) n FROM listings GROUP BY status"), "users_by_role": rows("SELECT role,COUNT(*) n FROM users GROUP BY role"),
                    "completed_by_region": rows("SELECT r.name_ar region,COUNT(*) n FROM delivery_orders o JOIN regions r ON r.id=o.region_id WHERE o.status='completed' GROUP BY r.id")})
            if method == "GET" and path == "/api/delivery/fee":
                f = region_fee(c, q.get("region_id", [0])[0])
                return self.send(200, {"available": bool(f)})  # السعر لا يظهر للعميل قبل اقتراح المندوب
            def anc(rid):
                out, n = [], rid
                while n and len(out) < 8:
                    out.append(n); r_ = c.execute("SELECT parent_id FROM regions WHERE id=?", (n,)).fetchone(); n = r_["parent_id"] if r_ else None
                return out
            def related(rid):
                # ancestors + the region itself + all descendants: a pharmacy and a customer match when one region contains the other
                ids = set(anc(rid)); ids.add(rid)
                ids.update(r_[0] for r_ in c.execute("WITH RECURSIVE r(id) AS (SELECT ? UNION SELECT g.id FROM regions g JOIN r ON g.parent_id=r.id) SELECT id FROM r", (rid,)))
                return sorted(ids)
            def prov():
                self.need(u); r = c.execute("SELECT * FROM providers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone()
                if not r: raise E(403, "حساب الصيدلية غير معتمد")
                return r
            def respond(table, col, pid_):
                d = self.body(); st = d.get("status"); price = d.get("price")
                if table == "prescription_responses" and rx._setting(c, "rx_claim_mode", 0) == 1:
                    raise E(409, "التوزيع التفصيلي مفعّل؛ استخدم نموذج تسعير الأصناف لتحديد حالة كل صنف وتأكيد التوافر الكامل")
                if st not in ("available", "unavailable", "needs_confirmation"): raise E(400, "حالة غير صالحة")
                if st == "available":
                    try: price = float(price)
                    except (TypeError, ValueError): price = 0
                    if price <= 0: raise E(400, "أدخل السعر عند تأكيد التوفر")
                else: price = None
                c.execute("INSERT INTO %s(%s,provider_id,status,price,note,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(%s,provider_id) DO UPDATE SET status=excluded.status,price=excluded.price,note=excluded.note,updated_at=excluded.updated_at" % (table, col, col), (pid_, u["id"], st, price, str(d.get("note", ""))[:300], int(time.time())))
                c.commit(); return self.send(200, {"ok": True})
            def resp_rows(table, col, id_): return [dict(r) for r in c.execute("SELECT x.provider_id,p.name_ar pharmacy,x.status,x.price,x.note,x.updated_at,(SELECT d.order_id FROM medical_delivery_links d JOIN delivery_orders o ON o.id=d.order_id WHERE d.source_type=? AND d.source_id=x.%s AND d.provider_id=x.provider_id AND o.status!='cancelled' ORDER BY d.order_id DESC LIMIT 1) delivery_order_id FROM %s x JOIN providers p ON p.user_id=x.provider_id WHERE x.%s=?%s ORDER BY x.updated_at DESC" % (col, table, col, " AND x.review='approved'" if table == "prescription_responses" else ""), ("inquiry" if table == "inquiry_responses" else "prescription", id_))]
            if method == "POST" and path == "/api/providers/apply":
                self.need(u); d = self.body(); nm = str(d.get("name_ar", "")).strip()
                if len(nm) < 3 or not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (d.get("region_id"),)).fetchone(): raise E(400, "اسم الصيدلية ومنطقة مفعّلة مطلوبان")
                try: c.execute("INSERT INTO providers(user_id,name_ar,region_id,address,created_at) VALUES(?,?,?,?,?)", (u["id"], nm, d["region_id"], str(d.get("address", ""))[:200], int(time.time())))
                except sqlite3.IntegrityError: raise E(409, "طلبك مقدّم بالفعل")
                c.commit(); return self.send(201, {"status": "pending"})
            if method == "GET" and path == "/api/admin/providers":
                self.need(u, "admin", "staff")
                st = q.get("status", ["pending"])[0]
                sql = "SELECT p.*,u.name,u.phone,rg.name_ar region_name,par.name_ar parent_region_name FROM providers p JOIN users u ON u.id=p.user_id JOIN regions rg ON rg.id=p.region_id LEFT JOIN regions par ON par.id=rg.parent_id WHERE (?='all' OR p.status=?) ORDER BY p.name_ar"
                return self.send(200, [dict(r) for r in c.execute(sql, (st, st))])
            if path == "/api/admin/rx/routing-settings":
                self.need(u, "admin")
                if method == "GET":
                    settings = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM settings WHERE key IN ('rx_claim_mode','rx_routing_mode','rx_direct_provider_id','rx_claim_timeout_minutes','rx_total_timeout_minutes','rx_distribution_regions')")}
                    regions = [dict(r) for r in c.execute("SELECT id,name_ar,parent_id FROM regions WHERE level='markaz' AND is_active=1 ORDER BY name_ar")]
                    pharmacies = [dict(r) for r in c.execute("SELECT p.user_id id,p.name_ar,p.region_id,p.distribution_enabled,rg.name_ar region_name FROM providers p JOIN regions rg ON rg.id=p.region_id WHERE p.status='approved' ORDER BY p.name_ar")]
                    try: selected_regions = json.loads(settings.get('rx_distribution_regions','[]'))
                    except Exception: selected_regions = []
                    return self.send(200, {"settings":settings,"regions":regions,"pharmacies":pharmacies,"distribution_regions":selected_regions,"distribution_provider_ids":[x['id'] for x in pharmacies if x['distribution_enabled']]})
                if method == "POST":
                    d = self.body()
                    mode = str(d.get('routing_mode','direct'))
                    if mode not in ('direct','automatic'): raise E(400, 'وضع التوجيه غير صالح')
                    current_claim_mode = str(cfg(c, 'rx_claim_mode', 0))
                    raw_claim_mode = d.get('claim_mode', current_claim_mode)
                    if raw_claim_mode in (True, 1, '1', 'true', 'on'): claim_mode = '1'
                    elif raw_claim_mode in (False, 0, '0', 'false', 'off'): claim_mode = '0'
                    else: raise E(400, 'قيمة تفعيل نظام الحجز غير صالحة')
                    try: direct = int(d.get('direct_provider_id') or 0); claim_timeout = int(d.get('claim_timeout_minutes',10)); total_timeout = int(d.get('total_timeout_minutes',60))
                    except (TypeError,ValueError): raise E(400, 'إحدى قيم التوجيه غير صالحة')
                    if not 1 <= claim_timeout <= 60: raise E(400, 'مهلة الحجز يجب أن تكون من 1 إلى 60 دقيقة')
                    if not 5 <= total_timeout <= 240: raise E(400, 'مدة الانتظار الكلية يجب أن تكون من 5 إلى 240 دقيقة')
                    if mode == 'direct' and not c.execute("SELECT 1 FROM providers WHERE user_id=? AND status='approved'",(direct,)).fetchone(): raise E(400,'اختر صيدلية مباشرة معتمدة')
                    regions = d.get('distribution_regions', [])
                    if not isinstance(regions,list) or len(regions)>200: raise E(400,'قائمة المراكز غير صالحة')
                    clean=[]
                    for rid in regions:
                        try: rid=int(rid)
                        except (TypeError,ValueError): raise E(400,'معرّف مركز غير صالح')
                        if not c.execute("SELECT 1 FROM regions WHERE id=? AND level='markaz' AND is_active=1",(rid,)).fetchone(): raise E(400,'كل الاختيارات يجب أن تكون مراكز مفعّلة')
                        if rid not in clean: clean.append(rid)
                    if mode == 'automatic' and not clean: raise E(400,'اختر مركزًا واحدًا على الأقل للتوزيع التلقائي')
                    provider_ids = d.get('distribution_provider_ids', [])
                    if not isinstance(provider_ids,list) or len(provider_ids)>500: raise E(400,'قائمة الصيدليات المشاركة غير صالحة')
                    selected_providers=[]
                    for pid in provider_ids:
                        try: pid=int(pid)
                        except (TypeError,ValueError): raise E(400,'معرّف صيدلية غير صالح')
                        if not c.execute("SELECT 1 FROM providers WHERE user_id=? AND status='approved'",(pid,)).fetchone(): raise E(400,'الصيدليات المشاركة يجب أن تكون معتمدة')
                        if pid not in selected_providers: selected_providers.append(pid)
                    values={'rx_claim_mode':claim_mode,'rx_routing_mode':mode,'rx_direct_provider_id':str(direct or ''),'rx_claim_timeout_minutes':str(claim_timeout),'rx_total_timeout_minutes':str(total_timeout),'rx_distribution_regions':json.dumps(clean)}
                    for k,val in values.items(): c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,val))
                    c.execute("UPDATE providers SET distribution_enabled=CASE WHEN status='approved' AND user_id IN (%s) THEN 1 ELSE 0 END" % (','.join('?'*len(selected_providers)) if selected_providers else 'NULL'), tuple(selected_providers))
                    audit(c,u['id'],'settings.rx_routing',None,{'mode':mode,'claim_mode':claim_mode,'direct_provider_id':direct or None,'claim_timeout_minutes':claim_timeout,'total_timeout_minutes':total_timeout,'distribution_regions':clean,'distribution_provider_ids':selected_providers})
                    c.commit(); return self.send(200,{'ok':True,'settings':values})
                raise E(405,'طريقة غير مدعومة')
            m = re.fullmatch(r"/api/admin/providers/(\d+)/settings", path)
            if method == "POST" and m:
                self.need(u, "admin"); pid = int(m[1]); d = self.body()
                old = c.execute('SELECT * FROM providers WHERE user_id=?', (pid,)).fetchone()
                if not old: raise E(404, "الصيدلية غير موجودة")
                rid = d.get('region_id', old['region_id'])
                if not c.execute("SELECT 1 FROM regions WHERE id=? AND level IN ('markaz','village','zone')", (rid,)).fetchone(): raise E(400, "اختر مركزًا أو منطقة صالحة")
                lat, lng = old['lat'], old['lng']
                if 'lat' in d or 'lng' in d: lat, lng = geo_pair(d.get('lat'), d.get('lng'))
                enabled = int(bool(d.get('distribution_enabled', old['distribution_enabled'])))
                if enabled and old['status'] != 'approved': raise E(400, "لا يمكن إشراك صيدلية غير معتمدة في التوزيع")
                c.execute('UPDATE providers SET region_id=?,lat=?,lng=?,distribution_enabled=? WHERE user_id=?', (rid,lat,lng,enabled,pid))
                audit(c,u['id'],'provider.settings',str(pid),{'region_id':rid,'distribution_enabled':enabled,'lat':lat,'lng':lng}); c.commit(); return self.send(200, {'ok':True})
            m = re.fullmatch(r"/api/admin/providers/(\d+)/review", path)
            if method == "POST" and m:
                self.need(u, "admin"); st = self.body().get("status")
                if st not in ("approved", "suspended", "rejected"): raise E(400, "حالة غير صالحة")
                if not c.execute("UPDATE providers SET status=? WHERE user_id=?", (st, int(m[1]))).rowcount: raise E(404, "غير موجود")
                c.execute("UPDATE users SET role=? WHERE id=? AND role IN('customer','medical_provider')", ("medical_provider" if st == "approved" else "customer", int(m[1])))
                audit(c, u["id"], "provider." + st, m[1]); c.commit(); return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/files":
                self.need(u); d = self.body(6_000_000)
                try: raw = base64.b64decode(str(d.get("data", "")), validate=True)
                except Exception: raise E(400, "ملف غير صالح")
                mime = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/png" if raw[:4] == b"\x89PNG" else None
                if not mime: raise E(400, "الصيغة المدعومة: JPG أو PNG")
                if len(raw) > 4_000_000: raise E(413, "الصورة كبيرة (الحد 4 ميجابايت)")
                try: raw = strip_image_metadata(raw)  # EXIF/GPS never reach disk (prescriptions and ID photos often carry the shooting location)
                except ValueError: raise E(400, "الصورة تالفة أو غير مدعومة، جرّب صورة أخرى")
                if u["role"] not in ("admin", "staff"): check_limit(c, "files", u["id"], "وصلت للحد الأقصى من الصور المرفوعة، احذف صورًا غير لازمة")  # the cap guards customers; admins upload one photo per doctor/lab
                os.makedirs(UP, exist_ok=True); name = secrets.token_hex(16); open(os.path.join(UP, name), "wb").write(raw)
                cur = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (u["id"], name, mime, len(raw), int(time.time()))); c.commit(); return self.send(201, {"id": cur.lastrowid})
            m = re.fullmatch(r"/api/files/(\d+)(/delete)?", path)
            if m:
                self.need(u)
                if u["role"] not in ("admin", "staff"):
                    try: rx.refresh_claims(c); c.commit()
                    except Exception: pass
                f = c.execute("SELECT * FROM files WHERE id=?", (int(m[1]),)).fetchone()
                allowed = f and (f["owner_id"] == u["id"] or u["role"] in ("admin", "staff") or c.execute("SELECT 1 FROM prescription_access a JOIN prescriptions p ON p.id=a.prescription_id JOIN providers v ON v.user_id=a.provider_id WHERE a.provider_id=? AND v.status='approved' AND (p.file_id=? OR ? IN (SELECT file_id FROM rx_images WHERE prescription_id=p.id))", (u["id"], f["id"], f["id"])).fetchone())
                if not allowed: raise E(404, "غير موجود")
                if method == "GET" and not m[2]:
                    if f["owner_id"] != u["id"]: rx.mark_seen_by_file(c, u["id"], f["id"]); audit(c, u["id"], "file.read", str(f["id"]), {"role": u["role"]}); c.commit()
                    return self.send(200, None, f["mime"], open(os.path.join(UP, f["path"]), "rb").read())
                if method == "POST" and m[2]:
                    if f["owner_id"] != u["id"]: raise E(404, "غير موجود")
                    if c.execute("SELECT 1 FROM courier_documents WHERE file_id=?", (f["id"],)).fetchone(): raise E(409, "هذه الصورة مستند في طلب انضمام مندوب")
                    if c.execute("SELECT 1 FROM couriers WHERE avatar_file_id=?", (f["id"],)).fetchone(): raise E(409, "هذه صورة البروفايل؛ استبدلها من ملفك")
                    if c.execute("SELECT 1 FROM doctors WHERE photo_file_id=? UNION SELECT 1 FROM labs WHERE photo_file_id=?", (f["id"], f["id"])).fetchone(): raise E(409, "هذه الصورة مستخدمة في بطاقة طبيب أو معمل")
                    if c.execute("SELECT 1 FROM listing_images WHERE file_id=?", (f["id"],)).fetchone(): raise E(409, "هذه الصورة مرتبطة بإعلان؛ عدّل الإعلان لإزالتها")
                    if c.execute("SELECT 1 FROM product_images WHERE file_id=?", (f["id"],)).fetchone(): raise E(409, "هذه الصورة مرتبطة بعرض منتج؛ عدّل العرض لإزالتها")
                    if c.execute("SELECT 1 FROM chat_messages WHERE file_id=?", (f["id"],)).fetchone(): raise E(409, "هذه الصورة جزء من محادثة")
                    if c.execute("SELECT 1 FROM service_request_images WHERE file_id=?", (f["id"],)).fetchone(): raise E(409, "هذه الصورة مرفقة بطلب خدمة؛ احذفها من الطلب")
                    if not rx.remove_image(c, f["id"]): c.execute("UPDATE prescriptions SET file_id=NULL,status='closed' WHERE file_id=?", (f["id"],))  # الصورة الوحيدة: تُغلق الروشتة كما كان؛ ولو بقيت صور أخرى تبقى الروشتة مفتوحة
                    c.execute("DELETE FROM files WHERE id=?", (f["id"],)); c.commit()
                    try: os.remove(os.path.join(UP, f["path"]))
                    except OSError: pass
                    return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/provider/stock":
                pv = prov(); d = self.body(); nm = str(d.get("medicine_name", "")).strip(); av = int(bool(d.get("available"))); pr = None
                if len(nm) < 2: raise E(400, "اسم الدواء مطلوب")
                if av:
                    try: pr = float(d.get("price"))
                    except (TypeError, ValueError): pr = 0
                    if pr <= 0: raise E(400, "أدخل السعر")
                c.execute("INSERT INTO provider_stock VALUES(?,?,?,?,?,?) ON CONFLICT(provider_id,name_norm) DO UPDATE SET available=excluded.available,price=excluded.price,confirmed_at=excluded.confirmed_at,medicine_name=excluded.medicine_name", (pv["user_id"], nm.lower(), nm, av, pr, int(time.time())))
                c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/medical/search":
                nm = q.get("q", [""])[0].strip().lower(); rid = q.get("region_id", [0])[0]
                if len(nm) < 2: raise E(400, "اكتب اسم الدواء")
                hrs = float(({r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}).get("stock_fresh_hours", 24)); a = related(toint(rid or 0)) or [0]
                return self.send(200, [dict(r) for r in c.execute("SELECT s.medicine_name,s.price,s.confirmed_at,p.name_ar pharmacy,p.address FROM provider_stock s JOIN providers p ON p.user_id=s.provider_id WHERE s.name_norm LIKE ? AND s.available=1 AND p.status='approved' AND p.region_id IN (%s) AND s.confirmed_at>? ORDER BY s.confirmed_at DESC,s.medicine_name COLLATE NOCASE" % ",".join("?" * len(a)), ("%" + nm + "%", *a, int(time.time() - hrs * 3600)))])
            if method == "POST" and path == "/api/medical/inquiries":
                self.need(u); d = self.body(); nm = str(d.get("medicine_name", "")).strip()
                if len(nm) < 2 or not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (d.get("region_id"),)).fetchone(): raise E(400, "اسم الدواء ومنطقة مفعّلة مطلوبان")
                check_limit(c, "inquiries", u["id"], "لديك استعلامات مفتوحة كثيرة، ألغِ بعضها أو انتظر الردود")
                cur = c.execute("INSERT INTO medicine_inquiries(customer_id,region_id,medicine_name,note,created_at) VALUES(?,?,?,?,?)", (u["id"], d["region_id"], nm[:120], str(d.get("note", ""))[:300], int(time.time()))); c.commit(); notif.inquiry_created(c, cur.lastrowid, related(d["region_id"])); return self.send(201, {"id": cur.lastrowid, "status": "waiting"})
            if method == "GET" and path == "/api/medical/inquiries":
                self.need(u); out = []
                for r in c.execute("SELECT id,medicine_name,note,status,created_at FROM medicine_inquiries WHERE customer_id=? ORDER BY id DESC", (u["id"],)).fetchall():
                    out.append({**dict(r), "responses": resp_rows("inquiry_responses", "inquiry_id", r["id"])})
                return self.send(200, out)
            m = re.fullmatch(r"/api/medical/inquiries/(\d+)/cancel", path)
            if method == "POST" and m:
                self.need(u)
                if not c.execute("UPDATE medicine_inquiries SET status='cancelled' WHERE id=? AND customer_id=? AND status='open'", (int(m[1]), u["id"])).rowcount: raise E(409, "لا يمكن إلغاء هذا الاستعلام")
                c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/provider/inquiries":
                pv = prov(); ids = related(pv["region_id"])  # region filter in SQL, before LIMIT
                rows = c.execute("SELECT i.id,i.medicine_name,i.note,i.region_id,i.created_at,x.status my_status,x.price my_price FROM medicine_inquiries i LEFT JOIN inquiry_responses x ON x.inquiry_id=i.id AND x.provider_id=? WHERE i.status='open' AND i.region_id IN (%s) ORDER BY i.id DESC LIMIT 100" % ",".join("?" * len(ids)), (u["id"], *ids)).fetchall()
                return self.send(200, [dict(r) for r in rows])
            m = re.fullmatch(r"/api/provider/inquiries/(\d+)/respond", path)
            if method == "POST" and m:
                pv = prov(); i = c.execute("SELECT region_id FROM medicine_inquiries WHERE id=? AND status='open'", (int(m[1]),)).fetchone()
                if not i or pv["region_id"] not in related(i["region_id"]): raise E(404, "غير موجود")
                return respond("inquiry_responses", "inquiry_id", int(m[1]))
            if method == "POST" and path == "/api/medical/prescriptions":
                self.need(u); d = self.body()
                raw_ids = d.get("file_ids") if d.get("file_ids") is not None else [d.get("file_id")]  # file_id القديم ما زال مقبولًا
                if not isinstance(raw_ids, list) or not raw_ids: raise E(400, "ارفع صورة الروشتة أولًا")
                if len(raw_ids) > rx.MAX_IMAGES: raise E(400, "الحد الأقصى %d صور للروشتة" % rx.MAX_IMAGES)
                fids = []
                for x in raw_ids:
                    try: x = int(x) if not isinstance(x, bool) else None
                    except (TypeError, ValueError): x = None
                    if x is None or x in fids: raise E(400, "صور الروشتة غير صالحة")
                    fids.append(x)
                for x in fids:
                    if not c.execute("SELECT 1 FROM files WHERE id=? AND owner_id=?", (x, u["id"])).fetchone(): raise E(400, "ارفع صورة الروشتة أولًا")
                    if c.execute("SELECT 1 FROM courier_documents WHERE file_id=?", (x,)).fetchone(): raise E(400, "هذه الصورة ليست روشتة")
                    if c.execute("SELECT 1 FROM prescriptions WHERE file_id=? UNION SELECT 1 FROM rx_images WHERE file_id=?", (x, x)).fetchone(): raise E(409, "هذه الصورة مستخدمة في روشتة أخرى")
                if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (d.get("region_id"),)).fetchone(): raise E(400, "المنطقة غير مفعّلة")
                check_limit(c, "prescriptions", u["id"], "لديك روشتات مفتوحة كثيرة، احذف صورة روشتة منتهية أولًا")
                kind = str(d.get("kind", "rx"));
                if kind not in ("rx", "item"): raise E(400, "نوع الطلب غير صالح")
                cur = c.execute("INSERT INTO prescriptions(customer_id,region_id,file_id,note,created_at,kind) VALUES(?,?,?,?,?,?)", (u["id"], d["region_id"], fids[0], str(d.get("note", ""))[:300], int(time.time()), kind)); rx.set_images(c, cur.lastrowid, fids); c.commit(); rx.auto_forward(c, cur.lastrowid); notif.prescription_pending(c, cur.lastrowid); return self.send(201, {"id": cur.lastrowid, "status": "pending"})
            if method == "GET" and path == "/api/medical/prescriptions":
                self.need(u); out=[]
                for r in c.execute("SELECT id,file_id,note,status,created_at,kind FROM prescriptions WHERE customer_id=? ORDER BY id DESC", (u["id"],)).fetchall():
                    d={**dict(r), "responses": resp_rows("prescription_responses", "prescription_id", r["id"]), "stage": rx.stage_of(c, r["id"], r["status"]), "images": rx.images_of(c, r["id"])}
                    d["aggregate_status"]=rx.aggregate_status(c,r["id"]); d["routing_state"]=rx.routing_state(c,r["id"]); out.append(d)
                return self.send(200, out)
            if method == "GET" and path == "/api/admin/prescriptions":
                self.need(u, "admin", "staff"); return self.send(200, [{**dict(r), "images": rx.images_of(c, r["id"])} for r in c.execute("SELECT p.id,p.file_id,p.note,p.status,p.region_id,p.created_at,u.name customer FROM prescriptions p JOIN users u ON u.id=p.customer_id WHERE p.status=? ORDER BY p.id", (q.get("status", ["pending"])[0],))])
            m = re.fullmatch(r"/api/admin/prescriptions/(\d+)/forward", path)
            if method == "POST" and m:
                self.need(u, "admin", "staff"); pid_ = self.body().get("provider_id"); pid = int(m[1])
                if not c.execute("SELECT 1 FROM providers WHERE user_id=? AND status='approved'", (pid_,)).fetchone() or not c.execute("SELECT 1 FROM prescriptions WHERE id=? AND file_id IS NOT NULL AND status!='closed'", (pid,)).fetchone(): raise E(400, "صيدلية معتمدة وروشتة متاحة مطلوبتان")
                c.execute("INSERT OR IGNORE INTO prescription_access VALUES(?,?)", (pid, pid_)); c.execute("UPDATE prescriptions SET status='forwarded' WHERE id=?", (pid,)); audit(c, u["id"], "prescription.forward", str(pid), {"provider": pid_}); c.commit(); return self.send(200, {"ok": True})
            if method == "GET" and path == "/api/provider/prescriptions":
                prov(); out=[]
                for r in c.execute("SELECT p.id,p.file_id,p.note,p.created_at,x.status my_status,x.price my_price,x.review my_review,x.review_reason my_review_reason FROM prescription_access a JOIN prescriptions p ON p.id=a.prescription_id AND p.status!='closed' AND p.file_id IS NOT NULL LEFT JOIN prescription_responses x ON x.prescription_id=p.id AND x.provider_id=a.provider_id WHERE a.provider_id=? ORDER BY p.id DESC", (u["id"],)):
                    d=dict(r); d["images"]=rx.images_of(c,r["id"]); d["requested_items"]=rx.requested_items(c,r["id"],u["id"]); out.append(d)
                return self.send(200, out)
            m = re.fullmatch(r"/api/provider/prescriptions/(\d+)/respond", path)
            if method == "POST" and m:
                prov()
                if int(({r["key"]:r["value"] for r in c.execute("SELECT key,value FROM settings")}).get("rx_claim_mode", "0")) == 1:
                    rx.refresh_claims(c); c.commit()
                    if not c.execute("SELECT 1 FROM rx_claims WHERE prescription_id=? AND provider_id=? AND status='active' AND expires_at>?", (int(m[1]), u["id"], int(time.time()))).fetchone(): raise E(404, "انتهت مهلة الحجز أو لم يعد الطلب مخصصًا لصيدليتك")
                if not c.execute("SELECT 1 FROM prescription_access a JOIN prescriptions p ON p.id=a.prescription_id WHERE a.prescription_id=? AND a.provider_id=? AND p.status!='closed'", (int(m[1]), u["id"])).fetchone(): raise E(404, "غير موجود")
                return respond("prescription_responses", "prescription_id", int(m[1]))
            if method == "POST" and path == "/api/medical/delivery":
                self.need(u); d = self.body(); st = d.get("source_type")
                SRC = {"inquiry": ("medicine_inquiries", "inquiry_responses", "inquiry_id", "open", "M"), "prescription": ("prescriptions", "prescription_responses", "prescription_id", None, "R")}
                if st not in SRC: raise E(400, "نوع الطلب غير صالح")
                sid, pid_ = toint(d.get("source_id")), toint(d.get("provider_id")); dr = str(d.get("dropoff_text", "")).strip()
                if len(dr) < 3: raise E(400, "عنوان التسليم مطلوب")
                dla, dln = geo_pair(d.get("dropoff_lat"), d.get("dropoff_lng"))
                tbl, rtbl, col, need_status, tag = SRC[st]
                c.commit(); c.execute("BEGIN IMMEDIATE")
                src = c.execute("SELECT status FROM %s WHERE id=? AND customer_id=?" % tbl, (sid, u["id"])).fetchone()
                if not src: raise E(404, "غير موجود")
                if (need_status and src["status"] != need_status) or src["status"] in ("closed", "cancelled"): raise E(409, "هذا الطلب لم يعد مفتوحًا")
                pv = c.execute("SELECT name_ar,address,region_id FROM providers WHERE user_id=? AND status='approved'", (pid_,)).fetchone()
                if not pv: raise E(409, "الصيدلية غير متاحة حاليًا")
                rr = c.execute("SELECT status,updated_at%s FROM %s WHERE %s=? AND provider_id=?" % (",review" if st == "prescription" else "", rtbl, col), (sid, pid_)).fetchone()
                if not rr or (st == "prescription" and rr["review"] != "approved"): raise E(404, "لا يوجد رد من هذه الصيدلية")  # الرد غير المعتمد من الإدارة لا وجود له عند العميل
                if rr["status"] != "available": raise E(409, "الصيدلية لم تؤكد توفر الدواء")
                hrs = float(({r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}).get("stock_fresh_hours", 24))
                if rr["updated_at"] <= time.time() - hrs * 3600: raise E(409, "رد الصيدلية قديم، اطلب تأكيدًا جديدًا")
                if st == "prescription" and not c.execute("SELECT 1 FROM prescription_access WHERE prescription_id=? AND provider_id=?", (sid, pid_)).fetchone(): raise E(409, "الصيدلية لم تعد مخوّلة بهذه الروشتة")
                if st == "prescription" and rx._setting(c, "rx_claim_mode", 0) == 1 and rx.requested_items(c, sid, pid_): raise E(409, "هذه الصيدلية أكدت الأصناف الناقصة فقط؛ لا يمكن إنشاء توصيل للروشتة كاملة من هذا الرد")
                if c.execute("SELECT 1 FROM medical_delivery_links l JOIN delivery_orders o ON o.id=l.order_id WHERE l.source_type=? AND l.source_id=? AND l.provider_id=? AND o.status!='cancelled'", (st, sid, pid_)).fetchone(): raise E(409, "يوجد طلب توصيل لهذا الرد بالفعل")
                f = region_fee(c, pv["region_id"])
                if not f: raise E(400, "الدليفري غير متاح في منطقة الصيدلية")
                check_limit(c, "orders", u["id"], "لديك طلبات توصيل مفتوحة كثيرة، أكمل أو ألغِ بعضها أولًا")
                now = int(time.time()); cm = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; comm = float(cm.get("commission_value", 0)) * (f["fee"] / 100 if cm.get("commission_type") == "percent" else 1)
                # the courier sees only a reference code: never the medicine name or the prescription
                code = "%06d" % secrets.randbelow(10 ** 6)  # كان ناقصًا: بدون رمز لا يستطيع المندوب إنهاء التسليم بالرمز ولا يراه العميل
                cur = c.execute("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,details,fee,commission,created_at,updated_at,search_started_at,delivery_code,dropoff_lat,dropoff_lng,fare_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'none')", (u["id"], pv["region_id"], ("صيدلية " + pv["name_ar"] + (" — " + pv["address"] if pv["address"] else ""))[:300], dr[:300], "طلب من صيدلية — المرجع %s%d" % (tag, sid), f["fee"], round(comm, 2), now, now, now, code, dla, dln))
                c.execute("INSERT INTO medical_delivery_links VALUES(?,?,?,?,?)", (cur.lastrowid, st, sid, pid_, now))
                c.execute("UPDATE delivery_orders SET comm_type=?,comm_value=? WHERE id=?", (cm.get("commission_type", "fixed"), float(cm.get("commission_value", 0)), cur.lastrowid))
                ev(cur.lastrowid, None, "searching"); c.commit(); push_new_order(cur.lastrowid); return self.send(201, {"id": cur.lastrowid, "status": "searching", "reference": "%s%d" % (tag, sid)})
            if method == "GET" and path == "/api/provider/deliveries":
                prov(); return self.send(200, [dict(r) for r in c.execute("SELECT o.id order_id,l.source_type,l.source_id,o.status,CASE WHEN o.status IN " + ACTIVE + " THEN cu.name END courier_name,i.medicine_name FROM medical_delivery_links l JOIN delivery_orders o ON o.id=l.order_id LEFT JOIN users cu ON cu.id=o.courier_id LEFT JOIN medicine_inquiries i ON l.source_type='inquiry' AND i.id=l.source_id WHERE l.provider_id=? ORDER BY l.order_id DESC LIMIT 50", (u["id"],))])
            raise E(404, "غير موجود")
        except E as e: self.send(e.code, {"error": e.msg})
        except Exception as e: print("ERR", e, file=sys.stderr); self.send(500, {"error": "حدث خطأ غير متوقع"})
        finally: c.close()
    def do_GET(self): self.route("GET")
    def do_POST(self): self.route("POST")
    def log_message(self, *a): pass
def push_resume():
    """After a restart the in-memory repeat-push loops are gone. Re-arm one loop for every order still searching inside its window (data-less push, a duplicate wake is harmless:
    sw.js asks /api/push/state for the real count), and send ONE sweep push so devices re-check state and drop alerts whose final sweep was lost with the old process. Returns the order ids resumed."""
    c = db()
    try:
        win = int(cfg(c, "search_timeout", 300)); now = int(time.time())
        ids = [r[0] for r in c.execute("SELECT id FROM delivery_orders WHERE status='searching' AND courier_id IS NULL AND (CASE WHEN search_started_at>0 THEN search_started_at ELSE created_at END)+?>?", (win, now)).fetchall()]
        uids = [r[0] for r in c.execute("SELECT DISTINCT user_id FROM push_subs").fetchall()]
    finally: c.close()
    def sweep():
        try:
            c2 = db()
            try:
                if uids: _push_to_users(c2, uids, 60, native=False)
            finally: c2.close()
        except Exception as e: print("PUSH RESUME ERR", e, file=sys.stderr)
    if uids: threading.Thread(target=sweep, daemon=True).start()
    for oid in ids: push_new_order(oid)
    return ids
def _rx_worker_acquire_lease(c, owner, now=None, lease_seconds=60):
    """Best-effort SQLite lease: only one server process sweeps a shared DB at a time.
    If the connection is a lightweight test double without SQL support, retain the old single-worker behavior.
    """
    if not hasattr(c, "execute"): return True
    now = int(now or time.time()); lease_seconds = max(10, int(lease_seconds))
    try:
        if not c.in_transaction: c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT value FROM settings WHERE key='rx_claim_worker_lease'").fetchone()
        if row:
            try: active_owner, until = row["value"].rsplit("|", 1); until = int(until)
            except (ValueError, TypeError): active_owner, until = "", 0
            if until > now and active_owner != owner:
                c.rollback(); return False
        c.execute("INSERT INTO settings(key,value) VALUES('rx_claim_worker_lease',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  ("%s|%d" % (owner, now + lease_seconds),))
        c.commit()
        return True
    except Exception as e:
        print("rx claim worker lease failed: %r" % (e,), file=sys.stderr)
        try: c.rollback()
        except Exception: pass
        return False


def rx_claim_worker(stop_event=None, interval=None, db_factory=None):
    """Periodic deadline processor for pharmacy claims. Disabled mode is a no-op.
    Uses a per-tick connection and a renewable SQLite lease so multiple app processes sharing the same DB do not all sweep.
    """
    stop_event = stop_event or threading.Event()
    interval = max(5, int(interval if interval is not None else os.environ.get("LAQINO_RX_CLAIM_SWEEP_SECONDS", "15")))
    db_factory = db_factory or db
    owner = secrets.token_hex(16)
    while not stop_event.is_set():
        c = None
        try:
            c = db_factory()
            if _rx_worker_acquire_lease(c, owner, lease_seconds=max(30, interval * 4)):
                processed = rx.refresh_claims(c)
                if c.in_transaction: c.commit()
                if processed:
                    print("rx claim worker: processed %d expired claim(s)" % processed, file=sys.stderr)
        except Exception as e:
            print("rx claim worker failed: %r" % (e,), file=sys.stderr)
            try:
                if c: c.rollback()
            except Exception: pass
        finally:
            try:
                if c: c.close()
            except Exception: pass
        if stop_event.wait(interval): break

if __name__ == "__main__":
    init(os.environ.get("LAQINO_ADMIN_PHONE"), os.environ.get("LAQINO_ADMIN_PASSWORD"))
    try: print("push resume: %d searching order(s) re-armed" % len(push_resume()))
    except Exception as e: print("push resume failed:", e, file=sys.stderr)
    threading.Thread(target=rx_claim_worker, name="rx-claim-deadlines", daemon=True).start()
    ThreadingHTTPServer((os.environ.get("HOST", "0.0.0.0"), int(os.environ.get("PORT", 8000))), H).serve_forever()
