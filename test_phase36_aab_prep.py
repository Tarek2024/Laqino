# تجهيز AAB وفحص الـManifest (المرحلة 36) — فحص بملفات نموذجية (لا بناء حقيقي ولا Android SDK).
import json, os, re, subprocess, sys, tempfile
R = lambda p: open(p, encoding="utf-8").read()
n = 0
def ok(name, c):
    global n; n += 1
    print(("PASS " if c else "FAIL ") + name)
    if not c: sys.exit(1)
PERM = lambda *p: "".join('<uses-permission android:name="android.permission.%s"/>' % x for x in p)
def manifest(perms, app_attrs="", act_exported="true"):
    return ('<?xml version="1.0" encoding="utf-8"?><manifest xmlns:android="http://schemas.android.com/apk/res/android">'
            + PERM(*perms) + '<application android:label="x" ' + app_attrs + '><activity android:name=".MainActivity" android:exported="%s">'
            '<intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter>'
            '</activity></application></manifest>' % act_exported)
GOOD = ["INTERNET", "POST_NOTIFICATIONS", "ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION"]
GRADLE = 'android {\n defaultConfig {\n  applicationId "com.laqino.app"\n  versionCode 1\n }\n}\n'
VARS = "ext { minSdkVersion = 24\n compileSdkVersion = 36\n targetSdkVersion = 36 }\n"
def make(mf, gradle=GRADLE, vars_=VARS, gs=True):
    d = tempfile.mkdtemp(); os.makedirs(d + "/app/src/main")
    open(d + "/app/src/main/AndroidManifest.xml", "w").write(mf); open(d + "/app/build.gradle", "w").write(gradle)
    open(d + "/variables.gradle", "w").write(vars_)
    if gs: open(d + "/app/google-services.json", "w").write("{}")
    json.dump({"server": {"url": "https://laqino.tech"}}, open(d + "/capacitor.config.json", "w"))
    return d
def run(*a): return subprocess.run([sys.executable] + list(a), capture_output=True, text=True)
sign = lambda d: run("android/tools/apply_signing.py", d + "/app/build.gradle")
check = lambda d: run("android/tools/check_manifest.py", d)

# apply_signing
d = make(manifest(GOOD)); r = sign(d); g = R(d + "/app/build.gradle")
ok("apply_signing يضيف العلامة وإعداد release", r.returncode == 0 and "LAQINO-SIGNING" in g and "signingConfigs.laqinoRelease" in g)
ok("apply_signing لا يحوي أي كلمة مرور أو مسار ثابت", not re.search(r"storePassword\s+['\"]\w", g) and "/home/" not in g)
once = g; sign(d)
ok("apply_signing آمن للتكرار (لا يضاعف الكتلة)", R(d + "/app/build.gradle") == once and once.count("LAQINO-SIGNING") == 1)
ok("apply_signing يرفض build.gradle.kts", run("android/tools/apply_signing.py", d + "/app/build.gradle.kts").returncode == 2)
ok("apply_signing يفشل بوضوح إن لم يوجد الملف", run("android/tools/apply_signing.py", "/nonexistent/build.gradle").returncode == 2)

# check_manifest — حالة سليمة
r = check(d)
ok("check_manifest ينجح على manifest سليم", r.returncode == 0 and "CHECK MANIFEST: OK" in r.stdout)
# حالات فاشلة
d2 = make(manifest(["INTERNET", "ACCESS_FINE_LOCATION"])); sign(d2); r = check(d2)
ok("ينكشف نقص POST_NOTIFICATIONS", r.returncode == 1 and "FAIL الأذونات المطلوبة" in r.stdout)
d3 = make(manifest(GOOD + ["READ_SMS", "ACCESS_BACKGROUND_LOCATION"])); sign(d3); r = check(d3)
ok("ينكشف إذن حساس غير مبرَّر", r.returncode == 1 and "READ_SMS" in r.stdout)
d4 = make(manifest(GOOD, 'android:usesCleartextTraffic="true"')); sign(d4)
ok("ينكشف usesCleartextTraffic=true", check(d4).returncode == 1)
d5 = make(manifest(GOOD, act_exported="false")); sign(d5)
ok("ينكشف launcher بلا exported=true", check(d5).returncode == 1)
d6 = make(manifest(GOOD), vars_=VARS.replace("targetSdkVersion = 36", "targetSdkVersion = 35")); sign(d6)
ok("ينكشف targetSdk غير 36", check(d6).returncode == 1)
d7 = make(manifest(GOOD)); r = check(d7)
ok("ينكشف غياب إعداد التوقيع", r.returncode == 1 and "LAQINO-SIGNING" in r.stdout)
d8 = make(manifest(GOOD), gs=False); sign(d8)
ok("ينكشف غياب google-services.json", check(d8).returncode == 1)
d9 = make(manifest(GOOD), gradle=GRADLE.replace("com.laqino.app", "com.other.app")); sign(d9)
ok("ينكشف applicationId مختلف", check(d9).returncode == 1)
ok("allowBackup=true تحذير لا فشل", (lambda d: (sign(d), check(d))[1])(make(manifest(GOOD, 'android:allowBackup="true"'))).returncode == 0)
ok("غياب manifest يعطي فشلًا واضحًا", run("android/tools/check_manifest.py", tempfile.mkdtemp()).returncode == 1)

# ملفات التسليم
ok("build_aab.sh موجود ويستدعي التوقيع والفحص ثم bundleRelease",
   all(s in R("android/tools/build_aab.sh") for s in ("apply_signing.py", "check_manifest.py", "bundleRelease")))
ok("keystore.properties.example بلا قيم سرية", not re.search(r"Password=\S", R("android/keystore.properties.example")))
gi = R("android/.gitignore")
ok(".gitignore يحجب المفاتيح و google-services.json", all(s in gi for s in ("keystore.properties", "*.jks", "*.keystore", "google-services.json")))
ok("لا مفاتيح فعلية داخل android/", not [f for _, _, fs in os.walk("android") for f in fs if f.endswith((".jks", ".keystore", ".pem", ".p12")) or f in ("keystore.properties", "google-services.json")])
ok("README_ANDROID يشرح خطوات 7 و8", all(s in R("android/README_ANDROID.md") for s in ("build_aab.sh", "check_manifest.py", "Play App Signing")))
print("ALL %d PASS" % n)
