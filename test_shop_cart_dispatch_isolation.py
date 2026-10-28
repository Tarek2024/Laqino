"""Regression guards: the unfinished shared cart must not dispatch or alter courier orders."""
import sqlite3
import unittest
import shop


class Handler:
    def __init__(self):
        self.responses = []
    def send(self, status, payload=None, *args, **kwargs):
        self.responses.append((status, payload))
    def body(self):
        return {}


class CartDispatchIsolationTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA foreign_keys=ON")
        self.c.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY, region_id INTEGER);
            CREATE TABLE regions(id INTEGER PRIMARY KEY, parent_id INTEGER);
            CREATE TABLE providers(user_id INTEGER PRIMARY KEY);
            CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE delivery_orders(
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
                status TEXT NOT NULL, courier_id INTEGER
            );
            INSERT INTO users(id,region_id) VALUES(1,10);
            INSERT INTO regions(id,parent_id) VALUES(10,NULL);
            INSERT INTO delivery_orders(id,customer_id,status,courier_id)
                VALUES(77,1,'searching',NULL);
        """)
        self.user = {"id": 1, "role": "customer"}

    def tearDown(self):
        self.c.close()

    def test_cart_routes_do_not_claim_unrelated_delivery_routes(self):
        h = Handler()
        handled = shop.handle(h, self.c, self.user, "POST", "/api/delivery/orders", {})
        self.assertFalse(handled)
        self.assertEqual(h.responses, [])

    def test_disabled_cart_does_not_touch_existing_searching_order(self):
        h = Handler()
        before = tuple(self.c.execute(
            "SELECT id,customer_id,status,courier_id FROM delivery_orders WHERE id=77"
        ).fetchone())
        handled = shop.handle(h, self.c, self.user, "POST", "/api/cart/checkout", {})
        after = tuple(self.c.execute(
            "SELECT id,customer_id,status,courier_id FROM delivery_orders WHERE id=77"
        ).fetchone())
        self.assertTrue(handled)
        self.assertEqual(h.responses[0][0], 404)
        self.assertEqual(before, after)

    def test_enabled_but_unfinished_checkout_is_blocked_without_dispatch(self):
        self.c.execute("INSERT INTO settings(key,value) VALUES('cart_enabled','1')")
        self.c.commit()
        h = Handler()
        before = tuple(self.c.execute(
            "SELECT id,customer_id,status,courier_id FROM delivery_orders WHERE id=77"
        ).fetchone())
        handled = shop.handle(h, self.c, self.user, "POST", "/api/cart/checkout", {})
        after = tuple(self.c.execute(
            "SELECT id,customer_id,status,courier_id FROM delivery_orders WHERE id=77"
        ).fetchone())
        count = self.c.execute("SELECT COUNT(*) FROM delivery_orders").fetchone()[0]
        self.assertTrue(handled)
        self.assertEqual(h.responses[0][0], 409)
        self.assertEqual(before, after)
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
