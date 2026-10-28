# Shared cart / pharmacy-first rollout — isolated branch

## Safety boundary
- Branch: `feature/cart-pharmacy-isolated`
- This remains isolated and is not merged into `main`.
- Runtime feature flag: `settings.cart_enabled`, default OFF.
- Existing delivery endpoints and lifecycle remain the source of truth for dispatch, courier offers/acceptance, fare negotiation/customer approval, status transitions, wallet checks, and commission charging.
- The cart adapter creates ordinary `delivery_orders` rows; it does not implement a parallel courier-selection system.

## Checkout behavior now implemented
- The customer submits a `request_key` and delivery address.
- Each pharmacy in the cart becomes one normal delivery order, with pickup at that pharmacy and dropoff at the customer.
- All child orders and the checkout idempotency record are committed in one SQLite `BEGIN IMMEDIATE` transaction, or none are committed.
- Stable child request keys and a unique parent key make retries return the existing order group instead of creating duplicates.
- All products and prescription quotes are revalidated at checkout, including provider approval, current availability/freshness, quote approval, customer ownership, and regional coverage.
- The same existing open-order cap is applied across the whole checkout before creating any child order.
- After commit, each child order is handed to the existing `push_new_order` callback. Orders retain normal `searching` status and normal fare negotiation/approval; delivery fee is per pharmacy order and is not included in product subtotal.
- The cart is emptied after successful checkout. A later visit starts a fresh cart.
- Prescription quotes have quantity one; they cannot multiply a whole-prescription quote.

## Regression coverage added
- Multi-pharmacy checkout creates one normal order per pharmacy and emits a push per child order.
- Existing searching orders remain unchanged.
- Same idempotency key returns the same order group and does not re-dispatch.
- A stale/rejected offer rolls back the entire checkout.
- Open-order cap is checked for the whole cart.
- Prescription quantity guard and default-off/additive schema checks.

## Remaining release gate
The new integration is not yet declared production-ready. Wait for GitHub Actions to complete the full project regression suite and inspect any failures. Add/run end-to-end tests against the real server DB schema for concurrent duplicate checkout, courier accept/reject, fare proposal and customer approval, courier wallet eligibility, and exactly-once commission settlement before merging or enabling `cart_enabled`.
