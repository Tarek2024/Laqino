"""Single-source version check: VERSION is the only place the release id and cache name are defined.
Run from the project root:  python3 check_versions.py"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).parent
cfg = dict(l.split("=", 1) for l in (ROOT / "VERSION").read_text().split() if "=" in l)
release, cache = cfg["release"], cfg["cache"]
errors = []

sw = (ROOT / "static/sw.js").read_text()
m = re.search(r'const V = "(laqino-v\d+)"', sw)
if not m or m.group(1) != cache:
    errors.append(f"sw.js cache is {m.group(1) if m else 'missing'}, VERSION says {cache}")

# Only the per-release note is enforced; README/STATUS/PROJECT_STATUS keep historical cache names legitimately.
for name in ("README_UPDATE.md",):
    p = ROOT / name
    if p.exists():
        t = p.read_text()
        if release not in t:
            errors.append(f"{name} does not mention {release}")
        stale = set(re.findall(r"laqino-v\d+", t)) - {cache}
        # older cache names are allowed only on lines that say they are the previous one (السابق / previous)
        for line in t.splitlines():
            for s in stale:
                if s in line and not re.search(r"السابق|previous|←|->", line):
                    errors.append(f"{name}: stale cache name {s} outside a 'previous' line: {line.strip()[:60]}")

# The four state documents must declare the current release and cache in their first lines.
for name in ("README.md", "HANDOFF.md", "PROJECT_STATE.md", "STATUS.md"):
    p = ROOT / name
    if p.exists():
        head = "\n".join(p.read_text().splitlines()[:8])
        for what, val in (("release", release), ("cache", cache)):
            if val not in head:
                errors.append(f"{name}: first lines do not state current {what} {val}")

if errors:
    print("\n".join("FAIL " + e for e in errors)); sys.exit(1)
print(f"OK  release={release}  cache={cache}  (VERSION, sw.js and docs agree)")
