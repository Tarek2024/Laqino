#!/usr/bin/env python3
"""Validate release signing inputs and add a repeatable Gradle signing block.

Run after `npx cap add android`:
  python3 tools/apply_signing.py android/app/build.gradle

The keystore path in keystore.properties must be absolute. Secrets are never
printed and the properties file must remain outside Git.
"""
import os
import re
import sys

MARK = "// LAQINO-SIGNING"
BLOCK = MARK + """ (generated; contains no secret values)
def laqinoKs = new Properties()
def laqinoKsFile = rootProject.file('../keystore.properties')
if (!laqinoKsFile.exists()) {
    throw new GradleException('Missing android/keystore.properties for Release signing')
}
laqinoKsFile.withInputStream { laqinoKs.load(it) }
def laqinoStoreFile = laqinoKs.getProperty('storeFile')
def laqinoStorePassword = laqinoKs.getProperty('storePassword')
def laqinoKeyAlias = laqinoKs.getProperty('keyAlias')
def laqinoKeyPassword = laqinoKs.getProperty('keyPassword')
if ([laqinoStoreFile, laqinoStorePassword, laqinoKeyAlias, laqinoKeyPassword].any { !it }) {
    throw new GradleException('Incomplete android/keystore.properties')
}
android {
    signingConfigs {
        laqinoRelease {
            storeFile file(laqinoStoreFile)
            storePassword laqinoStorePassword
            keyAlias laqinoKeyAlias
            keyPassword laqinoKeyPassword
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.laqinoRelease
        }
    }
}
"""

def read_properties(path):
    values = {}
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(("#", "!")):
                continue
            match = re.match(r"([^:=\\s]+)\\s*[:=]\\s*(.*)$", line)
            if match:
                values[match.group(1)] = match.group(2).strip()
    return values

def main(build_file):
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    props = os.path.join(project_dir, "keystore.properties")
    if not os.path.isfile(props):
        print("FAIL: android/keystore.properties is missing (copy the example and fill it securely)")
        return 2
    values = read_properties(props)
    required = ("storeFile", "storePassword", "keyAlias", "keyPassword")
    missing = [key for key in required if not values.get(key)]
    if missing:
        print("FAIL: missing signing properties: " + ", ".join(missing))
        return 2
    store = values["storeFile"]
    if not os.path.isabs(store):
        print("FAIL: storeFile must be an absolute path")
        return 2
    if not os.path.isfile(store):
        print("FAIL: keystore file does not exist at the configured path")
        return 2
    if build_file.endswith(".kts"):
        print("FAIL: build.gradle.kts is not supported by this signing patch; configure Kotlin DSL explicitly")
        return 2
    if not os.path.isfile(build_file):
        print("FAIL: app/build.gradle not found; run npx cap add android first")
        return 2
    with open(build_file, encoding="utf-8") as f:
        content = f.read()
    if MARK in content:
        if "signingConfig signingConfigs.laqinoRelease" not in content:
            print("FAIL: signing marker exists but the Release signing block is incomplete")
            return 2
        print("PASS: Release signing block already present")
        return 0
    with open(build_file, "a", encoding="utf-8") as f:
        f.write("\n" + BLOCK)
    print("PASS: Release signing block added (secret values were not written to Gradle)")
    return 0

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "android", "app", "build.gradle")
    sys.exit(main(target))
