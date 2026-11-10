# تطبيق لاقينو لأندرويد — Capacitor 8 / API 36

يعتمد تطبيق أندرويد على Capacitor لفتح واجهة لاقينو عبر WebView، مع تكاملات أندرويد الأصلية مثل إشعارات FCM والموقع. تُحمّل ملفات الواجهة مثل `static/native.js` من الموقع `https://laqino.tech`.

## حالة البناء والاختبار
- **بناء Release AAB وAPK:** نجح GitHub Actions في التشغيل [#3](https://github.com/Tarek2024/Laqino/actions/runs/42701517193) من Workflow `Build Android Release AAB`، على الفرع `feature/android-aab-release-prep` والالتزام `50a3dbb3bdaf5ec63635fc9f46282271a8d5a9fd` بتاريخ 9 نوفمبر 2026.
- **التوقيع والمخرجات:** تحقّق التشغيل من صحة توقيع AAB وAPK قبل رفعهما كـartifacts باسمَي `laqino-release-aab` و`laqino-release-apk`.
- **اختبار الهاتف:** أفاد صاحب المشروع بأنه ثبّت نسخة أندرويد من فرع GitHub واختبر الإشعارات ووظائف التطبيق الأساسية على هاتف فعلي، وكانت تعمل.
- هذان تحققان منفصلان: نجاح بناء CI لا يثبت وحده أن الملف الناتج هو نفسه الذي ثُبّت واختُبر يدويًا. عند تجهيز رفع جديد، اربط ملف AAB برقم التشغيل والالتزام المطابقين له، ثم اختبر النسخة النهائية نفسها.
- لا تعني هذه النتائج ضمان قبول Google Play؛ يلزم استكمال متطلبات Play Console والسياسات والاختبارات الخاصة بالإصدار المرفوع.
## المتطلبات (على كمبيوتر، لا Termux) — Capacitor 8 / API 36
- **Node 22+**، **JDK 21**، Android Studio (إصدار حديث يحوي SDK 36)، حساب Firebase، ونطاق **HTTPS**: `https://laqino.tech` (مضبوط في `capacitor.config.json`؛ أندرويد يمنع HTTP الصريح).
- Capacitor 8 يستهدف `compileSdk/targetSdk = 36` و`minSdk = 24` (AGP 8.13 وGradle 8.14.x). **لا تغيّر targetSdk يدويًا** (غير مدعوم من Capacitor)؛ أعلى بكثير من 35 مطلوب من Google Play للتطبيقات الجديدة والتحديثات منذ 31 أغسطس 2026 (تحقق من صفحة «Target API level requirements» في Play Console).
- التطبيق الأصلي يحتفظ بـ`appId = com.laqino.app` — **لا يمكن تغييره بعد النشر**.

## الخطوات
1. `capacitor.config.json`: `server.url` = `https://laqino.tech` (جاهز). تأكد أن الدومين يعمل بشهادة HTTPS قبل البناء (`deploy/Caddyfile` يتكفل بها؛ `DOMAIN=laqino.tech` في `.env`).
2. Firebase Console ← مشروع جديد ← أضف تطبيق Android بالاسم `com.laqino.app` ← نزّل `google-services.json`.
3. من داخل مجلد `android/`:
   ```
   npm install
   npx cap add android
   cp /path/to/google-services.json android/app/google-services.json
   npx cap sync android
   ```
4. **تحقق من API 36** قبل أي بناء:
   ```
   grep -n "compileSdkVersion\|targetSdkVersion\|minSdkVersion" android/variables.gradle
   ```
   يجب أن ترى `36` و`36` و`24`. غير ذلك: `npm ls @capacitor/android` يجب أن يظهر 8.x.
5. `npx cap open android` ← Android Studio ← جرّب على **محاكي أندرويد 16 (API 36)** وعلى هاتف حقيقي (انظر «الحافة إلى الحافة» أدناه). البناء النهائي الموقّع AAB: انظر «بناء AAB موقّع» أدناه (خطوة 7).
6. السيرفر: Firebase ← Project settings ← Service accounts ← Generate new private key، احفظ الملف خارج مجلد المشروع، ثم:
   ```
   export LAQINO_FCM_SERVICE_ACCOUNT=/مسار/الملف.json
   python3 server.py
   ```
   تحقق: ادخل كإدارة ثم `GET /api/admin/fcm/status` يعطي `{"enabled":true,"devices":N}`.
7. ثبّت التطبيق، سجّل الدخول (مندوب)، اسمح بالإشعارات؛ يظهر الجهاز في `devices`.

## الحافة إلى الحافة (Android 15/16)
عند targetSdk 36 لا يمكن إيقاف رسم المحتوى خلف شريطي الحالة والتنقل. صفحات `index/courier/pharmacy/admin` تعالج ذلك أصلًا (`viewport-fit=cover` + `env(safe-area-inset-*)`)، وأُضيف نفس المعالجة لـ`market.html` في phase-35. لم يُسجَّل هنا فحص مستقل لكل صفحة ولكل مقاس شاشة؛ راجع مواضع الهيدر وشريط التبويبات على أجهزة وأحجام شاشات مختلفة قبل الإصدار العام. إن ظهر خطأ في الـconsole عن «safe area CSS» فهو مسجَّل عند Capacitor 8.4.x (issue #8530) وليس من كود التطبيق.
**ملاحظة 16KB:** تأكد من فحص «16 KB page size» في Play Console عند رفع الـAAB (التطبيق بلا مكتبات native خاصة، لكن الإضافات الرسمية 8.x هي المسؤولة).

## الموقع (المرحلة 22)
التطبيق يطلب الموقع مرة واحدة عند الفتح عبر `static/location.js` (يتحمّل من السيرفر مثل `native.js`). `@capacitor/geolocation` مضاف إلى `package.json`
فيضيف `ACCESS_COARSE_LOCATION` و`ACCESS_FINE_LOCATION` للـmanifest تلقائيًا بعد `npm install` و`npx cap sync android`؛ و`location.js` يستعمله إن وُجد وإلا يرجع إلى `navigator.geolocation` في الـWebView.
تأكد بعد كل `cap sync` من وجود الإذنين في `android/app/src/main/AndroidManifest.xml`، واختبر طلب الإذن واستخدام الموقع على الجهاز المستهدف قبل تفعيل الميزة للمستخدمين.

## ما يصل وما لا يصل
- إشعار عام فقط («طلب توصيل جديد في منطقتك» / «عندك رسالة جديدة») بلا أسماء أو أرقام أو عناوين، ويفتح لوحة المندوب أو محادثات السوق عند الضغط.
- الإيقاظ المتكرر لطلب التوصيل (كل 25 ثانية) يستبدل نفس الإشعار (نفس الـtag). **إشعار الأندرويد لا يُسحب** بعد قبول الطلب (على عكس Web Push الذي يُمسح): يبقى حتى يزيله المندوب.
- الإشعارات الأخرى (الجرس: حالة طلب، موافقة...) ما زالت بالاستعلام الدوري داخل التطبيق، لا FCM، في هذه الدفعة.

## ملفات الأمان
لا تضع `google-services.json` ولا ملف حساب الخدمة داخل أي ZIP أو مستودع عام. ملف حساب الخدمة يخص السيرفر فقط ولا يدخل التطبيق.

## بناء AAB موقّع
1. أنشئ مفتاح الرفع مرة واحدة وخزّنه **خارج المشروع** مع نسخة احتياطية (فقدانه يعطّل التحديثات):
   `keytool -genkeypair -v -keystore laqino-release.jks -alias laqino -keyalg RSA -keysize 2048 -validity 10000`
2. انسخ `keystore.properties.example` إلى `keystore.properties` (في مجلد `android/`) واملأه. الملف محجوب في `.gitignore` ويرفضه `release_check.py` لو دخل المجلد.
3. فعّل **Play App Signing** عند أول رفع في Play Console (مفتاحك يصير «مفتاح رفع» وجوجل تحتفظ بمفتاح التوقيع النهائي).
4. من مجلد `android/`: `sh tools/build_aab.sh` (يشغّل: `npm install` ← `cap add` عند الحاجة ← `cap sync` ← `apply_signing.py` ← `check_manifest.py` ← `gradlew bundleRelease`).
5. الناتج: `android/android/app/build/outputs/bundle/release/app-release.aab`. **زوّد `versionCode`** في `android/android/app/build.gradle` مع كل رفع جديد.
6. `apply_signing.py` يضيف كتلة في آخر `app/build.gradle` (علامة `LAQINO-SIGNING`) تقرأ `keystore.properties`؛ بدونه يُبنى AAB غير موقّع.

## فحص AndroidManifest (خطوة 8 — phase-36)
`python3 tools/check_manifest.py` (من `android/`، أو مرّر مسار المجلد المولَّد). يفشل (خروج 1) عند: غياب `INTERNET`/`POST_NOTIFICATIONS`/`ACCESS_COARSE_LOCATION`/`ACCESS_FINE_LOCATION`، وجود إذن حساس (SMS/جهات اتصال/ميكروفون/موقع خلفي...)، `usesCleartextTraffic=true`، `debuggable=true`، launcher بلا `exported=true`، sdk غير 36/36/24، `applicationId` غير `com.laqino.app`، غياب `versionCode` أو إعداد التوقيع أو `google-services.json`، أو `server.url` غير HTTPS. يحذّر فقط من `allowBackup=true`.
**حدود الفحص:** الاختبار الآلي للفاحص على ملفات manifest نموذجية لا يغني عن تشغيله على manifest مولَّد فعليًا من إصدار Capacitor المستخدم، ومراجعة الناتج قبل رفع الإصدار. إذن `POST_NOTIFICATIONS` تضيفه إضافة push-notifications في 8.x (تحقق بعد `cap sync`؛ وإلا أضفه يدويًا في `AndroidManifest.xml`).



## GitHub Actions: signed Release AAB (isolated workflow)

يوجد Workflow تمهيدي مستقل باسم `.github/workflows/android-deps-preflight.yml` يعمل عند تحديث ملفات Android على فرع الإصلاح. يثبت الاعتماديات باستخدام `npm ci`، ويولّد مشروع Capacitor الأصلي ويزامنه، ويتحقق من هوية التطبيق وHTTPS وإعدادات SDK، ثم يحفظ `android/package-lock.json` تلقائيًا في **فرع الإصلاح فقط**.

ويوجد Workflow إصدار مستقل باسم `.github/workflows/android-release-aab.yml`، ويدعم التشغيل اليدوي من تبويب **Actions → Build Android Release AAB → Run workflow**، كما يعمل تلقائيًا عند الدفع إلى فرع `feature/android-aab-release-prep`، بعد إضافة الأسرار. يثبت Android Platform API 36 مع Build Tools 35.0.0، بما يتماشى مع إعدادات AGP 8.13 الافتراضية؛ رقم API الخاص بالمنصة ليس هو رقم Build Tools. لا يغيّر أي منهما Workflow الـDebug APK الموجود.

أضف القيم التالية في **Settings → Secrets and variables → Actions → New repository secret** قبل التشغيل:
- `GOOGLE_SERVICES_JSON`: محتوى ملف Firebase `google-services.json` كاملًا لتطبيق Android بالمعرّف `com.laqino.app`.
- `ANDROID_KEYSTORE_BASE64`: ملف مفتاح الرفع `.jks` بعد تحويله إلى Base64.
- `ANDROID_KEYSTORE_PASSWORD`: كلمة مرور ملف المفتاح.
- `ANDROID_KEY_ALIAS`: اسم المفتاح (alias).
- `ANDROID_KEY_PASSWORD`: كلمة مرور المفتاح.

لا تضع هذه القيم في ملفات Git أو في المحادثات. احتفظ بنسخة احتياطية آمنة من ملف المفتاح؛ لا تنشئ مفتاح رفع جديدًا إذا كان التطبيق قد نُشر بالفعل بمفتاح مختلف.

**ملف القفل:** Workflow التمهيدي ينشئ `android/package-lock.json` عند غيابه، ويتحقق منه باستخدام `npm ci`، ثم يحاول حفظه في فرع الإصلاح تلقائيًا. بعد تثبيت الملف في الفرع، لا يُعاد توليده مع كل إصدار.

**التحقق قبل كل إصدار:** راجع نتيجة Workflow وتأكد من نجاح Gradle والتوقيع، ثم اختبر نسخة الإصدار المقصودة على هاتف Android حقيقي، بما يشمل تسجيل الدخول والإشعارات والموقع والواجهات الأساسية. احتفظ برقم تشغيل Actions وCommit SHA الخاصين بكل artifact لتسهيل مطابقة النسخة التي جرى اختبارها مع النسخة التي سترفع إلى Google Play.
