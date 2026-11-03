"""Phase 88: account screen loading is progressive; refreshes are scoped and DB reads indexed."""
import os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
server = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()

def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        sys.exit(1)

# The old unconditional 8-second go(3) caused a full account rerender and
# refetched orders, listings, applications and shops even when nothing changed.
ok("no unconditional 8-second full account reload",
   "go(3)},8000)" not in html and "setInterval(()=>{if(tab==3" not in html)
ok("live order tracker still polls through the scoped tick() function",
   "setInterval(tick,4000)" in html and "osig(o)!==window._sg" in html)
ok("orders and listings load in the background with a bounded first wait",
   "window._mineDataPending" in html and "setTimeout(()=>resolve(null),650)" in html)
ok("applications and shop ownership load in the background",
   "window._metaPending" in html and "api('/my/applications')" in html and "api('/owner/shops')" in html)
ok("late responses cannot overwrite a newer navigation",
   "window._goSeq" in html and "if(navSeq!==window._goSeq)return" in html)
ok("all existing account actions and sections remain wired",
   all(x in html for x in ("mine-sj", "mine-po", "إعلاناتي", "window.fa=run", "window.oa=run", "window.sm=run", "window.ap=run")))
ok("customer order/listing indexes are additive and present",
   all(x in server for x in ("ix_delivery_customer_id ON delivery_orders(customer_id,id DESC)",
                             "ix_listings_owner_id ON listings(user_id,id DESC)",
                             "ix_order_events_order_status_at ON order_events(order_id,to_status,at)")))
print("PHASE 88 ACCOUNT LOADING CHECK: OK")
