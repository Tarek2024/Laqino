#!/usr/bin/env python3
"""فحص جاهزية الإصدار (المرحلة 9) — قبل أي ZIP أو نشر. قراءة فقط، بلا شبكة وبلا تشغيل خادم.
   python3 release_check.py        يطبع PASS/FAIL ويخرج 1 عند أي فشل.
يفحص: الوحدات في Dockerfile، ملفات SHELL، رقم الكاش، عدم وجود قواعد/أسرار/مفاتيح داخل المجلد، وجود README المرحلة لكل مرحلة،
واتساق README.md/DEPLOY.md مع الكاش الحالي ومتغيرات البيئة الموجودة فعلًا في الكود."""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__)); fails = []
rd = lambda p: open(os.path.join(here, p), encoding="utf8").read()
def chk(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + str(detail))); (cond or fails.append(name))
ver = dict(l.split("=", 1) for l in open(os.path.join(here, "VERSION")).read().split() if "=" in l).get("release", ""); chk("VERSION file present", re.fullmatch(r"phase-\d+\w*", ver), ver)
sw = rd("static/sw.js"); cache = int(re.search(r"laqino-v(\d+)", sw).group(1)); chk("sw.js cache number found", cache > 0)
shell = re.findall(r'"(/[^"]*)"', re.search(r"SHELL\s*=\s*\[(.*?)\]", sw, re.S).group(1))
miss = [p for p in shell if p != "/" and not os.path.exists(os.path.join(here, "static", p.lstrip("/")))]; chk("every SHELL file exists", not miss, miss)
mods = {f[:-3] for f in os.listdir(here) if f.endswith(".py") and not f.startswith("test_")} - {"release_check", "apply_phase17_safe", "phase16_imgutil", "imgutil", "testutil"}
dock = rd("Dockerfile"); copied = set()
for ln in dock.splitlines():
    if ln.startswith("COPY ") and "static" not in ln: copied |= {x[:-3] for x in ln.split()[1:-1] if x.endswith(".py")}
imp = set(re.findall(r"^import ([\w, ]+)$", rd("server.py"), re.M)); need = {m.strip() for x in imp for m in x.split(",")} & mods | {"server"}
chk("Dockerfile copies every module server.py imports", need <= copied, sorted(need - copied))
bad = []
for root, ds, fs in os.walk(here):
    ds[:] = [d for d in ds if d not in ("__pycache__", "node_modules")]
    for f in fs:
        # تجاهل قواعد البيانات المحلية في جذر المشروع فقط؛ لا تحذفها.
        if root == here and f in ("laqino.db", "laqino.db-wal", "laqino.db-shm"):
            continue
        if re.search(r"(\.db(-wal|-shm)?|\.env|google-services\.json|\.pem|\.p12|\.jks|\.keystore)$", f) or f.endswith("service-account.json"): bad.append(os.path.relpath(os.path.join(root, f), here))
    if os.path.basename(root) == "uploads": bad.append("uploads/")
chk("no database / .env / key / service-account files inside the project", not bad, bad)
phases = sorted(set(re.findall(r"phase-(\d+)", " ".join(os.listdir(os.path.join(here, "docs", "phases"))))), key=int)
chk("docs/phases has a README for every phase 1..%s" % phases[-1], [int(x) for x in phases] == list(range(1, int(phases[-1]) + 1)), phases)
rm = rd("README.md"); dp = rd("DEPLOY.md")
chk("README.md mentions the current cache laqino-v%d (no stale cache number)" % cache, ("laqino-v%d" % cache) in rm and not re.search(r"laqino-v(?!%d\b)\d+" % cache, rm), "stale cache number in README")
code = rd("server.py") + "".join(rd(f) for f in ("fcm.py", "notif.py"))
used = set(re.findall(r'LAQINO_[A-Z_]+', code)) - {"LAQINO_TEST_PRESENCE", "LAQINO_PUSH_ALLOW_ANY", "LAQINO_FCM_ALLOW_ANY", "LAQINO_FCM_BASE"}
undoc = sorted(v for v in used if v not in rm + dp + rd("deploy/env.example")); chk("every LAQINO_* variable is documented (README/DEPLOY/env.example)", not undoc, undoc)
chk("env.example documents the FCM key variable", "LAQINO_FCM_SERVICE_ACCOUNT" in rd("deploy/env.example"))
chk("android/ ships no Firebase key", not os.path.exists(os.path.join(here, "android", "app", "google-services.json")))
print("RELEASE CHECK: %s" % ("OK" if not fails else "%d FAILED" % len(fails))); sys.exit(1 if fails else 0)
