# حذف حساب مندوب عنده صورة بروفايل (المرحلة 38) يجب أن ينجح ويمسح الصورة من القاعدة والقرص — دمج phase-36 فوق phase-38.
import os, tempfile, time
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db"); os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, account
server.init("01000000000", "AdminPass123")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
c = server.db(); c.execute("PRAGMA foreign_keys=ON")
now = int(time.time())
c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,created_at) VALUES('01055555555','مندوب','x','y','courier',?)", (now,))
uid = c.execute("SELECT id FROM users WHERE phone='01055555555'").fetchone()["id"]
UP = os.environ["LAQINO_UPLOADS"]; open(os.path.join(UP, "av.jpg"), "wb").write(b"x")
cols = [r["name"] for r in c.execute("PRAGMA table_info(files)")]
vals = {"owner_id": uid, "path": "av.jpg", "mime": "image/jpeg", "size": 1, "created_at": now, "name": "av.jpg", "kind": "image"}
use = [k for k in vals if k in cols]
c.execute("INSERT INTO files(%s) VALUES(%s)" % (",".join(use), ",".join("?" * len(use))), [vals[k] for k in use])
fid = c.execute("SELECT id FROM files WHERE owner_id=?", (uid,)).fetchone()["id"]
rid = c.execute("SELECT id FROM regions LIMIT 1").fetchone()[0]
c.execute("INSERT INTO couriers(user_id,status,region_id,avatar_file_id,created_at) VALUES(?,?,?,?,?)", (uid, "approved", rid, fid, now))
c.commit()
paths = account.delete_account(c, uid, UP); c.commit(); account.remove_files(paths)
ok("deleting a courier with a profile photo succeeds", True)
ok("avatar link cleared", c.execute("SELECT avatar_file_id FROM couriers WHERE user_id=?", (uid,)).fetchone()[0] is None)
ok("file record gone", c.execute("SELECT COUNT(*) FROM files WHERE id=?", (fid,)).fetchone()[0] == 0)
ok("file removed from disk", not os.path.exists(os.path.join(UP, "av.jpg")))
ok("courier suspended and unavailable", tuple(c.execute("SELECT status,is_available FROM couriers WHERE user_id=?", (uid,)).fetchone()) == ("suspended", 0))
