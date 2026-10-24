# Phase 49: regression tests for prescription image count, compression, and quota separation.
from pathlib import Path
import rx

root = Path(__file__).resolve().parent
html = (root / "static" / "index.html").read_text(encoding="utf-8")
server = (root / "server.py").read_text(encoding="utf-8")
sw = (root / "static" / "sw.js").read_text(encoding="utf-8")
checks = [
    ("server-side prescription cap is five images", rx.MAX_IMAGES == 5),
    ("client preview allows up to five images", "rxChosen.length>=5" in html and "الحد الأقصى 5 صور للطلب الواحد" in html),
    ("client sends at most five images", "if(fs.length>5)throw 'الحد الأقصى 5 صور للطلب الواحد'" in html),
    ("prescription photos are compressed while preserving more detail before upload", "const compressed=await rxShrink(f)" in html and "await imgB64(compressed)" in html),
    ("old prescription images are excluded from generic file quota", "id NOT IN (SELECT file_id FROM prescriptions WHERE file_id IS NOT NULL)" in server and "id NOT IN (SELECT file_id FROM rx_images)" in server),
    ("service worker cache bumped for the new UI", 'laqino-v85' in sw),
]
for name, passed in checks:
    print(("PASS " if passed else "FAIL ") + name)
assert all(passed for _, passed in checks)
