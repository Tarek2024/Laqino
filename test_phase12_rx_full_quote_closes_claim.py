"""Phase 12: approval of a full quote by the active claimant ends routing immediately."""
import sqlite3
import rx
c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
c.executescript('''
CREATE TABLE rx_claims(id INTEGER PRIMARY KEY,prescription_id INTEGER,provider_id INTEGER,claimed_at INTEGER,expires_at INTEGER,released_at INTEGER,status TEXT);
CREATE TABLE prescription_access(prescription_id INTEGER,provider_id INTEGER,PRIMARY KEY(prescription_id,provider_id));
CREATE TABLE medical_delivery_links(order_id INTEGER,source_type TEXT,source_id INTEGER,provider_id INTEGER);
CREATE TABLE delivery_orders(id INTEGER PRIMARY KEY,status TEXT);
INSERT INTO rx_claims VALUES(1,7,10,100,700,NULL,'active');
INSERT INTO prescription_access VALUES(7,10),(7,20),(7,30);
INSERT INTO delivery_orders VALUES(55,'searching');
INSERT INTO medical_delivery_links VALUES(55,'prescription',7,30);
''')
assert rx.complete_claim_on_full_approval(c,7,20,200) is True
assert tuple(c.execute("SELECT status,released_at FROM rx_claims WHERE id=1").fetchone()) == ('completed',200)
assert [r[0] for r in c.execute("SELECT provider_id FROM prescription_access WHERE prescription_id=7 ORDER BY provider_id")] == [20,30]
assert rx.complete_claim_on_full_approval(c,7,10,201) is False
print('PASS full quote approval from any approved pharmacy ends the active route immediately')
print('PASS unrelated access is revoked while approved pharmacy and active delivery access are preserved')
