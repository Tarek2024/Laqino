# Phase 82 compatibility check: verify the shop's current self-contained delivery UI.
# The shop page no longer imports the pharmacy's pdelivery.js module; pharmacy still does.
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
rd = lambda *p: open(os.path.join(HERE, *p), encoding="utf-8").read()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))

shop = rd("static", "shop.html")
pharmacy = rd("static", "pharmacy.html")
sw = rd("static", "sw.js")
version = rd("VERSION")

scripts = re.findall(r'<script[^>]+src="([^"]+)"[^>]*>', shop)
inline = shop.find("<script>")
ok("shop loads its current notification and identity modules before inline app code",
   scripts.index("/notif.js") < inline and scripts.index("/shop-identity.js") < inline)
ok("shop does not depend on the pharmacy delivery module",
   "/pdelivery.js" not in scripts and "PDL." not in shop)
ok("shop renders its own delivery card and order rows",
   all(x in shop for x in ("const dlcard=", "const dlrows=", "const dltxt=", "const ordInner=")))
ok("shop owns request, polling, delivery-confirmation and cancel actions",
   all(x in shop for x in ("window.dlsend=async", "ordLoad(SEL)", "window.dldone=run", "window.dlx=run", "/delivery-request")))
ok("shop delivery requests are scoped to the selected shop",
   "/owner/shops/'+SEL+'/delivery-request" in shop and "/owner/shops/'+SEL+'/delivery-requests/'+id+'/delivered" in shop)
ok("pharmacy still loads the shared pdelivery.js module",
   '<script src="/pdelivery.js"></script>' in pharmacy)
m = re.search(r"cache=(laqino-v\d+)", version)
swv = re.search(r'const V = "(laqino-v\d+)"', sw)
ok("VERSION cache label matches the active service-worker cache",
   bool(m) and bool(swv) and m.group(1) == swv.group(1))
