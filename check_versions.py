"""Validate the single release/cache source without modifying the project.
Run from the repository root: python3 check_versions.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
errors = []


def read_text(relative):
    path = ROOT / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{relative}: cannot read file ({exc})")
        return ""


def parse_version(text):
    values = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"VERSION: malformed line: {line!r}")
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    release, cache = values.get("release", ""), values.get("cache", "")
    if not re.fullmatch(r"phase-\d+[a-zA-Z0-9_-]*", release):
        errors.append(f"VERSION: invalid or missing release value: {release!r}")
    if not re.fullmatch(r"laqino-v\d+", cache):
        errors.append(f"VERSION: invalid or missing cache value: {cache!r}")
    return release, cache


release, cache = parse_version(read_text("VERSION"))

sw = read_text("static/sw.js")
matches = re.findall(r'\bconst\s+V\s*=\s*["\'](laqino-v\d+)["\']', sw)
if len(matches) != 1:
    errors.append(f"static/sw.js: expected exactly one cache declaration, found {len(matches)}")
elif cache and matches[0] != cache:
    errors.append(f"static/sw.js: cache is {matches[0]}, VERSION says {cache}")

# Only the current release note is subject to stale-cache checks. Historical documents
# are allowed to retain old version numbers as archival evidence.
note = read_text("README_UPDATE.md")
if release and release not in note:
    errors.append(f"README_UPDATE.md: does not mention current release {release}")
if cache:
    stale = set(re.findall(r"laqino-v\d+", note)) - {cache}
    for line in note.splitlines():
        for value in stale:
            if value in line and not re.search(r"السابق|previous|تاريخي|archive|←|->", line, re.I):
                errors.append(f"README_UPDATE.md: stale cache {value} on non-historical line: {line.strip()[:100]}")

# These documents must expose the current release and cache near their top.
for name in ("README.md", "HANDOFF.md", "PROJECT_STATE.md", "STATUS.md"):
    text = read_text(name)
    head = "\n".join(text.splitlines()[:12])
    if release and release not in head:
        errors.append(f"{name}: first 12 lines do not state current release {release}")
    if cache and cache not in head:
        errors.append(f"{name}: first 12 lines do not state current cache {cache}")

if errors:
    print("\n".join("FAIL " + item for item in errors))
    sys.exit(1)
print(f"OK release={release} cache={cache}; VERSION, service worker and current status documents agree")
