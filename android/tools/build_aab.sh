#!/bin/sh
# Build a signed Release AAB. Run from the repository's android/ directory.
set -eu
cd "$(dirname "$0")/.."

fail() { echo "ERROR: $*" >&2; exit 1; }
command -v node >/dev/null 2>&1 || fail "Node.js 22+ is required"
command -v npm >/dev/null 2>&1 || fail "npm is required"
command -v java >/dev/null 2>&1 || fail "JDK 21 is required"
command -v python3 >/dev/null 2>&1 || fail "Python 3 is required"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
JAVA_MAJOR="$(java -version 2>&1 | sed -n '1s/.*version "\\([0-9]*\\).*/\\1/p')"
[ "$NODE_MAJOR" -ge 22 ] || fail "Node.js 22+ is required (found $NODE_MAJOR)"
[ "$JAVA_MAJOR" -ge 21 ] || fail "JDK 21+ is required (found $JAVA_MAJOR)"

[ -f keystore.properties ] || fail "Missing android/keystore.properties"
[ -f package.json ] || fail "Missing android/package.json"

# Generate a lockfile if this checkout does not have one yet. Commit the
# generated package-lock.json after reviewing it to make future builds repeatable.
if [ -f package-lock.json ]; then
  npm ci --no-audit --no-fund
else
  echo "WARN: package-lock.json is missing; generating one for this build."
  npm install --package-lock-only --ignore-scripts --no-audit --no-fund
  npm ci --no-audit --no-fund
fi

if [ ! -d android ]; then
  npx cap add android
fi
[ -f android/app/build.gradle ] || fail "Generated Android project is incomplete: android/app/build.gradle is missing"
[ -f android/variables.gradle ] || fail "Generated Android project is incomplete: android/variables.gradle is missing"
[ -f android/gradlew ] || fail "Gradle wrapper missing after npx cap add android"
[ -f android/gradle/wrapper/gradle-wrapper.properties ] || fail "Gradle wrapper properties are missing"
[ -f android/app/google-services.json ] || fail "Missing android/app/google-services.json from Firebase"

npx cap sync android
python3 tools/ensure_location_permissions.py android/app/src/main/AndroidManifest.xml
chmod +x android/gradlew
python3 tools/apply_signing.py android/app/build.gradle

cd android
./gradlew --no-daemon --stacktrace processReleaseMainManifest
cd ..
python3 tools/check_manifest.py android

cd android
./gradlew --no-daemon --stacktrace bundleRelease
AAB="app/build/outputs/bundle/release/app-release.aab"
[ -s "$AAB" ] || fail "Gradle completed but the AAB file is missing or empty"
echo "PASS: signed AAB created at android/$AAB"
