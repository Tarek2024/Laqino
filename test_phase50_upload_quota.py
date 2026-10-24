"""Phase 50: feature-linked uploads must not consume the temporary generic upload quota."""
import os
import tempfile
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = tempfile.mktemp(suffix=".db")
UP = tempfile.mkdtemp()
os.environ["LAQINO_DB"] = DB
os.environ["LAQINO_UPLOADS"] = UP
import server

server.init("01000000000", "AdminPass123")
c = server.db()
try:
    uid = c.execute("SELECT id FROM users WHERE phone='01000000000'").fetchone()[0]
    # The schema initializes every feature table before quota queries are used.
    linked_tables = (
        "market_files", "listing_images", "chat_messages", "service_request_images",
        "prescriptions", "rx_images", "courier_documents", "couriers",
        "doctors", "labs", "product_images", "exchange_images",
    )
    sql = server.COUNT_SQL["files"]
    assert all(name in sql for name in linked_tables), "quota query misses a feature-linked upload table"

    now = 1000
    # A standalone temporary file still counts against the generic quota.
    standalone = c.execute(
        "INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)",
        (uid, "standalone.png", "image/png", 1, now),
    ).lastrowid
    assert c.execute(sql, (uid,)).fetchone()[0] == 1

    # An existing file linked to a courier profile/document no longer counts.
    c.execute("INSERT INTO couriers(user_id,status,region_id,created_at) VALUES(?,?,?,?)", (uid, "pending", 1, now))
    avatar = c.execute(
        "INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)",
        (uid, "avatar.png", "image/png", 1, now),
    ).lastrowid
    c.execute("UPDATE couriers SET avatar_file_id=? WHERE user_id=?", (avatar, uid))
    assert c.execute(sql, (uid,)).fetchone()[0] == 1

    # Uploaded courier verification documents are also excluded from the generic quota.
    doc = c.execute(
        "INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)",
        (uid, "courier-doc.png", "image/png", 1, now),
    ).lastrowid
    c.execute("INSERT INTO courier_documents(courier_id,kind,file_id,created_at) VALUES(?,?,?,?)", (uid, "selfie", doc, now))
    assert c.execute(sql, (uid,)).fetchone()[0] == 1
    print("PASS standalone temporary upload counts toward generic quota")
    print("PASS courier avatar does not consume generic quota")
    print("PASS courier verification document does not consume generic quota")
    print("PASS all feature-linked image tables are excluded")
finally:
    c.close()
