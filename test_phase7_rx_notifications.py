"""Phase 7: terminal claim notifications are customer-scoped and idempotent."""
import sqlite3, time
import rx

c = sqlite3.connect(':memory:')
c.row_factory = sqlite3.Row
c.executescript('''
CREATE TABLE prescriptions(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE notifications(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT, link TEXT, ref_type TEXT, ref_id INTEGER, created_at INTEGER NOT NULL);
INSERT INTO prescriptions(id,customer_id,created_at) VALUES(7,42,1000);
''')
now = int(time.time())
a = rx._claim_terminal_notification(c, 7, 'rx.claim_timeout', 'انتهت المهلة', 'راجع طلبك', now)
b = rx._claim_terminal_notification(c, 7, 'rx.claim_timeout', 'انتهت المهلة', 'راجع طلبك', now + 1)
rows = c.execute("SELECT user_id,kind,ref_type,ref_id FROM notifications").fetchall()
assert a == 1 and b == 0, (a, b)
assert len(rows) == 1 and tuple(rows[0]) == (42, 'rx.claim_timeout', 'prescription', 7), rows
assert c.execute("SELECT link FROM notifications").fetchone()[0] == 'medical'
print('PASS terminal notification is customer-scoped and idempotent')
