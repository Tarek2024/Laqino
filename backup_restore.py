#!/usr/bin/env python3
"""نسخ احتياطي واستعادة للاقينو (بدون مكتبات خارجية).

  python3 backup_restore.py backup  [--out DIR] [--keep N]
  python3 backup_restore.py restore --file ARCHIVE.tgz [--force]

- backup: نسخة متسقة أثناء عمل الخادم (SQLite online backup) + فحص سلامة، ثم تغليف laqino.db + uploads/ في .tgz، وحذف الأقدم من N نسخة.
- restore: يتحقق من الأرشيف (مسارات آمنة + سلامة القاعدة) قبل لمس أي شيء؛ لا يستبدل قاعدة موجودة إلا بـ --force،
  وعندها يحتفظ بالقديم بجانبه باسم .before-restore-<وقت> (لا يحذف أي بيانات). أوقف الخادم قبل الاستعادة.
المسارات من LAQINO_DB (الافتراضي laqino.db) و LAQINO_UPLOADS (الافتراضي uploads).
"""
import argparse, os, re, shutil, sqlite3, sys, tarfile, tempfile, time

DB = os.environ.get("LAQINO_DB", "laqino.db")
UP = os.environ.get("LAQINO_UPLOADS", "uploads")
PATTERN = re.compile(r"^laqino-\d{8}-\d{6}\.tgz$")


def die(msg, code=1):
    print("خطأ: " + msg, file=sys.stderr); sys.exit(code)


def integrity_ok(path):
    try:
        c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        try: return c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] > 0
        finally: c.close()
    except sqlite3.Error:
        return False


def do_backup(out, keep):
    if not os.path.exists(DB): die("قاعدة البيانات غير موجودة: " + DB)
    os.makedirs(out, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S"); final = os.path.join(out, "laqino-%s.tgz" % ts)
    with tempfile.TemporaryDirectory() as tmp:
        snap = os.path.join(tmp, "laqino.db")
        src = sqlite3.connect(DB, timeout=30); dst = sqlite3.connect(snap)
        try: src.backup(dst)  # consistent snapshot even while the server is writing
        finally: dst.close(); src.close()
        if not integrity_ok(snap): die("فشل فحص سلامة النسخة؛ لم تُنشأ نسخة")
        part = final + ".part"
        with tarfile.open(part, "w:gz") as t:
            t.add(snap, arcname="laqino.db")
            if os.path.isdir(UP): t.add(UP, arcname="uploads")
        os.replace(part, final)  # a half-written archive never carries the final name
    olds = sorted(f for f in os.listdir(out) if PATTERN.match(f))
    for f in olds[:-keep] if keep > 0 else []:
        os.remove(os.path.join(out, f))
    print(final)
    return final


def safe_members(t):
    names = []
    for m in t.getmembers():
        n = m.name
        if n.startswith("/") or ".." in n.split("/") or not (n == "laqino.db" or n == "uploads" or n.startswith("uploads/")): die("الأرشيف يحوي مسارًا غير مسموح: " + n)
        if not (m.isfile() or m.isdir()): die("الأرشيف يحوي عنصرًا غير مسموح (روابط/أجهزة): " + n)
        names.append(n)
    if "laqino.db" not in names: die("الأرشيف لا يحوي laqino.db")
    return t.getmembers()


def do_restore(archive, force):
    if not os.path.isfile(archive): die("الملف غير موجود: " + archive)
    if os.path.exists(DB) and not force: die("قاعدة البيانات موجودة (%s). استخدم --force للاستبدال مع الاحتفاظ بنسخة القديمة." % DB, 2)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with tarfile.open(archive, "r:gz") as t:
                members = safe_members(t)
                t.extractall(tmp, members=members)
        except (tarfile.TarError, OSError, EOFError) as e:
            die("الأرشيف تالف أو غير صالح: %s" % e)
        db = os.path.join(tmp, "laqino.db")
        if not integrity_ok(db): die("قاعدة البيانات داخل الأرشيف غير سليمة؛ لم يُمس شيء")
        stamp = time.strftime("%Y%m%d-%H%M%S"); kept = []
        for suf in ("", "-wal", "-shm"):  # the -wal/-shm move together with the db, so the kept copy still opens with its recent writes
            if os.path.exists(DB + suf): shutil.move(DB + suf, "%s.before-restore-%s%s" % (DB, stamp, suf))
        if os.path.exists("%s.before-restore-%s" % (DB, stamp)): kept.append(DB)
        if os.path.isdir(UP): shutil.move(UP, "%s.before-restore-%s" % (UP.rstrip("/"), stamp)); kept.append(UP)
        os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
        shutil.move(db, DB)
        up_src = os.path.join(tmp, "uploads")
        if os.path.isdir(up_src): shutil.move(up_src, UP)
        else: os.makedirs(UP, exist_ok=True)
    print("تمت الاستعادة إلى %s و%s" % (DB, UP))
    for k in kept: print("نُسخ القديم إلى %s.before-restore-%s" % (k.rstrip("/"), stamp))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="نسخ احتياطي واستعادة للاقينو")
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("backup"); b.add_argument("--out", default="backups"); b.add_argument("--keep", type=int, default=14)
    r = sp.add_parser("restore"); r.add_argument("--file", required=True); r.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "backup": do_backup(a.out, a.keep)
    else: do_restore(a.file, a.force)
