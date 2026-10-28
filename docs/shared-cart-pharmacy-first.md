# Shared cart / pharmacy-first rollout — isolated branch

## Safety boundary
- Branch: `feature/cart-pharmacy-isolated`
- This remains isolated and is not merged into `main`.
- Runtime feature flag: `settings.cart_enabled`, default OFF.
- Existing delivery endpoints and lifecycle remain the source of truth for dispatch, courier offers/acceptance, fare negotiation/customer approval, status transitions, wallet checks, and commission charging.
- The cart adapter creates ordinary `delivery_orders` rows; it does not implement a parallel courier-selection system.

## Checkout behavior now implemented
- The customer submits a `request_key` and delivery address.
- The entire cart becomes exactly one ordinary delivery order, assigned to one courier and delivered once to the customer.
- A private `cart_checkout_stops` record is created for each pharmacy; the courier sees each pickup address and item list, and confirms each pickup separately.
- The shared order cannot advance from pickup to customer delivery until every pharmacy stop has been marked picked up.
- The shared order, all pharmacy pickup stops, and the checkout idempotency record are committed in one SQLite `BEGIN IMMEDIATE` transaction, or none are committed.
- A stable shared-order request key and unique checkout key make retries return the existing order instead of creating duplicates.
- All products and prescription quotes are revalidated at checkout, including provider approval, current availability/freshness, quote approval, customer ownership, and regional coverage.
- The same existing open-order cap is applied once to the shared checkout before creating the delivery order.
- After commit, the single shared order is handed once to the existing `push_new_order` callback. It retains normal `searching` status and normal fare negotiation/approval; delivery fee and commission are for the one shared route, not per pharmacy.
- Pharmacies receive an initial shared-cart request notification, a courier-on-the-way notification after assignment, and a pickup-completed notification for their own stop only.
- Courier stop endpoints enforce courier assignment and approved-courier role; pharmacy stop listings are restricted to the authenticated pharmacy.
- The cart is emptied after successful checkout. A later visit starts a fresh cart.
- Prescription quotes have quantity one; they cannot multiply a whole-prescription quote.

## Regression coverage added
- Multi-pharmacy checkout creates one normal order for the shared route, private stops per pharmacy, and emits one dispatch push.
- Existing searching orders remain unchanged.
- Same idempotency key returns the same order group and does not re-dispatch.
- A stale/rejected offer rolls back the entire checkout.
- Open-order cap counts the shared cart as one delivery job.
- Courier pickup progression is gated until all pharmacy stops are confirmed.
- Prescription quantity guard and default-off/additive schema checks.

## Remaining release gate
The new integration is not yet declared production-ready. Wait for GitHub Actions to complete the full project regression suite and inspect any failures. Add/run end-to-end tests against the real server DB schema for concurrent duplicate checkout, courier accept/reject, fare proposal and customer approval, courier wallet eligibility, and exactly-once commission settlement before merging or enabling `cart_enabled`.
