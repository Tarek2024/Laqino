# Homepage reliability gate

The homepage is a critical entry point. The reliability gate is split into four suites:

1. Backend, database, and campaign APIs: additive schema, admin-only CRUD, schedule visibility, safe destinations, and release consistency.
2. Existing-service regression: immutable delivery-page/lifecycle fingerprints, four-section contract, and homepage UI/API behavior.
3. Responsive browser checks: Chromium at 320, 360, 390, 430, 768, 1024, and 1440 CSS pixels; no horizontal overflow; search-first hierarchy; API-failure diagnostics; and a first-shell budget.
4. Full user experience and recovery: initial render with stalled requests, per-endpoint failure logs, emergency-shell recovery, admin campaign UI, and release smoke.

The tests use temporary databases and a local test server. They do not touch production data or deploy the application.

A passing gate is required before merging or deploying this homepage update. Browser checks are run on Ubuntu 24.04 because the pinned Playwright release does not support the newer runner image.
