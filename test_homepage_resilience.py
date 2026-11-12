"""Fail-safe homepage startup and diagnostic logging tests using the real UI harness."""
import os, tempfile, threading, time, json, subprocess
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server
from http.server import ThreadingHTTPServer
server.init("01000000000", "AdminPass123")
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
ROOT = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(ROOT, "test_ui_page_harness.js")

def page(steps):
    p = subprocess.run(["node", HARNESS, "index", BASE, "", json.dumps(steps)], capture_output=True, text=True, timeout=20)
    if p.returncode: raise AssertionError("UI harness failed: " + p.stderr[-1200:])
    return json.loads(p.stdout)

def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition: raise AssertionError(name)

# A permanently stalled network must not delay first paint of search and primary navigation.
r = page([{"js":"fetch=(u,o)=>new Promise(()=>{});go(0)","wait":150,"snap":"v"}])
v = r["v"]
check("home renders search before remote API requests resolve", 'id="gq"' in v and 'class="home-promo"' in v and v.index('id="gq"') < v.index('class="home-promo"') < v.index('class="tiles"'))
check("four primary section cards render while network is stalled", v.count('class="ti"') == 4 and all(x in v for x in ("الخدمات الطبية","سوق لاقينو","الخدمات المحلية","التوصيل")))

# Individual request failures are identified by endpoint and preserve the first-paint shell.
r = page([{"js":"var realFetch=fetch;fetch=(u,o)=>String(u).includes('/api')?Promise.reject(new Error('simulated-network-down')):realFetch(u,o);go(0)","wait":450,"snap":"v"}])
stages = [x.get("stage","") for x in r.get("diagnostics",[])]
check("failed homepage endpoints are logged with their endpoint names", any(x == "api:managed-campaigns" for x in stages) and any(x.startswith("api:") for x in stages))
check("API failure leaves search, promo, and four cards visible", 'id="gq"' in r["v"] and 'class="home-promo"' in r["v"] and r["v"].count('class="ti"') == 4)

# Force a synchronous render failure and verify the emergency shell plus a reasoned log.
r = page([{"js":"home=async()=>{throw new Error('forced-render-failure')};go(0)","wait":100,"snap":"v"}])
stages = [x.get("stage","") for x in r.get("diagnostics",[])]
messages = [x.get("message","") for x in r.get("diagnostics",[])]
check("render exception is recorded with a clear stage and message", "home-initial-render" in stages and any("forced-render-failure" in x for x in messages))
check("emergency home shell remains usable after render exception", 'id="gq"' in r["v"] and 'onclick="go(1)"' in r["v"] and "ظهرت النسخة الأساسية من الرئيسية" in r["v"])
print("ALL HOMEPAGE RESILIENCE CHECKS PASSED")
