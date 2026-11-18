# Regression tests for per-shop menu categories and safe Excel category inference.
import sqlite3
import test_shop_bulk_import as base

owner, customer, shop, admin = base.owner, base.customer, base.shop, base.admin
call, sql, ok, xlsx = base.call, base.sql, base.ok, base.xlsx
prefix = "/owner/shops/%d/categories" % shop

status, category = call("POST", prefix, {"name_ar": "مشروبات"}, owner)
ok("shop owner can create a category", status == 201 and category.get("id"))
cid = category["id"]
ok("customer cannot create merchant categories", call("POST", prefix, {"name_ar": "محاولات"}, customer)[0] == 403)
ok("owner can list only their own categories", call("GET", prefix, None, owner)[1]["items"][0]["id"] == cid)

status, item = call("POST", "/owner/shops/%d/items" % shop,
                    {"name_ar": "عصير اختبار", "price": 12, "category_id": cid, "is_available": True, "image_ids": []}, owner)
ok("new item accepts a category owned by the same shop",
   status == 201 and sql("SELECT category_id FROM shop_items WHERE id=?", item["id"])[0][0] == cid)
ok("item rejects a category from another shop",
   call("POST", "/owner/shops/%d/items/%d/edit" % (shop, item["id"]),
        {"category_id": 999999}, owner)[0] == 400)

# An existing manually-created category is preferred over an automatic guess.
data = xlsx([["اسم الصنف", "السعر"], ["عصير ليمون آلي", "15"]])
status, imported = call("POST", "/admin/shops/items-import/commit",
                        {"shop_id": shop, "data": data}, admin)
auto_id = sql("SELECT id FROM shop_items WHERE shop_id=? AND name_ar=?",
              shop, "عصير ليمون آلي")[0][0]
ok("Excel import links a confidently inferred item to an existing manual category",
   status == 200 and sql("SELECT category_id FROM shop_items WHERE id=?", auto_id)[0][0] == cid)

# Ambiguous products stay unassigned instead of receiving a guessed category.
data = xlsx([["اسم الصنف", "السعر"], ["منتج تجريبي غير واضح", "19"]])
status, imported = call("POST", "/admin/shops/items-import/commit",
                        {"shop_id": shop, "data": data}, admin)
unknown_id = sql("SELECT id FROM shop_items WHERE shop_id=? AND name_ar=?",
                 shop, "منتج تجريبي غير واضح")[0][0]
ok("ambiguous imported items remain without a category",
   status == 200 and sql("SELECT category_id FROM shop_items WHERE id=?", unknown_id)[0][0] is None)

# Archiving a category never deletes items; it unassigns them.
status, result = call("POST", prefix + "/%d/delete" % cid, {}, owner)
ok("archiving a category preserves and unassigns its items",
   status == 200 and sql("SELECT COUNT(*) FROM shop_items WHERE id IN (?,?) AND category_id IS NULL",
                         item["id"], auto_id)[0][0] == 2)
print("SHOP CATEGORY TESTS ALL PASS")
