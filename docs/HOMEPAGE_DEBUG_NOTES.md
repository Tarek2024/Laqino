# Homepage async debug notes

When a fake-DOM assertion fails after the first shell, inspect the separately exported `tiles`, `services`, and `promo` snapshots plus `window.__laqinoHomeDiagnostics`. The initial `#v` snapshot is intentionally not rewritten after first paint; hydrated child containers are updated independently.
