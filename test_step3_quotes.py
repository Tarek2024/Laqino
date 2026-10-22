# الخطوة 3: عروض أسعار الخدمات (توزيع، عرض المقدم، اعتماد الإدارة، اختيار العميل، تأكيد المقدم) + النزاع + ترحيل قاعدة الخطوة 2. قاعدة ورفع مؤقتان.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3
_DB = tempfile.mktemp(suffix=".db"); _UP = tempfile.mkdtemp()
os.environ["LAQINO_DB"] = _DB; os.environ["LAQINO_UPLOADS"] = _UP
import server, svc
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(.3)
BASE = "http://127.0.0.1:%d" % PORT; DB = _DB
def call(m, p, d=None, t=None):
    r = urllib.request.Request(BASE + "/api" + p, json.dumps(d).encode() if d is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + t} if t else {})}, method=m)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
def user(ph):
    call("POST", "/register", {"phone": ph, "name": "u" + ph[-2:], "password": "password1"}); return call("POST", "/login", {"phone": ph, "password": "password1"})[1]["token"]
def sql(q, a=()):
    c = sqlite3.connect(DB); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
at = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})[1]["token"]
C1, C2, C3, C4, PA, PB, PC, OT, PD = [user("0107770000%d" % i) for i in range(1, 10)]
rid = 3
tid = call("POST", "/admin/service-types", {"name_ar": "سباكة"}, at)[1]["id"]
def prov(name, r=rid, owner=None, pub=True):
    p = call("POST", "/admin/services", {"name_ar": name, "type_id": tid, "region_id": r, "description": "x", "address": "a", "phone": "01099990000", "whatsapp": ""}, at)[1]["id"]
    if pub: call("POST", f"/admin/services/{p}/publish", {"published": True}, at)
    if owner: call("POST", "/admin/service-owners", {"provider_id": p, "phone": owner}, at)
    return p
pa, pb, pc = prov("المعلم أ", owner="01077700005"), prov("المعلم ب", owner="01077700006"), prov("المعلم ج", owner="01077700007")
pd = None  # يُنشأ لاحقًا لاختبار فك الربط
pn = prov("بلا حساب")  # منشور بلا مالك: لا يُدعى
body = {"type_id": tid, "region_id": rid, "description": "محتاج سباك لإصلاح تسريب في الحمام"}
def mk(tok, **x):
    s, r = call("POST", "/service-requests", {**body, **x}, tok); assert s == 201, (s, r); return r["id"]
def st(rq, tok): return call("GET", f"/service-requests/{rq}", None, tok)[1]["status"]
def jobs(tok): return call("GET", "/my/service-jobs", None, tok)[1]["jobs"]

# ---------- المخطط
ok("quote tables exist", sql("select count(*) from sqlite_master where name in('service_quotes','service_request_invites')")[0][0] == 2)
ok("dispute columns exist", {"dispute_reason", "disputed_by", "disputed_at"} <= {r[1] for r in sql("PRAGMA table_info(service_requests)")})
ok("NEXT: disputed resolves to done/cancelled", svc.NEXT["disputed"] == ("done", "cancelled"))
ok("NEXT only points at valid statuses", all(t in svc.STATUSES for v in svc.NEXT.values() for t in v))

# ---------- طلب عروض أسعار
R1 = mk(C1)
d = call("GET", f"/service-requests/{R1}", None, C1)[1]
ok("open request offers quote providers (accounts only)", d["can_request_quotes"] and {p["id"] for p in d["quote_providers"]} == {pa, pb, pc})
ok("no phone leaks in detail", "phone" not in json.dumps(d))
ok("quotes list is empty before any quote", call("GET", f"/service-requests/{R1}/quotes", None, C1)[1]["quotes"] == [])
ok("stranger cannot request quotes -> 404", call("POST", f"/service-requests/{R1}/request-quotes", {}, OT)[0] == 404)
ok("unknown provider id rejected", call("POST", f"/service-requests/{R1}/request-quotes", {"provider_ids": [pn]}, C1)[0] == 400)
ok("empty provider list rejected", call("POST", f"/service-requests/{R1}/request-quotes", {"provider_ids": []}, C1)[0] == 400)
ok("bool provider ids rejected", call("POST", f"/service-requests/{R1}/request-quotes", {"provider_ids": [True]}, C1)[0] == 400)
s, r = call("POST", f"/service-requests/{R1}/request-quotes", {"provider_ids": [pa, pb]}, C1)
ok("request quotes from 2 providers -> awaiting_quotes", s == 200 and r["status"] == "awaiting_quotes" and r["invited"] == 2 and st(R1, C1) == "awaiting_quotes")
ok("cannot request twice", call("POST", f"/service-requests/{R1}/request-quotes", {}, C1)[0] == 409)
ok("invite notifies invited owners only", sql("select count(*) from notifications where kind='service_request.invite' and ref_id=?", (R1,))[0][0] == 2)
ok("history has awaiting_quotes", any(h["to"] == "awaiting_quotes" for h in call("GET", f"/service-requests/{R1}", None, C1)[1]["history"]))

# ---------- ما يراه المقدمون
ja = [j for j in jobs(PA) if j["id"] == R1]
ok("invited provider sees the request in quote mode", ja and ja[0]["quote_mode"] and ja[0]["my_quote"] is None)
ok("non-invited provider does not see it", not [j for j in jobs(PC) if j["id"] == R1])
ok("direct accept blocked in quote mode -> 409", call("POST", f"/my/service-jobs/{R1}/accept", {}, PA)[0] == 409)
ok("non-invited cannot quote -> 403", call("POST", f"/my/service-jobs/{R1}/quote", {"price": 100}, PC)[0] == 403)
ok("customer cannot quote own request", call("POST", f"/my/service-jobs/{R1}/quote", {"price": 100}, C1)[0] == 403)
for name, b in (("no price", {}), ("zero", {"price": 0}), ("negative", {"price": -5}), ("text", {"price": "كتير"}), ("bool", {"price": True}), ("huge", {"price": 10 ** 9}),
                ("long note", {"price": 100, "note": "ع" * 301}), ("phone in note", {"price": 100, "note": "كلمني على 01012345678"}),
                ("arabic digits phone", {"price": 100, "note": "٠١٠١٢٣٤٥٦٧٨"}), ("spaced phone", {"price": 100, "note": "0101 234 5678"})):
    ok("quote rejects " + name, call("POST", f"/my/service-jobs/{R1}/quote", b, PA)[0] == 400)
ok("short numbers in note are fine", call("POST", f"/my/service-jobs/{R1}/quote", {"price": 250, "note": "خلال 3 ساعات، ضمان 6 شهور"}, PA)[0] == 200)
q = [j for j in jobs(PA) if j["id"] == R1][0]["my_quote"]
ok("my_quote is pending with the price", q["status"] == "pending" and q["price"] == 250)
QA = q["id"]
ok("request stays awaiting_quotes while quote is pending", st(R1, C1) == "awaiting_quotes")
ok("customer sees no pending quote", call("GET", f"/service-requests/{R1}/quotes", None, C1)[1]["quotes"] == [])
ok("customer cannot select a pending quote -> 404", call("POST", f"/service-requests/{R1}/select", {"quote_id": QA}, C1)[0] == 404)
ok("admin notified of pending quote", sql("select count(*) from notifications where kind='service_quote.pending'")[0][0] >= 1)
s, r = call("POST", f"/my/service-jobs/{R1}/quote", {"price": 220}, PA); ok("provider edits own pending quote", s == 200 and r["quote"]["price"] == 220 and r["quote"]["id"] == QA)
ok("still one quote row per provider", sql("select count(*) from service_quotes where request_id=?", (R1,))[0][0] == 1)
QB = call("POST", f"/my/service-jobs/{R1}/quote", {"price": 300, "note": "شامل الخامات"}, PB)[1]["quote"]["id"]

# ---------- اعتماد الإدارة
ok("customer cannot use admin quotes API", call("GET", "/admin/service-quotes", None, C1)[0] == 403)
ok("provider cannot approve", call("POST", f"/admin/service-quotes/{QA}", {"action": "approve"}, PA)[0] == 403)
l = call("GET", "/admin/service-quotes", None, at)[1]
ok("admin lists pending quotes with context", {x["id"] for x in l} >= {QA, QB} and all(x["request_id"] == R1 for x in l if x["id"] in (QA, QB)) and any(x["provider_name"] == "المعلم أ" for x in l))
ok("bad filter rejected", call("GET", "/admin/service-quotes?status=zzz", None, at)[0] == 400)
ok("bad action rejected", call("POST", f"/admin/service-quotes/{QA}", {"action": "x"}, at)[0] == 400)
ok("reject needs a reason", call("POST", f"/admin/service-quotes/{QB}", {"action": "reject"}, at)[0] == 400)
ok("approve quote A", call("POST", f"/admin/service-quotes/{QA}", {"action": "approve"}, at)[1]["status"] == "approved")
ok("request moves to quotes_received", st(R1, C1) == "quotes_received")
ok("customer notified of the quote", sql("select count(*) from notifications where kind='service_quote.received' and ref_id=?", (R1,))[0][0] == 1)
ok("cannot approve twice -> 409", call("POST", f"/admin/service-quotes/{QA}", {"action": "approve"}, at)[0] == 409)
cq = call("GET", f"/service-requests/{R1}/quotes", None, C1)[1]
ok("customer sees only the approved quote, no phone", [x["id"] for x in cq["quotes"]] == [QA] and cq["can_select"] and "phone" not in json.dumps(cq) and cq["quotes"][0]["price"] == 220 and cq["invited_count"] == 2)
ok("other customer cannot read quotes -> 404", call("GET", f"/service-requests/{R1}/quotes", None, C2)[0] == 404)
ok("reject quote B with reason", call("POST", f"/admin/service-quotes/{QB}", {"action": "reject", "note": "السعر غير واضح"}, at)[1]["status"] == "rejected")
ok("provider B sees rejection reason", [j for j in jobs(PB) if j["id"] == R1][0]["my_quote"]["admin_note"] == "السعر غير واضح")
ok("provider B resubmits -> pending again", call("POST", f"/my/service-jobs/{R1}/quote", {"price": 280}, PB)[1]["quote"]["status"] == "pending")
ok("approve B", call("POST", f"/admin/service-quotes/{QB}", {"action": "approve"}, at)[0] == 200)
ok("customer sees both sorted by price", [x["price"] for x in call("GET", f"/service-requests/{R1}/quotes", None, C1)[1]["quotes"]] == [220, 280])
ok("editing an approved quote sends it back to approval", call("POST", f"/my/service-jobs/{R1}/quote", {"price": 270}, PB)[1]["quote"]["status"] == "pending")
ok("customer no longer sees the edited quote", [x["id"] for x in call("GET", f"/service-requests/{R1}/quotes", None, C1)[1]["quotes"]] == [QA])
call("POST", f"/admin/service-quotes/{QB}", {"action": "approve"}, at)

# ---------- اختيار العميل
ok("select needs quote_id", call("POST", f"/service-requests/{R1}/select", {}, C1)[0] == 400)
ok("other customer cannot select -> 404", call("POST", f"/service-requests/{R1}/select", {"quote_id": QA}, C2)[0] == 404)
s, r = call("POST", f"/service-requests/{R1}/select", {"quote_id": QA}, C1)
ok("customer selects quote A -> provider_selected", s == 200 and st(R1, C1) == "provider_selected" and r["provider_name"] == "المعلم أ")
d = call("GET", f"/service-requests/{R1}", None, C1)[1]
ok("detail shows selected provider but not 'accepted_by'", d["selected_provider"] == "المعلم أ" and d["accepted_by"] is None)
ok("cannot select again -> 409", call("POST", f"/service-requests/{R1}/select", {"quote_id": QB}, C1)[0] == 409)
ja = [j for j in jobs(PA) if j["id"] == R1][0]
ok("selected provider sees it pending confirmation, no customer data", ja["selected"] and ja["status"] == "provider_selected" and "customer_phone" not in ja and "address" not in ja and "images" not in ja)
ok("selected notification sent", sql("select count(*) from notifications where kind='service_quote.selected'")[0][0] == 1)
ok("provider B cannot accept the selection -> 409", call("POST", f"/my/service-jobs/{R1}/accept", {}, PB)[0] == 409)
ok("provider cannot progress before confirming -> 409", call("POST", f"/my/service-jobs/{R1}/progress", {"status": "on_the_way"}, PA)[0] == 409)
ok("provider cannot withdraw once selected -> 409", call("POST", f"/my/service-jobs/{R1}/withdraw", {}, PA)[0] == 409)
ok("provider cannot see customer images before confirming", call("POST", f"/my/service-jobs/{R1}/progress", {"status": "done"}, PA)[0] == 409)

# ---------- اعتذار المختار ثم اختيار آخر
s, r = call("POST", f"/my/service-jobs/{R1}/release", {}, PA)
ok("selected provider declines -> back to quotes_received", s == 200 and r["status"] == "quotes_received" and st(R1, C1) == "quotes_received")
ok("declined quote is withdrawn", sql("select status from service_quotes where id=?", (QA,))[0][0] == "withdrawn")
ok("customer notified of decline", sql("select count(*) from notifications where kind='service_request.select_declined'")[0][0] == 1)
ok("customer sees only quote B now", [x["id"] for x in call("GET", f"/service-requests/{R1}/quotes", None, C1)[1]["quotes"]] == [QB])
ok("provider A can quote again after decline? no: withdrawn can resubmit", call("POST", f"/my/service-jobs/{R1}/quote", {"price": 200}, PA)[0] == 200)
call("POST", f"/admin/service-quotes/{QA}", {"action": "approve"}, at)
ok("select B", call("POST", f"/service-requests/{R1}/select", {"quote_id": QB}, C1)[0] == 200)
s, r = call("POST", f"/my/service-jobs/{R1}/accept", {}, PB)
ok("provider B confirms -> accepted + customer data revealed", s == 200 and r["status"] == "accepted" and r["customer_phone"] == "01077700001")
ok("request accepted_by B", call("GET", f"/service-requests/{R1}", None, C1)[1]["accepted_by"] == "المعلم ب")
ok("other quotes become not_selected", sql("select status from service_quotes where id=?", (QA,))[0][0] == "not_selected")
ok("losing provider notified", sql("select count(*) from notifications where kind='service_quote.not_selected'")[0][0] == 1)
ok("losing provider cannot edit quote -> 409", call("POST", f"/my/service-jobs/{R1}/quote", {"price": 1}, PA)[0] == 409)
ok("flow continues: on_the_way", call("POST", f"/my/service-jobs/{R1}/progress", {"status": "on_the_way"}, PB)[0] == 200)
ok("history records the whole quote path", [h["to"] for h in call("GET", f"/service-requests/{R1}", None, C1)[1]["history"]][:4] == ["open", "awaiting_quotes", "quotes_received", "provider_selected"])

# ---------- سحب العرض + مسار القبول المباشر ما زال يعمل
R2 = mk(C2); call("POST", f"/service-requests/{R2}/request-quotes", {}, C2)
ok("request without provider_ids invites all eligible", sql("select count(*) from service_request_invites where request_id=?", (R2,))[0][0] == 3)
Q2 = call("POST", f"/my/service-jobs/{R2}/quote", {"price": 90}, PC)[1]["quote"]["id"]
call("POST", f"/admin/service-quotes/{Q2}", {"action": "approve"}, at)
ok("quotes_received after approval", st(R2, C2) == "quotes_received")
ok("withdraw approved quote", call("POST", f"/my/service-jobs/{R2}/withdraw", {}, PC)[0] == 200)
ok("request falls back to awaiting_quotes", st(R2, C2) == "awaiting_quotes")
ok("withdraw without a quote -> 404", call("POST", f"/my/service-jobs/{R2}/withdraw", {}, PA)[0] == 404)
R3 = mk(C3)
ok("legacy direct accept still works on open", call("POST", f"/my/service-jobs/{R3}/accept", {}, PC)[1].get("status") == "accepted")
ok("no quote request after acceptance", call("POST", f"/service-requests/{R3}/request-quotes", {}, C3)[0] == 409)

# ---------- ما لا يوجد له مقدمون + العميل لا يطلب عروضًا لنفسه
other_tid = call("POST", "/admin/service-types", {"name_ar": "نجارة"}, at)[1]["id"]
s, r = call("POST", "/service-requests", {**body, "type_id": other_tid}, C4); R4 = r["id"]
ok("no eligible providers -> can_request_quotes false", call("GET", f"/service-requests/{R4}", None, C4)[1]["can_request_quotes"] is False)
ok("request quotes with nobody eligible -> 409", call("POST", f"/service-requests/{R4}/request-quotes", {}, C4)[0] == 409)
ok("provider's own account is excluded from invites", [p["id"] for p in call("GET", f"/service-requests/{mk(PA)}", None, PA)[1]["quote_providers"]] == [pb, pc])

# ---------- انتهاء مهلة تأكيد المقدم المختار
R5 = mk(C4); call("POST", f"/service-requests/{R5}/request-quotes", {"provider_ids": [pa]}, C4)
Q5 = call("POST", f"/my/service-jobs/{R5}/quote", {"price": 150}, PA)[1]["quote"]["id"]
call("POST", f"/admin/service-quotes/{Q5}", {"action": "approve"}, at); call("POST", f"/service-requests/{R5}/select", {"quote_id": Q5}, C4)
ok("selected awaiting confirmation", st(R5, C4) == "provider_selected")
sql("update service_quotes set selected_at=? where id=?", (int(time.time()) - 3 * 86400, Q5))
ok("selection lapses after the TTL -> back to awaiting_quotes", st(R5, C4) == "awaiting_quotes")
ok("lapsed quote is withdrawn", sql("select status from service_quotes where id=?", (Q5,))[0][0] == "withdrawn")
ok("customer told the provider did not confirm", sql("select count(*) from notifications where kind='service_request.select_lapsed' and ref_id=?", (R5,))[0][0] == 1)
ok("customer can cancel at awaiting_quotes", call("POST", f"/service-requests/{R5}/cancel", {}, C4)[0] == 200)
ok("cannot select on a cancelled request -> 409", call("POST", f"/service-requests/{R5}/select", {"quote_id": Q5}, C4)[0] == 409)
ok("expiry also covers quote stages", (sql("update service_requests set created_at=? where id=?", (int(time.time()) - 15 * 86400, R2)), st(R2, C2))[1] == "expired")

# ---------- فك ربط مقدم مختار لم يؤكد
pd = prov("المعلم د", owner="01077700009")
R6 = mk(C4); call("POST", f"/service-requests/{R6}/request-quotes", {"provider_ids": [pd]}, C4)
Q6 = call("POST", f"/my/service-jobs/{R6}/quote", {"price": 120}, PD)[1]["quote"]["id"]
call("POST", f"/admin/service-quotes/{Q6}", {"action": "approve"}, at); call("POST", f"/service-requests/{R6}/select", {"quote_id": Q6}, C4)
call("POST", "/admin/service-owners", {"provider_id": pd, "phone": ""}, at)
ok("unlinking a selected provider reopens quoting", st(R6, C4) == "awaiting_quotes" and sql("select status from service_quotes where id=?", (Q6,))[0][0] == "withdrawn")
call("POST", f"/service-requests/{R6}/cancel", {}, C4)

# ---------- النزاع
R7 = R1  # عند المقدم ب، حالته on_the_way
ok("dispute needs a reason", call("POST", f"/service-requests/{R7}/dispute", {"reason": "قصير"}, C1)[0] == 400)
ok("stranger cannot dispute -> 404", call("POST", f"/service-requests/{R7}/dispute", {"reason": "سبب كافٍ للنزاع هنا"}, OT)[0] == 404)
ok("other provider cannot dispute -> 404", call("POST", f"/my/service-jobs/{R7}/dispute", {"reason": "سبب كافٍ للنزاع هنا"}, PA)[0] == 404)
ok("can_dispute true while assigned", call("GET", f"/service-requests/{R7}", None, C1)[1]["can_dispute"] is True)
s, r = call("POST", f"/service-requests/{R7}/dispute", {"reason": "المقدم طلب مبلغًا أكبر من العرض"}, C1)
ok("customer opens a dispute -> disputed", s == 200 and st(R7, C1) == "disputed")
d = call("GET", f"/service-requests/{R7}", None, C1)[1]
ok("customer sees own dispute reason", d["disputed_by"] == "customer" and d["dispute_reason"] == "المقدم طلب مبلغًا أكبر من العرض" and d["can_dispute"] is False)
ok("provider sees dispute without the customer's reason", [j for j in jobs(PB) if j["id"] == R7][0]["dispute_reason"] is None)
ok("second dispute -> 409", call("POST", f"/my/service-jobs/{R7}/dispute", {"reason": "سبب كافٍ للنزاع هنا"}, PB)[0] == 409)
ok("admin and provider notified", sql("select count(*) from notifications where kind='service_request.disputed' and ref_id=?", (R7,))[0][0] >= 2)
ok("disputed request cannot be cancelled by the customer", call("POST", f"/service-requests/{R7}/cancel", {}, C1)[0] == 409)
ok("provider cannot progress a disputed job", call("POST", f"/my/service-jobs/{R7}/progress", {"status": "done"}, PB)[0] == 409)
ad = [x for x in call("GET", "/admin/service-requests?status=disputed", None, at)[1] if x["id"] == R7][0]
ok("admin list shows reason and who disputed", ad["dispute_reason"] and ad["disputed_by"] == "customer")
ok("admin resolve needs a note", call("POST", f"/admin/service-requests/{R7}", {"status": "done"}, at)[0] == 400)
ok("admin cannot resolve to in_progress", call("POST", f"/admin/service-requests/{R7}", {"status": "in_progress", "note": "ملاحظة كافية"}, at)[0] == 400)
ok("non-admin cannot resolve", call("POST", f"/admin/service-requests/{R7}", {"status": "done", "note": "ملاحظة كافية"}, C1)[0] == 403)
ok("admin resolves dispute -> done", call("POST", f"/admin/service-requests/{R7}", {"status": "done", "note": "تم الاتفاق على السعر"}, at)[0] == 200 and st(R7, C1) == "done")
ok("resolution notified provider", sql("select count(*) from notifications where kind='service_request.dispute_resolved'")[0][0] == 1)
ok("resolved request can be rated", call("GET", f"/service-requests/{R7}", None, C1)[1]["can_rate"] is True)
ok("no second dispute after resolution -> 409", call("POST", f"/service-requests/{R7}/dispute", {"reason": "سبب كافٍ للنزاع هنا"}, C1)[0] == 409)

# نزاع المقدم على طلب منجز + نافذة النزاع
R8 = mk(C2); call("POST", f"/my/service-jobs/{R8}/accept", {}, PA); call("POST", f"/my/service-jobs/{R8}/progress", {"status": "done"}, PA)
ok("provider disputes a done job within the window", call("POST", f"/my/service-jobs/{R8}/dispute", {"reason": "العميل رفض الدفع بعد الإنجاز"}, PA)[0] == 200 and st(R8, C2) == "disputed")
ok("customer sees who disputed but not the provider's reason", (lambda d: d["disputed_by"] == "provider" and d["dispute_reason"] is None)(call("GET", f"/service-requests/{R8}", None, C2)[1]))
ok("admin resolves to cancelled sets cancelled_by admin", call("POST", f"/admin/service-requests/{R8}", {"status": "cancelled", "note": "لا إنجاز فعلي"}, at)[0] == 200 and sql("select cancelled_by from service_requests where id=?", (R8,))[0][0] == "admin")
R9 = mk(C3); call("POST", f"/my/service-jobs/{R9}/accept", {}, PA); call("POST", f"/my/service-jobs/{R9}/progress", {"status": "done"}, PA)
sql("update service_requests set updated_at=? where id=?", (int(time.time()) - 8 * 86400, R9))
ok("done older than the window -> cannot dispute", call("POST", f"/service-requests/{R9}/dispute", {"reason": "سبب كافٍ للنزاع هنا"}, C3)[0] == 409 and call("GET", f"/service-requests/{R9}", None, C3)[1]["can_dispute"] is False)
R10 = mk(C3)
ok("open request cannot be disputed", call("POST", f"/service-requests/{R10}/dispute", {"reason": "سبب كافٍ للنزاع هنا"}, C3)[0] == 409)

# ---------- ترحيل قاعدة الخطوة 2 (بلا الجداول والأعمدة الجديدة)
import sqlite3 as _s
old = tempfile.mktemp(suffix=".db"); oc = _s.connect(old); oc.row_factory = _s.Row
oc.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY);CREATE TABLE service_types(id INTEGER PRIMARY KEY);CREATE TABLE regions(id INTEGER PRIMARY KEY);CREATE TABLE files(id INTEGER PRIMARY KEY);"
                 "CREATE TABLE service_providers(id INTEGER PRIMARY KEY, owner_user_id INTEGER);INSERT INTO users VALUES(1);INSERT INTO service_types VALUES(1);INSERT INTO regions VALUES(1);")
oc.executescript("CREATE TABLE service_requests(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, type_id INTEGER NOT NULL, region_id INTEGER NOT NULL, description TEXT NOT NULL,"
                 "status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','accepted','on_the_way','in_progress','done','cancelled','expired','awaiting_quotes','quotes_received','provider_selected','disputed')),"
                 "admin_note TEXT, handled_by INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, provider_id INTEGER, accepted_at INTEGER, address TEXT, preferred_at INTEGER, budget_min INTEGER, budget_max INTEGER, cancelled_by TEXT);"
                 "INSERT INTO service_requests(user_id,type_id,region_id,description,status,created_at,updated_at) VALUES(1,1,1,'x','accepted',1,1);")
svc.install(oc); svc.install(oc)
ok("step-2 database gains dispute columns without losing rows", {"dispute_reason", "disputed_by", "disputed_at"} <= {r[1] for r in oc.execute("PRAGMA table_info(service_requests)")} and oc.execute("select count(*) from service_requests").fetchone()[0] == 1)
ok("step-2 database gains quote tables", oc.execute("select count(*) from sqlite_master where name in('service_quotes','service_request_invites')").fetchone()[0] == 2)
print("ALL OK")
