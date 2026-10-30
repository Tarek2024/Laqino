# حذف الحساب بإخفاء الهوية (Google Play — الخطوة 2). لا يستورد server.py.
# القرار: لا نمسح سجلات الطلبات القديمة (توصيل/تقييمات/محفظة) لأنها سجلات مالية وتشغيلية للطرف الآخر؛
# نفصلها عن صاحبها: الاسم والهاتف يُستبدلان، وكلمة المرور تُتلف، وكل نص حر أو صورة أو عنوان أدخله المستخدم يُمسح.
import os, secrets, sqlite3, time

DELETED_NAME = "حساب محذوف"
FINAL_ORDER = ("completed", "cancelled")
TXT = "[محذوف]"


class Blocked(Exception):
    def __init__(self, code, msg): super().__init__(msg); self.code, self.msg = code, msg


def _x(c, sql, *a):
    try: return c.execute(sql, a)
    except sqlite3.OperationalError: return None  # جدول/عمود غير موجود في قاعدة قديمة جدًا: نتخطاه


def ensure_column(c):
    try: c.execute("ALTER TABLE users ADD COLUMN deleted_at INTEGER")
    except sqlite3.OperationalError: pass


def check_allowed(c, u):
    if u["role"] in ("admin", "staff"): raise Blocked(403, "حسابات الإدارة لا تُحذف من هنا")
    ph = ",".join("?" * len(FINAL_ORDER))
    n = c.execute("SELECT COUNT(*) FROM delivery_orders WHERE (customer_id=? OR courier_id=?) AND status NOT IN (%s)" % ph, (u["id"], u["id"]) + FINAL_ORDER).fetchone()[0]
    if n: raise Blocked(409, "عندك طلبات توصيل غير منتهية، أكملها أو ألغها أولًا ثم احذف الحساب")


def delete_account(c, uid, upload_dir):
    """ينفّذ الإخفاء داخل معاملة واحدة (المستدعي يعمل commit). يرجع قائمة مسارات ملفات تُحذف من القرص بعد نجاح commit."""
    now = int(time.time())
    u = c.execute("SELECT phone FROM users WHERE id=?", (uid,)).fetchone()
    # 1) الملفات التي رفعها المستخدم (بطاقات، روشتات، صور محادثة وإعلانات وطلبات خدمة)
    files = c.execute("SELECT id,path FROM files WHERE owner_id=?", (uid,)).fetchall()
    fids = [f["id"] for f in files]
    for fid in fids:
        for t, col in (("courier_documents", "file_id"), ("rx_images", "file_id"), ("listing_images", "file_id"), ("exchange_images", "file_id"),
                       ("product_images", "file_id"), ("shop_item_images", "file_id"), ("service_request_images", "file_id"), ("market_files", "file_id")):
            _x(c, "DELETE FROM %s WHERE %s=?" % (t, col), fid)
        _x(c, "UPDATE prescriptions SET file_id=NULL WHERE file_id=?", fid)
        _x(c, "UPDATE chat_messages SET file_id=NULL WHERE file_id=?", fid)
        _x(c, "UPDATE doctors SET photo_file_id=NULL WHERE photo_file_id=?", fid)
        _x(c, "UPDATE labs SET photo_file_id=NULL WHERE photo_file_id=?", fid)
        _x(c, "UPDATE couriers SET avatar_file_id=NULL WHERE avatar_file_id=?", fid)  # صورة بروفايل المندوب (المرحلة 38)
        c.execute("DELETE FROM files WHERE id=?", (fid,))
    # 2) بيانات الدخول والتنبيهات
    for t in ("sessions", "push_subs", "password_resets", "notifications", "listing_favorites"):
        _x(c, "DELETE FROM %s WHERE user_id=?" % t, uid)
    _x(c, "DELETE FROM phone_verifications WHERE phone=?", u["phone"])
    # 3) النصوص الحرة والعناوين
    _x(c, "UPDATE delivery_orders SET pickup_text=?,dropoff_text=?,details=NULL,dropoff_lat=NULL,dropoff_lng=NULL,delivery_code=NULL WHERE customer_id=?", TXT, TXT, uid)
    _x(c, "UPDATE ratings SET comment=NULL WHERE customer_id=? OR courier_id=?", uid, uid)
    _x(c, "UPDATE medicine_inquiries SET note=NULL,status='cancelled' WHERE customer_id=?", uid)
    _x(c, "UPDATE prescriptions SET note=NULL,status='closed' WHERE customer_id=?", uid)
    _x(c, "UPDATE service_requests SET description=?,address=NULL,admin_note=NULL,dispute_reason=NULL WHERE user_id=?", TXT, uid)
    _x(c, "UPDATE chat_messages SET body=? WHERE sender_id=?", TXT, uid)
    _x(c, "UPDATE chat_reports SET reason=? WHERE reporter_id=?", TXT, uid)
    _x(c, "UPDATE listings SET status='deleted',title=?,description=NULL,data=NULL WHERE user_id=?", TXT, uid)
    _x(c, "UPDATE topup_requests SET note=NULL WHERE courier_id=?", uid)
    # 4) الصيدلية/المندوب: إخفاء الاسم والعنوان وإيقاف الظهور
    _x(c, "UPDATE couriers SET status='suspended',is_available=0 WHERE user_id=?", uid)
    _x(c, "UPDATE providers SET name_ar=?,address=NULL,status='suspended' WHERE user_id=?", DELETED_NAME, uid)
    _x(c, "UPDATE shop_items SET status='deleted',name_ar=?,description=NULL WHERE shop_id IN (SELECT id FROM shops WHERE owner_id=?)", DELETED_NAME, uid)  # م3: أصناف المحل
    _x(c, "UPDATE shops SET name_ar=?,name_norm='deleted-'||id,address='',phone='',lat=NULL,lng=NULL,status='suspended',is_open=0,review_reason=NULL WHERE owner_id=?", DELETED_NAME, uid)  # م1 المحلات: إخفاء بيانات المحل وإيقافه
    _x(c, "DELETE FROM provider_stock WHERE provider_id=?", uid)
    _x(c, "UPDATE exchange_deals SET status='deleted',title=?,details=NULL WHERE provider_id=?", TXT, uid)
    _x(c, "UPDATE product_offers SET status='deleted',title=?,brand=NULL,description=NULL WHERE provider_id=?", TXT, uid)
    # 5) المستخدم نفسه: لا يمكن الدخول (كلمة مرور عشوائية لا يعرفها أحد) والرقم يتحرر لتسجيل جديد
    c.execute("UPDATE users SET name=?,phone=?,pw_hash=?,salt=?,deleted_at=? WHERE id=?",
              (DELETED_NAME, "deleted-%d" % uid, secrets.token_hex(32), secrets.token_hex(16), now, uid))
    return [os.path.join(upload_dir, f["path"]) for f in files]


def remove_files(paths):
    for p in paths:
        try: os.remove(p)
        except OSError: pass
