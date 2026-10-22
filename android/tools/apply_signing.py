#!/usr/bin/env python3
"""يضيف إعداد توقيع release إلى android/app/build.gradle (بعد npx cap add android).
يقرأ المسار والكلمات من android/keystore.properties (خارج أي ZIP). آمن للتكرار (علامة LAQINO-SIGNING).
   python3 tools/apply_signing.py [مسار app/build.gradle]"""
import os, sys
MARK = "// LAQINO-SIGNING"
BLOCK = MARK + """ (يُضاف تلقائيًا؛ لا أسرار هنا)
def laqinoKs = new Properties()
def laqinoKsFile = rootProject.file('../keystore.properties')
if (laqinoKsFile.exists()) { laqinoKsFile.withInputStream { laqinoKs.load(it) } }
android {
    signingConfigs {
        laqinoRelease {
            if (laqinoKsFile.exists()) {
                storeFile file(laqinoKs['storeFile'])
                storePassword laqinoKs['storePassword']
                keyAlias laqinoKs['keyAlias']
                keyPassword laqinoKs['keyPassword']
            }
        }
    }
    buildTypes {
        release {
            if (laqinoKsFile.exists()) { signingConfig signingConfigs.laqinoRelease }
        }
    }
}
"""
def main(path):
    if path.endswith(".kts"):
        print("build.gradle.kts غير مدعوم هنا؛ أضف التوقيع يدويًا"); return 2
    if not os.path.isfile(path):
        print("لم أجد " + path + " — شغّل npx cap add android أولًا"); return 2
    t = open(path, encoding="utf-8").read()
    if MARK in t:
        print("التوقيع مضاف مسبقًا — لا تغيير"); return 0
    open(path, "a", encoding="utf-8").write("\n" + BLOCK)
    print("أُضيف إعداد التوقيع إلى " + path); return 0
if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "android", "app", "build.gradle")))
