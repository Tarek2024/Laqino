# لاقينو — المرحلة 79: إحصائيات ولوحات دليفري المحلات. نسخة مطابقة لوظائف لوحة الصيدلية (provider_delivery.dash/admin_dash، م3 وم4) لكن على طلبات «المحل يطلب مندوب» (origin_type='shop_pickup') فقط.
# وحدة مستقلة: لا تعدّل provider_delivery.py ولا تغيّر أي سلوك للصيدليات؛ تستعمل فقط دوالها الحسابية العامة (الأزمنة، الفترات، الملخص، العمولة) للقراءة.
# قراءة فقط (GET). بتوقيت القاهرة. المسارات:
#   مالك المحل (محله المعتمد فقط، لا يتطلب المفتاح العام كي تبقى البيانات القديمة متاحة): GET /api/owner/shops/<id>/delivery-(dashboard|search|order|export)
#   إدارة (admin فقط):                                                                      GET /api/admin/shop-delivery/(dashboard|export)
import re, time, csv, io
from datetime import datetime
import provider_delivery as pd
import shops, shop_delivery as sd

DASH = re.compile(r"/api/owner/shops/(\d{1,9})/delivery-(dashboard|search|order|export)")
ADM = re.compile(r"/api/admin/shop-delivery/(dashboard|export)")
XSHOP_MIN, ABANDON_ALERT, TOP = 2, 3, 50  # تنبيه: رقم عميل عند محلين+ في الفترة؛ مندوب تخلّى 3 مرات+؛ أعلى N في الترتيب
STATUS_AR = dict(pd.STATUS_AR, heading_pickup="في الطريق للمحل")
_FROM = (" FROM shop_delivery_links l JOIN delivery_orders o ON o.id=l.order_id LEFT JOIN users cu ON cu.id=o.courier_id")
_COLS = "o.id,o.status,o.created_at,o.dropoff_text,o.pd_cust_phone,o.pd_cust_norm,o.pd_price,o.pd_note,o.courier_id,cu.name courier_name,"


def timing(r, now, late_min, owner_id):
    r = pd.timing(r, now, late_min, owner_id)
    if r.get("delivered_by") == "pharmacy": r["delivered_by"] = "shop"  # المحل أكّد التسليم يدويًا (بدل المندوب)
    return r


def _rows(c, shop, where="", args=(), limit=pd.CAP):
    now = int(time.time()); lm = sd.late_minutes(c)
    sql = "SELECT " + _COLS + pd.EVSQL + _FROM + " WHERE l.shop_id=? AND l.kind=? " + where + " ORDER BY o.id DESC LIMIT ?"
    return [timing(dict(r), now, lm, shop["owner_id"]) for r in c.execute(sql, (shop["id"], sd.PICKUP) + tuple(args) + (limit,))]


def _rows_admin(c, where="", args=(), limit=pd.CAP):
    """كل طلبات المحلات (كل المحلات) مع اسم المحل والمندوب؛ owner_id لكل صف = مالك المحل كي تُحسب «أكّد التسليم» صحيحًا."""
    now = int(time.time()); lm = sd.late_minutes(c)
    sql = ("SELECT " + _COLS + "cu.phone courier_phone,l.shop_id,sh.name_ar shop,sh.owner_id," + pd.EVSQL + _FROM + " JOIN shops sh ON sh.id=l.shop_id WHERE l.kind=? " + where + " ORDER BY o.id DESC LIMIT ?")
    return [timing(dict(r), now, lm, r["owner_id"]) for r in c.execute(sql, (sd.PICKUP,) + tuple(args) + (limit,))]


def _public(r):
    return {k: v for k, v in r.items() if k not in ("pd_cust_norm", "courier_id")}  # لا معرّفات المناديب؛ اسم المندوب فقط


def _repeat(c, shop_id, since, mn):
    return [{"phone": r[0], "count": r[1]} for r in c.execute(
        "SELECT o.pd_cust_norm,COUNT(*) n FROM shop_delivery_links l JOIN delivery_orders o ON o.id=l.order_id WHERE l.shop_id=? AND l.kind=? AND o.pd_cust_norm IS NOT NULL AND o.status!='cancelled' AND o.created_at>=? GROUP BY o.pd_cust_norm HAVING n>=? ORDER BY n DESC,o.pd_cust_norm LIMIT 50",
        (shop_id, sd.PICKUP, since, mn))]


def _safe(v): return "'" + v if isinstance(v, str) and v != "" and v[0] in "=+-@\t\r" else v  # يمنع تنفيذ معادلات إكسل من نص حر


def _mins(x): return round(x / 60, 1) if x is not None else ""


def _csv(rows):
    tz = pd._tz(); out = io.StringIO(); w = csv.writer(out)
    w.writerow(["رقم الأوردر", "التاريخ (القاهرة)", "الحالة", "رقم العميل", "السعر", "التفاصيل", "العنوان", "المندوب", "قبول (د)", "استلام (د)", "توصيل (د)", "إجمالي (د)", "متأخر", "سريع جدًا", "مرات التخلّي"])
    for r in rows:
        w.writerow([r["id"], datetime.fromtimestamp(r["created_at"], tz).strftime("%Y-%m-%d %H:%M"), STATUS_AR.get(r["status"], r["status"]), r["pd_cust_phone"] or "", "" if r["pd_price"] is None else r["pd_price"],
                    _safe(r["pd_note"] or ""), _safe(r["dropoff_text"] or ""), _safe(r["courier_name"] or ""), _mins(r["accept_secs"]), _mins(r["pickup_secs"]), _mins(r["leg_secs"]), _mins(r["total_secs"]),
                    "نعم" if r["late"] else "", "نعم" if r["fast"] else "", r["abandons"] or ""])
    return "﻿" + out.getvalue()


def _csv_admin(rows, comm):
    tz = pd._tz(); out = io.StringIO(); w = csv.writer(out)
    w.writerow(["رقم الأوردر", "التاريخ (القاهرة)", "المحل", "الحالة", "رقم العميل", "السعر", "المندوب", "قبول (د)", "استلام (د)", "توصيل (د)", "إجمالي (د)", "متأخر", "سريع جدًا", "العمولة المحصّلة"])
    for r in rows:
        w.writerow([r["id"], datetime.fromtimestamp(r["created_at"], tz).strftime("%Y-%m-%d %H:%M"), _safe(r["shop"] or ""), STATUS_AR.get(r["status"], r["status"]), r["pd_cust_phone"] or "", "" if r["pd_price"] is None else r["pd_price"],
                    _safe(r["courier_name"] or ""), _mins(r["accept_secs"]), _mins(r["pickup_secs"]), _mins(r["leg_secs"]), _mins(r["total_secs"]), "نعم" if r["late"] else "", "نعم" if r["fast"] else "", comm.get(r["id"], 0)])
    return "﻿" + out.getvalue()


def admin_dash(h, c, u, path, q):
    """لوحة الإدارة: ملخص عام + ترتيب المحلات + ترتيب المناديب + نسب الإلغاء والتأخير + العمولات المحصّلة + تنبيهات (رقم عميل عبر محلات، مندوب كثير التخلّي)."""
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    g = lambda k: (q.get(k) or [""])[0].strip(); now = int(time.time())
    b = pd.bounds(q, now)
    if not b: return err(400, "التاريخ غير صالح")
    rows = _rows_admin(c, "AND o.created_at>=? AND o.created_at<?", (b[0], b[1])); ids = [r["id"] for r in rows]
    comm = pd._comm(c, ids)
    if path.endswith("/export"):
        h.send(200, {"count": len(rows), "csv": _csv_admin(rows, comm)}); return True
    sh = pd._group(rows, "shop_id", comm); co = pd._group(rows, "courier_id", comm)
    ab = {}  # التخلّي منسوب للمندوب الذي تخلّى فعلًا (الحدث بفاعله) لا لمن يحمل الأوردر الآن
    for i in range(0, len(ids), 500):
        ch = ids[i:i + 500]
        for r in c.execute("SELECT actor_id,COUNT(*) FROM order_events WHERE to_status='searching' AND from_status IN('assigned','heading_pickup') AND actor_id IS NOT NULL AND order_id IN (%s) GROUP BY actor_id" % ",".join("?" * len(ch)), ch): ab[r[0]] = ab.get(r[0], 0) + r[1]
    uids = list(set(list(ab) + [k for k, _, _ in co])) or [0]
    names = {r["id"]: (r["name"], r["phone"]) for r in c.execute("SELECT id,name,phone FROM users WHERE id IN (%s)" % ",".join("?" * len(uids)), tuple(uids))}
    srt = g("sort") or "orders"
    kf = {"orders": lambda x: -x[2]["total"], "cancel": lambda x: (-(x[2]["cancel_pct"] or 0), -x[2]["total"]), "late": lambda x: (-(x[2]["late_pct"] or 0), -x[2]["total"]), "commission": lambda x: -x[2]["commission"]}.get(srt)
    if not kf: return err(400, "ترتيب غير صالح")
    shop_list = [dict(shop_id=k, name=(rs[0]["shop"] or "—"), **s) for k, rs, s in sorted(sh, key=kf)[:TOP]]
    couriers = [dict(user_id=k, name=(names.get(k) or ("—", None))[0], phone=(names.get(k) or (None, None))[1], abandons_by=ab.get(k, 0), **s) for k, rs, s in sorted(co, key=kf)[:TOP]]
    x = {}  # رقم عميل ← محلات مختلفة (الملغي لا يُحتسب)
    for r in rows:
        if r["pd_cust_norm"] and r["status"] != "cancelled": x.setdefault(r["pd_cust_norm"], []).append(r)
    cross = sorted(({"phone": k, "orders": len(v), "shops": sorted({r["shop"] or "—" for r in v})} for k, v in x.items() if len({r["shop_id"] for r in v}) >= XSHOP_MIN), key=lambda a: (-len(a["shops"]), -a["orders"], a["phone"]))[:TOP]
    quitters = sorted(({"user_id": k, "name": (names.get(k) or ("—", None))[0], "phone": (names.get(k) or (None, None))[1], "abandons": n} for k, n in ab.items() if n >= ABANDON_ALERT), key=lambda a: (-a["abandons"], a["user_id"]))[:TOP]
    tot = pd.summarize(rows)
    h.send(200, {"range": b[2], "from": b[0], "to": b[1], "sort": srt, "truncated": len(rows) >= pd.CAP, "late_minutes": sd.late_minutes(c),
                 "summary": dict(tot, cancel_pct=pd._pct(tot["cancelled"], tot["total"]), commission=round(sum(comm.values()), 2), shops=len(sh), couriers=len(co)),
                 "shops": shop_list, "couriers": couriers,
                 "alerts": {"cross_shop_phones": cross, "frequent_abandoners": quitters, "thresholds": {"shops": XSHOP_MIN, "abandons": ABANDON_ALERT}}}); return True


def dash(h, c, u, shop, path, q):
    """لوحة المحل: قراءة فقط لطلبات هذا المحل."""
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    g = lambda k: (q.get(k) or [""])[0].strip(); now = int(time.time())
    if path.endswith("/delivery-order"):
        try: oid = int(g("id"))
        except ValueError: return err(400, "رقم الأوردر غير صالح")
        rs = _rows(c, shop, "AND o.id=?", (oid,))
        if not rs: return err(404, "غير موجود")
        r = rs[0]; act = r["status"] in ("assigned", "heading_pickup", "picked_up", "heading_customer")
        r["courier_phone"] = (c.execute("SELECT phone FROM users WHERE id=?", (r["courier_id"],)).fetchone() or [None])[0] if (act and r["courier_id"]) else None  # رقم المندوب أثناء النشاط فقط
        r["events"] = [{"to": e["to_status"], "at": e["at"], "by": "shop" if e["actor_id"] == shop["owner_id"] else ("courier" if e["actor_id"] else "system")}
                       for e in c.execute("SELECT to_status,at,actor_id FROM order_events WHERE order_id=? ORDER BY id", (oid,))]
        h.send(200, _public(r)); return True
    if path.endswith("/delivery-search"):
        ph, cr = g("phone"), g("courier")
        if bool(ph) == bool(cr): return err(400, "ابحث برقم عميل أو باسم/رقم مندوب (واحد فقط)")
        if ph:
            n = pd.norm_phone(ph)
            if not n: return err(400, "رقم العميل غير صالح")
            rows = _rows(c, shop, "AND o.pd_cust_norm=?", (n,), 200); tz = pd._tz(); d0 = pd._day(datetime.fromtimestamp(now, tz).date()); m0 = pd._day(datetime.fromtimestamp(now, tz).date().replace(day=1))
            live = [r for r in rows if r["status"] != "cancelled"]  # العدّ لا يشمل الملغي
            h.send(200, {"phone": n, "today": sum(r["created_at"] >= d0 for r in live), "month": sum(r["created_at"] >= m0 for r in live), "total": len(live), "items": [_public(r) for r in rows]}); return True
        if len(cr) < 2: return err(400, "اكتب حرفين على الأقل من اسم المندوب أو رقمه كاملًا")
        b = pd.bounds(q, now)
        if not b: return err(400, "التاريخ غير صالح")
        pn = pd.norm_phone(cr); nm = cr.lower()
        cands = {r["id"]: (r["name"], r["phone"]) for r in c.execute("SELECT DISTINCT cu.id,cu.name,cu.phone FROM shop_delivery_links l JOIN delivery_orders o ON o.id=l.order_id JOIN users cu ON cu.id=o.courier_id WHERE l.shop_id=? AND l.kind=?", (shop["id"], sd.PICKUP))}
        hit = [i for i, (n_, p_) in cands.items() if (pn and pd.norm_phone(p_) == pn) or (not pn and nm in str(n_ or "").lower())]  # الرقم: تطابق كامل فقط (لا استنتاج أرقام المناديب بالتخمين الجزئي)
        if not hit: h.send(200, {"couriers": [], "summary": pd.summarize([]), "items": []}); return True
        rows = _rows(c, shop, "AND o.courier_id IN (%s) AND o.created_at>=? AND o.created_at<?" % ",".join("?" * len(hit)), tuple(hit) + (b[0], b[1]), 200)
        h.send(200, {"couriers": sorted({cands[i][0] for i in hit}), "range": b[2], "summary": pd.summarize(rows), "items": [_public(r) for r in rows]}); return True
    b = pd.bounds(q, now)
    if not b: return err(400, "التاريخ غير صالح")
    rows = _rows(c, shop, "AND o.created_at>=? AND o.created_at<?", (b[0], b[1]))
    if path.endswith("/delivery-export"):
        h.send(200, {"count": len(rows), "csv": _csv(rows)}); return True
    try: bf = int(g("before") or 0)
    except ValueError: bf = 0
    page = [r for r in rows if not bf or r["id"] < bf]; today = datetime.fromtimestamp(now, pd._tz()).date()
    h.send(200, {"range": b[2], "from": b[0], "to": b[1], "summary": pd.summarize(rows), "truncated": len(rows) >= pd.CAP, "late_minutes": sd.late_minutes(c),
                 "repeat_today": _repeat(c, shop["id"], pd._day(today), pd.REPEAT_DAY), "regular_month": _repeat(c, shop["id"], pd._day(today.replace(day=1)), pd.REPEAT_MONTH),
                 "items": [_public(r) for r in page[:pd.PAGE]], "has_more": len(page) > pd.PAGE}); return True


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب (GET فقط). h = معالج السيرفر (send)."""
    mo, ma = DASH.fullmatch(path), ADM.fullmatch(path)
    if (not mo and not ma) or method != "GET": return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    if not u: return err(401, "سجّل الدخول أولًا")
    if ma:
        if u["role"] != "admin": return err(403, "ليس لديك صلاحية")
        return admin_dash(h, c, u, path, q)
    s, e = shops.need_shop_owner(c, u, int(mo[1]))
    if e: return err(*e)
    return dash(h, c, u, s, path, q)
