#!/usr/bin/env python3
"""Ensure the generated Capacitor Android app manifest declares foreground location permissions.

This edits only the generated android/app/src/main/AndroidManifest.xml.
It does not grant runtime permission; Android still prompts the user when the app requests location.
"""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

manifest = Path(sys.argv[1] if len(sys.argv) > 1 else "android/app/src/main/AndroidManifest.xml")
if not manifest.is_file():
    raise SystemExit(f"ERROR: Android app manifest not found: {manifest}")

original = manifest.read_text(encoding="utf-8")
root = ET.fromstring(original)
android_ns = "{http://schemas.android.com/apk/res/android}"
required = (
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.ACCESS_FINE_LOCATION",
)
present = {
    node.get(android_ns + "name")
    for node in root.findall("uses-permission")
}
missing = [name for name in required if name not in present]

if missing:
    insertion = "".join(
        f'    <uses-permission android:name="{name}" />\n'
        for name in missing
    )
    updated, count = re.subn(
        r"(?m)^(\s*)<application\b",
        lambda match: insertion + match.group(0),
        original,
        count=1,
    )
    if count != 1:
        raise SystemExit("ERROR: Could not safely locate the application element in AndroidManifest.xml")
    ET.fromstring(updated)
    manifest.write_text(updated, encoding="utf-8")
    print("Added foreground location permissions: " + ", ".join(missing))
else:
    print("Foreground location permissions already exist")

# Re-read the final XML and verify both declarations are present.
final_root = ET.parse(manifest).getroot()
final_permissions = {
    node.get(android_ns + "name")
    for node in final_root.findall("uses-permission")
}
still_missing = sorted(set(required) - final_permissions)
if still_missing:
    raise SystemExit(f"ERROR: Location permissions still missing: {still_missing}")
print("PASS: Android source manifest declares coarse and fine location permissions")
