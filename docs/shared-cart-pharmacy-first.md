# Shared cart / pharmacy-first rollout — isolated branch

## Safety boundary
- Branch: `feature/cart-pharmacy-isolated`
- This is an additive module. It is not merged into `main`.
- Runtime feature flag: `settings.cart_enabled`, default OFF.
- No existing delivery routes or legacy tables are rewritten.
- Cart checkout intentionally returns HTTP 409 until a transaction-safe adapter can create one delivery order per pharmacy and use the existing dispatch/commission lifecycle.

## Current implementation in this branch
- Additive `carts` and `cart_items` tables.
- Customer-only cart read/add/remove endpoints, guarded by the disabled-by-default flag.
- Product offers must be approved, available, pharmacy-approved, and freshly confirmed.
- Prescription quote insertion verifies that the prescription belongs to the authenticated customer and that the pharmacy is approved and the quote is approved/available.
- No phone numbers or private provider contact fields are returned.

## Required before checkout can be enabled
1. A server-side, idempotent checkout key for the entire cart submission and stable child keys per pharmacy.
2. Revalidate all offers, stock freshness, prescription approval, quantities, customer region and provider coverage in one SQLite transaction.
3. Create one delivery order per pharmacy using the existing delivery-order schema and existing push/offer/accept/status/commission machinery; never duplicate dispatch logic.
4. Commit all pharmacy orders or none; make retries return the same order group.
5. Add regression tests for duplicate submissions, concurrent checkout, stale prices, partial prescription quotes, region mismatch, wallet/commission exactly-once, and all legacy phase tests.
6. Only then add admin controls to enable checkout and customer-facing UI.

## Test gate
Do not merge or deploy this branch until the new API integration tests and existing `test_phase22_delivery_cycle.py`, prescription, products, and release smoke tests pass against temporary databases. This repository connector does not execute the test suite, so no test pass is claimed here.
