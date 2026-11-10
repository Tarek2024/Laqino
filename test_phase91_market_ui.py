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
from playwright.sync_api import sync_playwright

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
# Seed the optional price directly so this test exercises the share-preview price branch,
# independently of the listing form/API defaults.
with sqlite3.connect(server.DB) as connection:
    connection.execute("UPDATE listings SET price=? WHERE id=?", (1250, listing_id))

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
check("market details open a dedicated in-app image gallery",
      "function openGallery()" in market
      and 'role: "dialog"' in market
      and '"aria-modal": "true"' in market)
check("image gallery supports previous/next and thumbnail selection",
      'class: "lb-prev"' in market and 'class: "lb-next"' in market
      and 'class: "lb-thumb"' in market and "paintGallery()" in market)
check("image gallery supports keyboard navigation and Escape close",
      'e.key === "Escape"' in market and 'e.key === "ArrowRight"' in market
      and 'e.key === "ArrowLeft"' in market)
gallery_css = (ROOT / "static" / "market-enhancements.css").read_text(encoding="utf-8")
check("image gallery supports touch swipes and zoom",
      'e.changedTouches[0].clientX' in market
      and 'photo.classList.toggle("zoomed", zoomed)' in market
      and ".lb-photo.zoomed{" in gallery_css)
check("listing image swipe does not accidentally open the gallery",
      "didSwipe = true" in market and "if (didSwipe)" in market)
check("market page loads the dedicated market UI stylesheet",
      re.search(r'<link rel="stylesheet" href="/market-ui\.css\?v=\d+">', market) is not None)
check("service-worker precaches the market UI stylesheet",
      '"/market-ui.css"' in sw and '"/market-ui.css?v=1"' in sw)
check("market UI has responsive layouts for phone, tablet, and desktop",
      "@media(min-width:640px)" in market_css
      and "@media(min-width:1024px)" in market_css
      and "@media(max-width:520px)" in market_css)
app_css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
shell_js = (ROOT / "static" / "shell.js").read_text(encoding="utf-8")
location_js = (ROOT / "static" / "location.js").read_text(encoding="utf-8")
check("client navigation ignores stale asynchronous page renders",
      "__laqGoSeq" in index and "seq!==window.__laqGoSeq" in index)
check("app shell ignores stale navigation completion effects",
      "goSeq = 0" in shell_js and "if (seq !== goSeq) return r" in shell_js)
check("location permission is not requested automatically on first app open",
      "if (!lsGet(ASK)) request({})" not in location_js
      and "if (l && Date.now() - l.ts > STALE_MS) request({});" in location_js
      and "لا نطلب إذن الموقع إلا بعد اختيار المستخدم" in location_js)
check("manual location action still explicitly requests and resolves the user location",
      "request({ explicit: true })" in location_js
      and "حدّد موقعي تلقائيًا" in location_js)
check("customer app has an explicit tablet portrait width rule",
      "@media (min-width: 760px) and (max-width: 899px)" in app_css
      and "max-width:760px!important" in app_css)
check("customer app retains desktop navigation and wide layout rules",
      "@media (min-width: 900px)" in app_css
      and "body.app>nav" in app_css
      and "max-width:1200px!important" in app_css)
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
check("phase 93 release metadata is declared", release == "phase-93")
check("VERSION cache matches the service-worker cache", bool(cache and sw_cache_match and cache == sw_cache_match.group(1)))
check("new market UI stylesheet is part of the active service-worker shell",
      '"/market-ui.css"' in sw)

# Browser-level regression: the actual market detail gallery must work at phone,
# tablet and desktop viewport sizes without navigating away from the listing.
gallery_listing = {
    "id": 987, "images": [201, 202, 203], "title": "إعلان معرض الصور",
    "price": 1250, "condition": "used", "negotiable": True,
    "category": [{"name": "أثاث"}], "region": [{"name": "الرياض"}],
    "fields": [], "seller": "بائع الاختبار", "created_at": int(time.time()),
    "description": "اختبار عارض الصور", "is_owner": True, "contact_mode": "both",
}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    page = context.new_page()
    page.route("**/api/listings/987", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(gallery_listing, ensure_ascii=False)
    ))
    tiny_png = __import__("base64").b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pV8AAAAASUVORK5CYII="
    )
    page.route("**/api/listings/987/images/**", lambda route: route.fulfill(
        status=200, content_type="image/png", body=tiny_png
    ))
    page.goto(BASE + "/market.html#/l/987", wait_until="domcontentloaded")
    page.locator(".det .main").wait_for(state="visible", timeout=10000)
    check("market detail gallery opens in an in-page dialog on phone",
          page.locator(".det .main").is_visible())
    page.evaluate("""() => {
      const image = document.querySelector(".det .main");
      const start = new Touch({identifier: 1, target: image, clientX: 300, clientY: 200});
      const end = new Touch({identifier: 1, target: image, clientX: 220, clientY: 200});
      image.dispatchEvent(new TouchEvent("touchstart", {touches: [start], targetTouches: [start], changedTouches: [start], bubbles: true}));
      image.dispatchEvent(new TouchEvent("touchend", {touches: [], targetTouches: [], changedTouches: [end], bubbles: true}));
      image.click();
    }""")
    check("swiping the listing image does not accidentally open the gallery",
          page.locator(".lb").count() == 0)
    page.wait_for_timeout(700)
    page.locator(".det .main").click()
    page.locator(".lb").wait_for(state="visible")
    check("a normal tap still opens the gallery after a completed swipe",
          page.locator(".lb").is_visible())
    page.keyboard.press("Escape")
    page.locator(".lb").wait_for(state="detached")
    page.locator(".thumbs img").first.click()
    page.locator(".det .main").click()
    page.locator(".lb").wait_for(state="visible")
    check("gallery starts on the first image with the correct count",
          page.locator(".lb-count").inner_text() == "الصورة 1 من 3")
    controls_ok = page.evaluate("""() => {
      const nodes = [".lb-prev", ".lb-zoom", ".lb-next"].map(sel => document.querySelector(sel));
      const boxes = nodes.map(el => el.getBoundingClientRect());
      const normalFlow = nodes.every(el => getComputedStyle(el).position === "static");
      const noOverlap = boxes.every((a, i) => boxes.slice(i + 1).every(b =>
        a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top));
      return normalFlow && noOverlap;
    }""")
    check("gallery navigation and zoom controls stay in normal flow without overlap", controls_ok)
    check("gallery thumbnails stay in the thumbnail strip",
          page.locator(".lb-thumb").first.evaluate("(el) => getComputedStyle(el).position") == "static")
    page.locator(".lb-next").click()
    check("gallery next control advances within the same listing",
          page.locator(".lb-count").inner_text() == "الصورة 2 من 3")
    page.locator(".lb-thumb").nth(2).click()
    check("gallery thumbnails jump to the selected listing image",
          page.locator(".lb-count").inner_text() == "الصورة 3 من 3")
    page.keyboard.press("ArrowLeft")
    check("gallery keyboard navigation changes the current image",
          page.locator(".lb-count").inner_text() == "الصورة 2 من 3")
    page.locator(".lb-zoom").click()
    check("gallery zoom control toggles zoom state",
          "zoomed" in (page.locator(".lb-photo").get_attribute("class") or ""))
    page.locator(".lb-zoom").click()
    page.keyboard.press("Escape")
    page.locator(".lb").wait_for(state="detached")
    check("Escape closes the gallery and returns to the listing detail",
          page.locator(".det .main").is_visible() and page.locator(".lb").count() == 0)

    # The gallery should remain usable at tablet and desktop widths.
    for width, height, label in [(800, 1024, "tablet"), (1280, 900, "desktop")]:
        page.set_viewport_size({"width": width, "height": height})
        page.locator(".det .main").click()
        page.locator(".lb").wait_for(state="visible")
        overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        check("gallery has no horizontal viewport overflow on " + label, not overflow)
        page.locator(".lb-close").click()
        page.locator(".lb").wait_for(state="detached")

    gallery_listing["images"] = [201]
    page.reload(wait_until="domcontentloaded")
    page.locator(".det .main").wait_for(state="visible", timeout=10000)
    page.locator(".det .main").click()
    page.locator(".lb").wait_for(state="visible")
    check("single-image gallery shows one image and disables navigation",
          page.locator(".lb-count").inner_text() == "الصورة 1 من 1"
          and page.locator(".lb-prev").is_disabled()
          and page.locator(".lb-next").is_disabled())
    page.locator(".lb-close").click()
    page.locator(".lb").wait_for(state="detached")

    # Customer app shell: bottom navigation on phone/tablet and a non-overlapping
    # sticky horizontal navigation on desktop.
    app_context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    app_page = app_context.new_page()
    app_page.add_init_script("""try { localStorage.clear(); } catch (e) {}
      window.__gpsCalls = 0;
      window.__permissionState = "prompt";
      Object.defineProperty(navigator, "permissions", {configurable: true, value: {
        query: () => Promise.resolve({state: window.__permissionState})
      }});
      Object.defineProperty(navigator, "geolocation", {configurable: true, value: {
        getCurrentPosition: (success, error) => {
          window.__gpsCalls = (window.__gpsCalls || 0) + 1;
          if (error) error({code: 1});
        }
      }});
    }""")
    app_page.goto(BASE + "/", wait_until="domcontentloaded")
    app_page.locator("#v .find").wait_for(state="visible", timeout=20000)
    app_page.wait_for_timeout(900)
    check("first app open does not trigger a location permission prompt",
          app_page.evaluate("window.__gpsCalls === 0"))
    # Even when the OS/browser permission was granted previously, merely opening
    # delivery must not request a fresh GPS reading without a user action.
    app_page.evaluate("window.__permissionState = 'granted'")
    app_page.locator("#v .sc.dlv").click()
    app_page.locator("#lq-dl").wait_for(state="visible", timeout=5000)
    app_page.wait_for_timeout(250)
    check("opening delivery with granted permission does not request GPS automatically",
          app_page.evaluate("window.__gpsCalls === 0"))
    app_page.locator("#t0").click()
    app_page.locator("#v .find").wait_for(state="visible", timeout=5000)
    for width, height, label, expected_nav in [
        (390, 844, "phone", "fixed"),
        (800, 1024, "tablet", "fixed"),
        (1280, 900, "desktop", "sticky"),
    ]:
        app_page.set_viewport_size({"width": width, "height": height})
        metrics = app_page.evaluate("""() => {
          const nav = document.querySelector("body.app>nav");
          const header = document.querySelector("body.app>header.bar");
          const style = getComputedStyle(nav);
          return {
            overflow: document.documentElement.scrollWidth > window.innerWidth,
            navPosition: style.position,
            navTop: parseFloat(style.top) || 0,
            headerHeight: header.getBoundingClientRect().height
          };
        }""")
        check("customer app has no horizontal overflow on " + label, not metrics["overflow"])
        check("customer app navigation mode is correct on " + label,
              metrics["navPosition"] == expected_nav)
        if label == "desktop":
            check("desktop navigation stays below the sticky header",
                  metrics["navTop"] >= metrics["headerHeight"] - 2)
    app_page.locator("#rc").click()
    app_page.locator("#lq-loc-go").wait_for(state="visible", timeout=5000)
    app_page.locator("#lq-loc-go").click()
    app_page.wait_for_function("window.__gpsCalls === 1", timeout=5000)
    check("location permission is requested after the user selects the location button",
          app_page.evaluate("window.__gpsCalls === 1"))
    app_page.close()
    app_context.close()
    context.close()
    browser.close()

httpd.shutdown()
print("Phase 91 focused regression checks passed.")
