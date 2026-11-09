#!/usr/bin/env python3
"""Read-only release readiness checks. Run: python3 release_check.py"""
import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
fails = []


def read(relative):
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except OSError as exc:
        fail(relative + " readable", str(exc))
        return ""


def fail(name, detail):
    fails.append(name)
    print("FAIL " + name + " -> " + str(detail))


def check(name, condition, detail=""):
    if condition:
        print("PASS " + name)
    else:
        fail(name, detail)


# Version and cache are sourced from VERSION; never infer either from an old document.
version_text = read("VERSION")
version = {}
for line in version_text.splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        version[key.strip()] = value.strip()
release = version.get("release", "")
cache_name = version.get("cache", "")
check("VERSION release format", bool(re.fullmatch(r"phase-\d+[A-Za-z0-9_-]*", release)), release)
check("VERSION cache format", bool(re.fullmatch(r"laqino-v\d+", cache_name)), cache_name)

sw = read("static/sw.js")
cache_match = re.search(r'\bconst\s+V\s*=\s*["\'](laqino-v(\d+))["\']', sw)
check("service worker cache matches VERSION", bool(cache_match and cache_match.group(1) == cache_name),
      cache_match.group(1) if cache_match else "cache declaration missing")

# Every declared shell path must exist under static/. Parse only the SHELL array.
shell_match = re.search(r"\bSHELL\s*=\s*\[(.*?)\]", sw, re.S)
shell_paths = re.findall(r'["\'](/[^"\']*)["\']', shell_match.group(1)) if shell_match else []
check("service worker SHELL declaration found", bool(shell_match), "SHELL array missing")
missing_shell = [
    path for path in shell_paths
    if path != "/" and not (ROOT / "static" / path.lstrip("/").split("?", 1)[0]).is_file()
]
check("every service worker SHELL file exists", not missing_shell, missing_shell)

# Compare Python imports in server.py with Python modules copied into the Docker image.
server_text = read("server.py")
docker_text = read("Dockerfile")
try:
    tree = ast.parse(server_text)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    local_modules = {
        p.stem for p in ROOT.glob("*.py")
        if not p.name.startswith("test_")
    } - {"release_check", "check_versions", "apply_phase17_safe", "phase16_imgutil", "imgutil", "testutil"}
    required = (imported & local_modules) | {"server"}
    copied = set()
    for line in docker_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[0] == "COPY":
            for item in parts[1:-1]:
                if item.endswith(".py") and not item.startswith("--"):
                    copied.add(Path(item).stem)
    check("Dockerfile copies local server modules", required <= copied, sorted(required - copied))
except (SyntaxError, OSError) as exc:
    fail("Docker import analysis", str(exc))

# Detect accidentally committed runtime data and private key material.
sensitive = []
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", ".git", ".venv", "venv"}]
    for filename in files:
        full = Path(root) / filename
        rel = full.relative_to(ROOT).as_posix()
        if Path(root) == ROOT and filename in {"laqino.db", "laqino.db-wal", "laqino.db-shm"}:
            continue
        if (re.search(r"(\.db(?:-wal|-shm)?|\.env|\.pem|\.p12|\.jks|\.keystore)$", filename, re.I)
                or filename == "google-services.json"
                or filename.endswith("service-account.json")):
            sensitive.append(rel)
    if Path(root).name == "uploads":
        sensitive.append(Path(root).relative_to(ROOT).as_posix() + "/")
check("no runtime databases, secrets or uploads directory committed", not sensitive, sensitive)

# Phase documentation is historical inventory only; verify numbering without crashing on an empty folder.
phase_dir = ROOT / "docs" / "phases"
phase_numbers = []
if phase_dir.is_dir():
    for item in phase_dir.iterdir():
        match = re.search(r"phase-(\d+)", item.name)
        if match and item.is_file():
            phase_numbers.append(int(match.group(1)))
phase_numbers = sorted(set(phase_numbers))
check("phase README inventory exists and is contiguous from 1",
      bool(phase_numbers) and phase_numbers == list(range(1, max(phase_numbers) + 1)),
      phase_numbers)

readme = read("README.md")
if cache_match:
    # README intentionally retains old cache identifiers in its historical phase log.
    # Require the current cache near the top; do not reject legitimate archival references.
    readme_head = "\\n".join(readme.splitlines()[:12])
    readme_cache_ok = cache_name in readme_head
else:
    readme_cache_ok = False
check("README current cache reference", readme_cache_ok, "current cache missing from the opening status lines")

deploy_doc = read("DEPLOY.md")
env_example = read("deploy/env.example")
code = server_text + read("fcm.py") + read("notif.py")
used_vars = set(re.findall(r"\bLAQINO_[A-Z0-9_]+\b", code))
used_vars -= {"LAQINO_TEST_PRESENCE", "LAQINO_PUSH_ALLOW_ANY", "LAQINO_FCM_ALLOW_ANY", "LAQINO_FCM_BASE"}
undocumented = sorted(v for v in used_vars if v not in readme + deploy_doc + env_example)
check("LAQINO environment variables documented", not undocumented, undocumented)
check("FCM service-account variable documented in env.example",
      "LAQINO_FCM_SERVICE_ACCOUNT" in env_example)
check("Android Firebase secret file is not committed",
      not (ROOT / "android" / "app" / "google-services.json").exists())

print("RELEASE CHECK: " + ("OK" if not fails else str(len(fails)) + " FAILED"))
sys.exit(1 if fails else 0)
