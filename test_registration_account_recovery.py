"""Registration recovery and admin account activation regression tests.

Runs only against a temporary SQLite database and a loopback HTTP server:
    python test_registration_account_recovery.py
"""
import json
import os
import pathlib
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="laqino-account-recovery-")
os.environ["LAQINO_DB"] = os.path.join(TMP, "test.db")
os.environ["LAQINO_UPLOADS"] = os.path.join(TMP, "uploads")
os.makedirs(os.environ["LAQINO_UPLOADS"], exist_ok=True)

import server

assert os.path.realpath(server.DB).startswith(os.path.realpath(TMP)), "ISOLATION BROKEN: refusing to run"
server.init("01000000000", "AdminPass123")
httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
DB = server.DB
ROOT = pathlib.Path(__file__).resolve().parent


def call(method, path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + "/api" + path,
        json.dumps(data).encode() if data is not None else None,
        headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def sql(query, args=()):
    connection = sqlite3.connect(DB)
    try:
        return connection.execute(query, args).fetchall()
    finally:
        connection.close()


def check(label, condition):
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        raise AssertionError(label)


admin_response = call("POST", "/login", {"phone": "01000000000", "password": "AdminPass123"})
assert admin_response[0] == 200, admin_response
admin_token = admin_response[1]["token"]

customer_phone = "01055550001"
status, _ = call("POST", "/register", {
    "name": "عميل اختبار", "phone": customer_phone, "password": "password1"
})
assert status in (200, 201), ("test customer registration failed", status)
customer_token = call("POST", "/login", {
    "phone": customer_phone, "password": "password1"
})[1]["token"]

# The recovery route must be admin-only and validate inputs before creating a row.
check("customer cannot activate an account (admin-only)", call(
    "POST", "/admin/users/activate",
    {"name": "غير مصرح", "phone": "01055550002"}, customer_token
)[0] == 403)
check("invalid Egyptian mobile is rejected", call(
    "POST", "/admin/users/activate",
    {"name": "رقم غير صحيح", "phone": "011234"}, admin_token
)[0] == 400)
check("empty name is rejected", call(
    "POST", "/admin/users/activate",
    {"name": " ", "phone": "01055550002"}, admin_token
)[0] == 400)

# Create an account whose original registration never produced a user row.
new_phone = "01055550002"
status, created = call("POST", "/admin/users/activate", {
    "name": "عميل استعادة", "phone": new_phone
}, admin_token)
check("admin activation creates a customer account", status == 201 and created.get("ok") is True)
check("setup code is eight digits and expires in 30 minutes",
      bool(__import__("re").fullmatch(r"\d{8}", created.get("setup_code", "")))
      and created.get("expires_in") == 1800)
check("activation response never exposes a password or password hash",
      not ({"password", "pw_hash", "salt"} & set(created)))
check("new account appears in admin user search",
      any(x["phone"] == new_phone and x["name"] == "عميل استعادة"
          for x in call("GET", "/admin/users?q=" + new_phone, token=admin_token)[1]))
check("duplicate phone does not create a second account", call(
    "POST", "/admin/users/activate",
    {"name": "تكرار", "phone": new_phone}, admin_token
)[0] == 409)
check("only one user row exists for the activated phone",
      len(sql("SELECT id FROM users WHERE phone=?", (new_phone,))) == 1)
check("activation is recorded in audit log",
      bool(sql("SELECT id FROM audit_log WHERE action='account.admin_activated' AND target=?", (new_phone,))))

# The temporary password is inaccessible; the customer must set their own password.
check("generated account cannot log in using the chosen password before setup", call(
    "POST", "/login", {"phone": new_phone, "password": "CustomerPass123"}
)[0] == 401)
status, reset = call("POST", "/password/reset", {
    "phone": new_phone, "code": created["setup_code"], "new_password": "CustomerPass123"
})
check("one-time setup code lets the customer choose a password", status == 200 and reset.get("ok") is True)
check("customer can log in with their chosen password", call(
    "POST", "/login", {"phone": new_phone, "password": "CustomerPass123"}
)[0] == 200)
check("setup code cannot be reused", call("POST", "/password/reset", {
    "phone": new_phone, "code": created["setup_code"], "new_password": "AnotherPass123"
})[0] == 400)

# Expiry must be enforced server-side, not only by the admin-page countdown.
expired_phone = "01055550003"
status, expired = call("POST", "/admin/users/activate", {
    "name": "عميل منتهي", "phone": expired_phone
}, admin_token)
assert status == 201, (status, expired)
connection = sqlite3.connect(DB)
connection.execute("UPDATE password_resets SET expires=0 WHERE user_id=?", (expired["user_id"],))
connection.commit()
connection.close()
check("expired setup code is rejected", call("POST", "/password/reset", {
    "phone": expired_phone, "code": expired["setup_code"], "new_password": "CustomerPass123"
})[0] == 400)

# Static checks ensure the UI fixes remain present alongside the new admin recovery flow.
register_html = (ROOT / "static" / "register.html").read_text(encoding="utf-8")
index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
admin_html = (ROOT / "static" / "admin.html").read_text(encoding="utf-8")
check("standalone registration page prevents overlapping verification polls",
      "polling=true" in register_html and "if(!verification||polling)return" in register_html)
check("standalone registration recovers from an already-registered phone",
      "const finishRegistration=async d=>{try{await api('/register'" in register_html
      and "الرقم مسجّل بالفعل|الرقم مسجل بالفعل" in register_html)
check("main-page verification polling prevents concurrent requests",
      "let vfPolling=false" in index_html and "if(!VF||vfPolling)" in index_html)
check("main-page registration recovery handles an already-registered phone",
      "الرقم مسجّل بالفعل|الرقم مسجل بالفعل" in index_html)
check("admin page includes account activation and customer-password setup instructions",
      "activateUser" in admin_html and "استعادة كلمة المرور" in admin_html)

httpd.shutdown()
httpd.server_close()
print("ALL REGISTRATION / ACCOUNT ACTIVATION REGRESSION CHECKS PASSED")
