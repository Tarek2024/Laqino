# Homepage diagnostics runbook

For a live browser session, inspect `window.__laqinoHomeDiagnostics` in DevTools. The last 40 entries are retained in memory and mirrored to `sessionStorage` under `laqino_home_diagnostics` when storage is available. Each record includes timestamp, stage/endpoint, message, stack excerpt, and fallback action.

The initial shell must not wait for remote requests. Each optional homepage request has a bounded timeout; the initial shell is expected to paint before those requests settle. Tests that assert asynchronously hydrated sections wait beyond the 2.2-second maximum optional API timeout.

The emergency shell preserves search and primary navigation if homepage composition throws. Any such event is logged as `home-initial-render` and should be treated as a defect to diagnose, not as a normal successful full render.
