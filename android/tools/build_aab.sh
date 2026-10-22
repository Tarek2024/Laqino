#!/bin/sh
# بناء AAB موقّع لـGoogle Play. شغّله من مجلد android/ على كمبيوتر فيه Node 22 وJDK 21 وAndroid SDK.
# المتطلبات قبل التشغيل: google-services.json في android/app/ (بعد npx cap add android) وملف keystore.properties.
set -e
cd "$(dirname "$0")/.."
[ -f keystore.properties ] || { echo "ناقص: keystore.properties (انسخ keystore.properties.example)"; exit 1; }
npm install
[ -d android ] || npx cap add android
[ -f android/app/google-services.json ] || { echo "ناقص: android/app/google-services.json (من Firebase)"; exit 1; }
npx cap sync android
python3 tools/apply_signing.py android/app/build.gradle
python3 tools/check_manifest.py android
cd android && ./gradlew bundleRelease
echo "الناتج: android/app/build/outputs/bundle/release/app-release.aab"
