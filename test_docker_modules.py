# اختبار انحدار: كل وحدة بايثون محلية يستوردها server.py/setup_initial.py/backup_restore.py لازم يكون Dockerfile بينسخها،
# وكل ملف ثابت في SHELL الخاص بـ sw.js لازم يكون موجودًا فعلًا في static/.
import ast, os, re
here = os.path.dirname(os.path.abspath(__file__))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
local = {f[:-3] for f in os.listdir(here) if f.endswith(".py") and not f.startswith("test_")}
def local_imports(fn):
    t = ast.parse(open(os.path.join(here, fn), encoding="utf8").read()); m = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Import): m |= {a.name.split(".")[0] for a in n.names}
        if isinstance(n, ast.ImportFrom) and n.module: m.add(n.module.split(".")[0])
    return m & local
dock = open(os.path.join(here, "Dockerfile"), encoding="utf8").read()
copied = set()
for line in dock.splitlines():
    if line.startswith("COPY ") and "static" not in line:
        copied |= {x[:-3] for x in line.split()[1:-1] if x.endswith(".py")}
need = set()
for entry in ("server.py", "setup_initial.py", "backup_restore.py"):
    need |= local_imports(entry) | {entry[:-3]}
missing = sorted(need - copied)
ok("Dockerfile copies every local module the server needs (missing: %s)" % (missing or "none"), not missing)
sw = open(os.path.join(here, "static", "sw.js"), encoding="utf8").read()
shell = re.search(r"SHELL\s*=\s*\[(.*?)\]", sw, re.S).group(1)
paths = re.findall(r'"(/[^"]*)"', shell)
# Cache-busting query strings are URL parameters, not part of the on-disk filename.
bad = [p for p in paths if p != "/" and not os.path.exists(os.path.join(here, "static", p.split("?", 1)[0].lstrip("/")))]
ok("every sw.js SHELL path exists in static/ (bad: %s)" % (bad or "none"), not bad)
print("ALL PASSED")
