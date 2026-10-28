import sqlite3
import unittest
import shop

class SharedCartIsolationTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA foreign_keys=ON")
        self.c.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY, region_id INTEGER);
            CREATE TABLE regions(id INTEGER PRIMARY KEY, parent_id INTEGER);
            CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.c.execute("INSERT INTO users(id,region_id) VALUES(1,10),(2,10)")
        self.c.execute("INSERT INTO regions(id,parent_id) VALUES(10,NULL)")
        shop.install(self.c)

    def tearDown(self):
        self.c.close()

    def test_flag_is_off_by_default_and_opt_in(self):
        self.assertFalse(shop.enabled(self.c))
        self.c.execute("INSERT INTO settings(key,value) VALUES('cart_enabled','1')")
        self.assertTrue(shop.enabled(self.c))

    def test_cart_is_created_once_per_customer(self):
        first = shop._cart(self.c, 1)
        again = shop._cart(self.c, 1)
        second_customer = shop._cart(self.c, 2)
        self.assertEqual(first["id"], again["id"])
        self.assertNotEqual(first["id"], second_customer["id"])
        self.assertEqual(first["region_id"], 10)

    def test_schema_is_additive_and_does_not_create_delivery_tables(self):
        names = {r[0] for r in self.c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("carts", names)
        self.assertIn("cart_items", names)
        self.assertNotIn("delivery_orders", names)

if __name__ == "__main__":
    unittest.main()
