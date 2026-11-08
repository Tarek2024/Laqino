"""Phase 90: FCM payload safety, destinations and legacy-call compatibility."""
import sqlite3
import fcm
import notif


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print("PASS", name)


def main():
    shop = fcm.build_message("device-token", "shop", 120, "/shop.html#o")["message"]
    check("shop kind uses the shop notification text", shop["notification"]["body"] == fcm.TEXTS["shop"])
    check("shop push carries only kind and allowlisted internal destination",
          shop["data"] == {"kind": "shop", "url": "/shop.html#o"})
    check("FCM android notification uses Laqino channel",
          shop["android"]["notification"]["channel_id"] == fcm.CHANNEL)

    medical = fcm.build_message("device-token", "medical", 120, "/pharmacy.html")["message"]
    check("medical destination is allowlisted", medical["data"] == {"kind": "medical", "url": "/pharmacy.html"})
    inquiry = fcm.build_message("device-token", "inquiry", 120, "/pharmacy.html")["message"]
    check("new pharmacy inquiry has its own message kind and route",
          inquiry["data"] == {"kind": "inquiry", "url": "/pharmacy.html"} and inquiry["notification"]["body"] == fcm.TEXTS["inquiry"])
    for kind in ("product_update", "shop_update", "order_update"):
        msg = fcm.build_message("device-token", kind, 120, "/")["message"]
        check(kind + " is a customer update routed to the app home",
              msg["data"] == {"kind": kind, "url": "/"} and msg["notification"]["body"] == fcm.TEXTS[kind])
    bad = fcm.build_message("device-token", "shop", 120, "//attacker.example")["message"]
    check("external or malformed destinations are discarded", bad["data"] == {"kind": "shop"})
    unknown = fcm.build_message("device-token", "not-a-kind", 120)["message"]
    check("unknown kinds safely fall back to order", unknown["data"] == {"kind": "order"})

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE fcm_tokens(user_id INTEGER, token TEXT)")
    db.execute("INSERT INTO fcm_tokens(user_id, token) VALUES(?,?)", (7, "device-token"))
    db.commit()

    old_account, old_send = fcm.service_account, fcm.send_one
    calls = []
    fcm.service_account = lambda: {"project_id": "test-project"}

    def fake_send(sa, token, kind, ttl, target=None):
        calls.append((token, kind, ttl, target))
        return 200, False

    fcm.send_one = fake_send
    try:
        check("legacy FCM send signature remains supported", fcm.send(db, [7], 90, "chat") == 1)
        check("legacy call does not add a target argument", calls[-1] == ("device-token", "chat", 90, None))
        check("target-aware FCM send works", fcm.send(db, [7], 90, "shop", target="/shop.html#o") == 1)
        check("target-aware call preserves the internal destination", calls[-1] == ("device-token", "shop", 90, "/shop.html#o"))
    finally:
        fcm.service_account, fcm.send_one = old_account, old_send
        db.close()

    # New medicine inquiries should wake only approved pharmacies in the requested regions.
    nd = sqlite3.connect(":memory:")
    nd.row_factory = sqlite3.Row
    nd.executescript("""
        CREATE TABLE medicine_inquiries(id INTEGER PRIMARY KEY, medicine_name TEXT, customer_id INTEGER, status TEXT);
        CREATE TABLE providers(user_id INTEGER PRIMARY KEY, status TEXT, region_id INTEGER);
        CREATE TABLE notifications(id INTEGER PRIMARY KEY, user_id INTEGER, kind TEXT, title TEXT, body TEXT,
                                   link TEXT, ref_type TEXT, ref_id INTEGER, created_at INTEGER);
    """)
    nd.execute("INSERT INTO medicine_inquiries VALUES(101,'دواء تجريبي',20,'open')")
    nd.executemany("INSERT INTO providers VALUES(?,?,?)", [
        (10, "approved", 4), (11, "approved", 4), (12, "pending", 4),
        (13, "approved", 8), (20, "approved", 4)
    ])
    nd.commit()
    old_hook, pushed = notif.push_hook, []
    notif.push_hook = pushed.append
    try:
        count = notif.inquiry_created(nd, 101, [4])
        check("new inquiry push hook targets only approved pharmacies in-region",
              count == 2 and pushed == [10, 11])
        check("inquiry notifications retain their pharmacy destination",
              nd.execute("SELECT COUNT(*) FROM notifications WHERE kind='provider.inquiry' AND link='pharmacy'").fetchone()[0] == 2)
    finally:
        notif.push_hook = old_hook
        nd.close()


if __name__ == "__main__":
    main()
