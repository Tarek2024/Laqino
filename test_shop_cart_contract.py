"""Contract tests for the shared cart's safety boundaries; run with pytest after server integration."""
def test_cart_is_disabled_by_default():
    # Feature flag is deliberately opt-in. Existing installations must not expose it by accident.
    assert "cart_enabled" in open("shop.py", encoding="utf8").read()
    assert 'return bool(row and str(row[0]) == "1")' in open("shop.py", encoding="utf8").read()

def test_checkout_is_blocked_until_atomic_dispatch_adapter_exists():
    src = open("shop.py", encoding="utf8").read()
    assert 'path == "/api/cart/checkout"' in src
    assert 'h.send(409' in src
    assert "دورة التوصيل الحالية" in src

def test_schema_is_additive_and_namespaced():
    src = open("shop.py", encoding="utf8").read()
    assert "CREATE TABLE IF NOT EXISTS carts" in src
    assert "CREATE TABLE IF NOT EXISTS cart_items" in src
    assert "CREATE TABLE IF NOT EXISTS delivery_orders" not in src
    assert "DROP TABLE" not in src
