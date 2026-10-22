# لاقينو — نظرة عامة للإدارة (المرحلة 7). وحدة مستقلة بنمط svc.py/chat.py: لا تستورد server.py، وتُربط بسطرين.
#   إدارة/موظف: GET /api/admin/overview  ->  {pending: {<key>: n}, total_pending, totals: {<key>: n}, at}
# قراءة فقط: لا تكتب في أي جدول ولا تُرجع أي بيانات شخصية (أعداد فقط). كل عدّاد استعلام مستقل؛ جدول مفقود يُعطي 0 لا خطأ 500.
import time

# (المفتاح، التسمية، تبويب الإدارة الذي يفتحه، الاستعلام) — المفتاح = اسم الحقل في الاستجابة.
PENDING = (
    ("couriers", "طلبات انضمام مندوبين", "couriers", "SELECT COUNT(*) FROM couriers WHERE status='pending'"),
    ("topups", "طلبات شحن محفظة", "topups", "SELECT COUNT(*) FROM topup_requests WHERE status='pending'"),
    ("listings", "إعلانات بانتظار المراجعة", "listings", "SELECT COUNT(*) FROM listings WHERE status='pending'"),
    ("listing_reports", "بلاغات على إعلانات", "listings", "SELECT COUNT(*) FROM listing_reports WHERE status='open'"),
    ("chats", "بلاغات المحادثات", "chats", "SELECT COUNT(*) FROM chat_reports WHERE status='open'"),
    ("svcreq", "طلبات خدمات مفتوحة", "svcreq", "SELECT COUNT(*) FROM service_requests WHERE status='open'"),
    ("products", "منتجات بانتظار المراجعة", "products", "SELECT COUNT(*) FROM product_offers WHERE status='pending'"),
    ("providers", "طلبات انضمام صيدليات", "providers", "SELECT COUNT(*) FROM providers WHERE status='pending'"),
    ("rx", "روشتات بانتظار التحويل", "rx", "SELECT COUNT(*) FROM prescriptions WHERE status='pending'"),
    ("rx_responses", "ردود صيدليات على روشتات بانتظار الاعتماد", "rx", "SELECT COUNT(*) FROM prescription_responses x JOIN prescriptions r ON r.id=x.prescription_id WHERE x.review='pending' AND r.status!='closed'"),
    ("rating_reports", "بلاغات على تقييمات خدمات", "svcreq", "SELECT COUNT(*) FROM service_rating_reports WHERE status='pending'"),
    ("orders", "طلبات توصيل متنازع عليها", "orders", "SELECT COUNT(*) FROM delivery_orders WHERE status='disputed'"),
)
TOTALS = (
    ("users", "SELECT COUNT(*) FROM users"),
    ("couriers", "SELECT COUNT(*) FROM couriers WHERE status='approved'"),
    ("pharmacies", "SELECT COUNT(*) FROM providers WHERE status='approved'"),
    ("listings", "SELECT COUNT(*) FROM listings WHERE status='approved'"),
    ("orders_24h", "SELECT COUNT(*) FROM delivery_orders WHERE created_at>=?"),
)
META = [{"key": k, "label": lb, "tab": tb} for k, lb, tb, _ in PENDING]


def _count(c, sql, args=()):
    try: return int(c.execute(sql, args).fetchone()[0])
    except Exception as e:
        import sys; sys.stderr.write("overview count failed: %r\n" % (e,)); return 0


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب."""
    if path != "/api/admin/overview": return False
    if not u: h.send(401, {"error": "سجّل الدخول أولًا"}); return True
    if u["role"] not in ("admin", "staff"): h.send(403, {"error": "غير مسموح"}); return True
    if method != "GET": h.send(404, {"error": "غير موجود"}); return True
    now = int(time.time()); since = now - 86400  # آخر 24 ساعة (لا «اليوم» كي لا يتأثر بالمنطقة الزمنية)
    pend = {k: _count(c, sql) for k, _, _, sql in PENDING}
    tot = {k: _count(c, sql, (since,) if "?" in sql else ()) for k, sql in TOTALS}
    h.send(200, {"pending": pend, "total_pending": sum(pend.values()), "totals": tot, "items": META, "at": now}); return True
