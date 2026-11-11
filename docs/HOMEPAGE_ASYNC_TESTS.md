# Async homepage test harness

The home screen now renders its first shell immediately and hydrates promo, section cards, service chips, and account panels asynchronously. The Node fake-DOM harness therefore exports each hydrated container (`promo`, `tiles`, `services`, `panels`, and `account`) separately instead of treating the initial `#v` HTML snapshot as the final DOM. Browser layout and first-paint behavior are covered separately by the Chromium responsive suite.
