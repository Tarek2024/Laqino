# Extensible shared-cart architecture

## Decision

The shared cart is a cross-section order composition layer, not a pharmacy feature. Pharmacy is the first adapter only because those are the currently implemented inventory and quote sources. Future sections (supermarkets, bakeries, general shops, and other providers) must connect through the same contracts without changing delivery dispatch, courier assignment, fare approval, wallet, or commission code.

## Stable boundaries

1. **Section/source adapter**: translates a section's native item or quote into a canonical cart line and revalidates it at checkout.
2. **Canonical cart line**: `source_type`, `source_id`, `provider_type`, `provider_id`, `title`, `unit_price`, `quantity`, and optional section-specific metadata. The cart stores a source reference, not a copy of the section's business logic.
3. **Provider adapter**: resolves a provider's display name, pickup address, active status, region coverage, and pickup authorization.
4. **Canonical pickup stop**: one stop per distinct provider/location, with a list of its cart lines. Stop authorization is scoped to the owning provider; providers must never see other providers' items or addresses.
5. **Delivery adapter**: converts the validated cart and its stops into one existing `delivery_orders` job. The current delivery lifecycle remains authoritative and is not duplicated.

## Adding a future section

A new section should need only:
- register a stable `source_type` and implement the source adapter (resolve item, validate ownership/availability/price/quantity, return canonical line);
- implement or configure the provider adapter for provider identity, pickup location, region, and access permissions;
- expose an “add to cart” action in that section and use the shared cart API;
- add adapter tests for ownership, stale price/availability, region mismatch, quantity rules, stop privacy, and idempotent checkout.

It must not add a new delivery-order type, dispatch loop, courier assignment flow, fare negotiation, wallet, or commission path.

## Schema and migration requirements before declaring the architecture implemented

The current pharmacy-first implementation still has pharmacy-specific assumptions: `cart_items.item_type` is a fixed CHECK list, and `cart_checkout_stops.provider_id` references the pharmacy `providers` table with pharmacy-specific naming/authorization. Do not claim that future sections can already plug in without changes.

Before enabling the feature, refactor these boundaries additively:
- use a source adapter registry instead of hard-coded source-type branches;
- represent source and provider types explicitly, with a stable provider identity shared across sections (or a provider adapter that maps section-native IDs to that identity);
- generalize stop display/authorization to provider identity and stop location while preserving compatibility for pharmacy rows;
- migrate existing SQLite databases safely (SQLite CHECK constraints cannot simply be widened with an ordinary ALTER COLUMN);
- add contract tests using a fake non-pharmacy adapter, proving that a new section can add a line, group into a stop, check out as one delivery job, and cannot read another provider's stop.

## Release guardrails

- Keep `settings.cart_enabled` OFF by default.
- Keep the work on `feature/cart-pharmacy-isolated` and the PR in draft until the adapter registry, safe migration, fake-provider contract tests, and existing project regression suite pass.
- Do not merge or deploy as part of this architecture step.
