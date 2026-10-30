# تحديث phase-82 — الخطوة 1 من 3: «المحل يطلب مندوب» بالكود المشترك

> **الحالة: الإصدار `phase-82` — كاش الخدمة `laqino-v125`** (السابق: phase-81 / laqino-v124).
> **ده تحديث منفصل (ملفات التغيير بس)** — فكّه فوق مجلد المشروع phase-81 وتستبدل الملفات. آخر ZIP تطلعه هو الأحدث اللي تعتمد عليه.
> **اللي لسه:** الخطوة 2 (العميل يطلب من المحل) ثم الخطوة 3 (الروشتة). التفاصيل الكاملة تحت عشان أي محادثة جديدة تكمّل من غير المشروع الأصلي.

## ✅ اللي اتعمل في الخطوة 1
- `static/pdelivery.js` بقى ملف مشترك للصيدلية والمحل. إعداد اختياري بسطر واحد: `<script src="/pdelivery.js" data-pd="shop">` ← وضع المحل (نصوص «محلك/للمحل»، `delivered_by=='shop'`). **بدون `data-pd` يشتغل كصيدلية بالظبط زي ما كان.**
- في وضع المحل المكتبة **بتعرّف `window.PDL`** وبترجع بدري: `PDL.card(d, v)` (بطاقة «اطلب مندوب»، و`v`=قيم الخانات المكتوبة عشان ما تضيعش عند إعادة الرسم)، `PDL.rows`, `PDL.txt`, `PDL.trk`, `PDL.min`. مفيش جلب ولا إرسال ولا `setInterval` منها — صفحة المحل هي اللي بتجلب وتبعت.
- `static/shop.html`: اتشالت النسخة المكررة (`DLS/STP/STL/dltrk/dlmin/dltxt/dlrows/dlcard`) وبقى `const dlcard=d=>PDL.card(d,TXF)`. السكربت المشترك محمّل قبل سكربت الصفحة. باقي منطق المحل (`dlsend/dldone/dlx/dlboard/poll/ordLoad`) زي ما هو.
- النتيجة: التحديث الفوري في مكانه (poll كل 12 ثانية بيعيد رسم `#oslot` بس لو مفيش حقل متفوكس = مفيش تجمّد)، واسم المندوب ورقمه بيظهروا مع القبول (الباك إند `GET /api/owner/shops/<id>/delivery-requests` بيرجع `courier_name/courier_phone` طالما الحالة في `ACTIVE`).
- لم يُلمس: `server.py`, `shop_delivery.py`, `provider_delivery.py`, الأجرة/العمولة/المحفظة.
- الملفات: `static/pdelivery.js`, `static/shop.html`, `static/sw.js`, `VERSION`, `test_ui_page_harness.js` (يحمّل المكتبة المشتركة للصفحات اللي فيها `data-pd="shop"`), `test_phase82_step1.py` (جديد), `PROJECT_STATE.md`, الملف ده.

## الاختبارات (اللي اتشغّلت)
`test_phase82_step1.py` (9 PASS) + `test_phase69_shop_orders_ui` (14) + `test_phase69_shop_delivery` (77) + `test_phase40_provider_delivery` (44) + `test_phase75_pd_m2` (25) + `test_phase79_shop_delivery_stats` (32) — كلها PASS. **اتختبرت بـ DOM وهمي في node وسيرفر محلي، مش متصفح حقيقي ولا موبايل ولا Termux — جرّب عندك بعد التنزيل:** افتح `/shop.html` ← تبويب الطلبات ← «اطلب دليفري»، وافتح `/pharmacy.html` وتأكد إن زرار الصيدلية شغّال زي الأول.
شغّل الاختبارات واحد واحد مش بالتوازي (البورتات ثابتة).

## ⏭️ الخطوة 2 (لسه): العميل يطلب من المحل
**الهدف:** اسم المندوب ورقمه يظهروا للعميل في «طلباتي» من لحظة القبول لطلبات المحل (`origin_type='shop_order'`)، زي الصيدلية. التعديل يخص طلبات المحل فقط — **ممنوع لمس الأجرة ولا العمولة ولا المحفظة.**
**مفاتيح الكود:**
- `server.py:1321` — `GET /api/delivery/orders` (استعلام «طلباتي» للعميل). الأرقام/الأسماء بتتحجب بشرط `CASE WHEN o.status IN ACTIVE …`؛ `ACTIVE` معرّف في `server.py:339`. في استعلام المحل (`shop_delivery.py:~193`) الشرط `o.status IN ACTIVE AND o.fare_status='approved'` — يعني الاسم/الرقم حاليًا مربوط بموافقة الأجرة.
- `shop_delivery.py`: `ORDER='shop_order'`, `PICKUP='shop_pickup'`, جدول `shop_delivery_links(order_id, shop_id, kind, …)`. `server.py:356` `PICKUP_KINDS` = طلبات الاستلام (قبول مباشر بلا أجرة) — طلبات العميل من المحل (`shop_order`) **ليست** منها وليها دورة أجرة عادية (`fare_status`: proposed/approved).
- الواجهة: `static/index.html` — `osig` (سطر ~59، بصمة التحديث: فيها `courier_name,courier_id,courier_phone,fare_status`) وعرض «طلباتي» (سطر ~233-234) و`cpm` (سطر ~72، كارت المندوب). لازم التحديث يظهر بسرعة بعد القبول (راجع `osig` + فترة الـ poll).
**قاعدة وقوف:** لو إظهار الرقم قبل موافقة الأجرة محتاج تغيير في دورة الأجرة نفسها (`fare_status`) → **وقف وبلّغ** قبل ما تكمل.
**بعد الخطوة:** اختبارات جديدة + اختبارات المحل (`test_phase69_*`, `test_phase70_*`) + `test_phase22_delivery_cycle.py`، رفع الإصدار، ZIP تحديث مع README تراكمي (فيه الخطوة 3 لسه).

## ⏭️ الخطوة 3 (لسه): الروشتة — تقرير قبل أي تعديل
**الهدف:** مراجعة `rx.py` (1228 سطر) ومقارنتها بطلب المحل، وإرجاع **تقرير فقط قبل أي تعديل**، ووقوف لحد الموافقة.
**مفاتيح من التاريخ (HANDOFF.md):** `rx_completed` + `is_completed/mark_completed/open_prescription_count`، `complete_claim_on_full_approval`، `_claim_next`، `stage_of` (فيها `completed`)، `/quotes` بترجع `completed/completed_at`؛ حد 5 روشتات مفتوحة في `server.py`؛ تسمية المراحل في `static/index.html` و`admin.html`. القرار القديم: الطلب مش بيبقى `closed` (يكسر التوصيل). كروت العروض: `test_phase62_rx_quote_cards.py`.

## قواعد العمل (من صاحب المشروع)
بدون نسخة احتياطية وبدون اختبارات كتيرة — اختبارات مناسبة للنظام وبس، واستهلاك بيانات قليل. كل خطوة: ZIP تحديث منفصل + README عربي تراكمي + تقرير قصير، ويقف لحد الموافقة. الإصدار/الكاش: الخطة الأصلية «phase-82/v125» — الخطوات 2 و3 ترفع +1 لكل خطوة (phase-83/v126 ثم phase-84/v127) لأن الكاش لازم يتغير مع كل ملف واجهة جديد، إلا لو طلب غير كده.
