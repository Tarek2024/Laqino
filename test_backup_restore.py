# المرحلة 11 / A-7: النسخ الاحتياطي والاستعادة (بيانات اختبار في قاعدة مؤقتة فقط؛ لا يمسّ أي بيانات حقيقية).
import os, sys, json, sqlite3, subprocess, tempfile, tarfile, io, threading, time, shutil
W = tempfile.mkdtemp(); DBP = os.path.join(W, "data", "laqino.db"); UPD = os.path.join(W, "data", "uploads"); OUT = os.path.join(W, "bk")
os.makedirs(os.path.dirname(DBP)); os.makedirs(UPD)
ENV = {**os.environ, "LAQINO_DB": DBP, "LAQINO_UPLOADS": UPD}
D = os.path.dirname(os.path.abspath(__file__)); BR = os.path.join(D, "backup_restore.py")
def run(*a, **k): return subprocess.run([sys.executable, BR, *a], capture_output=True, text=True, env=ENV, **k)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
os.environ["LAQINO_DB"] = DBP; os.environ["LAQINO_UPLOADS"] = UPD
sys.path.insert(0, D); import server
server.init("01000000000", "AdminPass123")
con = sqlite3.connect(DBP); con.execute("PRAGMA journal_mode=WAL")
con.execute("INSERT INTO service_types(name_ar,name_norm) VALUES('سباكة','سباكه')"); con.commit()
open(os.path.join(UPD, "a.bin"), "wb").write(b"IMG-A" * 100)
before = con.execute("SELECT COUNT(*) FROM service_types").fetchone()[0]
r = run("backup", "--out", OUT, "--keep", "3"); arch = r.stdout.strip()
ok("backup succeeds and prints an archive path", r.returncode == 0 and arch.endswith(".tgz") and os.path.isfile(arch))
with tarfile.open(arch) as t: names = t.getnames()
ok("archive holds laqino.db and the uploads", "laqino.db" in names and "uploads/a.bin" in names and not any(n.startswith("/") or ".." in n for n in names))
ok("no half-written .part file left behind", not [f for f in os.listdir(OUT) if f.endswith(".part")])
# --- النسخة أثناء كتابة متزامنة تبقى سليمة
stop = False
def writer():
    c = sqlite3.connect(DBP, timeout=10)
    i = 0
    while not stop:
        try: c.execute("INSERT INTO service_types(name_ar,name_norm) VALUES(?,?)", (f"w{i}", f"w{i}")); c.commit(); i += 1
        except sqlite3.Error: pass
th = threading.Thread(target=writer); th.start(); time.sleep(.2)
time.sleep(1.1); r2 = run("backup", "--out", OUT, "--keep", "3"); stop = True; th.join()
ok("backup during concurrent writes succeeds", r2.returncode == 0)
with tempfile.TemporaryDirectory() as tmp:
    with tarfile.open(r2.stdout.strip()) as t: t.extract("laqino.db", tmp)
    c = sqlite3.connect(os.path.join(tmp, "laqino.db")); ok("backup taken under write load passes integrity_check", c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("SELECT COUNT(*) FROM service_types").fetchone()[0] >= before)
# --- التدوير
for _ in range(3): time.sleep(1.1); run("backup", "--out", OUT, "--keep", "3")
ok("retention keeps only the newest N archives", len([f for f in os.listdir(OUT) if f.startswith("laqino-") and f.endswith(".tgz")]) == 3)
open(os.path.join(OUT, "notes.txt"), "w").write("mine"); run("backup", "--out", OUT, "--keep", "1")
ok("retention never touches files that are not Laqino archives", os.path.isfile(os.path.join(OUT, "notes.txt")))
newest = sorted(f for f in os.listdir(OUT) if f.endswith(".tgz"))[-1]; arch = os.path.join(OUT, newest)
# --- الاستعادة
con.execute("DELETE FROM service_types"); con.execute("INSERT INTO service_types(name_ar,name_norm) VALUES('تالف','تالف')"); con.commit(); con.close()
os.remove(os.path.join(UPD, "a.bin")); open(os.path.join(UPD, "new.bin"), "wb").write(b"NEW")
r = run("restore", "--file", arch)
ok("restore refuses to overwrite an existing database without --force", r.returncode == 2 and sqlite3.connect(DBP).execute("SELECT name_ar FROM service_types").fetchone()[0] == "تالف")
bad = os.path.join(W, "bad.tgz"); open(bad, "wb").write(b"not a tar")
r = run("restore", "--file", bad, "--force")
ok("corrupt archive rejected, live data untouched", r.returncode != 0 and sqlite3.connect(DBP).execute("SELECT name_ar FROM service_types").fetchone()[0] == "تالف")
ev = os.path.join(W, "evil.tgz")
with tarfile.open(ev, "w:gz") as t:
    info = tarfile.TarInfo("../evil.txt"); info.size = 3; t.addfile(info, io.BytesIO(b"bad"))
r = run("restore", "--file", ev, "--force")
ok("path-traversal archive rejected, nothing written outside", r.returncode != 0 and not os.path.exists(os.path.join(W, "evil.txt")) and not os.path.exists(os.path.join(W, "data", "..", "evil.txt")))
bd = os.path.join(W, "baddb.tgz"); tmpf = os.path.join(W, "junk.db"); open(tmpf, "wb").write(b"X" * 4096)
with tarfile.open(bd, "w:gz") as t: t.add(tmpf, arcname="laqino.db")
r = run("restore", "--file", bd, "--force")
ok("archive with a damaged database rejected, live data untouched", r.returncode != 0 and sqlite3.connect(DBP).execute("SELECT name_ar FROM service_types").fetchone()[0] == "تالف")
ln = os.path.join(W, "link.tgz")
with tarfile.open(ln, "w:gz") as t:
    t.add(DBP, arcname="laqino.db"); info = tarfile.TarInfo("uploads/x"); info.type = tarfile.SYMTYPE; info.linkname = "/etc/passwd"; t.addfile(info)
r = run("restore", "--file", ln, "--force")
ok("archive with a symlink rejected", r.returncode != 0)
r = run("restore", "--file", arch, "--force")
ok("restore --force succeeds", r.returncode == 0)
c = sqlite3.connect(DBP)
ok("restored database equals the state at backup time", c.execute("SELECT COUNT(*) FROM service_types WHERE name_ar='تالف'").fetchone()[0] == 0 and c.execute("SELECT COUNT(*) FROM service_types WHERE name_ar='سباكة'").fetchone()[0] == 1 and c.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
ok("uploads restored to the backup state", os.path.isfile(os.path.join(UPD, "a.bin")) and not os.path.exists(os.path.join(UPD, "new.bin")))
kept_db = [f for f in os.listdir(os.path.dirname(DBP)) if f.startswith("laqino.db.before-restore-") and not f.endswith(("-wal", "-shm"))]
ok("the replaced database and uploads were kept (not deleted)", len(kept_db) >= 1 and any(f.startswith("uploads.before-restore-") for f in os.listdir(os.path.dirname(DBP))))
ok("the kept pre-restore database still holds the post-backup data", sqlite3.connect(os.path.join(os.path.dirname(DBP), kept_db[0])).execute("SELECT COUNT(*) FROM service_types WHERE name_ar='تالف'").fetchone()[0] == 1)
r = run("restore", "--file", arch + ".missing", "--force"); ok("missing archive file is a clear error", r.returncode != 0)
os.environ["LAQINO_DB"] = DBP; r = subprocess.run([sys.executable, "-c", "import server;print(server.DB)"], capture_output=True, text=True, env=ENV, cwd=D)
ok("server still opens the restored database", r.returncode == 0 and sqlite3.connect(DBP).execute("SELECT COUNT(*) FROM regions").fetchone()[0] >= 3)
shutil.rmtree(W, ignore_errors=True); print("ALL PASSED")
