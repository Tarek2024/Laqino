# لاقينو — سوق لاقينو: المحادثة داخل التطبيق + اختيار البائع لطريقة التواصل (المرحلة 4).
# وحدة مستقلة بنمط notif.py/products.py/rx.py: لا تستورد server.py، وتُربط بأسطر قليلة.
# قرار المالك: البائع يختار طريقة التواصل لكل إعلان: chat (محادثة فقط، الرقم مخفي) | phone (الرقم فقط) | both (الاثنان، الافتراضي حفاظًا على السلوك القائم).
#   بائع/مشترٍ:  POST /api/listings/<id>/contact-mode   {mode}                (صاحب الإعلان)
#                POST /api/listings/<id>/chat                                  (يفتح/يرجع محادثة المشتري مع البائع)
#                GET  /api/chats                                               (محادثاتي)
#                GET  /api/chats/<id>?after=<msg_id>                           (الرسائل؛ يعلّمها مقروءة)
#                POST /api/chats/<id>/messages {text}                          (إرسال)
#                POST /api/chats/<id>/block {block:true|false}                 (حظر/رفع حظر من طرف المحادثة)
#                POST /api/chats/<id>/images {data:base64, text?}              (صورة JPG/PNG في المحادثة؛ تُنظَّف من EXIF/GPS؛ تعليق اختياري)
#                GET  /api/chats/<id>/images/<msg_id>                          (الصورة لطرفي المحادثة فقط؛ private/no-store)
#                POST /api/chats/<id>/report {reason}                          (بلاغ للإدارة)
#   إدارة:       GET  /api/admin/chats/reports                                 (البلاغات المفتوحة)
#                GET  /api/admin/chats/<id>                                    (تُقرأ المحادثة فقط إن وُجد بلاغ عليها؛ كل اطلاع يُسجَّل في audit_log: chat.admin_view)
#                GET  /api/admin/chats/<id>/images/<msg_id>                    (صورة رسالة في محادثة عليها بلاغ؛ يُسجَّل: chat.admin_view_image)
#                POST /api/admin/chats/reports/<id>/resolve {status}
#   اعتراض:      GET /api/listings/<id>/contact يُرفض 403 إن كان وضع الإعلان chat؛ غير ذلك يمرّ لـ server.py كما كان (تسجيل دخول + حد ساعي).
# لا تُرجع هذه الوحدة أي رقم هاتف أبدًا. إضافة فقط: جداول chat_* وعمود listings.contact_mode.
import json, os, re, secrets, time
import market

push_hook = None   # server.py يضبطها: دالة(user_id) توقظ أجهزة المستلم (Web Push بلا بيانات؛ sw.js يسأل /api/push/state عن العدد)
_LAST_PUSH, PUSH_GAP = {}, 30   # أقل فاصل بالثواني بين إيقاظين لنفس المستلم في نفس المحادثة
MODES = ("chat", "phone", "both")
MAX_TEXT, PAGE, MAX_PER_MIN, MAX_NEW_THREADS_DAY = 1000, 100, 20, 30
MAX_IMAGES_DAY = 30   # أقصى عدد صور يرسلها المستخدم في 24 ساعة (عبر كل محادثاته)
UPLOADS = None        # server.py يضبطه: مجلد الرفع نفسه المستخدم لباقي الصور
SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_threads(id INTEGER PRIMARY KEY,
 listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
 buyer_id INTEGER NOT NULL REFERENCES users(id), seller_id INTEGER NOT NULL REFERENCES users(id),
 created_at INTEGER NOT NULL, last_message_at INTEGER NOT NULL DEFAULT 0,
 buyer_read_id INTEGER NOT NULL DEFAULT 0, seller_read_id INTEGER NOT NULL DEFAULT 0,
 blocked_by INTEGER REFERENCES users(id), UNIQUE(listing_id, buyer_id));
CREATE INDEX IF NOT EXISTS ix_chat_threads_buyer ON chat_threads(buyer_id, last_message_at);
CREATE INDEX IF NOT EXISTS ix_chat_threads_seller ON chat_threads(seller_id, last_message_at);
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY,
 thread_id INTEGER NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
 sender_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_chat_messages ON chat_messages(thread_id, id);
CREATE INDEX IF NOT EXISTS ix_chat_messages_sender ON chat_messages(sender_id, created_at);
CREATE TABLE IF NOT EXISTS chat_reports(id INTEGER PRIMARY KEY,
 thread_id INTEGER NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
 reporter_id INTEGER NOT NULL REFERENCES users(id), reason TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','resolved','dismissed')),
 handled_by INTEGER REFERENCES users(id), handled_at INTEGER, created_at INTEGER NOT NULL,
 UNIQUE(thread_id, reporter_id));
CREATE INDEX IF NOT EXISTS ix_chat_reports ON chat_reports(status, id);
"""


def install(c):
    """متكرر بأمان. يجب أن يُستدعى بعد market.migrate (جدول listings بمخططه الجديد)."""
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute("PRAGMA table_info(listings)")}
    if "contact_mode" not in cols:
        c.execute("ALTER TABLE listings ADD COLUMN contact_mode TEXT NOT NULL DEFAULT 'both' CHECK(contact_mode IN('chat','phone','both'))")
    mcols = {r[1] for r in c.execute("PRAGMA table_info(chat_messages)")}
    if "file_id" not in mcols:  # الخطوة 1: صورة اختيارية في الرسالة (الرسالة النصية القديمة file_id=NULL فلا تتأثر)
        c.execute("ALTER TABLE chat_messages ADD COLUMN file_id INTEGER REFERENCES files(id)")
    c.commit()


def unread_total(c, uid):
    """عدد الرسائل غير المقروءة للمستخدم عبر كل محادثاته (عدد فقط، لا محتوى) — يستعمله /api/push/state."""
    return c.execute("SELECT COUNT(*) FROM chat_messages m JOIN chat_threads t ON t.id=m.thread_id WHERE m.sender_id!=? AND "
                     "((t.buyer_id=? AND m.id>t.buyer_read_id) OR (t.seller_id=? AND m.id>t.seller_read_id))", (uid, uid, uid)).fetchone()[0]


def set_mode(c, listing_id, mode):
    if mode not in MODES: return False
    c.execute("UPDATE listings SET contact_mode=? WHERE id=?", (mode, listing_id)); return True


def _notify(c, to_user, thread_id, listing_title):
    """إشعار الجرس للطرف الآخر. إشعار واحد غير مقروء لكل محادثة. أي خطأ هنا لا يُفشل إرسال الرسالة."""
    try:
        c.execute("DELETE FROM notifications WHERE user_id=? AND ref_type='chat' AND ref_id=? AND read_at IS NULL", (to_user, thread_id))
        c.execute("INSERT INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (to_user, "chat", "رسالة جديدة في سوق لاقينو", "بخصوص: " + str(listing_title)[:60], "chat", "chat", thread_id, int(time.time())))
    except Exception as e:  # لا يُفشل الرسالة، لكن يُسجَّل للتشخيص
        import sys; sys.stderr.write("chat notify failed: %r\n" % (e,))


def _audit(c, actor, action, target, detail=None):
    """نفس صيغة server.audit (جدول audit_log) دون استيراد server.py."""
    c.execute("INSERT INTO audit_log(actor_id,action,target,detail,at) VALUES(?,?,?,?,?)", (actor, action, str(target), json.dumps(detail, ensure_ascii=False), int(time.time())))


def _finish_send(c, other, t, now):
    """بعد حفظ رسالة (نص أو صورة): إشعار الجرس ثم إيقاظ best-effort للمستلم. أي خطأ في الإيقاظ لا يُفشل الرسالة."""
    _notify(c, other, t["id"], t["listing_title"]); c.commit()
    if push_hook and now - _LAST_PUSH.get((other, t["id"]), 0) >= PUSH_GAP:
        if len(_LAST_PUSH) > 5000: _LAST_PUSH.clear()
        _LAST_PUSH[(other, t["id"])] = now
        try: push_hook(other)
        except Exception: pass


def _serve_image(h, c, tid, mid):
    """يرسل صورة رسالة محددة (يُستدعى بعد التحقق من الصلاحية). 404 إن لم توجد الرسالة أو الملف."""
    r = c.execute("SELECT f.path,f.mime FROM chat_messages m JOIN files f ON f.id=m.file_id WHERE m.id=? AND m.thread_id=?", (mid, tid)).fetchone()
    if not r or not UPLOADS: h.send(404, {"error": "غير موجود"}); return True
    try: raw = open(os.path.join(UPLOADS, r["path"]), "rb").read()
    except OSError: h.send(404, {"error": "غير موجود"}); return True
    h.send(200, None, r["mime"], raw, {"Cache-Control": "private, no-store"}); return True


def _thread_for(c, u, tid):
    """المحادثة إن كان المستخدم أحد طرفيها، وإلا None (يُعامَل كغير موجود)."""
    return c.execute("SELECT t.*,l.title listing_title,l.status listing_status,COALESCE(l.anonymous,0) listing_anonymous FROM chat_threads t JOIN listings l ON l.id=t.listing_id "
                     "WHERE t.id=? AND (t.buyer_id=? OR t.seller_id=?)", (tid, u["id"], u["id"])).fetchone()


def handle(h, c, u, method, path, q):
    """True إن عالج الطلب. الأخطاء تُرجَع مباشرة عبر h.send."""
    if not path.startswith(("/api/chats", "/api/admin/chats", "/api/listings/")): return False
    err = lambda code, msg: (h.send(code, {"error": msg}), True)[1]
    now = int(time.time())

    # ---------- اعتراض: رقم البائع مخفي إن اختار المحادثة فقط ----------
    m = re.fullmatch(r"/api/listings/(\d+)/contact", path)
    if m:
        if method != "GET" or not u: return False  # التسجيل والتحقق يبقيان في server.py
        r = c.execute("SELECT user_id,contact_mode FROM listings WHERE id=? AND status='approved'", (int(m[1]),)).fetchone()
        if r and r["user_id"] != u["id"] and r["contact_mode"] == "chat": return err(403, "البائع اختار التواصل عبر المحادثة داخل التطبيق")
        return False

    # ---------- اختيار البائع ----------
    m = re.fullmatch(r"/api/listings/(\d+)/contact-mode", path)
    if m:
        if method != "POST": return err(404, "غير موجود")
        if not u: return err(401, "سجّل الدخول أولًا")
        if not c.execute("SELECT 1 FROM listings WHERE id=? AND user_id=? AND status!='deleted'", (int(m[1]), u["id"])).fetchone(): return err(404, "غير موجود")
        mode = (h.body() or {}).get("mode")
        if not set_mode(c, int(m[1]), mode): return err(400, "طريقة التواصل غير صالحة")
        c.commit(); h.send(200, {"ok": True, "mode": mode}); return True

    # ---------- فتح محادثة (مشترٍ) ----------
    m = re.fullmatch(r"/api/listings/(\d+)/chat", path)
    if m:
        if method != "POST": return err(404, "غير موجود")
        if not u: return err(401, "سجّل الدخول أولًا")
        r = c.execute("SELECT id,user_id,category_id,contact_mode FROM listings WHERE id=? AND status='approved'", (int(m[1]),)).fetchone()
        if not r or not market.is_visible_category(c, r["category_id"]): return err(404, "غير موجود")
        if r["user_id"] == u["id"]: return err(400, "هذا إعلانك")
        if r["contact_mode"] == "phone": return err(403, "البائع لا يستقبل محادثات داخل التطبيق")
        t = c.execute("SELECT id FROM chat_threads WHERE listing_id=? AND buyer_id=?", (r["id"], u["id"])).fetchone()
        if not t:
            if c.execute("SELECT COUNT(*) FROM chat_threads WHERE buyer_id=? AND created_at>?", (u["id"], now - 86400)).fetchone()[0] >= MAX_NEW_THREADS_DAY:
                return err(429, "تجاوزت الحد اليومي لبدء المحادثات، حاول لاحقًا")
            cur = c.execute("INSERT INTO chat_threads(listing_id,buyer_id,seller_id,created_at,last_message_at) VALUES(?,?,?,?,?)", (r["id"], u["id"], r["user_id"], now, now))
            c.commit(); h.send(201, {"thread_id": cur.lastrowid}); return True
        h.send(200, {"thread_id": t["id"]}); return True

    # ---------- محادثاتي ----------
    if path == "/api/chats":
        if method != "GET": return err(404, "غير موجود")
        if not u: return err(401, "سجّل الدخول أولًا")
        out = []
        for t in c.execute("SELECT t.*,l.title listing_title,l.status listing_status,COALESCE(l.anonymous,0) listing_anonymous,ub.name buyer_name,us.name seller_name FROM chat_threads t "
                           "JOIN listings l ON l.id=t.listing_id JOIN users ub ON ub.id=t.buyer_id JOIN users us ON us.id=t.seller_id "
                           "WHERE t.buyer_id=? OR t.seller_id=? ORDER BY t.last_message_at DESC,t.id DESC LIMIT 100", (u["id"], u["id"])).fetchall():
            buyer = t["buyer_id"] == u["id"]; read = t["buyer_read_id"] if buyer else t["seller_read_id"]
            last = c.execute("SELECT body,created_at,sender_id,file_id FROM chat_messages WHERE thread_id=? ORDER BY id DESC LIMIT 1", (t["id"],)).fetchone()
            unread = c.execute("SELECT COUNT(*) FROM chat_messages WHERE thread_id=? AND id>? AND sender_id!=?", (t["id"], read, u["id"])).fetchone()[0]
            out.append({"id": t["id"], "listing_id": t["listing_id"], "listing_title": t["listing_title"], "listing_status": t["listing_status"],
                        "role": "buyer" if buyer else "seller", "other_name": ("مستخدم مجهول" if buyer and t["listing_anonymous"] else (t["seller_name"] if buyer else t["buyer_name"])) ,
                        "last": {"body": (last["body"] or "📷 صورة")[:80], "image": bool(last["file_id"]), "at": last["created_at"], "mine": last["sender_id"] == u["id"]} if last else None,
                        "unread": unread, "blocked": t["blocked_by"] is not None})
        h.send(200, out); return True

    # ---------- صور المحادثة ----------
    m = re.fullmatch(r"/api/chats/(\d+)/images", path)
    if m:
        if method != "POST": return err(404, "غير موجود")
        if not u: return err(401, "سجّل الدخول أولًا")
        t = _thread_for(c, u, int(m[1]))
        if not t: return err(404, "غير موجود")
        other = t["seller_id"] if t["buyer_id"] == u["id"] else t["buyer_id"]
        if t["blocked_by"] is not None: return err(403, "المحادثة موقوفة")
        if t["listing_status"] != "approved": return err(409, "الإعلان لم يعد متاحًا")
        if not UPLOADS: return err(503, "رفع الصور غير مفعّل")
        if c.execute("SELECT COUNT(*) FROM chat_messages WHERE sender_id=? AND created_at>?", (u["id"], now - 60)).fetchone()[0] >= MAX_PER_MIN:
            return err(429, "رسائل كثيرة، انتظر قليلًا")
        if c.execute("SELECT COUNT(*) FROM chat_messages WHERE sender_id=? AND file_id IS NOT NULL AND created_at>?", (u["id"], now - 86400)).fetchone()[0] >= MAX_IMAGES_DAY:
            return err(429, "وصلت للحد اليومي لإرسال الصور، حاول لاحقًا")
        raw, mime = h.read_image()  # يتحقق من الصيغة والحجم وينظّف EXIF/GPS (نفس مسار باقي الصور)
        cap = str((getattr(h, "last_body", None) or {}).get("text") or "").strip()
        if len(cap) > MAX_TEXT: return err(400, "التعليق حتى %d حرفًا" % MAX_TEXT)
        os.makedirs(UPLOADS, exist_ok=True); name = secrets.token_hex(16)
        with open(os.path.join(UPLOADS, name), "wb") as fh: fh.write(raw)
        fid = c.execute("INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)", (u["id"], name, mime, len(raw), now)).lastrowid
        cur = c.execute("INSERT INTO chat_messages(thread_id,sender_id,body,created_at,file_id) VALUES(?,?,?,?,?)", (t["id"], u["id"], cap, now, fid))
        c.execute("UPDATE chat_threads SET last_message_at=? WHERE id=?", (now, t["id"]))
        _finish_send(c, other, t, now)
        h.send(201, {"id": cur.lastrowid, "created_at": now, "image": True}); return True
    m = re.fullmatch(r"/api/chats/(\d+)/images/(\d+)", path)
    if m:
        if method != "GET": return err(404, "غير موجود")
        if not u: return err(401, "سجّل الدخول أولًا")
        t = _thread_for(c, u, int(m[1]))  # غير الطرفين => 404 (لا كشف لوجود المحادثة)
        if not t: return err(404, "غير موجود")
        return _serve_image(h, c, t["id"], int(m[2]))

    # ---------- محادثة بعينها ----------
    m = re.fullmatch(r"/api/chats/(\d+)(?:/(messages|block|report))?", path)
    if m:
        if not u: return err(401, "سجّل الدخول أولًا")
        t = _thread_for(c, u, int(m[1]))
        if not t: return err(404, "غير موجود")
        buyer = t["buyer_id"] == u["id"]; other = t["seller_id"] if buyer else t["buyer_id"]; sub = m[2]
        if sub is None:
            if method != "GET": return err(404, "غير موجود")
            try: after = max(0, int((q.get("after", ["0"])[0] or 0)))
            except (TypeError, ValueError): after = 0
            msgs = [{"id": x["id"], "mine": x["sender_id"] == u["id"], "body": x["body"], "created_at": x["created_at"], "image": bool(x["file_id"])}
                    for x in c.execute("SELECT id,sender_id,body,created_at,file_id FROM chat_messages WHERE thread_id=? AND id>? ORDER BY id LIMIT ?", (t["id"], after, PAGE))]
            if msgs:
                col = "buyer_read_id" if buyer else "seller_read_id"
                c.execute("UPDATE chat_threads SET %s=MAX(%s,?) WHERE id=?" % (col, col), (msgs[-1]["id"], t["id"])); c.commit()
            on = c.execute("SELECT name FROM users WHERE id=?", (other,)).fetchone()
            other_name = ("مستخدم مجهول" if buyer and t["listing_anonymous"] else (on["name"] if on else ""))
            h.send(200, {"thread": {"id": t["id"], "listing_id": t["listing_id"], "listing_title": t["listing_title"], "listing_status": t["listing_status"],
                                    "role": "buyer" if buyer else "seller", "other_name": other_name,
                                    "anonymous_seller": bool(t["listing_anonymous"]), "blocked": t["blocked_by"] is not None,
                                    "blocked_by_me": t["blocked_by"] == u["id"]}, "messages": msgs}); return True
        if method != "POST": return err(404, "غير موجود")
        if sub == "messages":
            if t["blocked_by"] is not None: return err(403, "المحادثة موقوفة")
            if t["listing_status"] != "approved": return err(409, "الإعلان لم يعد متاحًا")
            text = str((h.body() or {}).get("text") or "").strip()
            if not 1 <= len(text) <= MAX_TEXT: return err(400, "الرسالة من 1 إلى %d حرفًا" % MAX_TEXT)
            if c.execute("SELECT COUNT(*) FROM chat_messages WHERE sender_id=? AND created_at>?", (u["id"], now - 60)).fetchone()[0] >= MAX_PER_MIN:
                return err(429, "رسائل كثيرة، انتظر قليلًا")
            cur = c.execute("INSERT INTO chat_messages(thread_id,sender_id,body,created_at) VALUES(?,?,?,?)", (t["id"], u["id"], text, now))
            c.execute("UPDATE chat_threads SET last_message_at=? WHERE id=?", (now, t["id"]))  # علامة القراءة تتحدّث عند فتح المحادثة فقط (لا عند الإرسال) كي لا تُعلَّم رسائل لم تُشاهد
            _finish_send(c, other, t, now)
            h.send(201, {"id": cur.lastrowid, "created_at": now}); return True
        if sub == "block":
            want = bool((h.body() or {}).get("block", True))
            if want:
                if t["blocked_by"] is None: c.execute("UPDATE chat_threads SET blocked_by=? WHERE id=?", (u["id"], t["id"]))
            elif t["blocked_by"] == u["id"]: c.execute("UPDATE chat_threads SET blocked_by=NULL WHERE id=?", (t["id"],))
            elif t["blocked_by"] is not None: return err(403, "الحظر من الطرف الآخر")
            c.commit(); h.send(200, {"ok": True, "blocked": c.execute("SELECT blocked_by FROM chat_threads WHERE id=?", (t["id"],)).fetchone()[0] is not None}); return True
        if sub == "report":
            reason = str((h.body() or {}).get("reason") or "").strip()
            if not 3 <= len(reason) <= 300: return err(400, "سبب البلاغ من 3 إلى 300 حرف")
            c.execute("INSERT OR IGNORE INTO chat_reports(thread_id,reporter_id,reason,created_at) VALUES(?,?,?,?)", (t["id"], u["id"], reason, now)); c.commit()
            h.send(200, {"ok": True}); return True

    # ---------- إدارة ----------
    if path.startswith("/api/admin/chats"):
        if not u: return err(401, "سجّل الدخول أولًا")
        if u["role"] not in ("admin", "staff"): return err(403, "غير مسموح")
        if path == "/api/admin/chats/reports" and method == "GET":
            rows = c.execute("SELECT r.id,r.thread_id,r.reason,r.created_at,l.title listing_title,rp.name reporter FROM chat_reports r JOIN chat_threads t ON t.id=r.thread_id "
                             "JOIN listings l ON l.id=t.listing_id JOIN users rp ON rp.id=r.reporter_id WHERE r.status='open' ORDER BY r.id DESC LIMIT 200").fetchall()
            h.send(200, [dict(x) for x in rows]); return True
        m = re.fullmatch(r"/api/admin/chats/(\d+)/images/(\d+)", path)
        if m and method == "GET":  # صورة رسالة: فقط في محادثة عليها بلاغ، ويُسجَّل الاطلاع
            if not c.execute("SELECT 1 FROM chat_reports WHERE thread_id=?", (int(m[1]),)).fetchone(): return err(404, "غير موجود")
            _audit(c, u["id"], "chat.admin_view_image", m[1], {"message_id": int(m[2])}); c.commit()
            return _serve_image(h, c, int(m[1]), int(m[2]))
        m = re.fullmatch(r"/api/admin/chats/(\d+)", path)
        if m and method == "GET":  # لا تُقرأ محادثة إلا إن وُجد بلاغ عليها
            if not c.execute("SELECT 1 FROM chat_reports WHERE thread_id=?", (int(m[1]),)).fetchone(): return err(404, "غير موجود")
            t = c.execute("SELECT t.id,t.listing_id,t.buyer_id,t.seller_id,ub.name buyer,us.name seller FROM chat_threads t JOIN users ub ON ub.id=t.buyer_id JOIN users us ON us.id=t.seller_id WHERE t.id=?", (int(m[1]),)).fetchone()
            if not t: return err(404, "غير موجود")
            msgs = [{"id": x["id"], "from": "buyer" if x["sender_id"] == t["buyer_id"] else "seller", "body": x["body"], "created_at": x["created_at"], "image": bool(x["file_id"])}
                    for x in c.execute("SELECT id,sender_id,body,created_at,file_id FROM chat_messages WHERE thread_id=? ORDER BY id LIMIT 500", (t["id"],))]
            _audit(c, u["id"], "chat.admin_view", t["id"], {"messages": len(msgs)}); c.commit()  # كل اطلاع إداري على محادثة يُسجَّل
            h.send(200, {"thread_id": t["id"], "listing_id": t["listing_id"], "buyer": t["buyer"], "seller": t["seller"], "messages": msgs}); return True
        m = re.fullmatch(r"/api/admin/chats/reports/(\d+)/resolve", path)
        if m and method == "POST":
            st = (h.body() or {}).get("status")
            if st not in ("resolved", "dismissed"): return err(400, "حالة غير صالحة")
            n = c.execute("UPDATE chat_reports SET status=?,handled_by=?,handled_at=? WHERE id=? AND status='open'", (st, u["id"], now, int(m[1]))).rowcount; c.commit()
            if not n: return err(404, "غير موجود")
            h.send(200, {"ok": True}); return True
        return err(404, "غير موجود")
    return False
