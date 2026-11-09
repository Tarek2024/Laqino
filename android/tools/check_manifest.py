#!/usr/bin/env python3
"""Validate the generated Capacitor Android project before Release AAB packaging.

Run after cap sync and Gradle's processReleaseMainManifest task:
  python3 tools/check_manifest.py android
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ANDROID = "{http://schemas.android.com/apk/res/android}"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "android"))
FAILS, WARNS = [], []

def check(name, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + name + ("" if condition else " -> " + str(detail)))
    if not condition:
        FAILS.append(name)

def warn(name, detail=""):
    print("WARN " + name + (": " + str(detail) if detail else ""))
    WARNS.append(name)

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def find_release_merged_manifest():
    base = os.path.join(PROJECT, "app", "build", "intermediates")
    matches = []
    if os.path.isdir(base):
        for root, _, files in os.walk(base):
            if "AndroidManifest.xml" in files and "merged_manifest" in root and "release" in root:
                matches.append(os.path.join(root, "AndroidManifest.xml"))
    return sorted(matches, key=len)[0] if matches else None

def main():
    source_manifest = os.path.join(PROJECT, "app", "src", "main", "AndroidManifest.xml")
    check("generated Android project exists", os.path.isfile(source_manifest), source_manifest)
    if not os.path.isfile(source_manifest):
        return 1
    try:
        source_root = ET.parse(source_manifest).getroot()
    except (ET.ParseError, OSError) as exc:
        check("source AndroidManifest.xml is valid XML", False, exc)
        return 1

    merged_path = find_release_merged_manifest()
    check("Gradle Release merged manifest exists (run processReleaseMainManifest first)", bool(merged_path), "No merged Release manifest found")
    merged_root = source_root
    if merged_path:
        try:
            merged_root = ET.parse(merged_path).getroot()
        except (ET.ParseError, OSError) as exc:
            check("merged Release manifest is valid XML", False, exc)
            return 1

    perms = {e.get(ANDROID + "name") for e in merged_root.findall("uses-permission")}
    required = {
        "android.permission.INTERNET",
        "android.permission.POST_NOTIFICATIONS",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_FINE_LOCATION",
    }
    check("merged manifest includes Internet, notifications and location permissions",
          required <= perms, sorted(required - perms))

    risky_names = {
        "READ_SMS", "SEND_SMS", "RECEIVE_SMS", "READ_CALL_LOG", "READ_CONTACTS",
        "RECORD_AUDIO", "ACCESS_BACKGROUND_LOCATION", "READ_PHONE_STATE",
        "MANAGE_EXTERNAL_STORAGE", "SYSTEM_ALERT_WINDOW",
    }
    extra = sorted(p for p in perms if p and p.rsplit(".", 1)[-1] in risky_names)
    check("no unexplained sensitive permissions", not extra, extra)

    app = merged_root.find("application")
    check("merged manifest has an application element", app is not None)
    if app is not None:
        check("cleartext traffic is not enabled", app.get(ANDROID + "usesCleartextTraffic") != "true")
        if app.get(ANDROID + "allowBackup") == "true":
            warn("allowBackup=true", "review whether Android backup is appropriate for this app")
        check("application is not debuggable", app.get(ANDROID + "debuggable") != "true")
        launchers = [
            activity for activity in app.findall("activity")
            if any(category.get(ANDROID + "name") == "android.intent.category.LAUNCHER"
                   for intent in activity.findall("intent-filter")
                   for category in intent.findall("category"))
        ]
        check("exactly one launcher activity exists", len(launchers) == 1, len(launchers))
        check("launcher activity declares exported=true",
              len(launchers) == 1 and launchers[0].get(ANDROID + "exported") == "true",
              [a.get(ANDROID + "name") for a in launchers])
        missing_exported = [
            element.get(ANDROID + "name")
            for element in list(app)
            if element.tag in ("activity", "service", "receiver", "provider")
            and element.find("intent-filter") is not None
            and element.get(ANDROID + "exported") is None
        ]
        check("components with intent filters declare exported explicitly", not missing_exported, missing_exported)

    variables = os.path.join(PROJECT, "variables.gradle")
    if os.path.isfile(variables):
        content = read(variables)
        def sdk_value(key):
            match = re.search(r"\b" + re.escape(key) + r"\s*=\s*(\d+)", content)
            return int(match.group(1)) if match else None
        values = (sdk_value("compileSdkVersion"), sdk_value("targetSdkVersion"), sdk_value("minSdkVersion"))
        check("SDK levels are compile 36 / target 36 / min 24", values == (36, 36, 24), values)
    else:
        warn("variables.gradle not found; SDK levels could not be verified")

    app_gradle = os.path.join(PROJECT, "app", "build.gradle")
    if os.path.isfile(app_gradle):
        gradle = read(app_gradle)
        app_id = re.search(r"applicationId\s+[\"']([^\"']+)", gradle)
        version_code = re.search(r"versionCode\s+(\d+)", gradle)
        check("applicationId is com.laqino.app", bool(app_id) and app_id.group(1) == "com.laqino.app",
              app_id.group(1) if app_id else "not found")
        check("versionCode is declared", bool(version_code))
        check("Release signing block is configured",
              "LAQINO-SIGNING" in gradle and "signingConfig signingConfigs.laqinoRelease" in gradle)
    else:
        check("app/build.gradle exists", False, app_gradle)

    google_file = os.path.join(PROJECT, "app", "google-services.json")
    check("Firebase google-services.json exists for FCM", os.path.isfile(google_file))
    if os.path.isfile(google_file):
        try:
            firebase = json.loads(read(google_file))
            package_names = [
                client.get("client_info", {}).get("android_client_info", {}).get("package_name")
                for client in firebase.get("client", [])
            ]
            check("Firebase config contains package com.laqino.app", "com.laqino.app" in package_names, package_names)
        except (ValueError, OSError) as exc:
            check("Firebase config is valid JSON", False, exc)

    config_path = os.path.join(PROJECT, "..", "capacitor.config.json")
    if not os.path.isfile(config_path):
        config_path = os.path.join(HERE, "..", "capacitor.config.json")
    if os.path.isfile(config_path):
        try:
            config = json.loads(read(config_path))
            check("Capacitor appId is com.laqino.app", config.get("appId") == "com.laqino.app", config.get("appId"))
            check("Capacitor server.url uses HTTPS",
                  str(config.get("server", {}).get("url", "")).startswith("https://"))
        except (ValueError, OSError) as exc:
            check("Capacitor config is valid JSON", False, exc)
    else:
        check("Capacitor config exists", False, config_path)

    print("ANDROID RELEASE CHECK: %s (%d warnings)" %
          ("OK" if not FAILS else str(len(FAILS)) + " FAILED", len(WARNS)))
    return 1 if FAILS else 0

if __name__ == "__main__":
    sys.exit(main())
