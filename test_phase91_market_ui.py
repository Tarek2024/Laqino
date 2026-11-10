"""Phase 91 focused regression tests.

Covers public marketplace share previews, WhatsApp share routing, home-section
visibility/auth UX, responsive/dark marketplace assets, and release cache wiring.
Run: python test_phase91_market_ui.py
"""
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="laqino-phase91-")
os.environ["LAQINO_DB"] = os.path.join(TMP, "test.db")
os.environ["LAQINO_UPLOADS"] = os.path.join(TMP, "uploads")
os.makedirs(os.environ["LAQINO_UPLOADS"], exist_ok=True)

import server

assert os.path.realpath(server.DB).startswith(os.path.realpath(TMP)), "ISOLATION BROKEN"
server.init("01000000000", "AdminPass123")
httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
ROOT = pathlib.Path(__file__).resolve().parent


def check(label, condition):
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        raise AssertionError(label)


def api(method, path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + "/api" + path,
        json.dumps(data, ensure_ascii=False).encode() if data is not None else None,
        headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, json.loads(raw) if raw else None


def page(path):
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read().decode("utf-8"), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8"), dict(error.headers)


def sql(query, args=()):
    with sqlite3.connect(server.DB) as connection:
        return connection.execute(query, args).fetchall()


admin_status, admin_data = api("POST", "/login", {
    "phone": "01000000000", "password": "AdminPass123"
})
assert admin_status == 200, ("admin login failed", admin_status, admin_data)
admin = admin_data["token"]

seller_phone = "01091910001"
reg_status, _ = api("POST", "/register", {
    "name": "بائع اختبار", "phone": seller_phone, "password": "password1"
})
assert reg_status in (200, 201), ("seller registration failed", reg_status)
seller = api("POST", "/login", {
    "phone": seller_phone, "password": "password1"
})[1]["token"]

root_rows = sql("SELECT id FROM categories WHERE section='souq' AND parent_id IS NULL ORDER BY id LIMIT 1")
assert root_rows, "test setup: marketplace root category missing"
root_category = root_rows[0][0]
cat_status, cat_data = api("POST", "/admin/categories", {
    "section": "souq",
    "name_ar": "اختبار معاينة الإعلان",
    "slug": "phase91-preview-test",
    "parent_id": root_category,
    "is_active": True,
}, admin)
assert cat_status in (200, 201), ("test category creation failed", cat_status, cat_data)
cats = api("GET", "/categories?section=souq")[1]
category_id = next(x["id"] for x in cats if x.get("name_ar") == "اختبار معاينة الإعلان")
region_rows = sql("SELECT id FROM regions WHERE is_active=1 ORDER BY id LIMIT 1")
assert region_rows, "test setup: no active region"
region_id = region_rows[0][0]

title = "كرسي & طاولة للبيع"
description = "وصف اختبار معاينة الإعلان"
create_status, created = api("POST", "/listings", {
    "category_id": category_id,
    "region_id": region_id,
    "title": title,
    "description": description,
    "price": 1250,
}, seller)
check("market listing creation remains available", create_status == 201 and created.get("status") == "pending")
listing_id = created["id"]

pending_status, _, _ = page("/share/listing/%d" % listing_id)
check("unapproved listing is not exposed by public share route", pending_status == 404)

approve_status, approve_data = api(
    "POST", "/admin/listings/%d/review" % listing_id,
    {"status": "approved"}, admin
)
check("admin approval flow remains available", approve_status == 200)

share_status, html, headers = page("/share/listing/%d" % listing_id)
check("approved listing has a public HTML share preview", share_status == 200 and "text/html" in headers.get("Content-Type", ""))
check("share preview contains escaped listing title", "كرسي &amp; طاولة للبيع" in html and "<script>" not in html)
check("share preview contains description and price metadata", description in html and "1,250 جنيه" in html)
check("Open Graph and Twitter cards contain canonical share URL", 
      'property="og:url" content="https://laqino.tech/share/listing/%d"' % listing_id in html
      and 'name="twitter:card" content="summary_large_image"' in html)
check("share preview uses safe fallback image when listing has no uploaded photo",
      'og:image' in html and "assets/icon-512.png" in html)
check("share preview links back to the existing marketplace detail route",
      'href="/market.html#/l/%d"' % listing_id in html)
check("share preview is cacheable only for a short public window",
      "public, max-age=300" in headers.get("Cache-Control", ""))

# Existing API listing/detail behavior must remain available after share-page creation.
public_status, public_items = api("GET", "/listings")
check("approved listing remains in the existing public marketplace API",
      public_status == 200 and any(x.get("id") == listing_id for x in public_items))
detail_status, detail = api("GET", "/listings/%d" % listing_id)
check("existing listing detail API still serves the listing", detail_status == 200 and detail.get("id") == listing_id)

index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
market = (ROOT / "static" / "market.html").read_text(encoding="utf-8")
market_css = (ROOT / "static" / "market-ui.css").read_text(encoding="utf-8")
sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
version = (ROOT / "VERSION").read_text(encoding="utf-8")

check("market details build the public share URL from the listing id",
      'location.origin + "/share/listing/" + d.id' in market)
check("market details expose a WhatsApp share action",
      "share-whatsapp" in market and "https://wa.me/?text=" in market)
check("market page loads the dedicated market UI stylesheet",
      re.search(r'<link rel="stylesheet" href="/market-ui\.css\?v=\d+">', market) is not None)
check("service-worker precaches the market UI stylesheet",
      '"/market-ui.css"' in sw and '"/market-ui.css?v=1"' in sw)
check("market UI has responsive layouts for phone, tablet, and desktop",
      "@media(min-width:640px)" in market_css
      and "@media(min-width:1024px)" in market_css
      and "@media(max-width:520px)" in market_css)
check("market UI defines dark-mode colors for cards and controls",
      "@media(prefers-color-scheme:dark)" in market_css
      and ".card,.det" in market_css
      and "input,select,textarea" in market_css)
check("local-services home card is omitted when no published providers exist",
      "async function homeSectionCards(card,svOn,provided)" in index
      and "(x.key!=='svc'||svOn)" in index
      and "svOn=providers.length>0" in index)
check("home login is collapsed by default and can be expanded by the visitor",
      '<details class="home-auth"><summary>عندك حساب بالفعل؟ سجّل الدخول</summary>' in index)
check("homepage trust/footer links and contact route remain present",
      "منكم وليكم" in index and "ابعت والباقي علينا" in index
      and 'href="/privacy"' in index and 'href="/terms"' in index)
check("registration page keeps its dedicated form and brand header",
      'id="registerForm"' in (ROOT / "static" / "register.html").read_text(encoding="utf-8")
      and 'class="brand"' in (ROOT / "static" / "register.html").read_text(encoding="utf-8"))

release = next((line.split("=", 1)[1].strip() for line in version.splitlines() if line.startswith("release=")), "")
cache = next((line.split("=", 1)[1].strip() for line in version.splitlines() if line.startswith("cache=")), "")
sw_cache_match = re.search(r'const V = "([^"]+)"', sw)
check("phase 91 release metadata is declared", release == "phase-91")
check("VERSION cache matches the service-worker cache", bool(cache and sw_cache_match and cache == sw_cache_match.group(1)))
check("new market UI stylesheet is part of the active service-worker shell",
      '"/market-ui.css"' in sw)

httpd.shutdown()
print("Phase 91 focused regression checks passed.")
