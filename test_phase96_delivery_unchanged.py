"""Guard the original delivery request page and delivery lifecycle against regressions."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

# SHA-256 fingerprints captured from main before the account-orders archive update.
# These cover the customer-facing delivery form and its original lifecycle maps.
EXPECTED = {
    "delivery_page": "04c7a9870f900ff7cca09256caa64a24ebe2c8691929df8edff5bf7d276cec8b",
    "lifecycle": "16f19b88bdcd9a755c610dd4b8600689312b59b7634e757231e1fc01d27479ef",
}


def extract(start, end, label):
    first = SOURCE.find(start)
    if first < 0 or SOURCE.find(start, first + len(start)) >= 0:
        raise AssertionError(f"{label}: expected exactly one start marker")
    last = SOURCE.find(end, first + len(start))
    if last < 0:
        raise AssertionError(f"{label}: end marker not found")
    return SOURCE[first:last]


def verify(label, value):
    actual = hashlib.sha256(value.encode("utf-8")).hexdigest()
    ok = actual == EXPECTED[label]
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        raise AssertionError(
            f"{label} changed: expected {EXPECTED[label]}, got {actual}"
        )


delivery_page = extract("async function deliv(){", "let RK=''", "delivery page")
lifecycle = extract("const STEP=", "const SHP=", "delivery lifecycle")

verify("delivery_page", delivery_page)
verify("lifecycle", lifecycle)
print("ALL DELIVERY-UNCHANGED CHECKS PASSED")
