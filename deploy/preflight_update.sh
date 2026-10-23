#!/usr/bin/env sh
# Fast release gate for a staging copy. Tests use temporary databases; no production data is modified.
set -eu
python3 check_versions.py
python3 release_check.py
python3 -m py_compile server.py rx.py svc.py
python3 test_phase44_auth_separation.py
python3 test_phase45_region_scope.py
python3 test_phase46_medical_ui.py
python3 test_phase47_rx_missing_items.py
python3 test_phase47_rx_schema_migration.py
python3 test_phase9_medical_delivery.py
printf '\nPRE-FLIGHT PASSED. Run backup/restore, broader regression, and browser/device tests separately before production.\n'
