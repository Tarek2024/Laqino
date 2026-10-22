# لاقينو — مفضلة الإعلانات وبلاغات الإعلانات (المرحلة 8ب/«كمّل»). وحدة مستقلة بنمط chat.py/svc.py: لا تستورد server.py، وتُربط بأسطر قليلة.
# الجدولان listing_favorites وlisting_reports موجودان أصلًا (market.py) لكن بلا أي مسار؛ هذه الوحدة تضيف المسارات فقط (لا جداول ولا أعمدة جديدة).
#   مستخدم مسجّل:  POST /api/listings/<id>/favorite {on:true|false}    إضافة/إزالة من المفضلة (إعلان منشور فقط؛ الإزالة مسموحة دائمًا)
#                  GET  /api/my/favorites                               مفضلتي (المنشور حاليًا فقط؛ ما أُخفي أو حُذف لا يظهر ولا يُسرَّب)
#                  POST /api/listings/<id>/report {reason, details?}    بلاغ عن إعلان منشور (مرة لكل مستخدم لكل إعلان؛ لا بلاغ على إعلانك)
#   إدارة/موظف:   GET  /api/admin/listing-reports?status=open|resolved|dismissed
#                  POST /api/admin/listing-reports/<id>/resolve {status:resolved|dismissed, hide?:bool}
#                       hide=true (مع resolved): يُخفي الإعلان (status=hidden) ويغلق كل البلاغات المفتوحة عليه. لا إخفاء تلقائي بالبلاغات (منعًا لاستغلالها).
# لا تُرجع أي مسار هنا رقم هاتف؛ اسم المبلِّغ يظهر للإدارة فقط.
import json, re, time
import market

REASONS = {"spam": "مكرر أو إعلان مزعج", "scam": "احتيال أو نصب", "prohibited": "سلعة أو محتوى ممنوع", "wrong_info": "بيانات أو صور مضللة", "sold": "تم البيع ولم يُغلق الإعلان", "other": "سبب آخر"}
MAX_FAVORITES, MAX_REPORTS_DAY, MAX_DETAILS = 500, 10, 300


def _public(c, lid):
    """الإعلان إن كان منشورًا في تصنيف ظاهر وإلا None."""
    r = c.execute("SELECT id,user_id,title,status,category_id FROM listings WHERE id=?", (lid,)).fetchone()
    return r if r and r["status"] == "approved" and market.is_visible_category(c, r["category_id"]) else None


def _notify(c, user_id, kind, title, body, link, lid):
    """إشعار داخل التطبيق (الجرس). أي خطأ هنا لا يُفشل العملية الأساسية."""
    try:
        c.execute("INSERT INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (user_id, kind, title, body, link, "listing", lid, int(time.time())))
    except Exception as e:
        import sys; sys.stderr.write("lsocial notify failed: %r\n" % (e,))


def _notify_admins(c, lid, title):
    """إشعار واحد غير مقروء لكل مدير/موظف مهما بلغ عدد البلاغات (منعًا للإغراق)؛ يتجدد بعد أن يقرأه."""
    n = c.execute("SELECT COUNT(*) FROM listing_reports WHERE status='open'").fetchone()[0]
    for a in c.execute("SELECT id FROM users WHERE role IN('admin','staff')").fetchall():
        if c.execute("SELECT 1 FROM notifications WHERE user_id=? AND kind='admin.listing_report' AND read_at IS NULL", (a["id"],)).fetchone(): continue
        _notify(c, a["id"], "admin.listing_report", "بلاغ جديد على إعلان", "%d بلاغ مفتوح بانتظار المراجعة" % n, "admin:listings", lid)


def flags(c, u, lid):
    """حقول تُضاف إلى تفاصيل الإعلان للمستخدم المسجّل (للواجهة)."""
    if not u: return {}
    return {"is_favorite": bool(c.execute("SELECT 1 FROM listing_favorites WHERE user_id=? AND listing_id=?", (u["id"], lid)).fetchone()),
            "reported": bool(c.execute("SELECT 1 FROM listing_reports WHERE reporter_id=? AND listing_id=?", (u["id"], lid)).fetchone())}


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب."""
    m = re.fullmatch(r"/api/listings/(\d+)/(favorite|report)", path)
    ma = re.fullmatch(r"/api/admin/listing-reports/(\d+)/resolve", path)
    if not (m or ma or path in ("/api/my/favorites", "/api/admin/listing-reports")): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    if not u: return err(401, "سجّل الدخول أولًا")
    now = int(time.time())

    if path == "/api/my/favorites":
        if method != "GET": return err(404, "غير موجود")
        rows = [dict(r) for r in c.execute(
            "SELECT l.id,l.title,l.price,l.condition,l.negotiable,l.closed_kind,l.created_at,f.created_at fav_at FROM listing_favorites f JOIN listings l ON l.id=f.listing_id "
            "WHERE f.user_id=? AND l.status='approved' AND l.category_id IN " + market.VISIBLE_CATEGORIES + " ORDER BY f.created_at DESC, l.id DESC LIMIT 200", (u["id"],))]
        imgs = market.images_for(c, [r["id"] for r in rows])
        for r in rows: r["images"] = imgs[r["id"]]
        h.send(200, rows); return True

    if m:
        lid = int(m[1])
        if method != "POST": return err(404, "غير موجود")
        b = h.body()
        if m[2] == "favorite":
            on = b.get("on", True)
            if not isinstance(on, bool): return err(400, "on يجب أن تكون true أو false")
            if not on:
                c.execute("DELETE FROM listing_favorites WHERE user_id=? AND listing_id=?", (u["id"], lid)); c.commit()
                h.send(200, {"favorite": False}); return True
            if not _public(c, lid): return err(404, "غير موجود")
            if c.execute("SELECT COUNT(*) FROM listing_favorites WHERE user_id=?", (u["id"],)).fetchone()[0] >= MAX_FAVORITES and \
               not c.execute("SELECT 1 FROM listing_favorites WHERE user_id=? AND listing_id=?", (u["id"], lid)).fetchone():
                return err(400, "وصلت للحد الأقصى من المفضلة، احذف بعضها أولًا")
            c.execute("INSERT OR IGNORE INTO listing_favorites(user_id,listing_id,created_at) VALUES(?,?,?)", (u["id"], lid, now)); c.commit()
            h.send(200, {"favorite": True}); return True
        # report
        r = _public(c, lid)
        if not r: return err(404, "غير موجود")
        if r["user_id"] == u["id"]: return err(400, "لا يمكنك الإبلاغ عن إعلانك")
        reason = str(b.get("reason", "")).strip()
        if reason not in REASONS: return err(400, "اختر سبب البلاغ من القائمة")
        details = str(b.get("details") or "").strip()[:MAX_DETAILS] or None
        if reason == "other" and not details: return err(400, "اكتب تفاصيل البلاغ")
        if c.execute("SELECT 1 FROM listing_reports WHERE listing_id=? AND reporter_id=?", (lid, u["id"])).fetchone(): return err(409, "سبق أن بلّغت عن هذا الإعلان")
        if c.execute("SELECT COUNT(*) FROM listing_reports WHERE reporter_id=? AND created_at>?", (u["id"], now - 86400)).fetchone()[0] >= MAX_REPORTS_DAY:
            return err(429, "تجاوزت الحد اليومي للبلاغات، حاول غدًا")
        c.execute("INSERT INTO listing_reports(listing_id,reporter_id,reason,details,created_at) VALUES(?,?,?,?,?)", (lid, u["id"], reason, details, now))
        _notify_admins(c, lid, r["title"]); c.commit()
        h.send(200, {"ok": True}); return True

    # ---- إدارة
    if u["role"] not in ("admin", "staff"): return err(403, "غير مسموح")
    if path == "/api/admin/listing-reports":
        if method != "GET": return err(404, "غير موجود")
        st = q.get("status", ["open"])[0]
        if st not in ("open", "resolved", "dismissed"): return err(400, "حالة غير صالحة")
        rows = []
        for r in c.execute("SELECT r.id,r.listing_id,r.reason,r.details,r.status,r.created_at,r.handled_at,l.title,l.status listing_status,l.user_id seller_id,s.name seller,p.name reporter,"
                           "(SELECT COUNT(*) FROM listing_reports x WHERE x.listing_id=r.listing_id AND x.status='open') open_count "
                           "FROM listing_reports r JOIN listings l ON l.id=r.listing_id JOIN users s ON s.id=l.user_id JOIN users p ON p.id=r.reporter_id "
                           "WHERE r.status=? ORDER BY open_count DESC, r.id DESC LIMIT 200", (st,)).fetchall():
            d = dict(r); d["reason_label"] = REASONS.get(d["reason"], d["reason"]); rows.append(d)
        h.send(200, rows); return True
    if method != "POST": return err(404, "غير موجود")
    b = h.body(); st = b.get("status"); hide = b.get("hide", False)
    if st not in ("resolved", "dismissed"): return err(400, "حالة غير صالحة")
    if not isinstance(hide, bool) or (hide and st != "resolved"): return err(400, "الإخفاء يتطلب status=resolved")
    r = c.execute("SELECT listing_id FROM listing_reports WHERE id=? AND status='open'", (int(ma[1]),)).fetchone()
    if not r: return err(409, "البلاغ غير مفتوح أو غير موجود")
    lid = r["listing_id"]; lt = c.execute("SELECT title,user_id,status FROM listings WHERE id=?", (lid,)).fetchone()
    if hide:
        was_public = lt["status"] == "approved"
        c.execute("UPDATE listings SET status='hidden', hidden_reason=? WHERE id=? AND status='approved'", ("بعد مراجعة بلاغ من مستخدمين", lid))
        closing = [x["reporter_id"] for x in c.execute("SELECT reporter_id FROM listing_reports WHERE listing_id=? AND status='open'", (lid,)).fetchall()]
        c.execute("UPDATE listing_reports SET status='resolved',handled_by=?,handled_at=? WHERE listing_id=? AND status='open'", (u["id"], now, lid))
        if was_public: _notify(c, lt["user_id"], "listing.hidden", "تم إخفاء إعلانك", "«%s» — أخفته الإدارة بعد مراجعة بلاغ. للاستفسار تواصل مع الإدارة." % lt["title"], "souq", lid)
    else:
        closing = [c.execute("SELECT reporter_id FROM listing_reports WHERE id=?", (int(ma[1]),)).fetchone()["reporter_id"]]
        c.execute("UPDATE listing_reports SET status=?,handled_by=?,handled_at=? WHERE id=?", (st, u["id"], now, int(ma[1])))
    msg = "راجعت الإدارة بلاغك على «%s»" % lt["title"] + (" ولم تجد مخالفة." if st == "dismissed" else " وتم إخفاء الإعلان. شكرًا لك." if hide else " وأغلقته دون إجراء على الإعلان.")
    for rid in closing: _notify(c, rid, "listing.report_result", "تمت مراجعة بلاغك", msg, "souq", lid)
    c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (u["id"], "listing.report." + st, str(lid), json.dumps({"report": int(ma[1]), "hide": hide}, ensure_ascii=False), now))
    c.commit(); h.send(200, {"ok": True}); return True
