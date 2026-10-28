"""Regression tests for safe shared-cart checkout against the existing delivery lifecycle."""
import sqlite3
import time
import unittest
import shop


class Handler:
    def __init__(self, payload=None):
        self.responses = []
        self.payload = payload or {}
    def send(self, status, payload=None, *args, **kwargs):
        self.responses.append((status, payload))
    def body(self):
        return self.payload


class CartDispatchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA foreign_keys=ON")
        self.pushed = []
        self.audits = []
        self.c.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY, region_id INTEGER);
            CREATE TABLE regions(id INTEGER PRIMARY KEY, parent_id INTEGER, is_active INTEGER DEFAULT 1);
            CREATE TABLE providers(user_id INTEGER PRIMARY KEY REFERENCES users(id), name_ar TEXT, address TEXT,
                region_id INTEGER, status TEXT);
            CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE product_offers(id INTEGER PRIMARY KEY, provider_id INTEGER, title TEXT, price REAL,
                available INTEGER, status TEXT, confirmed_at INTEGER);
            CREATE TABLE prescriptions(id INTEGER PRIMARY KEY, customer_id INTEGER, status TEXT);
            CREATE TABLE prescription_responses(prescription_id INTEGER, provider_id INTEGER, price REAL,
                status TEXT, review TEXT);
            CREATE TABLE delivery_orders(
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, region_id INTEGER NOT NULL,
                pickup_text TEXT NOT NULL, dropoff_text TEXT NOT NULL, details TEXT, fee REAL NOT NULL,
                courier_id INTEGER, status TEXT NOT NULL DEFAULT 'searching', commission REAL NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, search_started_at INTEGER NOT NULL DEFAULT 0,
                delivery_code TEXT, request_key TEXT, dropoff_lat REAL, dropoff_lng REAL,
                fare_status TEXT NOT NULL DEFAULT 'approved', comm_type TEXT, comm_value REAL, origin_type TEXT
            );
            CREATE UNIQUE INDEX ux_order_reqkey ON delivery_orders(customer_id,request_key) WHERE request_key IS NOT NULL;
            CREATE TABLE order_events(id INTEGER PRIMARY KEY, order_id INTEGER, actor_id INTEGER,
                from_status TEXT, to_status TEXT, at INTEGER);
            INSERT INTO users(id,region_id) VALUES(1,10),(20,10),(30,10);
            INSERT INTO regions(id,parent_id,is_active) VALUES(10,NULL,1);
            INSERT INTO providers(user_id,name_ar,address,region_id,status)
                VALUES(20,'صيدلية ألف','شارع 1',10,'approved'),(30,'صيدلية باء','شارع 2',10,'approved');
            INSERT INTO settings(key,value) VALUES('cart_enabled','1'),('products_enabled','1'),
                ('commission_type','fixed'),('commission_value','5');
            INSERT INTO delivery_orders(id,customer_id,region_id,pickup_text,dropoff_text,fee,status,courier_id,
                created_at,updated_at,request_key,fare_status)
                VALUES(77,1,10,'استلام قديم','تسليم قديم',0,'searching',NULL,1,1,'existing-order','none');
            INSERT INTO product_offers(id,provider_id,title,price,available,status,confirmed_at)
                VALUES(101,20,'منتج ألف',25,1,'approved',strftime('%s','now')),
                      (102,30,'منتج باء',40,1,'approved',strftime('%s','now'));
        """)
        self.user = {"id": 1, "role": "customer"}
        shop.bind(self.dispatch, self.audit,
                  "SELECT COUNT(*) FROM delivery_orders WHERE customer_id=? AND status IN ('searching','assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation')", 5, self.resolve_region)

    def resolve_region(self, c, lat, lng):
        if lat > 40:
            return ({"id":99,"name_ar":"منطقة أخرى"},None,"test")
        return ({"id":10,"name_ar":"الرياض"},None,"test")

    def dispatch(self, oid):
        # The real callback starts the existing push loop; checkout must commit first.
        self.assertFalse(self.c.in_transaction)
        self.pushed.append(oid)

    def audit(self, *args):
        self.audits.append(args)

    def tearDown(self):
        self.c.close()

    def add_item(self, source_id, provider_id, qty=1):
        cart = shop._cart(self.c, 1)
        now = int(time.time())
        self.c.execute("""INSERT INTO cart_items(cart_id,item_type,source_id,provider_id,quantity,created_at,updated_at)
                          VALUES(?,'product',?,?,?,?,?)""",
                       (cart["id"],source_id,provider_id,qty,now,now))
        self.c.commit()
        return cart

    def checkout(self, key="checkout-123"):
        return shop.handle(Handler({"request_key":key,"dropoff_text":"عنوان العميل"}), self.c, self.user,
                           "POST", "/api/cart/checkout", {})

    def test_delivery_routes_are_not_claimed_by_cart_module(self):
        h = Handler()
        self.assertFalse(shop.handle(h,self.c,self.user,"POST","/api/delivery/orders",{}))
        self.assertEqual(h.responses,[])

    def test_checkout_creates_one_normal_delivery_order_per_pharmacy_and_pushes_after_commit(self):
        self.add_item(101,20)
        self.add_item(102,30,2)
        h = Handler({"request_key":"checkout-multi","dropoff_text":"عنوان العميل"})
        handled = shop.handle(h,self.c,self.user,"POST","/api/cart/checkout",{})
        self.assertTrue(handled)
        status, payload = h.responses[0]
        self.assertEqual(status,201)
        self.assertEqual(len(payload["orders"]),2)
        self.assertEqual(len(self.pushed),2)
        orders = self.c.execute("SELECT * FROM delivery_orders WHERE id!=77 ORDER BY id").fetchall()
        self.assertEqual(len(orders),2)
        self.assertTrue(all(o["status"]=="searching" and o["courier_id"] is None for o in orders))
        self.assertTrue(all(o["fare_status"]=="none" and o["origin_type"] is None for o in orders))
        self.assertTrue(all(o["fee"]==0 and o["commission"]==5 for o in orders))
        self.assertEqual({o["region_id"] for o in orders},{10})
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM order_events WHERE to_status='searching'").fetchone()[0],2)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM cart_items").fetchone()[0],0)
        self.assertEqual(self.c.execute("SELECT status FROM carts").fetchone()[0],"checked_out")
        old = self.c.execute("SELECT status,courier_id,request_key FROM delivery_orders WHERE id=77").fetchone()
        self.assertEqual(tuple(old),("searching",None,"existing-order"))

    def test_same_idempotency_key_returns_existing_orders_without_second_dispatch(self):
        self.add_item(101,20)
        h1 = Handler({"request_key":"retry-safe","dropoff_text":"عنوان العميل"})
        shop.handle(h1,self.c,self.user,"POST","/api/cart/checkout",{})
        self.assertEqual(h1.responses[0][0],201)
        count = self.c.execute("SELECT COUNT(*) FROM delivery_orders").fetchone()[0]
        pushes = list(self.pushed)
        h2 = Handler({"request_key":"retry-safe","dropoff_text":"عنوان العميل"})
        shop.handle(h2,self.c,self.user,"POST","/api/cart/checkout",{})
        self.assertEqual(h2.responses[0][0],200)
        self.assertTrue(h2.responses[0][1]["duplicate"])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM delivery_orders").fetchone()[0],count)
        self.assertEqual(self.pushed,pushes)

    def test_invalid_line_rolls_back_all_child_orders(self):
        self.add_item(101,20)
        # Offer is rejected between add-to-cart and checkout.
        self.c.execute("UPDATE product_offers SET status='rejected' WHERE id=101")
        self.c.commit()
        h=Handler({"request_key":"invalid-line","dropoff_text":"عنوان العميل"})
        shop.handle(h,self.c,self.user,"POST","/api/cart/checkout",{})
        self.assertEqual(h.responses[0][0],409)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM delivery_orders").fetchone()[0],1)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM cart_checkouts").fetchone()[0],0)
        self.assertEqual(self.pushed,[])

    def test_region_mismatch_requires_confirmation_and_rolls_back(self):
        self.add_item(101,20)
        h=Handler({"request_key":"region-mismatch","dropoff_text":"عنوان العميل","dropoff_lat":50,"dropoff_lng":31})
        shop.handle(h,self.c,self.user,"POST","/api/cart/checkout",{})
        self.assertEqual(h.responses[0][0],409)
        self.assertIn("REGION_MISMATCH",h.responses[0][1]["error"])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM delivery_orders").fetchone()[0],1)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM cart_checkouts").fetchone()[0],0)
        self.assertEqual(self.pushed,[])
        self.assertFalse(self.c.in_transaction)

    def test_open_order_cap_is_checked_for_all_pharmacy_orders(self):
        for i in range(2,6):
            self.c.execute("""INSERT INTO delivery_orders(customer_id,region_id,pickup_text,dropoff_text,fee,status,
                created_at,updated_at,request_key,fare_status) VALUES(1,10,'x','y',0,'searching',1,1,?,'none')""",
                ("existing-%s"%i,))
        self.c.commit()
        self.add_item(101,20)
        self.add_item(102,30)
        h=Handler({"request_key":"over-cap","dropoff_text":"عنوان العميل"})
        shop.handle(h,self.c,self.user,"POST","/api/cart/checkout",{})
        self.assertEqual(h.responses[0][0],429)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM delivery_orders").fetchone()[0],5)
        self.assertEqual(self.pushed,[])

    def test_rx_quote_quantity_cannot_multiply_whole_prescription_price(self):
        h = Handler({"item_type":"rx_quote","source_id":99,"provider_id":88,"quantity":2})
        shop.handle(h,self.c,self.user,"POST","/api/cart/items",{})
        self.assertEqual(h.responses[0][0],400)
        self.assertEqual(h.responses[0][1]["error"],"كمية الروشتة يجب أن تكون 1")


if __name__ == "__main__":
    unittest.main()
