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
        if page.evaluate("document.querySelectorAll('#v > .card.od').length === 2"):
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
        activeCards: [...document.querySelectorAll('#v > .card.od')].map(x => x.textContent),
        previousCount: previous?.querySelectorAll(':scope > .card.od').length ?? -1,
        previousOpen: previous?.open ?? null,
        completedHas3D: !!completed?.querySelector('.sc3d[data-st="completed"]'),
        completedCanRate: !!completed?.querySelector('button[onclick^="rt("]'),
        cancelledInPrevious: (previous?.textContent || '').includes('ملغي'),
        servicesFolded: byTitle('طلبات الخدمات')?.open === false,
        pharmacyProductsFolded: byTitle('طلبات منتجات الصيدليات')?.open === false,
        adsFolded: byTitle('إعلاناتي وإدارة السوق')?.open === false,
        serviceIcon: !!byTitle('طلبات الخدمات')?.querySelector(':scope > summary .account-fold-icon.services svg'),
        pharmacyIcon: !!byTitle('طلبات منتجات الصيدليات')?.querySelector(':scope > summary .account-fold-icon.pharmacy svg'),
        archiveIcon: !!previous?.querySelector(':scope > summary .account-fold-icon.archive svg'),
        adsIcon: !!byTitle('إعلاناتي وإدارة السوق')?.querySelector(':scope > summary .account-fold-icon.market svg'),
        deliveryIcon: !!document.querySelector('#v>.sec .account-fold-icon.delivery svg')
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
          const completed = [...(previous?.querySelectorAll(':scope > .card.od') || [])]
            .filter(card => card.querySelector('.sc3d[data-st="completed"]'));
          return {
            activeCount: document.querySelectorAll('#v > .card.od').length,
            previousCount: previous?.querySelectorAll(':scope > .card.od').length ?? -1,
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
    check("account sections use branded icons from the app icon family",
          state["serviceIcon"] and state["pharmacyIcon"] and state["archiveIcon"] and
          state["adsIcon"] and state["deliveryIcon"])

    page.locator("#v details.account-fold summary").filter(
        has_text="الطلبات السابقة"
    ).click()
    check("previous-orders box opens on demand",
          page.locator("#v details.account-fold").filter(
              has_text="الطلبات السابقة"
          ).evaluate("(el) => el.open"))

    check("no browser JavaScript errors", not errors)
    browser.close()

httpd.shutdown()
print("ALL PASSED")
