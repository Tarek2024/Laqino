# Phase 71 Shops — Compatibility Review

Date: 2026-10-29
Base reviewed: `main` at `c5cc7f92bf6802a557a1f505169d4568879c66cf`
Scope: review only; no merge or deployment.

## Verdict

**Not ready to merge.** The phase 71 archive has working feature-specific tests, but the current `main` branch does not contain the shops feature files or integration hooks. Simply copying the older archive's `server.py`, `account.py`, `static/index.html`, or `static/admin.html` would overwrite newer project changes. The safe path is a selective port onto current `main`, followed by regression testing.

## Confirmed integration gaps

1. `main/server.py` has no `shops` or `shop_delivery` imports, install hooks, or request dispatch hooks. The archive adds them around the existing `provider_delivery` integration.
2. Current courier transitions special-case only `provider_delivery.KIND` (`provider_pickup`). The archive expects `PICKUP_KINDS` to include both pharmacy pickup and `shop_pickup`. Without this change, shop pickup orders can follow the wrong fare/status path.
3. Current `static/pdelivery-courier.js` renders only `provider_pickup`; it needs a selective extension for `shop_pickup`, while preserving the current pharmacy behavior.
4. Current `static/index.html`, `static/admin.html`, and `static/sw.js` do not reference `shops.html` or `shop.html`; the customer/owner/admin entry points and offline shell need selective integration.
5. Current `account.py` lacks shop anonymization and does not remove `shop_item_images` links before deleting owned files. The archive includes those cleanup steps. They must be carried over without replacing the newer account-deletion behavior.
6. Current main already provides the dependencies used by the archive's delivery adapter (`push_new_order`, `push_stop_order`, `default_delivery_region`, `region_fee`, `commission_for`, and the order limit), but the pickup-kind branching and feature dispatch still need integration.

## Feature archive test results

- `test_phase66_shops.py`: PASS (includes account deletion/anonymization without item images).
- `test_phase67_shops_admin.py`: PASS (completed with exit 0 on the longer run).
- `test_phase68_shop_items.py`: PASS.
- `test_phase68_shop_panel.py`: INCOMPLETE — local UI harness stalled during an interaction after several passing checks; not treated as a product pass or fail.
- `test_phase69_shop_delivery.py`: PASS.
- `test_phase69_shop_orders_ui.py`: INCOMPLETE — local UI harness stalled after several passing checks.
- `test_phase70_shops_browse.py`: PASS.
- `test_phase71_shops_hardening.py`: PASS, including region gating, duplicate request key race, 10/hour limit, and suspended-shop blocking.
- Python syntax compilation for the archive's `server.py`, `account.py`, `shops.py`, and `shop_delivery.py`: PASS.
- Full project regression and browser-level end-to-end against current `main`: NOT YET RUN. Chromium/browser E2E is not available in this environment.

The UI scripts that hang use local HTTP/UI harnesses. Their partial passing checks are recorded, but the hangs prevent treating those runs as complete.

## Required before merge

1. Selectively port the shops modules and frontend additions onto the latest `main`; do not replace whole files with archive versions.
2. Add `PICKUP_KINDS` handling in courier acceptance/transitions and extend courier UI only for the new shop pickup type.
3. Add shop image-link cleanup and shop anonymization to the current account-deletion flow.
4. Integrate the customer/owner/admin entry points and service-worker cache entries without removing existing links or cache assets.
5. Run all shop tests to completion, then regression tests for registration/login, pharmacy delivery, regular delivery, notifications, file privacy, and account deletion against the integrated branch.
6. Test with a disposable copy of the current database and verify existing delivery orders and pharmacy flows remain unchanged.

No production files were changed, no PR was merged, and nothing was deployed.
