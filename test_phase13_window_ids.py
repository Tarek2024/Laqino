# المرحلة 13: المتصفح الحقيقي يربط كل عنصر له id بـ window، فأي window.X بنفس اسم id لازم يُعرَّف قبل أول استخدام.
# فحص ثابت (الاختبارات بـ DOM مُحاكى لا تلتقط هذا الخلل).
import re, os
s = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"), encoding="utf-8").read()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
ids = set(re.findall(r'id=\\?"([A-Za-z_][\w-]*)\\?"', s)); wins = set(re.findall(r"window\.([A-Za-z_$][\w$]*)", s))
clash = sorted(wins & ids)
ok("some window state names equal element ids (the risk exists): " + ",".join(clash), len(clash) > 0)
first = s.find("<script")
for n in clash:
    m = re.search(r"window\." + re.escape(n) + r"\s*=(?!=)", s[first:])
    reads = [x.start() for x in re.finditer(r"window\." + re.escape(n) + r"\b(?!\s*=(?!=))", s[first:])]
    ok(f"window.{n} is initialised before its first read", bool(m) and (not reads or m.start() < min(reads)))
