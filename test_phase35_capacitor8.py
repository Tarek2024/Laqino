# تجهيز Capacitor 8 / API 36 (المرحلة 35) — فحص ثابت (لا بناء).
import json, re, sys
R = lambda p: open(p, encoding="utf-8").read()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
p = json.loads(R("android/package.json"))
deps = {**p["dependencies"], **p["devDependencies"]}
ok("all @capacitor/* are ^8", all(v.startswith("^8.") for k, v in deps.items() if k.startswith("@capacitor/")))
ok("geolocation + push-notifications + android + core + cli present", {"@capacitor/geolocation", "@capacitor/push-notifications", "@capacitor/android", "@capacitor/core", "@capacitor/cli"} <= set(deps))
ok("node >= 22", p.get("engines", {}).get("node") == ">=22")
c = json.loads(R("android/capacitor.config.json"))
ok("server.url is https://laqino.tech", c["server"]["url"] == "https://laqino.tech" and c["server"]["cleartext"] is False)
ok("appId unchanged", c["appId"] == "com.laqino.app")
ok("env.example domain", "DOMAIN=laqino.tech" in R("deploy/env.example"))
m = R("static/market.html")
ok("market viewport-fit=cover", "viewport-fit=cover" in m)
ok("market header respects safe-area-inset-top", "safe-area-inset-top" in m)
ok("README_ANDROID mentions API 36 + Node 22 + JDK 21", all(s in R("android/README_ANDROID.md") for s in ("API 36", "Node 22", "JDK 21")))
ok("no CHANGE-ME left in android/", "CHANGE-ME" not in R("android/capacitor.config.json") + R("android/README_ANDROID.md"))
