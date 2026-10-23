"""Phase 47 migration: legacy per-item available booleans remain readable as explicit item states."""
import sqlite3, rx
c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
c.executescript('''
CREATE TABLE users(id INTEGER PRIMARY KEY,role TEXT);
CREATE TABLE providers(user_id INTEGER PRIMARY KEY,name_ar TEXT,address TEXT,status TEXT);
CREATE TABLE files(id INTEGER PRIMARY KEY);
CREATE TABLE prescriptions(id INTEGER PRIMARY KEY,customer_id INTEGER,region_id INTEGER,file_id INTEGER,note TEXT,status TEXT,created_at INTEGER,kind TEXT);
CREATE TABLE notifications(user_id INTEGER,kind TEXT,title TEXT,body TEXT,link TEXT,ref_type TEXT,ref_id INTEGER,created_at INTEGER);
CREATE TABLE audit_log(actor_id INTEGER,action TEXT,target TEXT,detail TEXT,at INTEGER);
CREATE TABLE prescription_responses(prescription_id INTEGER,provider_id INTEGER,status TEXT,price REAL,note TEXT,updated_at INTEGER,PRIMARY KEY(prescription_id,provider_id));
CREATE TABLE rx_quote_items(prescription_id INTEGER,provider_id INTEGER,line_no INTEGER,name TEXT,qty INTEGER DEFAULT 1,unit_price REAL,available INTEGER DEFAULT 1,PRIMARY KEY(prescription_id,provider_id,line_no));
INSERT INTO rx_quote_items VALUES(1,2,1,'دواء غير متوفر',1,NULL,0);
INSERT INTO rx_quote_items VALUES(1,2,2,'دواء متوفر',1,12,1);
''')
rx.install(c)
rows=[dict(r) for r in c.execute('SELECT i.name,i.available,s.item_status FROM rx_quote_items i JOIN rx_quote_item_status s USING(prescription_id,provider_id,line_no) ORDER BY i.line_no')]
assert rows==[{'name':'دواء غير متوفر','available':0,'item_status':'unavailable'},{'name':'دواء متوفر','available':1,'item_status':'available'}],rows
assert 'item_status' not in [r[1] for r in c.execute('PRAGMA table_info(rx_quote_items)')]
for table in ('rx_prescription_items','rx_claim_items','rx_claims','rx_claim_attempts'):
    assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone(),table
rx.install(c)
assert c.execute('SELECT COUNT(*) FROM rx_quote_items').fetchone()[0]==2
# The legacy positional INSERT still works because the old table retains exactly seven columns.
c.execute("INSERT INTO rx_quote_items VALUES(1,2,3,'إضافة من الإصدار السابق',1,9,1)")
rx.install(c)
assert c.execute("SELECT item_status FROM rx_quote_item_status WHERE prescription_id=1 AND provider_id=2 AND line_no=3").fetchone()[0]=='available'
print('PASS old rx_quote_items data migrates to a separate status table without changing the legacy table columns')
print('PASS new expected-item and claim-scope tables install idempotently')
print('PASS old-version seven-column inserts still work and are backfilled on restart')
c.close()
