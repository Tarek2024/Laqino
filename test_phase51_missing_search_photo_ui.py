from pathlib import Path

root = Path(__file__).parent
ui = (root / "static" / "index.html").read_text(encoding="utf-8")
sw = (root / "static" / "sw.js").read_text(encoding="utf-8")
rx = (root / "rx.py").read_text(encoding="utf-8")
checks = {
    "missing-search UI offers optional single-image picker": "input.accept='image/jpeg,image/png,image/webp'" in ui and "body.file_ids=[" in ui,
    "image is compressed before upload": "const compressed=await rxShrink(file)" in ui,
    "typed-only path remains available": "await send(null)" in ui,
    "server enforces at most one image": "len(raw_ids) > 1" in rx,
    "server labels child search as photo-backed": '"item_photo" if fids else "typed_items"' in rx,
    "service worker cache is bumped": __import__('re').search(r'const V = "laqino-v(\d+)"', sw) is not None and int(__import__('re').search(r'const V = "laqino-v(\d+)"', sw).group(1)) >= 87,
}
for label, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + label)
if not all(checks.values()):
    raise SystemExit(1)
