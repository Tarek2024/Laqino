# المرحلة 8 (الدفعة 1) — إشعارات أندرويد عبر FCM + هيكل غلاف Capacitor

## 1. القرار والنطاق
لم يُحسم شكل الغلاف نصًا، فاخترت الأضيق الآمن اتساقًا مع التوثيق («Capacitor + FCM بمراحل»): **غلاف يفتح موقعك نفسه** (لا نسخة ثانية من الواجهة)، وجهة السيرفر جاهزة ومقفولة حتى تضع مفتاح Firebase. Web Push الحالي للمندوب/المحادثة لم يُمس ويعمل كما كان.
**بيئتي بلا Android SDK ولا Firebase: لم يُبنَ APK ولم يُرسل إشعار حقيقي.** كل ما سبق مُختبَر على خادم Google وهمي (يتحقق من توقيع JWT فعليًا) وعلى Capacitor وهمي في Chromium.

## 2. ما أُنجز
- `fcm.py` (بنمط notif/chat/svc، لا يستورد server.py): جدول `fcm_tokens`؛ `POST /api/fcm/register` و`/api/fcm/unregister` (مستخدم مسجّل)، `GET /api/admin/fcm/status` (إدارة/موظف: `enabled` + عدد الأجهزة). إرسال FCM HTTP v1 بتوقيع RS256 (مكتبة cryptography الموجودة أصلًا للـVAPID) وتخزين مؤقت لتوكن الوصول.
- **مقفول افتراضيًا:** بلا `LAQINO_FCM_SERVICE_ACCOUNT` يرجع التسجيل 503 ولا يُرسل شيء ولا تُلمس الشبكة. ملف تالف أو `token_uri` خارج `googleapis.com` = معطّل بأمان.
- **الرسالة عامة بلا بيانات** مثل Web Push: عنوان «لاقينو» + نص ثابت («طلب توصيل جديد في منطقتك» / «عندك رسالة جديدة»)، `collapse_key`/`tag` فيستبدل الإيقاظ المتكرر نفس الإشعار، أولوية عالية، TTL محصور 30–3600 ث.
- توكن ميت (404/UNREGISTERED) يُحذف تلقائيًا. 5 أجهزة كحد أقصى لكل مستخدم **بإبقاء الأحدث** (إعادة تثبيت التطبيق تولّد توكنًا جديدًا فلا نرفض). توكن جهاز يُنقل لحساب آخر إن سجّله (هاتف مشترك).
- ربط `server.py` (سطور قليلة): `import fcm` + `fcm.install` + `fcm.handle`؛ `_push_to_users` يرسل FCM بعد Web Push (وسيط `native=False` للكنسة الأخيرة، لأن إشعار أندرويد لا يُسحب)؛ المندوب يُعتبر مؤهَّلًا للإيقاظ إن كان عنده اشتراك Web Push **أو** توكن أندرويد؛ إيقاظ المحادثة يرسل FCM بنوع `chat`.
- `static/native.js`: خامل تمامًا خارج غلاف Capacitor. داخله: طلب إذن الإشعارات، قناة `laqino_alerts`، تسجيل التوكن بعد تسجيل الدخول (مزامنة كل 15ث لأن الدخول يأتي بعد فتح التطبيق)، حذفه عند `/api/logout`، والضغط على الإشعار يفتح `/courier.html` أو `/market.html#/chats`. محمّل في `index.html` و`courier.html`. كاش `laqino-v40`.
- `android/`: `package.json` وCapacitor 6 و`capacitor.config.json` (`com.laqino.app`، `server.url` **غيّره**، `cleartext:false`) و`www/index.html` احتياطي و`README_ANDROID.md` بخطوات Firebase والبناء.

## 3. الملفات
جديد: `fcm.py` `52f9e8f0e06c`، `static/native.js` `db9f143610eb`، `android/*`، `test_phase8_fcm.py` (35 فحصًا)، `test_phase8_native_browser.py` (6 فحوص Chromium)، هذا الملف. معدّل: `server.py` `7f2453d03c32`، `static/index.html`، `static/courier.html`، `static/sw.js` `fef3668c448e`، `Dockerfile` (+fcm.py).

## 4. لم يُنفَّذ / لم يُجرَّب (بصدق)
- لم يُبنَ APK، ولم يُجرَّب `native.js` على جهاز حقيقي (الاختبار على Capacitor وهمي؛ سلوك `window.Capacitor.Plugins.PushNotifications` مع صفحة بعيدة `server.url` يحتاج تأكيدك على الهاتف).
- لم يُرسل إشعار إلى خدمة Firebase الحقيقية؛ صيغة رسالة v1 مبنية على التوثيق ومحاكاة.
- **إشعار أندرويد لا يُسحب** بعد قبول الطلب/إلغائه (Web Push كان يُمسح)؛ والإيقاظ المتكرر كل 25ث (حتى 20 مرة) قد يُصدر نغمة كل مرة رغم استبدال نفس الإشعار.
- جرس الإشعارات (حالة الطلب، الموافقات...) ما زال بالاستعلام الدوري لا FCM. لا iOS. لا أيقونة/شاشة بداية مخصصة للتطبيق، ولا توقيع Release أو نشر على Play.
- خارج النطاق ولم أصلحه: تحذير `no such table: listing_reports` في `test_phase7_overview` (الجدول يُنشأ في `market.py`)؛ العدّاد يرجع 0 بأمان. لم أتحقق إن كان يحدث على قاعدة حقيقية.

## 5. التطبيق
نسخة احتياطية (`backup_restore.py backup`) ← فك الـZIP فوق المشروع ← `python3 test_phase8_fcm.py` ← إعادة تشغيل الخادم (ينشئ `fcm_tokens` تلقائيًا). بلا `LAQINO_FCM_SERVICE_ACCOUNT` لا فرق في السلوك عن م7. الغلاف: `android/README_ANDROID.md`.
الرجوع: استرجاع `server.py`/`Dockerfile`/`sw.js`/`index.html`/`courier.html` وحذف `fcm.py` و`native.js`؛ جدول `fcm_tokens` الفارغ لا يضر.

## 6. الخطوة التالية
جرّب الغلاف على هاتفك وأبلغني (الدفعة 2 تعتمد على نتيجتك: سحب الإشعار بإرسال data-only، جرس الإشعارات عبر FCM، أيقونات). ثم المرحلة 9 (التكامل والإصدار).

## 7. نتيجة التشغيل الكامل
71 ملف اختبار (69 + ملفا م8)، كلها exit 0 في تشغيل نظيف واحد، بلا أي سطر FAIL.
