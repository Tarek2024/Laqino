"""Phase 6: periodic worker retries claim deadline processing without HTTP traffic."""
import threading, time
import server

class FakeDB:
    def __init__(self): self.closed = False; self.rolled_back = False
    def close(self): self.closed = True
    def rollback(self): self.rolled_back = True

calls = []
stop = threading.Event()
instances = []
def factory():
    x = FakeDB(); instances.append(x); return x
original = server.rx.refresh_claims
def fake_refresh(c):
    calls.append(c)
    if len(calls) >= 2: stop.set()
    return 1
server.rx.refresh_claims = fake_refresh
try:
    server.rx_claim_worker(stop_event=stop, interval=5, db_factory=factory)
finally:
    server.rx.refresh_claims = original
assert len(calls) >= 2, "worker should periodically process deadlines"
assert all(x.closed for x in instances), "worker must close each DB connection"
print("PASS periodic worker ticks and closes per-tick DB connections")
