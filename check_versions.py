"""Validate the single current release/cache source and documentation consistency.
Run from the repository root: python3 check_versions.py
This is a read-only documentation/version check; it does not build Android or contact Firebase.
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
        key = key.strip()
        if key in values:
            errors.append(f"VERSION: duplicate key: {key}")
        values[key] = value.strip()
    release, cache = values.get("release", ""), values.get("cache", "")
    if not re.fullmatch(r"phase-\d+[a-zA-Z0-9_-]*", release):
        errors.append(f"VERSION: invalid or missing release value: {release!r}")
    if not re.fullmatch(r"laqino-v\d+", cache):
        errors.append(f"VERSION: invalid or missing cache value: {cache!r}")
    extra = set(values) - {"release", "cache"}
    if extra:
        errors.append(f"VERSION: unexpected keys: {sorted(extra)}")
    if set(values) != {"release", "cache"}:
        errors.append("VERSION: expected exactly release and cache keys")
    return release, cache


release, cache = parse_version(read_text("VERSION"))

sw = read_text("static/sw.js")
matches = re.findall(r'\bconst\s+V\s*=\s*["\'](laqino-v\d+)["\']', sw)
if len(matches) != 1:
    errors.append(f"static/sw.js: expected exactly one cache declaration, found {len(matches)}")
elif cache and matches[0] != cache:
    errors.append(f"static/sw.js: cache is {matches[0]}, VERSION says {cache}")

# These are the only current status/release documents. Each must declare both
# identifiers at the top, while all old phase notes remain explicitly archived.
current_docs = ("README.md", "README_UPDATE.md", "HANDOFF.md", "PROJECT_STATE.md", "STATUS.md")
for name in current_docs:
    doc = read_text(name)
    head = "\n".join(doc.splitlines()[:16])
    if release and release not in head:
        errors.append(f"{name}: opening 16 lines do not state current release {release}")
    if cache and cache not in head:
        errors.append(f"{name}: opening 16 lines do not state current cache {cache}")

# The update note is the current release note, not a container for old release IDs.
note = read_text("README_UPDATE.md")
if release and release not in note:
    errors.append(f"README_UPDATE.md: does not mention current release {release}")
if cache and cache not in note:
    errors.append(f"README_UPDATE.md: does not mention current cache {cache}")

# Recursively inventory README and phase/update documentation. Historical phase
# documents must say so in their opening lines; Android setup is intentionally
# a separate operational guide and is not forced to carry web release numbers.
archive_files = []
for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    rel = path.relative_to(ROOT).as_posix()
    if any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in path.parts):
        continue
    is_archive = (
        rel in {
            "README_HISTORY.md", "PHASE18_HANDOFF.md", "UPDATE-INSTRUCTIONS.txt", "docs/ROADMAP.md",
            "docs/PROJECT_STATUS.md", "docs/CONSOLIDATED_REPORT.md",
        }
        or rel.startswith("README_UPDATE_PHASE")
        or (path.suffix.lower() in {".md", ".txt"} and re.match(r"^(?:PHASE|.*_PHASE)\d", path.name, re.I))
        or rel.startswith("docs/steps/")
        or rel.startswith("docs/phases/")
        or rel.startswith("docs/implementation/")
        or (path.suffix.lower() in {".md", ".txt"} and re.match(r"^(?:BACKUP_AND_ROLLBACK_PHASE|CHANGES_PHASE|PROJECT_REVIEW_PHASE|RX_AUTO_DISTRIBUTION_PHASE|TEST_RESULTS_PHASE)", path.name, re.I))
    )
    is_readme = path.name.lower().startswith("readme")
    if is_archive:
        archive_files.append(rel)
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:5]
        if not any("مؤرشف" in line or "أرشيف" in line or "ARCHIVE" in line.upper()
                   for line in head):
            errors.append(f"{rel}: historical document lacks an archive notice")
    elif is_readme and rel not in {"README.md", "README_UPDATE.md", "android/README_ANDROID.md"}:
        # Any additional README must be explicitly classified instead of silently
        # becoming a competing source of current project status.
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:8]
        if not any("مؤرشف" in line or "أرشيف" in line or "ARCHIVE" in line.upper()
                   for line in head):
            errors.append(f"{rel}: README needs an explicit current/archive classification")

# Current cache tokens may appear elsewhere only as references to VERSION or
# service-worker behavior; old cache tokens in changelog/history are expected.
print(f"ARCHIVE INVENTORY: {len(archive_files)} historical documents classified")
if errors:
    print("\n".join("FAIL " + item for item in errors))
    sys.exit(1)
print(f"OK release={release} cache={cache}; VERSION, service worker and current docs agree")
