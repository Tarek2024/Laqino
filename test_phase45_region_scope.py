"""Phase 45: Riyad's customer-facing scope is the markaz, while legacy child records remain intact."""
import os, tempfile
os.environ['LAQINO_DB'] = tempfile.mktemp(suffix='.db')
os.environ['LAQINO_UPLOADS'] = tempfile.mkdtemp()
import server, svc
server.init('01000000000', 'AdminPass123')
c = server.db()

def check(name, cond):
    print(('PASS ' if cond else 'FAIL ') + name)
    if not cond: raise SystemExit(1)

try:
    mk = c.execute("SELECT * FROM regions WHERE slug='eg-kfs-riyad'").fetchone()
    zone = c.execute("SELECT * FROM regions WHERE parent_id=? AND level='zone' ORDER BY id LIMIT 1", (mk['id'],)).fetchone()
    check('seeded Riyad markaz and legacy zone records exist', bool(mk and zone))
    c.execute('UPDATE regions SET lat=?,lng=? WHERE id=?', (31.315, 30.929, zone['id']))
    c.commit()
    region, distance, state = server.resolve_region(c, 31.315, 30.929)
    check('GPS hit on a Riyad child zone returns the markaz, not the child', state == 'clear' and region['id'] == mk['id'] and region['level'] == 'markaz')
    check('child-zone database row is retained unchanged apart from test coordinates', c.execute('SELECT 1 FROM regions WHERE id=? AND parent_id=?', (zone['id'], mk['id'])).fetchone() is not None)

    # Other centers keep the existing nearest-village behavior.
    other = c.execute("INSERT INTO regions(parent_id,level,slug,name_ar,is_active,lat,lng) VALUES(2,'markaz','test-other-markaz','مركز تجريبي',1,31.6,30.9)").lastrowid
    village = c.execute("INSERT INTO regions(parent_id,level,slug,name_ar,is_active,lat,lng) VALUES(?,'village','test-other-village','قرية اختبار',1,31.6001,30.9)", (other,)).lastrowid
    c.commit()
    region, _, state = server.resolve_region(c, 31.6001, 30.9)
    check('non-Riyad location resolution behavior remains unchanged', state == 'clear' and region['id'] == village)

    # The service-search scope includes Riyad's descendants, and providers in a child region
    # can see center-scoped requests without changing the stored region tree.
    tid = c.execute("INSERT INTO service_types(name_ar,name_norm,is_active) VALUES('خدمة اختبار','خدمة اختبار',1)").lastrowid
    c.execute("INSERT INTO service_providers(name_ar,name_norm,type_id,region_id,is_published,created_at,updated_at) VALUES('مقدم اختبار','مقدم اختبار',?,?,1,1,1)", (tid, zone['id']))
    c.commit()
    check('center-scope local-service search includes providers in child zones', len(svc._matching(c, tid, mk['id'])) == 1)
    check('provider in a Riyad child zone is associated with center-scoped requests', mk['id'] in svc._provider_request_regions(c, zone['id']))
    check('non-Riyad scopes are not broadened', svc._riyad_scope_ids(c, other) == [other])
finally:
    c.close()

from pathlib import Path
html = Path(__file__).with_name('static').joinpath('index.html').read_text(encoding='utf-8')
check('general region picker no longer presents a village dropdown', 'id="vl"' not in html and 'aria-label="القرية"' not in html)
check('legacy Riyad child selection is normalized to the center scope', 'normalizeRiyadScope' in html and "slug==='eg-kfs-riyad'" in html)
