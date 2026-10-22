import os, tempfile, subprocess, sqlite3, sys
db = tempfile.mktemp(suffix=".db"); env = {**os.environ, "LAQINO_DB": db}
run = lambda *a: subprocess.run([sys.executable, "setup_initial.py", *a], env=env, capture_output=True, text=True)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
base = ["--region", "3", "--fee", "10", "--commission-type", "fixed", "--commission-value", "2"]
ok("requires explicit values", run("--region", "3").returncode != 0)
ok("rejects bad region", run("--region", "99", *base[2:]).returncode != 0)
r = run(*base); ok("first run applies", r.returncode == 0 and "رسوم" in r.stdout)
q = lambda s: sqlite3.connect(db).execute(s).fetchall()
ok("fee set", q("SELECT fee FROM region_fees WHERE region_id=3") == [(10.0,)])
ok("sections active, services hidden", sorted(q("SELECT section FROM categories WHERE parent_id IS NULL AND is_active=1")) == [("delivery",), ("medical",), ("souq",)])
ok("souq children + fields", q("SELECT COUNT(*) FROM categories WHERE parent_id IS NOT NULL")[0][0] == 4 and q("SELECT COUNT(*) FROM category_fields")[0][0] == 6)
n = q("SELECT COUNT(*) FROM categories WHERE section!='medical'")[0][0]  # تصنيفات المنتجات الطبية تُبذر تلقائيًا عند أول تشغيل للخادم بعد تفعيل القسم
r = run("--region", "3", "--fee", "99", "--commission-type", "percent", "--commission-value", "50")
ok("rerun is idempotent, keeps existing values", q("SELECT fee FROM region_fees")[0][0] == 10.0 and q("SELECT value FROM settings WHERE key='commission_value'") == [("2.0",)] and q("SELECT COUNT(*) FROM categories WHERE section!='medical'")[0][0] == n)
run("--region", "3", "--fee", "12", "--commission-type", "fixed", "--commission-value", "3", "--overwrite")
ok("--overwrite updates", q("SELECT fee FROM region_fees")[0][0] == 12.0)
ok("no users created", q("SELECT COUNT(*) FROM users")[0][0] == 0)
print("ALL PASSED")
