"""Phase 13: a SQLite lease prevents two app processes sharing one DB from sweeping simultaneously."""
import sqlite3
import server
c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
c.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
assert server._rx_worker_acquire_lease(c, 'worker-A', now=100, lease_seconds=20) is True
assert server._rx_worker_acquire_lease(c, 'worker-B', now=101, lease_seconds=20) is False
# The current owner can renew its lease.
assert server._rx_worker_acquire_lease(c, 'worker-A', now=102, lease_seconds=20) is True
# A second process can take over after the lease expires.
assert server._rx_worker_acquire_lease(c, 'worker-B', now=123, lease_seconds=20) is True
assert c.execute("SELECT value FROM settings WHERE key='rx_claim_worker_lease'").fetchone()[0] == 'worker-B|143'
print('PASS shared-database worker lease prevents overlapping sweep ownership')
print('PASS lease can be renewed and acquired after expiry')
