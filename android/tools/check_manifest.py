#!/usr/bin/env python3
"""فحص AndroidManifest وإعدادات الغلاف قبل رفع AAB (خطوة 8). قراءة فقط.
   python3 tools/check_manifest.py [مجلد android/ المولَّد]   (الافتراضي: ../android)
يخرج 1 عند أي FAIL. التحذيرات (WARN) لا تفشل الفحص."""
import os, re, sys, xml.etree.ElementTree as ET
A = "{http://schemas.android.com/apk/res/android}"
here = os.path.dirname(os.path.abspath(__file__))
root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "android")
fails = []; warns = []
def chk(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else "  -> " + str(d)))
    if not c: fails.append(n)
def warn(n, d=""): print("WARN " + n + (" -> " + str(d) if d else "")); warns.append(n)
mp = os.path.join(root, "app", "src", "main", "AndroidManifest.xml")
if not os.path.isfile(mp):
    print("FAIL لا يوجد " + mp + " — شغّل npx cap add android ثم npx cap sync android"); sys.exit(1)
m = ET.parse(mp).getroot()
perms = {e.get(A + "name") for e in m.findall("uses-permission")}
need = {"android.permission.INTERNET", "android.permission.POST_NOTIFICATIONS",
        "android.permission.ACCESS_COARSE_LOCATION", "android.permission.ACCESS_FINE_LOCATION"}
chk("الأذونات المطلوبة موجودة (إنترنت/إشعارات/موقع)", need <= perms, sorted(need - perms))
risky = {"READ_SMS", "SEND_SMS", "RECEIVE_SMS", "READ_CALL_LOG", "READ_CONTACTS", "RECORD_AUDIO",
         "ACCESS_BACKGROUND_LOCATION", "READ_PHONE_STATE", "MANAGE_EXTERNAL_STORAGE", "SYSTEM_ALERT_WINDOW"}
extra = sorted(p for p in perms if p.rsplit(".", 1)[-1] in risky)
chk("لا أذونات حساسة غير مبرَّرة (SMS/جهات اتصال/ميكروفون/موقع خلفي...)", not extra, extra)
app = m.find("application")
chk("وجود عنصر application", app is not None)
if app is not None:
    chk("لا usesCleartextTraffic=true", app.get(A + "usesCleartextTraffic") != "true")
    if app.get(A + "allowBackup") == "true": warn("allowBackup=true", "قرّر هل تريد نسخ بيانات التطبيق احتياطيًا عبر Google")
    if app.get(A + "debuggable") == "true": chk("التطبيق ليس debuggable", False, "android:debuggable=true")
    launch = [a for a in app.findall("activity") if any(
        c.get(A + "name") == "android.intent.category.LAUNCHER" for f in a.findall("intent-filter") for c in f.findall("category"))]
    chk("نشاط launcher واحد على الأقل", len(launch) >= 1)
    chk("نشاط launcher معلَن exported=true (مطلوب من Android 12+)", all(a.get(A + "exported") == "true" for a in launch), [a.get(A + "name") for a in launch])
    bad = [e.get(A + "name") for e in app if e.tag in ("activity", "service", "receiver", "provider")
           and e.find("intent-filter") is not None and e.get(A + "exported") is None]
    chk("كل مكوّن بـintent-filter يصرّح exported صراحةً", not bad, bad)
vg = os.path.join(root, "variables.gradle")
if os.path.isfile(vg):
    v = open(vg, encoding="utf-8").read()
    g = lambda k: (re.search(k + r"\s*=\s*(\d+)", v) or [None, None])[1]
    chk("compileSdk=36 و targetSdk=36 و minSdk=24", (g("compileSdkVersion"), g("targetSdkVersion"), g("minSdkVersion")) == ("36", "36", "24"),
        (g("compileSdkVersion"), g("targetSdkVersion"), g("minSdkVersion")))
else: warn("لا variables.gradle", "تعذّر فحص إصدارات SDK")
ag = os.path.join(root, "app", "build.gradle")
if os.path.isfile(ag):
    t = open(ag, encoding="utf-8").read()
    mm = re.search(r"applicationId\s+[\"']([^\"']+)", t)
    chk("applicationId = com.laqino.app", bool(mm) and mm.group(1) == "com.laqino.app", mm and mm.group(1))
    vc = re.search(r"versionCode\s+(\d+)", t)
    chk("versionCode موجود (زوّده مع كل رفع لـPlay)", bool(vc))
    chk("إعداد التوقيع مضاف (LAQINO-SIGNING)", "LAQINO-SIGNING" in t, "شغّل tools/apply_signing.py")
else: warn("لا app/build.gradle")
chk("google-services.json موجود (للإشعارات FCM) — للبناء فقط، لا يُسلَّم", os.path.isfile(os.path.join(root, "app", "google-services.json")))
cfg = os.path.join(root, "capacitor.config.json")
if not os.path.isfile(cfg): cfg = os.path.join(here, "..", "capacitor.config.json")
if os.path.isfile(cfg):
    import json
    c = json.load(open(cfg, encoding="utf-8"))
    chk("server.url يبدأ بـhttps", str(c.get("server", {}).get("url", "")).startswith("https://"))
print("CHECK MANIFEST: %s (%d تحذير)" % ("OK" if not fails else "%d FAILED" % len(fails), len(warns)))
sys.exit(1 if fails else 0)
