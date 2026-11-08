# Local Shops Order Flow Audit — 2026-11-08

## Scope
Reviewed the customer flow in `static/shops.html`, the shop-owner dashboard in `static/shop.html`, and the backend flow in `shop_delivery.py`. Base: `main` at `e88627f1697836bcd23d512d66670b2320b1d47e`.

## Finding: dashboard silently hides order-list API failures
- `static/shop.html`: `ordLoad(id)` catches every error from both `/owner/shops/<id>/delivery-requests` and `/owner/shops/<id>/orders`, then substitutes `{enabled:false, items:[]}`.
- The UI consequently renders an empty order list / “no orders” for transient network errors, 5xx responses, or authorization failures instead of showing a retryable error.
- `poll()` refreshes every 4 seconds and can overwrite the orders panel with that false empty state.
- The polling function has no in-flight guard, and `api()` has no request timeout. If a request stalls, subsequent 4-second polls can start additional overlapping requests.
- Impact: shop owners may believe new orders disappeared; repeated stalled requests can create unnecessary load.

## Backend / flow review
- `shop_delivery.py` validates shop ownership, approval, open state, item ownership/availability, quantities, drop-off address/coordinates, regional delivery fee, customer open-order limits, and duplicate request keys.
- Order creation commits the delivery order, item snapshot, shop link, and initial order event together.
- Shop accept/ready updates are guarded by pre-pickup delivery states; reject is limited to pre-pickup states and records an order event.
- Courier acceptance, fare proposal/approval, delivery stages, handover code, customer confirmation, and commission use the shared delivery flow.
- Existing backend regression test: `test_phase69_shop_delivery.py` covers order creation, duplicate idempotency, shop order listing, accept/ready, reject before pickup, courier flow, fare approval, and completion.

## Verification status
- Static source review completed.
- Existing regression test source reviewed.
- Runtime execution of the Python test suite and live browser/device flow was not available in this audit session; no claim of passing runtime tests is made.
- No application source files were changed. This branch contains only this audit note and is not merged into `main`.

## Recommended isolated fix / follow-up tests
1. Preserve the last known order list when a poll fails; show an explicit stale/error state with retry rather than returning an empty list.
2. Add a single in-flight polling guard and a bounded request timeout / abort.
3. Add regression tests proving a failed order-list request does not render “no orders”, and that repeated polls do not overlap.
