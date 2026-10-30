# تحديث phase-83 — الخطوة 2 من 3: العميل يرى المندوب من لحظة القبول (طلبات المحل)

> **الحالة: الإصدار `phase-83` — كاش الخدمة `laqino-v126`** (السابق: phase-82 / laqino-v125).
> **تحديث منفصل (ملفات التغيير بس)** — فكّه فوق مجلد المشروع (بعد تحديث phase-82 الخطوة 1) واستبدل الملفات.
> **اللي لسه:** الخطوة 3 (الروشتة — تقرير قبل أي تعديل).

## ✅ اللي اتعمل
- طلب العميل من المحل (`shop_order`) لما المندوب يقبله بيبقى `fare_status='draft'`. قبل كده العميل ما كانش يشوف أي بيانات للمندوب في الحالة دي. دلوقتي **اسم المندوب ورقمه (وكارت ملفه) بيظهروا في «طلباتي» من القبول**، قبل اقتراح الأجرة.
- التعديل في `server.py` بس، في مكانين:
  1. `GET /api/delivery/orders`: `courier_id/courier_name` يظهروا في `draft` لـ`shop_order`، و`courier_phone` كمان (بشرط الطلب في `ACTIVE`).
  2. صلاحية `/api/couriers/<id>/profile|photo` للعميل: بتشمل `draft` لـ`shop_order`، عشان كارت المندوب يفتح.
- **ما اتغيرش:** دورة الأجرة (`draft ← proposed ← approved`)، الأجرة نفسها (لسه مخفية عن العميل لحد `proposed`)، العمولة، المحفظة، الطلبات العادية، وإخفاء بيانات العميل عن المندوب قبل موافقة الأجرة. الواجهة `index.html` ما اتلمستش (بتعرض اللي يرجعه الـAPI).
- **تنبيه خصوصية (قرار صاحب المشروع):** لو العميل رفض الأجرة، المندوب اللي اتشاف رقمه بيرجع الطلب للبحث والعميل يفضل عارف رقمه، وأي رقم اتعرض قبل كده بيتعرض فعلًا. لو عايز الاسم بس بدون الرقم قبل موافقة الأجرة: شيل `OR (o.origin_type='shop_order' AND o.fare_status='draft')` من شرط `courier_phone` فقط.
- الملفات: `server.py`, `VERSION`, `static/sw.js`, `PROJECT_STATE.md`, `test_phase83_step2.py` (جديد), `test_phase82_step1.py` (فحص الإصدار بقى phase-83/v126), الملف ده.

## الاختبارات (اللي اتشغّلت)
`test_phase83_step2.py` (13 PASS) + `test_phase82_step1` (9) + `test_phase69_shop_delivery` (77) + `test_phase69_shop_orders_ui` (14) + `test_phase70_shops_browse` (22) + `test_phase22_delivery_cycle` (27) + `test_phase75_pd_m2` (25) + `test_phase79_shop_delivery_stats` (32) + `test_phase40_provider_delivery` (44) — كلها PASS. **اتشغّلت على سيرفر محلي، مش متصفح حقيقي ولا موبايل.** جرّب: اطلب من محل بحساب عميل، اقبله بحساب مندوب، وافتح «طلباتي» (تظهر البيانات خلال دورة الـpoll). شغّل الاختبارات واحد واحد (البورتات ثابتة).
- ملاحظة: `check_versions.py` بيفشل أصلًا من قبل التحديث ده لأن `README.md/HANDOFF.md/STATUS.md/README_UPDATE.md` لسه بتقول phase-77. ما اتلمسوش.

## ⏭️ الخطوة 3 (لسه): الروشتة — تقرير قبل أي تعديل
**الهدف:** مراجعة `rx.py` (1228 سطر) ومقارنتها بطلب المحل، وإرجاع **تقرير فقط قبل أي تعديل**، ووقوف لحد الموافقة.
**مفاتيح من التاريخ (HANDOFF.md):** `rx_completed` + `is_completed/mark_completed/open_prescription_count`، `complete_claim_on_full_approval`، `_claim_next`، `stage_of` (فيها `completed`)، `/quotes` بترجع `completed/completed_at`؛ حد 5 روشتات مفتوحة في `server.py`؛ تسمية المراحل في `static/index.html` و`admin.html`. القرار القديم: الطلب مش بيبقى `closed` (يكسر التوصيل). كروت العروض: `test_phase62_rx_quote_cards.py`.
**الإصدار:** الخطوة 3 = phase-84 / laqino-v127.

## قواعد العمل (من صاحب المشروع)
بدون نسخة احتياطية وبدون اختبارات كتيرة — اختبارات مناسبة للنظام وبس، واستهلاك بيانات قليل. كل خطوة: ZIP تحديث منفصل + README عربي تراكمي + تقرير قصير، ويقف لحد الموافقة.
