# Regression tests for per-shop menu categories and safe Excel category inference.
import sqlite3
import test_shop_bulk_import as base

owner, customer, shop, admin = base.owner, base.customer, base.shop, base.admin
call, sql, ok, xlsx = base.call, base.sql, base.ok, base.xlsx
prefix = "/owner/shops/%d/categories" % shop

status, category = call("POST", prefix, {"name_ar": "مشروبات"}, owner)
ok("shop owner can create a category", status == 201 and category.get("id"))
cid = category["id"]
ok("customer cannot create merchant categories", call("POST", prefix, {"name_ar": "محاولات"}, customer)[0] == 404)
ok("owner can list only their own categories", call("GET", prefix, None, owner)[1]["items"][0]["id"] == cid)

status, item = call("POST", "/owner/shops/%d/items" % shop,
                    {"name_ar": "عصير اختبار", "price": 12, "category_id": cid, "is_available": True, "image_ids": []}, owner)
ok("new item accepts a category owned by the same shop",
   status == 201 and sql("SELECT category_id FROM shop_items WHERE id=?", item["id"])[0][0] == cid)
ok("item rejects a category from another shop",
   call("POST", "/owner/shops/%d/items/%d/edit" % (shop, item["id"]),
        {"category_id": 999999}, owner)[0] == 400)

# Owner can control category/item order and select curated products for the top of the customer menu.
status, category2 = call("POST", prefix, {"name_ar": "حلويات"}, owner)
item2_status, item2 = call("POST", "/owner/shops/%d/items" % shop,
                           {"name_ar": "كيكة اختبار", "price": 25, "category_id": category2["id"]}, owner)
before_cats = call("GET", prefix, None, owner)[1]["items"]
before_items = call("GET", "/owner/shops/%d/items" % shop, None, owner)[1]["items"]
ordered = call("POST", "/owner/shops/%d/menu-order" % shop,
               {"category_ids": [category2["id"]] + [x["id"] for x in before_cats if x["id"] != category2["id"]],
                "item_ids": [item2["id"]] + [x["id"] for x in before_items if x["id"] != item2["id"]],
                "featured_item_ids": [item2["id"]]}, owner)
after_cats = call("GET", prefix, None, owner)[1]["items"]
after_items = call("GET", "/owner/shops/%d/items" % shop, None, owner)[1]["items"]
public_order = call("GET", "/shops/%d/menu" % shop)[1]["items"]
ok("merchant can save a custom category order", ordered[0] == 200 and after_cats[0]["id"] == category2["id"])
ok("merchant can save item order and mark selected products as featured",
   ordered[0] == 200 and after_items[0]["id"] == item2["id"] and after_items[0]["is_featured"] is True)
ok("customer menu puts merchant-featured products first",
   public_order[0]["id"] == item2["id"] and public_order[0]["is_featured"] is True)
ok("customer cannot change the menu order", call("POST", "/owner/shops/%d/menu-order" % shop,
   {"category_ids": [cid, category2["id"]], "item_ids": [item["id"], item2["id"]], "featured_item_ids": []}, customer)[0] == 404)
ok("menu order rejects incomplete item lists", call("POST", "/owner/shops/%d/menu-order" % shop,
   {"category_ids": [cid, category2["id"]], "item_ids": [item["id"]], "featured_item_ids": []}, owner)[0] == 400)

# Owner-managed size variants and add-ons are returned to the public menu.
groups = [
    {"name_ar": "الحجم", "kind": "variant", "required": True,
     "values": [{"name_ar": "صغير", "price_delta": 0}, {"name_ar": "كبير", "price_delta": 10}]},
    {"name_ar": "إضافات", "kind": "addon", "required": False,
     "values": [{"name_ar": "جبنة", "price_delta": 5}]},
]
option_path = "/owner/shops/%d/items/%d/options" % (shop, item["id"])
option_status, saved = call("POST", option_path, {"groups": groups}, owner)
ok("owner can save size and add-on groups", option_status == 200 and len(saved["groups"]) == 2)
ok("customer cannot edit item options", call("POST", option_path, {"groups": []}, customer)[0] == 404)
loaded_status, loaded = call("GET", option_path, None, owner)
ok("saved item options can be loaded again", loaded_status == 200 and loaded["groups"][0]["values"][1]["price_delta"] == 10)

# An existing manually-created category is preferred over an automatic guess.
data = xlsx([["اسم الصنف", "السعر"], ["عصير ليمون آلي", "15"]])
status, imported = call("POST", "/admin/shops/items-import/commit",
                        {"shop_id": shop, "data": data}, admin)
auto_id = sql("SELECT id FROM shop_items WHERE shop_id=? AND name_ar=?",
              shop, "عصير ليمون آلي")[0][0]
ok("Excel import links a confidently inferred item to an existing manual category",
   status == 200 and sql("SELECT category_id FROM shop_items WHERE id=?", auto_id)[0][0] == cid)

# The public customer menu exposes category metadata without changing the order flow.
menu_status, menu = call("GET", "/shops/%d/menu" % shop)
ok("customer menu exposes the shop's categories", menu_status == 200 and any(x["id"] == cid for x in menu.get("categories", [])))

menu_item = next((x for x in menu.get("items", []) if x["id"] == item["id"]), None)
ok("public menu exposes size and add-on choices with prices",
   menu_item is not None and len(menu_item.get("options", [])) == 2
   and menu_item["options"][0]["values"][1]["price_delta"] == 10)

# An explicit category column in Excel is authoritative and may create a new section.
data = xlsx([["اسم الصنف", "السعر", "القسم (اختياري)"], ["صنف بقسم صريح", "20", "مخبوزات"]])
status, imported = call("POST", "/admin/shops/items-import/commit",
                        {"shop_id": shop, "data": data}, admin)
explicit_id = sql("SELECT id FROM shop_items WHERE shop_id=? AND name_ar=?",
                  shop, "صنف بقسم صريح")[0][0]
explicit_category = sql("SELECT c.name_ar FROM shop_categories c JOIN shop_items i ON i.category_id=c.id WHERE i.id=?",
                        explicit_id)[0][0]
ok("explicit Excel category is preserved", status == 200 and explicit_category == "مخبوزات")

# Ambiguous products stay unassigned instead of receiving a guessed category.
data = xlsx([["اسم الصنف", "السعر"], ["منتج تجريبي غير واضح", "19"]])
status, imported = call("POST", "/admin/shops/items-import/commit",
                        {"shop_id": shop, "data": data}, admin)
unknown_id = sql("SELECT id FROM shop_items WHERE shop_id=? AND name_ar=?",
                 shop, "منتج تجريبي غير واضح")[0][0]
ok("ambiguous imported items remain without a category",
   status == 200 and sql("SELECT category_id FROM shop_items WHERE id=?", unknown_id)[0][0] is None)

# A known but non-matching suggestion must not create a new section when the owner already curated categories.
before_categories = sql("SELECT COUNT(*) FROM shop_categories WHERE shop_id=? AND is_active=1", shop)[0][0]
data = xlsx([["اسم الصنف", "السعر"], ["فول بلدي"], ["فول بلدي", "12"]])
status, imported = call("POST", "/admin/shops/items-import/commit",
                        {"shop_id": shop, "data": data}, admin)
# This row is intentionally malformed (missing price); it must not create a guessed category.
ok("unmatched inferred category does not create a new section",
   status == 200 and sql("SELECT COUNT(*) FROM shop_categories WHERE shop_id=? AND is_active=1", shop)[0][0] == before_categories)

# With no manually curated categories, a single confident type-specific match creates its section.
auto_owner = base.user("01080000003")
auto_shop = call("POST", "/shops/apply",
                 {"type_id": 1, "name_ar": "مطعم التصنيف التلقائي", "address": "شارع النصر",
                  "phone": "01012345678", "region_id": base.region}, auto_owner)[1]["id"]
call("POST", "/admin/shops/%d/review" % auto_shop, {"status": "approved"}, admin)
status, imported = call("POST", "/admin/shops/items-import/commit",
                        {"shop_id": auto_shop,
                         "data": xlsx([["اسم الصنف", "السعر"], ["فول بلدي", "15"]])}, admin)
auto_category = sql("SELECT c.name_ar FROM shop_categories c JOIN shop_items i ON i.category_id=c.id WHERE i.shop_id=?",
                    auto_shop)
ok("confident inference creates a category when the shop has no manual categories",
   status == 200 and auto_category == [("فول وطعمية",)])

# Archiving a category never deletes items; it unassigns them.
status, result = call("POST", prefix + "/%d/delete" % cid, {}, owner)
ok("archiving a category preserves and unassigns its items",
   status == 200 and sql("SELECT COUNT(*) FROM shop_items WHERE id IN (?,?) AND category_id IS NULL",
                         item["id"], auto_id)[0][0] == 2)
print("SHOP CATEGORY TESTS ALL PASS")
