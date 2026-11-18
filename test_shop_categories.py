# Regression tests for per-shop menu categories and safe Excel category inference.
import os
import sqlite3
import urllib.parse
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
menu_status, menu = call("GET", "/shops/%d/menu?q=%s&limit=40" % (shop, urllib.parse.quote("عصير اختبار")))
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
# Public menu pagination: large menus must be complete but never arrive as one huge response.
perf_cat_status, perf_cat_row = call("POST", prefix, {"name_ar": "قسم الأداء"}, owner)
perf_cat = perf_cat_row.get("id")
now = 1900000000
c = sqlite3.connect(base.DB)
existing = c.execute("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active' AND is_available=1", (shop,)).fetchone()[0]
for n in range(205):
    c.execute("INSERT INTO shop_items(shop_id,name_ar,description,price,is_available,sort,is_featured,status,created_at,updated_at,category_id) VALUES(?,?,?,?,1,?,0,'active',?,?,?)",
              (shop, "عنصر أداء %03d" % n, "عنصر لاختبار تحميل المنيو", 5 + n, 10000 + n, now, now, perf_cat))
c.commit()
c.close()
total_public = sql("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active' AND is_available=1", shop)[0][0]
first_status, first_page = call("GET", "/shops/%d/menu?limit=40&offset=0" % shop)
ok("large public menu returns a bounded first page with metadata",
   first_status == 200 and len(first_page["items"]) == 40 and first_page["total_items"] == total_public
   and first_page["offset"] == 0 and first_page["has_more"] is True)
second_status, second_page = call("GET", "/shops/%d/menu?limit=40&offset=40" % shop)
ok("next menu page advances without repeating first-page items",
   second_status == 200 and len(second_page["items"]) == 40
   and not ({x["id"] for x in first_page["items"]} & {x["id"] for x in second_page["items"]}))
all_ids = []
offset = 0
while True:
    page_status, page = call("GET", "/shops/%d/menu?limit=40&offset=%d" % (shop, offset))
    if page_status != 200:
        break
    all_ids.extend(x["id"] for x in page["items"])
    offset += len(page["items"])
    if not page["has_more"]:
        break
ok("all pages expose every available item exactly once",
   page_status == 200 and len(all_ids) == total_public and len(set(all_ids)) == total_public)
cat_status, cat_page = call("GET", "/shops/%d/menu?limit=40&category_id=%d" % (shop, perf_cat))
ok("server-side category filter returns only items from that shop category",
   perf_cat_status == 201 and cat_status == 200 and cat_page["total_items"] == 205
   and all(x["category_id"] == perf_cat for x in cat_page["items"]))
search_status, search_page = call("GET", "/shops/%d/menu?q=%s" % (shop, urllib.parse.quote("عنصر أداء 007")))
ok("server-side menu search returns matching item names",
   search_status == 200 and len(search_page["items"]) == 1 and search_page["items"][0]["name_ar"] == "عنصر أداء 007")
ok("menu page size and category validation are bounded",
   call("GET", "/shops/%d/menu?limit=500" % shop)[0] == 400
   and call("GET", "/shops/%d/menu?category_id=999999" % shop)[0] == 400)

# Swipe hint must remain visible with one category: the customer can still swipe between "الكل" and that category.
shops_ui = open(os.path.join(base.HERE, "static", "shops.html"), encoding="utf-8").read()
ok("single-category menu shows swipe hint", "const swipeHint=cats.length>0?" in shops_ui)

print("SHOP CATEGORY TESTS ALL PASS")

# Regression guards for horizontal touch navigation in the customer shop menu.
shops_ui = open(os.path.join(base.HERE, "static", "shops.html"), encoding="utf-8").read()
ok("category strip keeps native horizontal touch scrolling",
   ".menu-cats{display:flex" in shops_ui and "touch-action:pan-x" in shops_ui
   and "scroll-snap-align:center" in shops_ui)
ok("vertical page scrolling remains native while menu results accept horizontal gestures",
   "#menu-results{touch-action:pan-y" in shops_ui and ".menu-grid{touch-action:pan-y" in shops_ui)
ok("swipe starts from any product card, including image and quantity controls",
   "e.target.closest('#menu-results .gi')" in shops_ui
   and "e.target.closest('.opt-modal,[data-no-menu-swipe],input,select,textarea,a')" in shops_ui
   and "menuSwipeBlocked" not in shops_ui)
ok("swipe uses dominant horizontal movement and matching pointer identity",
   "e.pointerId!==s.id" in shops_ui and "Math.abs(dx)<Math.abs(dy)*1.3" in shops_ui)
ok("swipe direction is bidirectional and bounded by available categories",
   "(dx<0?1:-1)" in shops_ui and "Math.max(0,Math.min(ids.length-1" in shops_ui)
ok("category toolbar is persistent and only results are replaced",
   "host.innerHTML=tools;" in shops_ui and "results.innerHTML=top+pop+list+pager" in shops_ui
   and "menu-tools-host" in shops_ui)
ok("selected category updates immediately and preserves accessible pressed state",
   "updateMenuCategoryUI();const results=$('menu-results')" in shops_ui
   and "b.setAttribute('aria-pressed',on?'true':'false')" in shops_ui)
ok("swipe click is suppressed without blocking normal taps",
   "menuSwipeClickGuard" in shops_ui and "MENU_SUPPRESS_SWIPE_TARGET=s.target" in shops_ui and "MENU_SUPPRESS_SWIPE_CLICK=false;MENU_SUPPRESS_SWIPE_TARGET=null},250)" in shops_ui)
ok("category auto-centering does not rebuild the strip",
   "active.scrollIntoView({block:'nearest',inline:'nearest',behavior:'smooth'})" in shops_ui)
