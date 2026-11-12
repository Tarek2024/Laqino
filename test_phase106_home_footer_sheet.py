"""Phase 106 homepage footer and support sheet regression checks."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent
html = (ROOT / "static/index.html").read_text(encoding="utf-8")
css = (ROOT / "static/app.css").read_text(encoding="utf-8")
version = (ROOT / "VERSION").read_text(encoding="utf-8")
sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")
checks = {
    "legacy navy footer removed from homepage template": 'class="site-footer"' not in html,
    "welcome and guest account cards open support sheet": 'openHomeQuickSheet()' in html and 'الدعم، الشركاء، وعن لاقينو' in html and 'home-guest-menu-card' in html,
    "pharmacy eligibility is rechecked when the sheet opens": 'canApplyPharmacy()' in html and "results[7].status==='fulfilled'" in html,
    "pharmacy eligibility is rechecked when the sheet opens": 'canApplyPharmacy()' in html and "results[7].status==='fulfilled'" in html,
    "sheet contains pharmacy and shop partner routes": 'href="/pharmacy.html"' in html and 'href="/shop.html"' in html,
    "sheet preserves diagnostics and WhatsApp support": 'sendHomeDiagnostics()' in html and 'https://wa.me/201017011170' in html,
    "legal routes remain available": all(x in html for x in ('href="/privacy"', 'href="/terms"', 'href="/contact"')),
    "latest ads request and render up to six cards": "'/listings?limit=6'" in html and 'ads.slice(0,6)' in html,
    "bottom sheet is scrollable and layered above app": '.home-sheet-backdrop' in css and 'overflow:hidden auto' in css and 'z-index:1000' in css,
    "end brand uses centered small logo": '.home-end-brand' in css and 'align-items:center' in css,
    "release and service worker cache are aligned": 'release=phase-106' in version and 'cache=laqino-v153' in version and 'laqino-v153' in sw,
}
for label, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + label)
assert all(checks.values()), "Phase 106 homepage regression checks failed"
