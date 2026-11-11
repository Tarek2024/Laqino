"""Phase 95: account order archive grouping without changing delivery lifecycle."""
import json
import os
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TMP = tempfile.mkdtemp(prefix="lq95-account-")
os.environ["LAQINO_DB"] = str(Path(TMP) / "laqino.db")
os.environ["LAQINO_UPLOADS"] = str(Path(TMP) / "uploads")
os.environ["LAQINO_AUTO_BACKUP"] = "0"
Path(os.environ["LAQINO_UPLOADS"]).mkdir(parents=True, exist_ok=True)

import server

server.init("01000000000", "AdminPass123")
httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
DB = os.environ["LAQINO_DB"]


def call(method, path, data=None, token=None):
    req = urllib.request.Request(
        BASE + "/api" + path,
        json.dumps(data).encode() if data is not None else None,
        {"Content-Type": "application/json",
         **({"Authorization": "Bearer " + token} if token else {})},
        method=method,
    )
    try:
        response = urllib.request.urlopen(req)
        return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


phone = "01095550001"
check("customer registration", call("POST", "/register", {
    "phone": phone, "name": "عميل اختبار الأرشيف", "password": "password1"
})[0] in (200, 201))
token = call("POST", "/login", {
    "phone": phone, "password": "password1"
})[1]["token"]

ids = {}
for label in ("searching", "completed", "cancelled", "disputed"):
    status, result = call("POST", "/delivery/orders", {
        "region_id": 3,
        "pickup_text": "مكان الاستلام " + label,
        "dropoff_text": "مكان التسليم " + label,
        "details": "اختبار فصل الطلبات",
        "request_key": "phase95-" + label,
    }, token)
    check("create fixture order " + label, status == 201 and result.get("id"))
    ids[label] = result["id"]

with sqlite3.connect(DB) as db:
    for label, order_id in ids.items():
        db.execute("UPDATE delivery_orders SET status=? WHERE id=?", (label, order_id))
    db.commit()

api_status, api_orders = call("GET", "/delivery/orders", token=token)
check("unified delivery API still returns all source orders", api_status == 200 and
      {x["status"] for x in api_orders if x["id"] in ids.values()} ==
      {"searching", "completed", "cancelled", "disputed"})

from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        service_workers="block",
    )
    context.add_init_script(
        "localStorage.setItem('t', %s); localStorage.setItem('rg', '3');"
        % json.dumps(token)
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/shell.js", lambda route: route.abort())
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_selector("nav", timeout=10000)
    page.evaluate("go(3)")
    deadline = time.time() + 10
    while time.time() < deadline:
        if page.evaluate("document.querySelectorAll('#mine-active-orders > .card.od').length === 2"):
            break
        page.wait_for_timeout(200)
    else:
        raise AssertionError("account page did not render the two current delivery orders")

    state = page.evaluate("""() => {
      const folds = [...document.querySelectorAll('#v details.account-fold')];
      const byTitle = title => folds.find(d =>
        (d.querySelector(':scope > summary')?.textContent || '').includes(title));
      const previous = byTitle('الطلبات السابقة');
      const completed = previous?.querySelector('.card.od:has(.sc3d[data-st="completed"])');
      return {
        activeCards: [...document.querySelectorAll('#mine-active-orders > .card.od')].map(x => x.textContent),
        previousCount: previous?.querySelectorAll('#mine-archive-orders > .card.od').length ?? -1,
        previousOpen: previous?.open ?? null,
        completedHas3D: !!completed?.querySelector('.sc3d[data-st="completed"]'),
        completedCanRate: !!completed?.querySelector('button[onclick^="rt("]'),
        cancelledInPrevious: (previous?.textContent || '').includes('ملغي'),
        servicesFolded: byTitle('طلبات الخدمات')?.open === false,
        pharmacyProductsFolded: byTitle('طلبات منتجات الصيدليات')?.open === false,
        adsFolded: byTitle('إعلاناتي وإدارة السوق')?.open === false,
        serviceIcon: !!byTitle('طلبات الخدمات')?.querySelector('summary .account-fold-icon.services svg'),
        pharmacyIcon: !!byTitle('طلبات منتجات الصيدليات')?.querySelector('summary .account-fold-icon.pharmacy svg'),
        archiveIcon: !!previous?.querySelector('summary .account-fold-icon.archive svg'),
        adsIcon: !!byTitle('إعلاناتي وإدارة السوق')?.querySelector('summary .account-fold-icon.market svg'),
        deliveryIcon: !!document.querySelector('#v .sec .account-fold-icon.delivery svg')
      };
    }""")

    check("only active and unresolved orders remain expanded",
          len(state["activeCards"]) == 2 and
          any("قيد البحث" in x for x in state["activeCards"]) and
          any("اعتراض" in x for x in state["activeCards"]))
    check("completed and cancelled orders are grouped in the previous-orders box",
          state["previousCount"] == 2 and state["cancelledInPrevious"])
    check("previous orders are collapsed initially", state["previousOpen"] is False)
    check("completed order keeps the existing 3D tracker", state["completedHas3D"])
    check("completed order remains rateable without requiring a rating to archive",
          state["completedCanRate"])

    # Change a live order after the account page is already open. The existing
    # polling flow should refresh the account and move it to the archive itself.
    with sqlite3.connect(DB) as db:
        db.execute("UPDATE delivery_orders SET status='completed' WHERE id=?",
                   (ids["searching"],))
        db.commit()
    deadline = time.time() + 12
    transition = None
    while time.time() < deadline:
        transition = page.evaluate("""() => {
          const previous = [...document.querySelectorAll('#v details.account-fold')]
            .find(d => (d.querySelector(':scope > summary')?.textContent || '').includes('الطلبات السابقة'));
          const completed = [...(previous?.querySelectorAll('#mine-archive-orders > .card.od') || [])]
            .filter(card => card.querySelector('.sc3d[data-st="completed"]'));
          return {
            activeCount: document.querySelectorAll('#mine-active-orders > .card.od').length,
            previousCount: previous?.querySelectorAll('#mine-archive-orders > .card.od').length ?? -1,
            completedRateable: completed.filter(card => card.querySelector('button[onclick^="rt("]')).length
          };
        }""")
        if transition["activeCount"] == 1 and transition["previousCount"] == 3:
            break
        page.wait_for_timeout(250)
    check("a live order moves automatically to previous orders after completion",
          transition is not None and transition["activeCount"] == 1 and
          transition["previousCount"] == 3)
    check("newly completed archived orders remain rateable",
          transition is not None and transition["completedRateable"] == 2)

    check("service, pharmacy-product and marketplace sections are folded",
          state["servicesFolded"] and state["pharmacyProductsFolded"] and state["adsFolded"])
    check("service requests section renders its SVG icon", state["serviceIcon"])
    check("pharmacy product orders section renders its SVG icon", state["pharmacyIcon"])
    check("previous orders section renders its SVG icon", state["archiveIcon"])
    check("market management section renders its SVG icon", state["adsIcon"])
    check("delivery orders heading renders its SVG icon", state["deliveryIcon"])

    page.locator("#v details.account-fold summary").filter(
        has_text="الطلبات السابقة"
    ).click()
    check("previous-orders box opens on demand",
          page.locator("#v details.account-fold").filter(
              has_text="الطلبات السابقة"
          ).evaluate("(el) => el.open"))

    # Exercise the actual account accordion state across a full account re-render.
    # This catches regressions that source-only checks cannot see.
    for title in ("طلبات الخدمات", "طلبات منتجات الصيدليات", "إعلاناتي وإدارة السوق"):
        fold = page.locator("#v details.account-fold").filter(has=page.locator("summary").filter(has_text=title))
        if fold.count():
            if not fold.evaluate("(el) => el.open"):
                fold.locator(":scope > summary").click()
            check(title + " section opens by user tap", fold.evaluate("(el) => el.open"))

    page.evaluate("go(3)")
    page.wait_for_function("""() => {
      const titles = ["طلبات الخدمات", "طلبات منتجات الصيدليات", "إعلاناتي وإدارة السوق", "الطلبات السابقة"];
      const all = [...document.querySelectorAll("#v details.account-fold")];
      return titles.every(title => all.some(el =>
        (el.querySelector(":scope > summary")?.textContent || "").includes(title) && el.open));
    }""", timeout=10000)
    check("all opened account sections stay open after a full re-render", True)

    # The courier application section is conditional by eligibility. If the
    # test account is eligible, verify its disclosure state is preserved too.
    courier = page.locator("#mine-fold-courier")
    if courier.count():
        courier.locator(":scope > summary").click()
        page.evaluate("go(3)")
        page.wait_for_function("() => document.querySelector('#mine-fold-courier')?.open === true")
        check("courier application section preserves its open state", True)
    else:
        print("INFO courier application section is not available to this test account")

    # Keep keyboard focus on an accordion summary while the 8-second account
    # refresh interval elapses; the user must not lose the active control.
    archive_summary = page.locator("#mine-fold-archive > summary")
    archive_summary.focus()
    page.evaluate("window.__accountFoldNodes = [...document.querySelectorAll('#v details.account-fold')]; window.__archiveSummaryNode = document.querySelector('#mine-fold-archive > summary')")
    page.wait_for_timeout(8500)
    check("automatic account refresh does not steal focus from the active summary",
          page.evaluate("document.activeElement === document.querySelector('#mine-fold-archive > summary')"))
    check("archive remains open after the automatic refresh interval",
          page.locator("#mine-fold-archive").evaluate("(el) => el.open"))
    check("automatic delivery refresh keeps the same accordion DOM nodes",
          page.evaluate("window.__accountFoldNodes.every(el => el.isConnected && document.getElementById(el.id) === el) && window.__archiveSummaryNode === document.querySelector('#mine-fold-archive > summary')"))
    check("service, pharmacy and market sections remain open after the 8-second refresh",
          page.evaluate("['#mine-fold-services','#mine-fold-pharmacy','#mine-fold-market'].every(id => document.querySelector(id)?.open === true)"))

    check("no browser JavaScript errors", not errors)
    browser.close()

httpd.shutdown()
print("ALL PASSED")
