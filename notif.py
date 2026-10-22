# لاقينو — نظام الإشعارات (المهمة 1: أساس السيرفر).
# الفكرة: الإشعارات تُولَّد بـ triggers داخل SQLite، فتعمل من أي مسار في server.py (وحتى من سكربتات الصيانة)
# دون تعديل كل endpoint. الملف لا يستورد server.py (لا اعتماد دائري) ولا يستخدم إلا مكتبة بايثون القياسية.
#
# الربط في server.py (3 أسطر فقط — انظر README_TASK1.md):
#   import notif                                        # أعلى الملف
#   notif.install(c)                                    # داخل init() قبل c.commit()
#   if notif.handle(self, c, u, method, path, q): return   # داخل route() بعد u = self.user(c)
#
# إزالة كاملة (للتراجع إن أردت قاعدة بلا أثر): python3 notif.py --uninstall laqino.db
import sqlite3, sys, time

VERSION = 3
KEEP_PER_USER = 200          # أقصى عدد إشعارات محفوظة لكل مستخدم
KEEP_DAYS = 90               # الأقدم من ذلك يُحذف عند أول قراءة

TABLE = """
CREATE TABLE IF NOT EXISTS notifications(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT,
  link TEXT,
  ref_type TEXT,
  ref_id INTEGER,
  created_at INTEGER NOT NULL,
  read_at INTEGER);
CREATE INDEX IF NOT EXISTS ix_notif_user ON notifications(user_id,id);
CREATE INDEX IF NOT EXISTS ix_notif_unread ON notifications(user_id,read_at);
"""

def _ins(user, kind, title, body="NULL", link="NULL", ref_type="NULL", ref_id="NULL", frm="", where=""):
    """INSERT OR IGNORE: خطأ في الإشعار لا يجوز أبدًا أن يُفشل العملية الأصلية (طلب/اعتماد/رد)."""
    q = lambda s: s if s == "NULL" or s.startswith(("NEW.", "OLD.", "(", "COALESCE", "CASE", "'")) else "'" + s + "'"
    return ("INSERT OR IGNORE INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) "
            "SELECT %s,%s,%s,%s,%s,%s,%s,CAST(strftime('%%s','now') AS INTEGER) %s %s;"
            % (user, q(kind), q(title), q(body), q(link), q(ref_type), ref_id, frm, where)).replace(" ;", ";")

def _order_status_title(col="NEW.status"):
    return ("CASE %s WHEN 'assigned' THEN 'تم قبول طلب التوصيل' WHEN 'heading_pickup' THEN 'المندوب في الطريق للاستلام' "
            "WHEN 'picked_up' THEN 'تم استلام الطلب من المصدر' WHEN 'heading_customer' THEN 'المندوب في الطريق إليك' "
            "WHEN 'arrived' THEN 'المندوب وصل إلى عنوانك' WHEN 'awaiting_confirmation' THEN 'تم التسليم — أكّد الاستلام' "
            "WHEN 'completed' THEN 'اكتمل طلب التوصيل' WHEN 'cancelled' THEN 'تم إلغاء طلب التوصيل' "
            "WHEN 'disputed' THEN 'تم تسجيل اعتراض على الطلب' END" % col)

def _triggers():
    T = {}
    # --- طلب انضمام مندوب / صيدلية: استلام، اعتماد، رفض، إيقاف ---
    for tbl, who, link, reason in (("couriers", "المندوب", "courier", "NEW.review_reason"), ("providers", "الصيدلية", "pharmacy", "NULL")):
        title = ("CASE NEW.status WHEN 'approved' THEN 'تم اعتماد حسابك كـ%s' WHEN 'rejected' THEN 'تم رفض طلب الانضمام' "
                 "WHEN 'suspended' THEN 'تم إيقاف حسابك' WHEN 'pending' THEN 'استلمنا طلب الانضمام وهو قيد المراجعة' END" % ("مندوب" if tbl == "couriers" else "صيدلية"))
        T["app_%s_ins" % tbl] = ("AFTER INSERT ON %s" % tbl, "", _ins("NEW.user_id", "application." + tbl, "استلمنا طلب الانضمام وهو قيد المراجعة", link=link, ref_type=tbl, ref_id="NEW.user_id"))
        T["app_%s_upd" % tbl] = ("AFTER UPDATE OF status ON %s" % tbl, "WHEN OLD.status IS NOT NEW.status",
                                 _ins("NEW.user_id", "application." + tbl, title, body=reason, link=link, ref_type=tbl, ref_id="NEW.user_id"))
    # --- حالة طلب التوصيل: للعميل، وللمندوب عند الإلغاء/الإغلاق ---
    T["order_status"] = ("AFTER UPDATE OF status ON delivery_orders", "WHEN OLD.status IS NOT NEW.status AND NEW.status IN ('assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation','completed','cancelled','disputed')",
        _ins("NEW.customer_id", "order.status", _order_status_title(), body="'طلب رقم ' || NEW.id", link="orders", ref_type="order", ref_id="NEW.id")
        + _ins("NEW.courier_id", "order.courier", _order_status_title(), body="'طلب رقم ' || NEW.id", link="courier", ref_type="order", ref_id="NEW.id",
               where="WHERE NEW.courier_id IS NOT NULL AND NEW.status IN ('completed','cancelled','disputed')"))
    T["order_fare_proposed"] = ("AFTER UPDATE OF fare_status ON delivery_orders", "WHEN NEW.fare_status='proposed'",
        _ins("NEW.customer_id", "order.fare", "المندوب اقترح أجرة التوصيل — بانتظار موافقتك", body="'طلب رقم ' || NEW.id", link="orders", ref_type="order", ref_id="NEW.id"))
    T["order_fare_approved"] = ("AFTER UPDATE OF fare_status ON delivery_orders", "WHEN NEW.fare_status='approved' AND OLD.fare_status IS NOT 'approved' AND NEW.courier_id IS NOT NULL",
        _ins("NEW.courier_id", "order.fare", "وافق العميل على الأجرة — ابدأ التوصيل", body="'طلب رقم ' || NEW.id", link="courier", ref_type="order", ref_id="NEW.id"))
    T["order_unassigned"] = ("AFTER UPDATE OF courier_id ON delivery_orders", "WHEN OLD.courier_id IS NOT NULL AND (NEW.courier_id IS NULL OR NEW.courier_id != OLD.courier_id) AND NEW.status NOT IN ('completed','cancelled','disputed')",
        _ins("OLD.courier_id", "order.released", "لم يعد الطلب مسندًا إليك", body="'طلب رقم ' || OLD.id", link="courier", ref_type="order", ref_id="OLD.id"))
    # --- رد صيدلية على استفسار دواء / روشتة (للعميل) ---
    for tbl, col, what, rtype in (("inquiry_responses", "inquiry_id", "medicine_inquiries", "inquiry"), ("prescription_responses", "prescription_id", "prescriptions", "prescription")):
        title = "CASE NEW.status WHEN 'available' THEN 'صيدلية ردّت: الدواء متوفر' WHEN 'unavailable' THEN 'صيدلية ردّت: غير متوفر' ELSE 'صيدلية تطلب تأكيدًا منك' END"
        body = "COALESCE((SELECT name_ar FROM providers WHERE user_id=NEW.provider_id),'صيدلية') || CASE WHEN NEW.price IS NOT NULL THEN ' — السعر ' || NEW.price ELSE '' END"
        sel = _ins("(SELECT customer_id FROM %s WHERE id=NEW.%s)" % (what, col), "medical." + rtype, title, body=body, link="medical", ref_type=rtype, ref_id="NEW.%s" % col,
                   where="WHERE (SELECT customer_id FROM %s WHERE id=NEW.%s) IS NOT NULL" % (what, col))
        T[tbl + "_ins"] = ("AFTER INSERT ON " + tbl, "", sel)
        T[tbl + "_upd"] = ("AFTER UPDATE OF status,price ON " + tbl, "WHEN OLD.status IS NOT NEW.status OR OLD.price IS NOT NEW.price", sel)
    # --- روشتة وُجّهت إلى صيدلية ---
    T["rx_access"] = ("AFTER INSERT ON prescription_access", "",
        _ins("NEW.provider_id", "provider.prescription", "روشتة جديدة وُجّهت إلى صيدلية", link="pharmacy", ref_type="prescription", ref_id="NEW.prescription_id"))
    # --- مراجعة طلب شحن رصيد المندوب ---
    T["topup_review"] = ("AFTER UPDATE OF status ON topup_requests", "WHEN OLD.status IS NOT NEW.status AND NEW.status IN ('approved','rejected')",
        _ins("NEW.courier_id", "wallet.topup", "CASE NEW.status WHEN 'approved' THEN 'تم قبول طلب شحن الرصيد' ELSE 'تم رفض طلب شحن الرصيد' END", body="NEW.reason", link="courier", ref_type="topup", ref_id="NEW.id"))
    # --- مراجعة إعلان في السوق ---
    T["listing_review"] = ("AFTER UPDATE OF status ON listings", "WHEN OLD.status IS NOT NEW.status AND NEW.status IN ('approved','rejected')",
        _ins("NEW.user_id", "listing.review", "CASE NEW.status WHEN 'approved' THEN 'تم نشر إعلانك' ELSE 'تم رفض إعلانك' END", body="COALESCE(NEW.reject_reason, NEW.title)", link="souq", ref_type="listing", ref_id="NEW.id"))
    # --- إشعارات للإدارة والموظفين: كل حساب role admin/staff يستلم نسخة (الرابط admin:<قسم> يفتح القسم في لوحة الإدارة) ---
    def adm(kind, title, body, section, ref_type, ref_id):
        return _ins("(users.id)", kind, title, body=body, link="admin:" + section, ref_type=ref_type, ref_id=ref_id, frm="FROM users", where="WHERE users.role IN ('admin','staff')")
    for tbl, section, title, body in (("couriers", "couriers", "طلب انضمام مندوب جديد", "COALESCE((SELECT name FROM users WHERE id=NEW.user_id),'')"),
                                      ("providers", "providers", "طلب انضمام صيدلية جديد", "COALESCE(NEW.name_ar,'')")):
        T["adm_%s_ins" % tbl] = ("AFTER INSERT ON %s" % tbl, "WHEN NEW.status='pending'", adm("admin." + tbl, title, body, section, tbl, "NEW.user_id"))
        T["adm_%s_upd" % tbl] = ("AFTER UPDATE OF status ON %s" % tbl, "WHEN NEW.status='pending' AND OLD.status IS NOT 'pending'", adm("admin." + tbl, title + " (إعادة تقديم)", body, section, tbl, "NEW.user_id"))
    T["adm_topup_ins"] = ("AFTER INSERT ON topup_requests", "WHEN NEW.status='pending'", adm("admin.topup", "طلب شحن رصيد جديد", "'مبلغ ' || NEW.amount || ' ج'", "topups", "topup", "NEW.id"))
    T["adm_listing_ins"] = ("AFTER INSERT ON listings", "WHEN NEW.status='pending'", adm("admin.listing", "إعلان جديد بانتظار المراجعة", "NEW.title", "listings", "listing", "NEW.id"))
    # --- الخطوة 7: اعتراض العميل على طلب توصيل -> الإدارة، وصيدلية الطلب الطبي (إن وُجدت) ---
    T["adm_order_disputed"] = ("AFTER UPDATE OF status ON delivery_orders", "WHEN NEW.status='disputed' AND OLD.status IS NOT 'disputed'",
        adm("admin.order_dispute", "اعتراض جديد على طلب توصيل", "'طلب رقم ' || NEW.id", "orders", "order", "NEW.id"))
    T["pharm_order_disputed"] = ("AFTER UPDATE OF status ON delivery_orders", "WHEN NEW.status='disputed' AND OLD.status IS NOT 'disputed'",
        _ins("(l.provider_id)", "provider.order_dispute", "اعتراض العميل على طلب توصيل من تسعيرتك", body="'طلب رقم ' || NEW.id", link="pharmacy", ref_type="order", ref_id="NEW.id",
             frm="FROM medical_delivery_links l", where="WHERE l.order_id=NEW.id"))
    return T

# --- الخطوة 7: إشعارات تحتاج منطقًا (مناطق متداخلة) فتُرسل من الكود لا من triggers. best-effort: لا تُفشل العملية الأصلية أبدًا ---
MAX_PHARMACIES = 50

def _safe(fn):
    def w(*a, **k):
        try: return fn(*a, **k)
        except Exception as e:
            sys.stderr.write("notif %s failed: %r\n" % (fn.__name__, e)); return 0
    return w

@_safe
def inquiry_created(c, inquiry_id, region_ids):
    """استفسار دواء جديد -> كل صيدلية معتمدة في منطقة متداخلة معه (نفس منطق /api/provider/inquiries). يرجع عدد المُشعَرين."""
    row = c.execute("SELECT medicine_name,customer_id FROM medicine_inquiries WHERE id=? AND status='open'", (inquiry_id,)).fetchone()
    if not row or not region_ids: return 0
    ids = [r[0] for r in c.execute("SELECT user_id FROM providers WHERE status='approved' AND user_id!=? AND region_id IN (%s) ORDER BY user_id LIMIT ?" % ",".join("?" * len(region_ids)), (row["customer_id"], *region_ids, MAX_PHARMACIES))]
    now = int(time.time())
    for uid in ids:
        c.execute("INSERT OR IGNORE INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (uid, "provider.inquiry", "استفسار دواء جديد في منطقتك", row["medicine_name"][:120], "pharmacy", "inquiry", inquiry_id, now))
    c.commit(); return len(ids)

@_safe
def prescription_pending(c, rx_id):
    """روشتة جديدة لم تُوجَّه لأي صيدلية (لا توجيه تلقائي) -> الإدارة والموظفون لتوجيهها. لا شيء إن كانت وُجّهت فعلًا."""
    r = c.execute("SELECT status FROM prescriptions WHERE id=?", (rx_id,)).fetchone()
    if not r or r["status"] != "pending": return 0
    n = c.execute("INSERT OR IGNORE INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) "
                  "SELECT id,'admin.rx_new','روشتة جديدة بانتظار التوجيه','روشتة #'||?,'admin:rx','prescription',?,CAST(strftime('%s','now') AS INTEGER) FROM users WHERE role IN('admin','staff')", (rx_id, rx_id)).rowcount
    c.commit(); return n

PREFIX = "ntf_"

def install(c):
    """يُستدعى من init(): جدول + triggers. آمن للتكرار، ولا يمس أي صف موجود. الـtriggers تُعاد كتابتها كل مرة لتتحدّث مع الإصدار."""
    c.executescript(TABLE)
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE ?", (PREFIX + "%",)).fetchall()]
    c.execute("BEGIN IMMEDIATE") if not c.in_transaction else None
    for n in names: c.execute("DROP TRIGGER IF EXISTS " + n)
    for name, (when, cond, body) in _triggers().items():
        c.execute("CREATE TRIGGER %s%s %s %s BEGIN %s END" % (PREFIX, name, when, cond, body))
    c.commit()

def uninstall(c):
    for (n,) in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE ?", (PREFIX + "%",)).fetchall(): c.execute("DROP TRIGGER IF EXISTS " + n)
    c.execute("DROP TABLE IF EXISTS notifications"); c.commit()

def _prune(c, uid):
    now = int(time.time())
    c.execute("DELETE FROM notifications WHERE user_id=? AND (created_at<? OR id NOT IN (SELECT id FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?))", (uid, now - KEEP_DAYS * 86400, uid, KEEP_PER_USER))

def _applications(c, uid):
    out = {"courier": None, "pharmacy": None}
    r = c.execute("SELECT status,region_id,review_reason,created_at,(SELECT COUNT(*) FROM courier_documents d WHERE d.courier_id=couriers.user_id AND d.kind IN('id_front','id_back')) nd FROM couriers WHERE user_id=?", (uid,)).fetchone()
    if r: out["courier"] = {"status": r["status"], "region_id": r["region_id"], "reason": r["review_reason"] if r["status"] in ("rejected", "suspended") else None, "created_at": r["created_at"], "needs_documents": r["status"] == "pending" and r["nd"] < 2}
    r = c.execute("SELECT status,region_id,name_ar,address,created_at FROM providers WHERE user_id=?", (uid,)).fetchone()
    if r: out["pharmacy"] = {"status": r["status"], "region_id": r["region_id"], "name_ar": r["name_ar"], "address": r["address"], "created_at": r["created_at"]}
    return out

def _int(v, d, lo, hi):
    try: return max(lo, min(hi, int(v)))
    except (TypeError, ValueError): return d

def handle(h, c, u, method, path, q):
    """True إن عالج الطلب (ردّ أُرسل)، False إن لم يكن من مساراته. h = معالج السيرفر (يوفّر send/body)."""
    if not path.startswith(("/api/notifications", "/api/my/applications")): return False
    if not u: h.send(401, {"error": "سجّل الدخول أولًا"}); return True
    uid = u["id"]
    if method == "GET" and path == "/api/my/applications":
        h.send(200, _applications(c, uid)); return True
    if method == "GET" and path == "/api/notifications/count":   # خفيف للاستعلام الدوري من الجرس
        r = c.execute("SELECT COALESCE(MAX(id),0) latest,SUM(read_at IS NULL) unread FROM notifications WHERE user_id=?", (uid,)).fetchone()
        h.send(200, {"unread": r["unread"] or 0, "latest_id": r["latest"]}); return True
    if method == "GET" and path == "/api/notifications":
        _prune(c, uid); c.commit()
        after = _int(q.get("after", [0])[0], 0, 0, 2 ** 62); lim = _int(q.get("limit", [30])[0], 30, 1, 100)
        rows = [dict(r) for r in c.execute("SELECT id,kind,title,body,link,ref_type,ref_id,created_at,read_at FROM notifications WHERE user_id=? AND id>? ORDER BY id DESC LIMIT ?", (uid, after, lim))]
        r = c.execute("SELECT COALESCE(MAX(id),0) latest,SUM(read_at IS NULL) unread FROM notifications WHERE user_id=?", (uid,)).fetchone()
        h.send(200, {"items": rows, "unread": r["unread"] or 0, "latest_id": r["latest"]}); return True
    if method == "POST" and path == "/api/notifications/read":
        d = h.body(); now = int(time.time())
        if d.get("all") is True: n = c.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", (now, uid)).rowcount
        else:
            ids = [i for i in (d.get("ids") or []) if isinstance(i, int) and not isinstance(i, bool)][:200]
            n = c.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL AND id IN (%s)" % ",".join("?" * len(ids)), (now, uid, *ids)).rowcount if ids else 0
        c.commit(); h.send(200, {"ok": True, "marked": n}); return True
    h.send(404, {"error": "غير موجود"}); return True

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--uninstall":
        c = sqlite3.connect(sys.argv[2]); uninstall(c); print("notifications removed from", sys.argv[2])
    else: print("usage: python3 notif.py --uninstall <db-file>")
