# لاقينو — المرحلة 40: زر «اطلب دليفري» للصيدليات. مؤسسة معتمدة تضغط زرًا فيستلم أول مندوب متاح الأوردر منها. (م2/phase-75: الدورة صارت تمتد حتى التسليم للعميل؛ العمولة تبقى عند الاستلام من الصيدلية.)
# وحدة مستقلة بنمط products.py/notif.py: لا تستورد server.py (ما تحتاجه من server يمرّره server.bind). إضافة فقط: عمود delivery_orders.origin_type.
# المسارات:  صيدلية: POST /api/provider/delivery-request  |  GET /api/provider/delivery-requests   —   إدارة: GET|POST /api/admin/provider-delivery
# المفتاح العام settings.provider_delivery_enabled (مطفي افتراضيًا) + عمولة ثابتة على المندوب settings.provider_delivery_commission (0 = مجانية).
import re, time, secrets, sqlite3, csv, io
from datetime import datetime, timedelta, timezone, date

KIND = "provider_pickup"  # قيمة delivery_orders.origin_type؛ NULL = الطلب العادي
NEXT = {"assigned": "heading_pickup", "heading_pickup": "picked_up", "picked_up": "heading_customer", "heading_customer": "completed"}  # م2 (phase-75): في الطريق للصيدلية ← استلم ← في الطريق للعميل ← سلّم؛ الطلب ينتهي (completed) عند التسليم للعميل
DASH = ("/api/provider/delivery-dashboard", "/api/provider/delivery-search", "/api/provider/delivery-order", "/api/provider/delivery-export")  # م3: لوحة الدليفري (قراءة فقط، لطلبات هذه الصيدلية فقط)
ADM = ("/api/admin/provider-delivery/dashboard", "/api/admin/provider-delivery/export")  # م4: لوحة الإدارة على كل الصيدليات (GET، admin فقط، قراءة فقط)
XPHARM_MIN, ABANDON_ALERT, TOP = 2, 3, 50  # تنبيه: رقم عميل عند صيدليتين+ في الفترة؛ مندوب تخلّى 3 مرات+؛ أعلى N في الترتيب
REPEAT_DAY, REPEAT_MONTH, PAGE, CAP = 2, 4, 50, 5000  # عميل متكرر: مرتان+ اليوم، «دائم»: 4+ في الشهر؛ حجم الصفحة؛ سقف أمان للصفوف
DEFAULT_LATE_MIN = 45  # حد تأخير مرحلة التوصيل (من الاستلام حتى التسليم) بالدقائق؛ 0 = بلا إنذار
FAST_SECS = 120  # تسليم أسرع من هذا بعد الاستلام يُعلَّم «سريع جدًا» للمراجعة
MAX_OPEN = 10
ACTIVE = "('assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation')"
_H = {}


def bind(push, audit, region, count_sql):
    """يُستدعى من server.init: دوال server التي تحتاجها الوحدة (دفع الطلب للمناديب، سجل التدقيق، منطقة افتراضية، عدّ الطلبات المفتوحة)."""
    _H.update(push=push, audit=audit, region=region, count_sql=count_sql)


PD_COLS = ("pd_cust_phone TEXT", "pd_cust_norm TEXT", "pd_price REAL", "pd_note TEXT")  # phase-74 (م1): تفاصيل اختيارية يكتبها صاحب الطلب؛ تُملأ لطلبات الصيدلية فقط


def install(c):
    """أعمدة إضافية فقط، آمنة للتكرار، ولا تمسّ البيانات القديمة."""
    for col in ("origin_type TEXT",) + PD_COLS:
        try: c.execute("ALTER TABLE delivery_orders ADD COLUMN " + col)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower(): raise


_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def norm_phone(s):
    """يوحّد رقم العميل للعدّ والبحث: أرقام لاتينية فقط، 00/+20 تُحوَّل إلى 0، وإلا None. الرقم الفارغ مسموح (اختياري)."""
    d = "".join(ch for ch in str(s or "").translate(_AR) if ch.isdigit())
    if d.startswith("0020"): d = "0" + d[4:]
    elif d.startswith("20") and len(d) == 12: d = "0" + d[2:]
    return d if 7 <= len(d) <= 15 else None


def settings(c):
    g = lambda k: (c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone() or [None])[0]
    try: comm = max(0.0, float(g("provider_delivery_commission") or 0))
    except (TypeError, ValueError): comm = 0.0
    return str(g("provider_delivery_enabled") or "0") == "1", comm


def late_minutes(c):
    r = c.execute("SELECT value FROM settings WHERE key='provider_delivery_late_minutes'").fetchone()
    try: return max(0, int(float(r[0]))) if r else DEFAULT_LATE_MIN
    except (TypeError, ValueError): return DEFAULT_LATE_MIN


def timing(r, now, late_min, owner_id):
    """يحوّل أحداث order_events الخام (pickup_ev/hc_at/done_at/done_by) إلى أزمنة جاهزة. الأوردرات القديمة (قبل م2) انتهت عند الاستلام: completed بلا حدث picked_up فيُعدّ وقت الإتمام وقت الاستلام ولا يوجد وقت تسليم."""
    pk, hc, done, by = r.pop("pickup_ev"), r.pop("hc_at"), r.pop("done_at"), r.pop("done_by")
    legacy = r["status"] == "completed" and pk is None
    pk_at = done if legacy else pk
    dl_at = done if (r["status"] == "completed" and pk is not None) else None
    end = dl_at or (now if r["status"] in ("picked_up", "heading_customer") else None)
    leg = end - pk_at if (end and pk_at) else None
    r.update(picked_at=pk_at, heading_customer_at=hc, delivered_at=dl_at, legacy=legacy,
             accept_secs=(r["accepted_at"] - r["created_at"]) if r.get("accepted_at") else None,
             pickup_secs=(pk_at - r["accepted_at"]) if (pk_at and r.get("accepted_at")) else None,
             leg_secs=leg, total_secs=(dl_at - r["created_at"]) if dl_at else None,
             late=bool(late_min and leg is not None and leg > late_min * 60),
             fast=bool(dl_at and leg is not None and leg < FAST_SECS),
             delivered_by=(("pharmacy" if by == owner_id else "courier") if dl_at else None))
    return r


STATUS_AR = {"searching": "بانتظار مندوب", "assigned": "تم القبول", "heading_pickup": "في الطريق للصيدلية", "picked_up": "تم الاستلام", "heading_customer": "في الطريق للعميل", "completed": "تم التسليم", "cancelled": "ملغي", "disputed": "قيد المراجعة"}
OPEN_ST = ("searching", "assigned", "heading_pickup", "picked_up", "heading_customer")


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Africa/Cairo")
    except Exception: return timezone(timedelta(hours=2))  # لو لم تتوفر بيانات المناطق الزمنية على الجهاز: UTC+2 (بدون التوقيت الصيفي)


def _day(d): return int(datetime(d.year, d.month, d.day, tzinfo=_tz()).timestamp())  # بداية يوم (بتوقيت القاهرة) من تاريخ


def bounds(q, now):
    """(من، إلى) بالثواني بتوقيت القاهرة؛ إلى حصرية. range=today|week|month|all أو from/to بصيغة YYYY-MM-DD (شاملتان). None لو التاريخ غير صالح."""
    g = lambda k: (q.get(k) or [""])[0].strip()
    today = datetime.fromtimestamp(now, _tz()).date(); nxt = _day(today + timedelta(days=1))
    if g("from") or g("to"):
        try:
            a = date.fromisoformat(g("from")) if g("from") else date(2000, 1, 1); b = date.fromisoformat(g("to")) if g("to") else today
        except ValueError: return None
        if b < a: return None
        return _day(a), _day(b + timedelta(days=1)), "custom"
    r = g("range") or "today"
    if r == "all": return 0, nxt, "all"
    if r == "week": return _day(today - timedelta(days=6)), nxt, "week"
    if r == "month": return _day(today.replace(day=1)), nxt, "month"
    return _day(today), nxt, "today"


EVSQL = ("(SELECT MIN(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='assigned') accepted_at,"
         "(SELECT MIN(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='picked_up') pickup_ev,"
         "(SELECT MIN(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='heading_customer') hc_at,"
         "(SELECT MAX(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='completed') done_at,"
         "(SELECT e.actor_id FROM order_events e WHERE e.order_id=o.id AND e.to_status='completed' ORDER BY e.id DESC LIMIT 1) done_by,"
         "(SELECT COUNT(*) FROM order_events e WHERE e.order_id=o.id AND e.to_status='searching' AND e.from_status IS NOT NULL) abandons")


def _rows(c, uid, where="", args=(), limit=CAP):
    now = int(time.time()); lm = late_minutes(c)
    sql = ("SELECT o.id,o.status,o.created_at,o.dropoff_text,o.pd_cust_phone,o.pd_cust_norm,o.pd_price,o.pd_note,o.courier_id,cu.name courier_name," + EVSQL +
           " FROM delivery_orders o LEFT JOIN users cu ON cu.id=o.courier_id WHERE o.customer_id=? AND o.origin_type=? " + where + " ORDER BY o.id DESC LIMIT ?")
    return [timing(dict(r), now, lm, uid) for r in c.execute(sql, (uid, KIND) + tuple(args) + (limit,))]


def _avg(v):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v)) if v else None


def summarize(rows):
    done = [r for r in rows if r["status"] == "completed"]; real = [r for r in done if not r["legacy"]]  # الأوردرات القديمة (انتهت عند الاستلام) خارج متوسطات التوصيل
    leg = [r for r in real if r["leg_secs"] is not None]; pr = [r["pd_price"] for r in done if r["pd_price"] is not None]
    return {"total": len(rows), "completed": len(done), "cancelled": sum(r["status"] == "cancelled" for r in rows),
            "open": sum(r["status"] in OPEN_ST for r in rows), "abandoned": sum(r["abandons"] for r in rows),
            "price_sum": round(sum(pr), 2), "priced": len(pr),
            "avg_accept_secs": _avg(r["accept_secs"] for r in rows), "avg_pickup_secs": _avg(r["pickup_secs"] for r in real),
            "avg_leg_secs": _avg(r["leg_secs"] for r in leg), "avg_total_secs": _avg(r["total_secs"] for r in real),
            "late": sum(r["late"] for r in leg), "late_pct": round(100 * sum(r["late"] for r in leg) / len(leg)) if leg else None, "fast": sum(r["fast"] for r in real)}


def _public(r):
    r = {k: v for k, v in r.items() if k not in ("pd_cust_norm", "courier_id")}  # لا أرقام المناديب ولا معرّفاتهم؛ اسم المندوب فقط
    return r


def _repeat(c, uid, since, mn):
    return [{"phone": r[0], "count": r[1]} for r in c.execute("SELECT pd_cust_norm,COUNT(*) n FROM delivery_orders WHERE customer_id=? AND origin_type=? AND pd_cust_norm IS NOT NULL AND status!='cancelled' AND created_at>=? GROUP BY pd_cust_norm HAVING n>=? ORDER BY n DESC,pd_cust_norm LIMIT 50", (uid, KIND, since, mn))]


def _csv(rows):
    safe = lambda v: ("'" + v if isinstance(v, str) and v != "" and v[0] in "=+-@\t\r" else v)  # يمنع تنفيذ معادلات إكسل من نص حر
    mins = lambda x: round(x / 60, 1) if x is not None else ""
    tz = _tz(); out = io.StringIO(); w = csv.writer(out)
    w.writerow(["رقم الأوردر", "التاريخ (القاهرة)", "الحالة", "رقم العميل", "السعر", "التفاصيل", "العنوان", "المندوب", "قبول (د)", "استلام (د)", "توصيل (د)", "إجمالي (د)", "متأخر", "سريع جدًا", "مرات التخلّي"])
    for r in rows:
        w.writerow([r["id"], datetime.fromtimestamp(r["created_at"], tz).strftime("%Y-%m-%d %H:%M"), STATUS_AR.get(r["status"], r["status"]), r["pd_cust_phone"] or "", "" if r["pd_price"] is None else r["pd_price"],
                    safe(r["pd_note"] or ""), safe(r["dropoff_text"] or ""), safe(r["courier_name"] or ""), mins(r["accept_secs"]), mins(r["pickup_secs"]), mins(r["leg_secs"]), mins(r["total_secs"]),
                    "نعم" if r["late"] else "", "نعم" if r["fast"] else "", r["abandons"] or ""])
    return "\ufeff" + out.getvalue()


def _rows_admin(c, where="", args=(), limit=CAP):
    """م4: كل طلبات الصيدليات (كل المالكين) مع اسم الصيدلية والمندوب؛ owner_id لكل صف = customer_id كي تُحسب «أكّدتَ التسليم» صحيحًا."""
    now = int(time.time()); lm = late_minutes(c)
    sql = ("SELECT o.id,o.status,o.created_at,o.dropoff_text,o.pd_cust_phone,o.pd_cust_norm,o.pd_price,o.pd_note,o.courier_id,o.customer_id,cu.name courier_name,cu.phone courier_phone,pv.name_ar pharmacy," + EVSQL +
           " FROM delivery_orders o LEFT JOIN users cu ON cu.id=o.courier_id LEFT JOIN providers pv ON pv.user_id=o.customer_id WHERE o.origin_type=? " + where + " ORDER BY o.id DESC LIMIT ?")
    return [timing(dict(r), now, lm, r["customer_id"]) for r in c.execute(sql, (KIND,) + tuple(args) + (limit,))]


def _pct(a, b): return round(100 * a / b) if b else None


def _comm(c, ids):
    """صافي العمولة المحصّلة لكل أوردر (خصم − عكس) من دفتر المحفظة؛ {order_id: amount}."""
    out = {}
    for i in range(0, len(ids), 500):
        ch = ids[i:i + 500]
        for r in c.execute("SELECT ref_id,SUM(-amount) FROM wallet_entries WHERE ref_type='order' AND kind IN('commission','reversal') AND ref_id IN (%s) GROUP BY ref_id" % ",".join("?" * len(ch)), ch): out[r[0]] = round(r[1] or 0, 2)
    return out


def _group(rows, key, comm):
    g = {}
    for r in rows:
        if r[key] is not None: g.setdefault(r[key], []).append(r)
    out = []
    for k, rs in g.items():
        s = summarize(rs); done = s["completed"]; leg = sum(1 for r in rs if r["status"] == "completed" and not r["legacy"] and r["leg_secs"] is not None)
        out.append((k, rs, dict(s, cancel_pct=_pct(s["cancelled"], s["total"]), commission=round(sum(comm.get(r["id"], 0) for r in rs), 2), legs=leg)))
    return out


def admin_dash(h, c, u, path, q):
    """م4 — لوحة الإدارة: ملخص عام + ترتيب الصيدليات + ترتيب المناديب + نسب الإلغاء والتأخير + العمولات المحصّلة + تنبيهات (رقم عميل عبر صيدليات، مندوب كثير التخلّي). قراءة فقط، بتوقيت القاهرة."""
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    g = lambda k: (q.get(k) or [""])[0].strip(); now = int(time.time())
    b = bounds(q, now)
    if not b: return err(400, "التاريخ غير صالح")
    rows = _rows_admin(c, "AND o.created_at>=? AND o.created_at<?", (b[0], b[1]))
    if path.endswith("/export"):
        h.send(200, {"count": len(rows), "csv": _csv_admin(rows, _comm(c, [r["id"] for r in rows]))}); return True
    comm = _comm(c, [r["id"] for r in rows]); ids = [r["id"] for r in rows]
    ph = _group(rows, "customer_id", comm); co = _group(rows, "courier_id", comm)
    ab = {}  # التخلّي منسوب للمندوب الذي تخلّى فعلًا (الحدث بفاعله) لا لمن يحمل الأوردر الآن
    for i in range(0, len(ids), 500):
        ch = ids[i:i + 500]
        for r in c.execute("SELECT actor_id,COUNT(*) FROM order_events WHERE to_status='searching' AND from_status IN('assigned','heading_pickup') AND actor_id IS NOT NULL AND order_id IN (%s) GROUP BY actor_id" % ",".join("?" * len(ch)), ch): ab[r[0]] = ab.get(r[0], 0) + r[1]
    names = {r["id"]: (r["name"], r["phone"]) for r in c.execute("SELECT id,name,phone FROM users WHERE id IN (%s)" % ",".join("?" * len(set(list(ab) + [k for k, _, _ in co]) or [0])), tuple(set(list(ab) + [k for k, _, _ in co]) or [0]))}
    srt = g("sort") or "orders"
    kf = {"orders": lambda x: -x[2]["total"], "cancel": lambda x: (-(x[2]["cancel_pct"] or 0), -x[2]["total"]), "late": lambda x: (-(x[2]["late_pct"] or 0), -x[2]["total"]), "commission": lambda x: -x[2]["commission"]}.get(srt)
    if not kf: return err(400, "ترتيب غير صالح")
    pharmacies = [dict(user_id=k, name=(rs[0]["pharmacy"] or "—"), **s) for k, rs, s in sorted(ph, key=kf)[:TOP]]
    couriers = [dict(user_id=k, name=(names.get(k) or ("—", None))[0], phone=(names.get(k) or (None, None))[1], abandons_by=ab.get(k, 0), **s) for k, rs, s in sorted(co, key=kf)[:TOP]]
    x = {}  # رقم عميل ← صيدليات مختلفة (الملغي لا يُحتسب)
    for r in rows:
        if r["pd_cust_norm"] and r["status"] != "cancelled": x.setdefault(r["pd_cust_norm"], []).append(r)
    cross = sorted(({"phone": k, "orders": len(v), "pharmacies": sorted({r["pharmacy"] or "—" for r in v})} for k, v in x.items() if len({r["customer_id"] for r in v}) >= XPHARM_MIN), key=lambda a: (-len(a["pharmacies"]), -a["orders"], a["phone"]))[:TOP]
    quitters = sorted(({"user_id": k, "name": (names.get(k) or ("—", None))[0], "phone": (names.get(k) or (None, None))[1], "abandons": n} for k, n in ab.items() if n >= ABANDON_ALERT), key=lambda a: (-a["abandons"], a["user_id"]))[:TOP]
    tot = summarize(rows)
    h.send(200, {"range": b[2], "from": b[0], "to": b[1], "sort": srt, "truncated": len(rows) >= CAP, "late_minutes": late_minutes(c),
                 "summary": dict(tot, cancel_pct=_pct(tot["cancelled"], tot["total"]), commission=round(sum(comm.values()), 2), pharmacies=len(ph), couriers=len(co)),
                 "pharmacies": pharmacies, "couriers": couriers,
                 "alerts": {"cross_pharmacy_phones": cross, "frequent_abandoners": quitters, "thresholds": {"pharmacies": XPHARM_MIN, "abandons": ABANDON_ALERT}}}); return True


def _csv_admin(rows, comm):
    safe = lambda v: ("'" + v if isinstance(v, str) and v != "" and v[0] in "=+-@\t\r" else v)
    mins = lambda x: round(x / 60, 1) if x is not None else ""
    tz = _tz(); out = io.StringIO(); w = csv.writer(out)
    w.writerow(["رقم الأوردر", "التاريخ (القاهرة)", "الصيدلية", "الحالة", "رقم العميل", "السعر", "المندوب", "قبول (د)", "استلام (د)", "توصيل (د)", "إجمالي (د)", "متأخر", "سريع جدًا", "العمولة المحصّلة"])
    for r in rows:
        w.writerow([r["id"], datetime.fromtimestamp(r["created_at"], tz).strftime("%Y-%m-%d %H:%M"), safe(r["pharmacy"] or ""), STATUS_AR.get(r["status"], r["status"]), r["pd_cust_phone"] or "", "" if r["pd_price"] is None else r["pd_price"],
                    safe(r["courier_name"] or ""), mins(r["accept_secs"]), mins(r["pickup_secs"]), mins(r["leg_secs"]), mins(r["total_secs"]), "نعم" if r["late"] else "", "نعم" if r["fast"] else "", comm.get(r["id"], 0)])
    return "\ufeff" + out.getvalue()


def dash(h, c, u, path, q):
    """لوحة الصيدلية: قراءة فقط لطلبات هذه الصيدلية، بتوقيت القاهرة. لا تتطلب المفتاح العام (البيانات القديمة تبقى متاحة)."""
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    g = lambda k: (q.get(k) or [""])[0].strip(); uid = u["id"]; now = int(time.time())
    if path == "/api/provider/delivery-order":
        try: oid = int(g("id"))
        except ValueError: return err(400, "رقم الأوردر غير صالح")
        rs = _rows(c, uid, "AND o.id=?", (oid,))
        if not rs: return err(404, "غير موجود")
        r = rs[0]; act = r["status"] in ("assigned", "heading_pickup", "picked_up", "heading_customer")
        r["courier_phone"] = (c.execute("SELECT phone FROM users WHERE id=?", (r["courier_id"],)).fetchone() or [None])[0] if (act and r["courier_id"]) else None  # كما في القائمة: رقم المندوب أثناء النشاط فقط
        r["events"] = [{"to": e["to_status"], "at": e["at"], "by": "pharmacy" if e["actor_id"] == uid else ("courier" if e["actor_id"] else "system")}
                       for e in c.execute("SELECT to_status,at,actor_id FROM order_events WHERE order_id=? ORDER BY id", (oid,))]
        h.send(200, _public(r)); return True
    if path == "/api/provider/delivery-search":
        ph, cr = g("phone"), g("courier")
        if bool(ph) == bool(cr): return err(400, "ابحث برقم عميل أو باسم/رقم مندوب (واحد فقط)")
        if ph:
            n = norm_phone(ph)
            if not n: return err(400, "رقم العميل غير صالح")
            rows = _rows(c, uid, "AND o.pd_cust_norm=?", (n,), 200); tz = _tz(); d0 = _day(datetime.fromtimestamp(now, tz).date()); m0 = _day(datetime.fromtimestamp(now, tz).date().replace(day=1))
            live = [r for r in rows if r["status"] != "cancelled"]  # العدّ لا يشمل الملغي
            h.send(200, {"phone": n, "today": sum(r["created_at"] >= d0 for r in live), "month": sum(r["created_at"] >= m0 for r in live), "total": len(live), "items": [_public(r) for r in rows]}); return True
        if len(cr) < 2: return err(400, "اكتب حرفين على الأقل من اسم المندوب أو رقمه كاملًا")
        b = bounds(q, now)
        if not b: return err(400, "التاريخ غير صالح")
        pn = norm_phone(cr); nm = cr.lower()
        cands = {r["id"]: (r["name"], r["phone"]) for r in c.execute("SELECT DISTINCT cu.id,cu.name,cu.phone FROM delivery_orders o JOIN users cu ON cu.id=o.courier_id WHERE o.customer_id=? AND o.origin_type=?", (uid, KIND))}
        hit = [i for i, (n_, p_) in cands.items() if (pn and norm_phone(p_) == pn) or (not pn and nm in str(n_ or "").lower())]  # الرقم: تطابق كامل فقط (لا استنتاج أرقام المناديب بالتخمين الجزئي)
        if not hit: h.send(200, {"couriers": [], "summary": summarize([]), "items": []}); return True
        rows = _rows(c, uid, "AND o.courier_id IN (%s) AND o.created_at>=? AND o.created_at<?" % ",".join("?" * len(hit)), tuple(hit) + (b[0], b[1]), 200)
        h.send(200, {"couriers": sorted({cands[i][0] for i in hit}), "range": b[2], "summary": summarize(rows), "items": [_public(r) for r in rows]}); return True
    b = bounds(q, now)
    if not b: return err(400, "التاريخ غير صالح")
    rows = _rows(c, uid, "AND o.created_at>=? AND o.created_at<?", (b[0], b[1]))
    if path == "/api/provider/delivery-export":
        h.send(200, {"count": len(rows), "csv": _csv(rows)}); return True
    try: bf = int(g("before") or 0)
    except ValueError: bf = 0
    page = [r for r in rows if not bf or r["id"] < bf]; tz = _tz(); today = datetime.fromtimestamp(now, tz).date()
    h.send(200, {"range": b[2], "from": b[0], "to": b[1], "summary": summarize(rows), "truncated": len(rows) >= CAP, "late_minutes": late_minutes(c),
                 "repeat_today": _repeat(c, uid, _day(today), REPEAT_DAY), "regular_month": _repeat(c, uid, _day(today.replace(day=1)), REPEAT_MONTH),
                 "items": [_public(r) for r in page[:PAGE]], "has_more": len(page) > PAGE}); return True


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. h = معالج السيرفر (send/body). الأخطاء تُرجَع مباشرة عبر h.send."""
    dm = re.fullmatch(r"/api/provider/delivery-requests/(\d+)/delivered", path)
    if not dm and path not in ("/api/provider/delivery-request", "/api/provider/delivery-requests", "/api/admin/provider-delivery") + DASH + ADM: return False
    if (path in DASH or path in ADM) and method != "GET": return False
    if dm and method != "POST": return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    if path in ADM:
        if not u: return err(401, "سجّل الدخول أولًا")
        if u["role"] != "admin": return err(403, "ليس لديك صلاحية")
        return admin_dash(h, c, u, path, q)
    if path == "/api/admin/provider-delivery":
        if method not in ("GET", "POST"): return False
        if not u: return err(401, "سجّل الدخول أولًا")
        if u["role"] != "admin": return err(403, "ليس لديك صلاحية")
        if method == "GET":
            on, comm = settings(c); h.send(200, {"enabled": on, "commission": comm, "late_minutes": late_minutes(c)}); return True
        d = h.body(); en = d.get("enabled")
        if not isinstance(en, bool): return err(400, "قيمة التفعيل غير صالحة")
        try: comm = round(float(d.get("commission", 0) or 0), 2)
        except (TypeError, ValueError): return err(400, "قيمة العمولة غير صالحة")
        if not (0 <= comm <= 100000): return err(400, "قيمة العمولة غير صالحة")  # يرفض NaN/inf/سالب
        kv = [("provider_delivery_enabled", "1" if en else "0"), ("provider_delivery_commission", str(comm))]
        if d.get("late_minutes") is not None:  # اختياري: غيابه يُبقي القيمة الحالية (توافق مع الواجهة القديمة)
            try: lm = int(float(str(d["late_minutes"]).translate(_AR)))
            except (TypeError, ValueError, OverflowError): return err(400, "حد التأخير غير صالح")
            if not (0 <= lm <= 1440): return err(400, "حد التأخير غير صالح")
            kv.append(("provider_delivery_late_minutes", str(lm)))
        for k, x in kv:
            c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, x))
        _H["audit"](c, u["id"], "settings.provider_delivery", None, {"enabled": en, "commission": comm, "late_minutes": late_minutes(c)}); c.commit()
        h.send(200, {"enabled": en, "commission": comm, "late_minutes": late_minutes(c)}); return True
    if not dm and path not in DASH and (method, path) not in (("POST", "/api/provider/delivery-request"), ("GET", "/api/provider/delivery-requests")): return False
    if not u: return err(401, "سجّل الدخول أولًا")
    pv = c.execute("SELECT * FROM providers WHERE user_id=? AND status='approved'", (u["id"],)).fetchone()
    if not pv: return err(403, "حساب الصيدلية غير معتمد")
    if path in DASH: return dash(h, c, u, path, q)
    on, comm = settings(c)
    if dm:  # م2: «تم التسليم» يدويًا من الصيدلية (لو المندوب لم يضغطها) — صاحب الطلب فقط، بعد الاستلام فقط؛ لا يتطلب المفتاح العام كي لا يعلق أوردر شغّال
        oid = int(dm[1]); now = int(time.time())
        o = c.execute("SELECT status FROM delivery_orders WHERE id=? AND customer_id=? AND origin_type=?", (oid, u["id"], KIND)).fetchone()
        if not o: return err(404, "غير موجود")
        if not c.execute("UPDATE delivery_orders SET status='completed',updated_at=? WHERE id=? AND customer_id=? AND origin_type=? AND status IN ('picked_up','heading_customer')", (now, oid, u["id"], KIND)).rowcount: return err(409, "لا يمكن تأكيد التسليم في الحالة الحالية")
        c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, u["id"], o["status"], "completed", now))
        _H["audit"](c, u["id"], "provider.delivery_confirm", str(oid)); c.commit()
        h.send(200, {"id": oid, "status": "completed"}); return True
    if method == "GET":
        rows = [dict(r) for r in c.execute(
            "SELECT o.id,o.status,o.dropoff_text,o.pd_cust_phone,o.pd_price,o.pd_note,o.created_at,o.updated_at,CASE WHEN o.status IN " + ACTIVE + " THEN cu.name END courier_name,"
            "CASE WHEN o.status IN " + ACTIVE + " THEN cu.phone END courier_phone,"
            "(SELECT MIN(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='assigned') accepted_at,"
            "(SELECT MIN(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='picked_up') pickup_ev,"
            "(SELECT MIN(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='heading_customer') hc_at,"
            "(SELECT MAX(e.at) FROM order_events e WHERE e.order_id=o.id AND e.to_status='completed') done_at,"
            "(SELECT e.actor_id FROM order_events e WHERE e.order_id=o.id AND e.to_status='completed' ORDER BY e.id DESC LIMIT 1) done_by,o.customer_id "
            "FROM delivery_orders o LEFT JOIN users cu ON cu.id=o.courier_id WHERE o.customer_id=? AND o.origin_type=? ORDER BY o.id DESC LIMIT 20", (u["id"], KIND))]
        now = int(time.time()); lm = late_minutes(c)
        for r in rows: timing(r, now, lm, r.pop("customer_id"))
        h.send(200, {"enabled": on, "late_minutes": lm, "items": rows}); return True
    # POST: ضغطة واحدة — بلا أجرة ولا تفاصيل؛ عنوان العميل اختياري
    if not on: return err(403, "طلب المندوب من الصيدلية غير مفعّل حاليًا")
    d = h.body(); rid = pv["region_id"]
    if not c.execute("SELECT 1 FROM regions WHERE id=? AND is_active=1", (rid,)).fetchone(): rid = _H["region"](c)
    if not rid: return err(400, "الدليفري غير متاح حاليًا")
    rk = str(d.get("request_key", "")).strip()[:64] or None  # مفتاح من الواجهة لكل ضغطة: الضغط المزدوج أو إعادة المحاولة يرجعان نفس الطلب
    if rk:
        dup = c.execute("SELECT id,status FROM delivery_orders WHERE customer_id=? AND request_key=?", (u["id"], rk)).fetchone()
        if dup: h.send(200, {"id": dup["id"], "status": dup["status"], "duplicate": True}); return True
    if c.execute(_H["count_sql"], (u["id"],)).fetchone()[0] >= MAX_OPEN: return err(429, "لديك طلبات مندوب مفتوحة كثيرة، انتظر أو ألغِ بعضها أولًا")
    dr = str(d.get("dropoff_text", "")).strip()[:300]; now = int(time.time())
    cph = str(d.get("customer_phone", "") or "").strip(); cn = None
    if cph:
        cn = norm_phone(cph)
        if not cn: return err(400, "رقم العميل غير صالح")
    pr = d.get("price"); pnote = str(d.get("note", "") or "").strip()[:500]
    if pr is not None and str(pr).strip() != "":
        try: pr = round(float(str(pr).translate(_AR)), 2)
        except (TypeError, ValueError): return err(400, "السعر غير صالح")
        if not (0 <= pr <= 1000000): return err(400, "السعر غير صالح")  # يرفض NaN/inf/سالب
    else: pr = None
    pk = ("صيدلية " + pv["name_ar"] + (" — " + pv["address"] if pv["address"] else ""))[:300]
    cur = c.execute("INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,details,fee,commission,created_at,updated_at,search_started_at,delivery_code,request_key,fare_status,origin_type,comm_type,comm_value) VALUES(?,?,?,?,?,0,?,?,?,?,?,?,'approved',?,'fixed',?)",
                    (u["id"], rid, pk, dr, "طلب استلام من صيدلية", comm, now, now, now, "%06d" % secrets.randbelow(10 ** 6), rk, KIND, comm))
    oid = cur.lastrowid
    if cn or pr is not None or pnote: c.execute("UPDATE delivery_orders SET pd_cust_phone=?,pd_cust_norm=?,pd_price=?,pd_note=? WHERE id=?", (cn, cn, pr, pnote or None, oid))
    c.execute("INSERT INTO order_events(order_id,actor_id,from_status,to_status,at) VALUES(?,?,?,?,?)", (oid, u["id"], None, "searching", now))
    _H["audit"](c, u["id"], "provider.delivery_request", str(oid)); c.commit(); _H["push"](oid)
    h.send(201, {"id": oid, "status": "searching"}); return True
