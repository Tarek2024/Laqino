"""Phase 52/53 integration: periodic worker, expired claim, and safe redistribution."""
import os
import tempfile
import threading
import time

DB = tempfile.mktemp(prefix="laqino-p52-worker-", suffix=".db")
os.environ["LAQINO_DB"] = DB
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp(prefix="laqino-p52-up-")

import server

server.init("01000000000", "AdminPass123")
rx = server.rx
c = server.db()

def scalar(conn, sql, args=()):
    return conn.execute(sql, args).fetchone()[0]

def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS " + message)

try:
    now = int(time.time())
    region_row = (
        c.execute("SELECT id FROM regions WHERE level='markaz' ORDER BY id LIMIT 1").fetchone()
        or c.execute("SELECT id FROM regions ORDER BY id LIMIT 1").fetchone()
    )
    assert region_row, "No region available in temporary database"
    region = int(region_row["id"])

    # Enable the real claim path and keep the test deadline in the future.
    for key, value in (
        ("rx_distribution_mode", "auto"),
        ("rx_claim_mode", "1"),
        ("rx_claim_timeout_minutes", "10"),
        ("rx_total_timeout_minutes", "60"),
    ):
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    customer = c.execute(
        "INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("01090530000", "Test Customer", server.hp("password1", "abababababababab"),
         "abababababababab", "customer", region, now)
    ).lastrowid

    providers = []
    for i in range(3):
        pid = c.execute(
            "INSERT INTO users(phone,name,pw_hash,salt,role,region_id,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            ("0109053%04d" % (i + 1), "Test Pharmacy %d" % i,
             server.hp("password1", "cdcdcdcdcdcdcdcd"), "cdcdcdcdcdcdcdcd",
             "medical_provider", region, now)
        ).lastrowid
        c.execute(
            "INSERT INTO providers(user_id,name_ar,kind,region_id,address,status,created_at,distribution_enabled) "
            "VALUES(?,?,'pharmacy',?,?,'approved',?,1)",
            (pid, "Test Pharmacy %d" % i, region, "Test address", now)
        )
        providers.append(pid)

    file_id = c.execute(
        "INSERT INTO files(owner_id,path,mime,size,created_at) VALUES(?,?,?,?,?)",
        (customer, "worker-test.png", "image/png", 1, now)
    ).lastrowid

    rx_id = c.execute(
        "INSERT INTO prescriptions(customer_id,region_id,file_id,note,status,created_at,kind) "
        "VALUES(?,?,?,'worker integration test','pending',?,'rx')",
        (customer, region, file_id, now - 60)
    ).lastrowid
    c.commit()

    # Enter the same claim flow used by the application.
    result = rx.auto_forward(c, rx_id)
    c.commit()

    claim = c.execute(
        "SELECT provider_id, expires_at FROM rx_claims "
        "WHERE prescription_id=? AND status='active'",
        (rx_id,)
    ).fetchone()

    if not claim:
        # In broadcast mode auto_forward may create offers without a claim.
        # Accept one eligible offer to create the actual reservation.
        accepted = None
        class Handler:
            def __init__(self): self.out = None
            def body(self): return {}
            def send(self, code, obj): self.out = (code, obj)

        for pid in providers:
            cc = server.db()
            try:
                h = Handler()
                handled = rx.handle(
                    h, cc, {"id": pid, "role": "medical_provider"},
                    "POST", "/api/provider/prescriptions/%d/accept" % rx_id, {}
                )
                if handled and h.out and h.out[0] == 200:
                    accepted = pid
                    break
                print(
                    "ACCEPT DIAGNOSTIC:",
                    "provider_id=", pid,
                    "handled=", handled,
                    "response=", repr(h.out),
                    "offers=",
                    cc.execute(
                        "SELECT provider_id, state FROM rx_offers WHERE prescription_id=?",
                        (rx_id,)
                    ).fetchall()
                )
            finally:
                cc.close()

        c.commit()
        claim = c.execute(
            "SELECT provider_id, expires_at FROM rx_claims "
            "WHERE prescription_id=? AND status='active'",
            (rx_id,)
        ).fetchone()
        check(accepted is not None and claim is not None,
              "real acceptance creates an active claim")
    else:
        check(True, "claim flow created an active claim")

    old_provider = int(claim["provider_id"])

    # Force expiry while keeping the overall prescription deadline valid.
    expired_at = int(time.time()) - 1
    c.execute(
        "UPDATE rx_claims SET expires_at=? WHERE prescription_id=? AND status='active'",
        (expired_at, rx_id)
    )
    c.commit()

    # Run the actual periodic worker briefly. Its normal minimum interval is
    # 5 seconds, so the test observes database state until a bounded deadline.
    stop = threading.Event()
    worker = threading.Thread(
        target=server.rx_claim_worker,
        kwargs={"stop_event": stop, "interval": 5, "db_factory": server.db},
        daemon=True,
    )
    worker.start()

    deadline = time.time() + 12
    new_provider = None
    while time.time() < deadline:
        time.sleep(0.25)
        check_conn = server.db()
        try:
            active = check_conn.execute(
                "SELECT provider_id FROM rx_claims "
                "WHERE prescription_id=? AND status='active' AND expires_at>?",
                (rx_id, int(time.time()))
            ).fetchone()
            if active:
                new_provider = int(active["provider_id"])
                break
        finally:
            check_conn.close()

    stop.set()
    worker.join(timeout=7)

    check(not worker.is_alive(), "periodic worker stops cleanly")
    check(
        scalar(c, "SELECT COUNT(*) FROM rx_claims WHERE prescription_id=? AND status='expired'", (rx_id,)) >= 1,
        "expired claim history is preserved"
    )
    check(
        scalar(c, "SELECT COUNT(*) FROM rx_claim_attempts WHERE prescription_id=?", (rx_id,)) >= 1,
        "claim attempts are persisted"
    )
    check(
        scalar(c, "SELECT COUNT(*) FROM rx_claims WHERE prescription_id=? AND status='active'", (rx_id,)) <= 1,
        "no more than one active claim exists"
    )

    if rx.distribution_mode(c) == "auto" and scalar(
        c, "SELECT value FROM settings WHERE key='rx_claim_mode'"
    ) == "1":
        check(
            scalar(c, "SELECT COUNT(*) FROM rx_offers WHERE prescription_id=? AND state='open'", (rx_id,)) >= 1
            or new_provider is not None,
            "expired reservation is redistributed or offered to remaining eligible pharmacies"
        )

    if new_provider is not None:
        check(new_provider != old_provider,
              "expired reservation is not assigned back to the previous pharmacy")

    print("INTEGRATION TEST FINISHED")
finally:
    c.close()
    try:
        os.remove(DB)
    except OSError:
        pass
    for suffix in ("-wal", "-shm"):
        try:
            os.remove(DB + suffix)
        except OSError:
            pass
