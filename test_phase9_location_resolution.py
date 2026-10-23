"""Phase 9: GPS resolution distinguishes clear, ambiguous, and unspecified states."""
import sqlite3, pathlib
import server

def db_with(rows):
    c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE regions(id INTEGER PRIMARY KEY,parent_id INTEGER,level TEXT,name_ar TEXT,lat REAL,lng REAL,is_active INTEGER)')
    c.executemany('INSERT INTO regions(id,parent_id,level,name_ar,lat,lng,is_active) VALUES(?,?,?,?,?,?,?)', rows)
    return c
# Equidistant nearby villages: never guess.
c = db_with([(1,None,'village','قرية أ',0,-0.005,1),(2,None,'village','قرية ب',0,0.005,1)])
r, dist, state = server.resolve_region(c, 0, 0)
assert r is None and state == 'ambiguous' and dist is not None, (r, dist, state)
c.close()
# A single candidate is a clear match.
c = db_with([(1,None,'village','قرية أ',0,0.002,1),(2,None,'village','قرية ب',0,0.02,1)])
r, dist, state = server.resolve_region(c, 0, 0)
assert r and r['id'] == 1 and state == 'clear', (r, dist, state)
c.close()
# No active candidate inside configured radius: manual selection required.
c = db_with([(1,None,'village','بعيدة',10,10,1)])
r, dist, state = server.resolve_region(c, 0, 0)
assert r is None and dist is None and state == 'unspecified', (r, dist, state)
c.close()
# Regression: remove call to a function that does not exist; it previously interrupted startup before go(0).
html = pathlib.Path(__file__).with_name('static').joinpath('index.html').read_text(encoding='utf-8')
assert 'suggestRegionFromGPS()' not in html
print('PASS GPS clear/ambiguous/unspecified states')
print('PASS index startup does not call undefined suggestRegionFromGPS')
