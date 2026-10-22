# غلاف أندرويد لاقينو (Capacitor 8، API 36) — هيكل جاهز للبناء، **لم يُبنَ ولم يُجرَّب**

التطبيق هنا «غلاف»: يفتح موقع لاقينو من سيرفرك (`server.url`) داخل WebView، ويضيف إشعارات FCM الأصلية عبر `static/native.js`
(الذي يتحمّل تلقائيًا من الموقع نفسه، فلا تحتاج إعادة بناء التطبيق عند تحديث الواجهة).
بيئتي لا تحوي Android SDK ولا Firebase، فكل ما هنا **كتابة بلا بناء**؛ جرّبه على جهازك وأبلغني بأي خطأ.

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
عند targetSdk 36 لا يمكن إيقاف رسم المحتوى خلف شريطي الحالة والتنقل. صفحات `index/courier/pharmacy/admin` تعالج ذلك أصلًا (`viewport-fit=cover` + `env(safe-area-inset-*)`)، وأُضيف نفس المعالجة لـ`market.html` في phase-35. **لم تُجرَّب على جهاز**: افحص يدويًا أن الهيدر لا يختفي تحت شريط الحالة وأن شريط التبويبات السفلي لا يختفي تحت شريط التنقل في كل صفحة. إن ظهر خطأ في الـconsole عن «safe area CSS» فهو مسجَّل عند Capacitor 8.4.x (issue #8530) وليس من كود التطبيق.
**ملاحظة 16KB:** تأكد من فحص «16 KB page size» في Play Console عند رفع الـAAB (التطبيق بلا مكتبات native خاصة، لكن الإضافات الرسمية 8.x هي المسؤولة).

## الموقع (المرحلة 22)
التطبيق يطلب الموقع مرة واحدة عند الفتح عبر `static/location.js` (يتحمّل من السيرفر مثل `native.js`). `@capacitor/geolocation` مضاف إلى `package.json`
فيضيف `ACCESS_COARSE_LOCATION` و`ACCESS_FINE_LOCATION` للـmanifest تلقائيًا بعد `npm install` و`npx cap sync android`؛ و`location.js` يستعمله إن وُجد وإلا يرجع إلى `navigator.geolocation` في الـWebView.
تأكد بعد البناء من وجود الإذنين في `android/app/src/main/AndroidManifest.xml` (وإلا أضفهما يدويًا). **هذا الجزء كتابة بلا بناء ولم يُجرَّب على جهاز.**

## ما يصل وما لا يصل
- إشعار عام فقط («طلب توصيل جديد في منطقتك» / «عندك رسالة جديدة») بلا أسماء أو أرقام أو عناوين، ويفتح لوحة المندوب أو محادثات السوق عند الضغط.
- الإيقاظ المتكرر لطلب التوصيل (كل 25 ثانية) يستبدل نفس الإشعار (نفس الـtag). **إشعار الأندرويد لا يُسحب** بعد قبول الطلب (على عكس Web Push الذي يُمسح): يبقى حتى يزيله المندوب.
- الإشعارات الأخرى (الجرس: حالة طلب، موافقة...) ما زالت بالاستعلام الدوري داخل التطبيق، لا FCM، في هذه الدفعة.

## ملفات الأمان
لا تضع `google-services.json` ولا ملف حساب الخدمة داخل أي ZIP أو مستودع عام. ملف حساب الخدمة يخص السيرفر فقط ولا يدخل التطبيق.

## بناء AAB موقّع (خطوة 7 — phase-36) — **لم يُنفَّذ هنا، أدوات فقط**
1. أنشئ مفتاح الرفع مرة واحدة وخزّنه **خارج المشروع** مع نسخة احتياطية (فقدانه يعطّل التحديثات):
   `keytool -genkeypair -v -keystore laqino-release.jks -alias laqino -keyalg RSA -keysize 2048 -validity 10000`
2. انسخ `keystore.properties.example` إلى `keystore.properties` (في مجلد `android/`) واملأه. الملف محجوب في `.gitignore` ويرفضه `release_check.py` لو دخل المجلد.
3. فعّل **Play App Signing** عند أول رفع في Play Console (مفتاحك يصير «مفتاح رفع» وجوجل تحتفظ بمفتاح التوقيع النهائي).
4. من مجلد `android/`: `sh tools/build_aab.sh` (يشغّل: `npm install` ← `cap add` عند الحاجة ← `cap sync` ← `apply_signing.py` ← `check_manifest.py` ← `gradlew bundleRelease`).
5. الناتج: `android/android/app/build/outputs/bundle/release/app-release.aab`. **زوّد `versionCode`** في `android/android/app/build.gradle` مع كل رفع جديد.
6. `apply_signing.py` يضيف كتلة في آخر `app/build.gradle` (علامة `LAQINO-SIGNING`) تقرأ `keystore.properties`؛ بدونه يُبنى AAB غير موقّع.

## فحص AndroidManifest (خطوة 8 — phase-36)
`python3 tools/check_manifest.py` (من `android/`، أو مرّر مسار المجلد المولَّد). يفشل (خروج 1) عند: غياب `INTERNET`/`POST_NOTIFICATIONS`/`ACCESS_COARSE_LOCATION`/`ACCESS_FINE_LOCATION`، وجود إذن حساس (SMS/جهات اتصال/ميكروفون/موقع خلفي...)، `usesCleartextTraffic=true`، `debuggable=true`، launcher بلا `exported=true`، sdk غير 36/36/24، `applicationId` غير `com.laqino.app`، غياب `versionCode` أو إعداد التوقيع أو `google-services.json`، أو `server.url` غير HTTPS. يحذّر فقط من `allowBackup=true`.
**حدود صادقة:** جُرّب على ملفات manifest نموذجية كتبتها بنفسي (`test_phase36_aab_prep.py`) لا على manifest مولَّد فعليًا من Capacitor؛ قد يختلف الشكل قليلًا. ولم يُبنَ AAB ولم يُجرَّب على جهاز. إذن `POST_NOTIFICATIONS` تضيفه إضافة push-notifications في 8.x (تحقق بعد `cap sync`؛ وإلا أضفه يدويًا في `AndroidManifest.xml`).
