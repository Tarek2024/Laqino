# شرح الأذونات (المرحلة 34): سلوك perm.js بـnode + فحص الربط الثابت.
import subprocess, re, sys
R = lambda p: open(p, encoding="utf-8").read()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or sys.exit(1))
r = subprocess.run(["node", "test_phase34_permissions.js"], capture_output=True, text=True); print(r.stdout, end="")
ok("perm.js behaviour (node)", r.returncode == 0 and "ALL OK" in r.stdout)
ok("perm.js syntax", subprocess.run(["node", "--check", "static/perm.js"]).returncode == 0)
for f in ("static/native.js", "static/location.js"): ok(f + " syntax", subprocess.run(["node", "--check", f]).returncode == 0)
ok("native.js asks via LaqPerm before requestPermissions", re.search(r"LaqPerm\.explain\('notif'\)[\s\S]{0,200}P\.requestPermissions", R("static/native.js")) is not None)
ok("location.js asks via LaqPerm before requestPermissions", re.search(r"LaqPerm\.explain\('location'\)[\s\S]{0,300}NG\.requestPermissions", R("static/location.js")) is not None)
ok("location.js 'later' is not a denial", "code: 'later'" in R("static/location.js") and "later:" in R("static/location.js"))
for f in ("index", "courier"):
    t = R(f"static/{f}.html"); ok(f"{f}.html loads perm.js before native.js", 0 <= t.find('/perm.js') < t.find('/native.js'))
ok("sw.js caches perm.js", '"/perm.js"' in R("static/sw.js"))
