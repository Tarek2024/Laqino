"""Homepage campaign API, authorization, scheduling, and additive-schema regression tests."""
import os, tempfile, threading, time, json, urllib.request, urllib.error, datetime, sqlite3
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer

server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d/api" % srv.server_address[1]

def call(method, path, data=None, token=None):
    req = urllib.request.Request(BASE + path, json.dumps(data).encode() if data is not None else None,
        {"Content-Type":"application/json", **({"Authorization":"Bearer "+token} if token else {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")

def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition: raise AssertionError(name)

def login(phone, password):
    st, data = call("POST", "/login", {"phone":phone,"password":password})
    check("login " + phone, st == 200 and bool(data.get("token")))
    return data["token"]

admin = login("01000000000", "AdminPass123")
call("POST", "/register", {"phone":"01011112222","name":"عميل اختبار","password":"password1"})
customer = login("01011112222", "password1")

# Schema is additive and indexed; existing homepage section settings remain available.
with sqlite3.connect(os.environ["LAQINO_DB"]) as db:
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
check("campaign table and active index created", "home_campaigns" in tables and "ix_home_campaigns_active" in indexes)
st, sections = call("GET", "/home-sections")
check("existing four homepage sections still available", st == 200 and {x["key"] for x in sections} == {"med","souq","svc","dlv"})

check("anonymous cannot read admin campaign manager", call("GET", "/admin/home-campaigns")[0] == 401)
check("customer cannot read admin campaign manager", call("GET", "/admin/home-campaigns", token=customer)[0] == 403)
check("customer cannot create homepage campaign", call("POST", "/admin/home-campaigns", {"title":"محاولة","destination_type":"home","is_active":True}, customer)[0] == 403)

today = server.home_campaign_today()
check("campaign date uses the Cairo timezone database", today == datetime.datetime.now(server.ZoneInfo("Africa/Cairo")).date())
tomorrow = (today + datetime.timedelta(days=1)).isoformat()
yesterday = (today - datetime.timedelta(days=1)).isoformat()
base = {"title":"حملة اختبار","description":"وصف مختصر","destination_type":"market","destination_value":"","sort_order":2,"is_active":True}
st, created = call("POST", "/admin/home-campaigns", base, admin)
check("admin creates a campaign", st == 201 and created.get("ok") and created.get("id"))
cid = created["id"]
st, public = call("GET", "/home-campaigns")
check("active campaign appears in public feed", st == 200 and any(x["id"] == cid and x["title"] == "حملة اختبار" and x["href"] == "/market.html" for x in public))

# Schedule boundaries are enforced by the public feed, not by customer submissions.
st, future = call("POST", "/admin/home-campaigns", {**base,"title":"حملة مجدولة","start_date":tomorrow,"sort_order":3}, admin)
check("admin can schedule a campaign", st == 201)
st, expired = call("POST", "/admin/home-campaigns", {**base,"title":"حملة منتهية","end_date":yesterday,"sort_order":4}, admin)
check("admin can save an expired campaign", st == 201)
st, public = call("GET", "/home-campaigns")
visible = {x["id"] for x in public}
check("future and expired campaigns are hidden", future["id"] not in visible and expired["id"] not in visible)

st, _ = call("POST", "/admin/home-campaigns", {**base,"title":"رابط غير آمن","destination_type":"external","destination_value":"http://example.com"}, admin)
check("HTTP external destination is rejected", st == 400)
st, wa = call("POST", "/admin/home-campaigns", {**base,"title":"واتساب","destination_type":"whatsapp","destination_value":"+20 10 1234 5678","sort_order":5}, admin)
check("WhatsApp destination is accepted and normalized", st == 201)
st, public = call("GET", "/home-campaigns")
wa_item = next((x for x in public if x["id"] == wa.get("id")), None)
check("WhatsApp public destination is a safe wa.me URL", bool(wa_item and wa_item["href"] == "https://wa.me/201012345678" and wa_item["external"]))

st, _ = call("POST", "/admin/home-campaigns", {**base,"title":"تاريخ خطأ","start_date":tomorrow,"end_date":yesterday}, admin)
check("invalid date range is rejected", st == 400)
st, _ = call("POST", "/admin/home-campaigns", {**base,"title":"ترتيب خطأ","sort_order":101}, admin)
check("out-of-range ordering is rejected", st == 400)
st, _ = call("POST", "/admin/home-campaigns", {**base,"title":"عنوان","destination_type":"external","destination_value":"javascript:alert(1)"}, admin)
check("unsafe destination scheme is rejected", st == 400)
st, _ = call("POST", "/admin/home-campaigns", {**base,"title":"وجهة غير صالحة","destination_type":"listing","destination_value":"999999"}, admin)
check("unpublished/nonexistent market listing destination is rejected", st == 400)

st, edited = call("POST", "/admin/home-campaigns/%d" % cid, {**base,"title":"حملة معدلة","is_active":False}, admin)
check("admin edits and disables campaign", st == 200 and edited.get("ok"))
st, public = call("GET", "/home-campaigns")
check("disabled campaign disappears from public feed", all(x["id"] != cid for x in public))
st, _ = call("GET", "/admin/home-campaigns", token=admin)
check("admin list retains all campaigns including inactive/scheduled", st == 200)

st, deleted = call("POST", "/admin/home-campaigns/%d/delete" % cid, {}, admin)
check("admin deletes campaign", st == 200 and deleted.get("ok"))
st, public = call("GET", "/home-campaigns")
check("deleted campaign no longer appears publicly", all(x["id"] != cid for x in public))
print("ALL HOMEPAGE CAMPAIGN API CHECKS PASSED")
