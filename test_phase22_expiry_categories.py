# إصلاح: صيغ تاريخ الصلاحية في سوق الصيدليات + بذر تصنيفات المنتجات تلقائيًا
import os, tempfile, datetime
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, exchange, sqlite3
server.init("01000000000", "AdminPass123")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
for s, want in [("2027-06", "2027-06-30"), ("06/2027", "2027-06-30"), ("2027/06", "2027-06-30"), ("6-2027", "2027-06-30"), ("2027-6", "2027-06-30"),
                ("06/27", "2027-06-30"), ("٠٦/٢٠٢٧", "2027-06-30"), ("12/2027", "2027-12-31"), ("2027-06-15", "2027-06-15"), ("15/06/2027", "2027-06-15"), (" 06 / 2027 ", "2027-06-30")]:
    try: got = exchange._expiry(s)[0]
    except ValueError as e: got = "ERR " + str(e)
    ok("expiry %r -> %s" % (s, want), got == want)
for bad in ["", "abc", "13/2027", "00/2027", "2027-02-31", "2027", "1/2/3/4"]:
    try: exchange._expiry(bad); good = False
    except ValueError: good = True
    ok("expiry %r rejected" % bad, good)
try: exchange._clean({"title": "بنادول", "qty": 2, "expiry_date": (exchange._today() + datetime.timedelta(days=10)).strftime("%m/%Y"), "orig_price": 100, "price": 50}); m = ""
except ValueError as e: m = str(e)
ok("too-soon expiry message states remaining/min days", "60" in m and "يومًا" in m)
import products
c = sqlite3.connect(os.environ["LAQINO_DB"]); c.row_factory = sqlite3.Row
cnt = lambda: c.execute("SELECT COUNT(*) FROM categories WHERE section='medical' AND parent_id IS NOT NULL").fetchone()[0]
products.autoseed(c); ok("no auto-seed while the medical section is still hidden", cnt() == 0)
c.execute("UPDATE categories SET is_active=1 WHERE section='medical' AND parent_id IS NULL"); c.commit()
products.autoseed(c); ok("4 product categories auto-seeded once the medical section is active", cnt() == 4)
products.autoseed(c); ok("auto-seed is idempotent", cnt() == 4)
c.execute("DELETE FROM categories WHERE slug='med-supplies'"); c.commit(); products.autoseed(c)
ok("admin-deleted category is not recreated", c.execute("SELECT COUNT(*) FROM categories WHERE slug='med-supplies'").fetchone()[0] == 0)
print("ALL PASSED")
