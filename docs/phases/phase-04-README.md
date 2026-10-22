# المرحلة 4 — سوق لاقينو: المحادثة داخل التطبيق + اختيار البائع لطريقة التواصل

## 1. الهدف والقرار
قرار المالك: لكل إعلان يختار البائع طريقة التواصل: **محادثة داخل التطبيق فقط** (`chat`، الرقم مخفي) أو **الرقم فقط** (`phone`) أو **الاثنان** (`both`). الافتراضي `both` لكل الإعلانات القائمة والجديدة حفاظًا على السلوك السابق (تسجيل دخول + حد ساعي لعرض الرقم)، والبائع يقيّده متى شاء.

## 2. ما أُنجز فعليًا
**الخادم**
- وحدة `chat.py` (بنمط rx/products، لا تستورد `server.py`) + جداول بإضافة فقط: `chat_threads` (محادثة واحدة لكل مشترٍ في كل إعلان)، `chat_messages`، `chat_reports`، وعمود `listings.contact_mode` (ALTER آمن ومتكرر).
- المسارات: `POST /api/listings/<id>/contact-mode`، `POST /api/listings/<id>/chat`، `GET /api/chats`، `GET /api/chats/<id>?after=`، `POST /api/chats/<id>/messages|block|report`، وللإدارة `GET /api/admin/chats/reports`، `GET /api/admin/chats/<id>` (فقط إن وُجد بلاغ)، `POST /api/admin/chats/reports/<id>/resolve`.
- `GET /api/listings/<id>/contact` يُرفض 403 إن اختار البائع `chat`؛ غير ذلك يمر لـ `server.py` كما كان. إنشاء الإعلان يقبل `contact_mode`، وتفاصيل الإعلان وقائمته العامة و`/api/my/listings` ترجعه (بلا أي رقم).
- القواعد: الرسالة 1–1000 حرف، 20 رسالة/دقيقة (429)، 30 محادثة جديدة/يوم (429)، لا مراسلة لنفسك، المحادثة مرئية لطرفيها فقط (غيرهما 404)، الإعلان غير المعتمد لا يقبل رسائل جديدة (409) والتاريخ يبقى مقروءًا، حظر من أي طرف (لا يرفعه إلا من حظر)، بلاغ للإدارة، والإدارة لا تقرأ المحادثة إلا بعد بلاغ عليها. علامة القراءة تتحدّث عند فتح المحادثة لا عند الإرسال.
- إشعار الجرس: إشعار واحد غير مقروء لكل محادثة، الرابط `chat` ← `/market.html#/chats`.
- **Web Push للمحادثة:** مسارات عامة لأي مستخدم مسجّل `GET /api/push/key` و`POST /api/push/subscribe|unsubscribe` (نفس جدول `push_subs` ونفس مفتاح VAPID، حد 5 أجهزة). عند رسالة جديدة يُوقَظ جهاز المستلم فقط (إيقاظ بلا بيانات، بفاصل 30 ثانية لكل محادثة) و`POST /api/push/state` يرجع الآن أعدادًا وعلامة فقط: `{pending, chat, courier}`.

**الواجهات**
- `market.html`: أزرار «راسل البائع» و«إظهار رقم البائع» حسب اختيار البائع، ومنتقي الطريقة لصاحب الإعلان، وشاشتا «محادثاتي» والمحادثة (تحديث كل 5 ثوانٍ وهي مفتوحة)، حظر/إبلاغ، وبطاقة تفعيل/إيقاف إشعارات الرسائل، وتسجيل الـ service worker. كل النصوص بـ `textContent`.
- `index.html`: منتقي «طريقة التواصل» في نموذج إنشاء الإعلان؛ بطاقة الإعلان تعرض «راسل البائع» و/أو «تواصل مع البائع» حسب الاختيار؛ وفي «إعلاناتي» منتقي لتغيير الطريقة بعد النشر.
- `admin.html`: تبويب جديد «بلاغات المحادثات» (قائمة البلاغات المفتوحة، عرض المحادثة، تمت المعالجة/تجاهل). صار عدد أقسام الإدارة 19.
- `sw.js` (v35): تنبيه المندوب كما كان حرفيًا وله الأولوية؛ إن لم يوجد طلب وكان هناك رسائل غير مقروءة يُعرض إشعار عادي يفتح «محادثاتي»؛ دون اتصال وعلى جهاز معروف أنه ليس مندوبًا لا يظهر تنبيه مندوب أبدًا. `notificationclick` يفتح الرابط الذي يحمله الإشعار (الافتراضي صفحة المندوب).

## 3. الملفات
جديد: `chat.py`، `test_phase4_chat.py`، `test_phase4_chat_ui.py`، `test_phase4_sw_push.py`، `test_phase4_browser.py`، `test_market_dom_harness.js`، `test_sw_push_harness.js`، هذا الملف.
معدّل: `server.py`، `Dockerfile` (+`chat.py`)، `static/market.html`، `static/index.html`، `static/admin.html`، `static/notif.js`، `static/sw.js` (v35)، و`test_phase1_search.py` و`test_phase3_rx.py` (شرط الكاش «≥ الإصدار» بدل نص حرفي) و`test_phase15_admin_nav.py` و`test_phase16_compat.py` (أقسام الإدارة 19 بدل 18)، والتوثيق.
البصمات:
- `server.py` `721dd0af108e`
- `chat.py` `a47c6c75b8d9`
- `rx.py` `7f8e327e933a`
- `products.py` `f0804230b8b5`
- `gsearch.py` `6aaa9a622c7d`
- `Dockerfile` `39cd4e5f8471`
- `static/market.html` `c93ced69c580`
- `static/index.html` `77d247985aad`
- `static/admin.html` `aeae9d4db5f6`
- `static/pharmacy.html` `45c175a874ee`
- `static/notif.js` `4b039d7a57db`
- `static/sw.js` `2a3809bb265f`
- `test_phase4_chat.py` `86a3304b2d05`
- `test_phase4_chat_ui.py` `0e5b752d9589`
- `test_phase4_sw_push.py` `76852473f7e4`
- `test_phase4_browser.py` `374425138093`
- `test_market_dom_harness.js` `cc99f6a8290c`
- `test_sw_push_harness.js` `5a2b6363e831`

## 4. الاختبارات (بيئتي)
- `test_phase4_chat.py`: واجهة API كاملة (المخطط، الأوضاع، الصلاحيات، الحدود، الإشعارات، الحظر، البلاغ، الإدارة، **الإيقاظ بـ Push مقابل خادم التقاط محلي**، حد الأجهزة، فحوص نصية لـ index/admin/market).
- `test_phase4_sw_push.py`: يشغّل معالجات `sw.js` الحقيقية في vm (تنبيه المندوب لم يتغير، فرع المحادثة، حالات عدم الاتصال، النقر).
- `test_phase4_chat_ui.py`: سكربت `market.html` في محاكي DOM مصغّر.
- `test_phase4_browser.py`: **Chromium حقيقي (playwright) بمقاس موبايل** — محادثة مشترٍ/بائع بالنقر الفعلي، منع حقن HTML، حظر وبلاغ، تغيير الطريقة من السوق ومن «إعلاناتي»، وتبويب الإدارة. يُتخطى بأمان إن لم يتوفر playwright.
- الانحدار: 65 ملف اختبار كلها ناجحة.

## 5. لم يُنفَّذ / لم يُجرَّب
- **لم يُجرَّب على هاتف حقيقي ولا Docker ولا Termux.** المتصفح الحقيقي المستعمل هو Chromium على حاسوب بمحاكاة مقاس موبايل.
- **Web Push الحقيقي غير مجرَّب:** اختُبر إرسال الإيقاظ للخادم المحلي (VAPID بلا بيانات) ومنطق `sw.js` في vm، لكن لم يُجرَّب مع خدمة دفع فعلية (FCM/Mozilla/Apple) ولا على آيفون.
- الاشتراك في الإشعارات مشترك بين المندوب والمحادثة (نفس الجهاز/الـ endpoint): «إيقاف» التنبيهات من صفحة المندوب يوقف إشعارات الرسائل على ذلك الجهاز أيضًا.
- **لا صور/مرفقات في المحادثة** (نصوص فقط) — تحتاج قرارًا: مسار رفع جديد وحدود حجم ومراجعة.
- المحادثة بالاستعلام الدوري (5 ثوانٍ) داخل الصفحة المفتوحة؛ لا WebSocket.
- لم يُغيَّر حد الساعة لعرض الأرقام (`contact_guard`) ولا قرار «مقدم الخدمة كحساب».

## 6. التطبيق (Termux)
```
cd ~/laqino-phase14
python3 backup_restore.py backup --out ~/laqino-backups --keep 14
unzip -o ~/storage/downloads/laqino-cumulative-phase-04.zip -d ~/
python3 test_phase4_chat.py && python3 test_phase4_sw_push.py && python3 test_phase4_chat_ui.py   # يتوقعون ALL PASSED
# أعد تشغيل الخادم (ملف جديد chat.py + ALTER على listings)، ثم تحديث كامل للتطبيق (كاش v35)
```
**الرجوع:** استرجع النسخة الاحتياطية بـ `backup_restore.py` (الجداول `chat_*` والعمود `contact_mode` لا تضر الخادم القديم).

## 7. الخطوة التالية
المرحلة 5 (الخدمات المحلية وطلبات العملاء). المتبقي من المرحلة 4 بقرارك: صور المحادثة، واختبار Push حقيقي على هاتف.
