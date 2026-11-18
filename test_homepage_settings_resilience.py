import unittest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


class HomepageSettingsResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
        cls.version = (ROOT / "VERSION").read_text(encoding="utf-8")

    def test_first_render_does_not_show_legacy_hardcoded_sections(self):
        self.assertIn("const initialTiles='<div class=\"home-config-state loading\"", self.html)
        self.assertNotIn("const initialTiles=[", self.html)

    def test_home_sections_have_no_client_side_legacy_defaults_or_hidden_fetch(self):
        start = self.html.index("function homeSectionCards(")
        end = self.html.index("\nfunction homeStateMessage", start)
        helper = self.html[start:end]
        self.assertNotIn("HOME_SECTION_DEFAULTS", helper)
        self.assertNotIn("api('/home-sections')", helper)
        self.assertIn("x.visible===true", helper)

    def test_public_api_does_not_return_legacy_defaults_when_admin_config_is_missing(self):
        server = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('if not u or u["role"] != "admin":', server)
        self.assertIn('{"error": "home_sections_not_configured"}', server)
        self.assertIn("saved = defaults", server)

    def test_last_known_good_settings_are_cached_and_reused(self):
        self.assertIn("laqino_home_sections_last_valid_v1", self.html)
        self.assertIn("writeHomeCache(HOME_SECTION_CACHE_KEY,homeCfg)", self.html)
        self.assertIn("readHomeCache(HOME_SECTION_CACHE_KEY,validHomeSections)", self.html)
        self.assertIn("fallback:'last-known-good-or-explicit-error'", self.html)

    def test_products_stay_inside_medical_section_not_as_homepage_card(self):
        self.assertIn("card('shops'", self.html)
        self.assertNotIn("card('products'", self.html)
        self.assertIn("FT.products?msc('prod'", self.html)
        self.assertIn("productsEnabled", self.html)
        self.assertNotIn("shopTypes.items.length", self.html)

    def test_loading_error_and_hidden_are_distinct(self):
        self.assertIn("homeStateMessage('إعدادات الأقسام',sectionsState)", self.html)
        self.assertIn("homeStateMessage('إعدادات المحلات',shopsState)", self.html)
        self.assertIn("shopsEnabled)tileHtml", self.html)

    def test_optional_home_data_is_deferred_until_after_settings(self):
        self.assertIn("const hydrateExtras=async()=>", self.html)
        self.assertIn("requestIdleCallback", self.html)
        self.assertNotIn("timeout(signal=>api('/service-types'", self.html)

    def test_release_and_service_worker_cache_are_aligned(self):
        self.assertIn("release=phase-110", self.version)
        self.assertIn("cache=laqino-v157", self.version)
        match = re.search(r'const V = "([^"]+)"', self.sw)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "laqino-v157")


if __name__ == "__main__":
    unittest.main()
