# Smart shop menu rollout (draft)

- Shop menu categories are tenant-scoped and separate from shop types.
- Existing items remain valid with a nullable category; category archival unassigns items without deleting them.
- Excel import accepts an optional category column. Clear type-specific name matches may be inferred; ambiguous items remain unassigned.
- If a shop already has manually maintained categories, automatic inference only attaches to an exact matching category and does not create a competing section.
- Public menu responses include active categories and each available item's category ID.
- Shop owner category management is restricted to the approved owner of that shop.
- Customer menu uses a horizontal category strip, search, and vertical product rows.
- Shop owners can manually reorder all active categories and items; the order is stored per shop and reflected in the public menu.
- Owners can mark up to 20 items as featured; featured available items are shown in a dedicated "اختيارات المحل" section before the regular menu.
- Menu-order writes validate the complete active category/item ID sets against the authenticated shop owner to prevent cross-shop or partial reorder updates.
- Merchant order counts refresh while the owner is viewing any tab; the existing delivery lifecycle and image upload endpoints remain unchanged.

This branch and its pull request are draft-only until regression checks and review pass.
