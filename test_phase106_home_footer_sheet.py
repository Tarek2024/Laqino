"""Phase 106 homepage footer and support sheet regression checks."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent
html = (ROOT / "static/index.html").read_text(encoding="utf-8")
css = (ROOT / "static/app.css").read_text(encoding="utf-8")
version = (ROOT / "VERSION").read_text(encoding="utf-8")
quick_sheet_fn = html.split("window.openHomeQuickSheet=()=>{", 1)[1].split("};", 1)[0]
native = (ROOT / "static/native.js").read_text(encoding="utf-8")
privacy = (ROOT / "static/privacy.html").read_text(encoding="utf-8")
terms = (ROOT / "static/terms.html").read_text(encoding="utf-8")
contact = (ROOT / "static/contact.html").read_text(encoding="utf-8")
delete_account = (ROOT / "static/delete-account.html").read_text(encoding="utf-8")
sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")
checks = {
    "legacy navy footer removed from homepage template": 'class="site-footer"' not in html,
    "welcome and guest account cards open support sheet": 'openHomeQuickSheet()' in html and 'الدعم، الشركاء، وعن لاقينو' in html and 'home-guest-menu-card' in html,
    "authenticated hydration keeps support and partner menu visible": 'account.innerHTML=`<div class="card home-welcome-card"><div class="me">' in html and '${quickMenu}</div>`' in html,
    "authenticated support sheet does not access hydration-local results": "results[" not in quick_sheet_fn and "AP" in quick_sheet_fn and "canApplyPharmacy()" in quick_sheet_fn,
    "sheet contains pharmacy and shop partner routes": 'href="/pharmacy.html"' in html and 'href="/shop.html"' in html,
    "sheet preserves diagnostics and WhatsApp support": 'sendHomeDiagnostics()' in html and 'https://wa.me/201017011170' in html,
    "legal routes remain available": all(x in html for x in ('href="/privacy"', 'href="/terms"', 'href="/contact"')),
    "latest ads request and render up to six cards": "'/listings?limit=6'" in html and 'ads.slice(0,6)' in html,
    "bottom sheet is scrollable and layered above app": '.home-sheet-backdrop' in css and 'overflow:hidden auto' in css and 'z-index:1000' in css,
    "end brand uses centered small logo": '.home-end-brand' in css and 'align-items:center' in css,
    "Android hardware back is intercepted without exiting the app": "addListener('backButton', appBack)" in native and "location.pathname === '/shops.html'" in native and "At the app home screen: consume Back" in native,
    "legal and account pages show a visible return link and load native back handling": all('class="lq-page-back"' in page and '<script src="/native.js" defer></script>' in page for page in (privacy, terms, contact, delete_account)),
    "release and service worker cache are aligned": 'release=phase-109' in version and 'cache=laqino-v156' in version and 'laqino-v156' in sw,
}
for label, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + label)
assert all(checks.values()), "Authenticated support sheet regression checks failed"
