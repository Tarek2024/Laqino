# Phase 71 Shops — Compatibility Review & Test Run

Date: 2026-10-29
Base reviewed: `main` at `c5cc7f92bf6802a557a1f505169d4568879c66cf`
Feature source: uploaded Phase 71 archive and selective integration kit
Scope: archive tests + compatibility review; no merge or deployment.

## Verdict

**Feature tests are encouraging, but this is not yet merge-ready.** The shop feature modules and UI tests pass in the extracted Phase 71 source tree for most test scripts. The current GitHub `main` branch still lacks the feature modules and integration hooks, so these results do not prove the feature works after integration with current main.

The branch `test/phase71-shops-m6` is a compatibility-review branch; it does not yet contain the actual feature source files. No code has been merged into main and nothing has been deployed.

## Confirmed integration gaps

1. Current `main/server.py` has no `shops` or `shop_delivery` imports, install hooks, or request dispatch hooks.
2. Current courier acceptance/status logic special-cases only `provider_delivery.KIND` (`provider_pickup`). It must be extended to include `shop_pickup` without changing pharmacy or regular-delivery behavior.
3. Current `static/pdelivery-courier.js` needs a selective extension to render shop pickup jobs and their pickup-only lifecycle.
4. Current `static/index.html`, `static/admin.html`, and `static/sw.js` need selective customer/owner/admin entry points and cache entries.
5. Current `account.py` needs shop anonymization and shop-item image-link cleanup added to its existing account deletion transaction. Do not replace the file with the older archive version.
6. Do not replace current `server.py`, `account.py`, `static/index.html`, `static/admin.html`, `static/pdelivery-courier.js`, or `static/sw.js` with the archive versions; they may predate current main.

## Feature test results (executed one file at a time)

| Test | Result |
|---|---|
| `test_phase66_shops.py` | PASS — exit 0 |
| `test_phase67_shops_admin.py` | All assertions printed PASS; process did not exit before timeout. Marked INCOMPLETE at process level |
| `test_phase68_shop_items.py` | PASS — exit 0 |
| `test_phase68_shop_panel.py` | All assertions printed PASS; process did not exit before timeout. Marked INCOMPLETE at process level |
| `test_phase69_shop_delivery.py` | PASS — exit 0 |
| `test_phase69_shop_orders_ui.py` | PASS — exit 0 |
| `test_phase70_shops_browse.py` | PASS — exit 0 |
| `test_phase71_shops_hardening.py` | PASS — exit 0 |
| Python `py_compile` for archive `server.py`, `account.py`, `shops.py`, `shop_delivery.py` | PASS |
| JavaScript syntax extracted from `static/shops.html` and `static/shop.html` | PASS |

Phase 67 and phase 68 panel emitted ALL PASS / PASS for their assertions but held the process open until timeout. They are not represented as fully completed runs; the local harness shutdown issue needs fixing.

## Existing-flow regression tests (same extracted archive tree, not current-main integration)

| Test | Result |
|---|---|
| `test_phase22_delivery_cycle.py` | PASS — exit 0 |
| `test_phase28_commission_and_delivery.py` | PASS — exit 0 |
| `test_phase32_delete_account.py` | PASS — exit 0 |
| `test_phase40_provider_delivery.py` | PASS — exit 0 |
| `test_phase16_admin_courier_wallet.py` | PASS — exit 0 |
| `test_phase9_close_orders.py` | PASS — exit 0 |
| `test_phase40_provider_delivery_browser.py` | Browser portion SKIPPED because Chromium is unavailable |

These regression checks show the extracted archive's existing delivery/account paths still pass their scripts, but they do not replace testing against the current-main code after the selective port.

## Merge plan — still required

1. Add the new `shops.py`, `shop_delivery.py`, `static/shops.html`, and `static/shop.html` files to a branch based on the latest `main`.
2. Port the minimal server initialization/dispatch and `PICKUP_KINDS` handling into current `server.py`; retain pharmacy pickup semantics and normal customer delivery fare/confirmation semantics.
3. Extend the current courier UI for `shop_pickup`.
4. Port image ownership/anonymization cleanup into current `account.py`.
5. Add current UI entry points and service-worker cache entries without removing existing features.
6. Run the full shop test set and existing regression tests on the integrated branch; fix the UI harness shutdown issue and run browser E2E where Chromium is available.
7. Inspect the full branch diff, confirm no secrets or local database files, then open a PR for review. Merge/deploy only after the integrated tests pass.

## Current state

- No production files changed.
- No feature code committed to the GitHub compatibility branch yet.
- No pull request created.
- No merge or deployment performed.
