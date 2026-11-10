"""Read-only release/cache and documentation inventory check.

Run from the repository root: python3 check_versions.py
This check does not build Android, contact Firebase, or deploy anything.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURRENT_DOCS = {
    "README.md", "README_UPDATE.md", "STATUS.md",
    "PROJECT_STATE.md", "HANDOFF.md",
}
OUT_OF_SCOPE_DOCS = {"android/README_ANDROID.md"}
ARCHIVE_EXACT = {
    "README_HISTORY.md", "PHASE18_HANDOFF.md", "UPDATE-INSTRUCTIONS.txt",
    "docs/ROADMAP.md", "docs/PROJECT_STATUS.md", "docs/CONSOLIDATED_REPORT.md",
    "CHANGES_PHASE11.md", "PROJECT_REVIEW_PHASE19.md",
    "RX_AUTO_DISTRIBUTION_PHASE53.md", "TEST_RESULTS_2026-10-23.md",
}
ARCHIVE_PREFIXES = (
    "README_UPDATE_PHASE", "BACKUP_AND_ROLLBACK_PHASE",
    "TEST_RESULTS_PHASE", "PHASE",
)
ARCHIVE_DIRS = ("docs/steps/", "docs/phases/", "docs/implementation/", "docs/archive/")
OPERATIONAL_DOCS = {
    "CHANGELOG.md", "DEPLOY.md", "PATCH_README.txt",
    "PLAN_PHARMACY_DELIVERY.md",
}

def classify_doc(relative):
    """Return current, historical, out-of-scope, or None (unclassified)."""
    name = Path(relative).name
    if relative in CURRENT_DOCS:
        return "current"
    if relative in OUT_OF_SCOPE_DOCS:
        return "out-of-scope"
    if relative in OPERATIONAL_DOCS:
        return "out-of-scope"
    if relative in ARCHIVE_EXACT or relative.startswith(ARCHIVE_DIRS):
        return "historical"
    if name.startswith(ARCHIVE_PREFIXES):
        return "historical"
    if re.match(r"^(?:PHASE|.*_PHASE)\d", name, re.I):
        return "historical"
    if name.lower().startswith("readme"):
        return "unclassified"
    if relative.startswith("docs/") and Path(relative).suffix.lower() in {".md", ".txt", ".rst"}:
        return "unclassified"
    return "out-of-scope"

def has_archive_notice(text):
    head = "\n".join(text.splitlines()[:8]).upper()
    return "ARCHIVE" in head or "مؤرشف" in head or "أرشيف" in head

def run_check(root=ROOT):
    errors = []
    version_path = root / "VERSION"
    values = {}
    for line in version_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"VERSION: malformed line: {line!r}")
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key in values:
            errors.append(f"VERSION: duplicate key: {key}")
        values[key] = value
    release, cache = values.get("release", ""), values.get("cache", "")
    if set(values) != {"release", "cache"}:
        errors.append("VERSION: expected exactly release and cache keys")
    if not re.fullmatch(r"phase-\d+[a-zA-Z0-9_-]*", release):
        errors.append(f"VERSION: invalid release {release!r}")
    if not re.fullmatch(r"laqino-v\d+", cache):
        errors.append(f"VERSION: invalid cache {cache!r}")

    sw = (root / "static/sw.js").read_text(encoding="utf-8")
    matches = re.findall(r'\bconst\s+V\s*=\s*["\'](laqino-v\d+)["\']', sw)
    if len(matches) != 1:
        errors.append(f"static/sw.js: expected one cache declaration, found {len(matches)}")
    elif cache and matches[0] != cache:
        errors.append(f"static/sw.js: {matches[0]} != VERSION {cache}")

    counts = {"current": 0, "historical": 0, "out-of-scope": 0}
    doc_paths = sorted(
        p for p in root.rglob("*") if p.is_file()
        and p.suffix.lower() in {".md", ".txt", ".rst"}
        and not any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"}
                    for part in p.relative_to(root).parts)
    )
    for path in doc_paths:
        relative = path.relative_to(root).as_posix()
        category = classify_doc(relative)
        if category == "unclassified":
            errors.append(f"{relative}: documentation has no explicit inventory classification")
            continue
        counts[category] += 1
        content = path.read_text(encoding="utf-8", errors="replace")
        if category == "historical" and not has_archive_notice(content):
            errors.append(f"{relative}: historical document lacks archive notice")

    for name in sorted(CURRENT_DOCS):
        path = root / name
        if not path.exists():
            errors.append(f"{name}: required current document is missing")
            continue
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:16])
        if release and release not in head:
            errors.append(f"{name}: opening 16 lines omit {release}")
        if cache and cache not in head:
            errors.append(f"{name}: opening 16 lines omit {cache}")

    update_note = (root / "README_UPDATE.md").read_text(encoding="utf-8")
    if release not in update_note or cache not in update_note:
        errors.append("README_UPDATE.md: current release/cache reference is missing")

    return errors, counts, release, cache

if __name__ == "__main__":
    errors, counts, release, cache = run_check()
    print("DOCUMENT INVENTORY: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    if errors:
        print("\n".join("FAIL " + error for error in errors))
        sys.exit(1)
    print(f"OK release={release} cache={cache}; source, service worker and documentation inventory agree")
