# (تسامح 1 بكسل في حدود الأزرار: خط الاحتياط في بيئات الاختبار يعطي كسور بكسل مثل -0.03؛ شرط عدم وجود تمرير أفقي scrollWidth<=clientWidth بقي صارمًا.)
# المرحلة 15: شريط أقسام لوحة الإدارة كان صفًا أفقيًا واحدًا (overflow-x:auto) بـ17 قسمًا، فلا يظهر على الهاتف إلا أول 4
# والباقي (ومنها «الأطباء والتخصصات») خارج الشاشة بلا مؤشر. الإصلاح: التفاف الأقسام على عدة صفوف. فحص ثابت + فحص متصفح اختياري.
import re, os
d = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(d, "static", "admin.html"), encoding="utf-8").read()
sw = open(os.path.join(d, "static", "sw.js"), encoding="utf-8").read()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
css = re.search(r"(?<![\w-])nav\{([^}]*)\}", s).group(1)
ok("admin nav wraps onto several rows", "flex-wrap:wrap" in css)
ok("admin nav is not a hidden horizontal scroller", "overflow-x" not in css)
tabs = re.search(r"const TABS=\{(.*?)\};", s, re.S).group(1)
keys = re.findall(r"(\w+):'", tabs)
ok("23 admin sections declared (22 + home-sections tab from phase 18)", len(keys) == 23 and "doctors" in keys and "homeui" in keys)
vbody = s[s.index("const V={"):]
missing = [k for k in keys if not re.search(r"(?:^|[\n,;{])\s*(?:async\s+)?%s\s*\(\)\s*\{|V\.%s\s*=" % (k, k), vbody)]
ok("every section has a view handler: missing=%s" % missing, not missing)
ok("doctors view has specialty + doctor add forms and publish button", all(x in s for x in ("id=\"sn\"", "إضافة تخصص", "id=\"dn\"", "/publish")))
ok("service worker cache version bumped (>=v18) so phones refetch admin.html", int(re.search(r'laqino-v(\d+)', sw).group(1)) >= 18)
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP browser check (playwright not installed)"); raise SystemExit(0)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 390, "height": 780}).new_page()
    pg.set_content(s.split("<script>")[0] + "<div id='app'></div>")
    pg.evaluate("document.getElementById('app').innerHTML='<nav>'+" + repr(keys) .replace("'", '"') + ".map(k=>'<button>'+k+'</button>').join('')+'</nav>'")
    r = pg.evaluate("(()=>{const n=document.querySelector('nav');return [n.scrollWidth<=n.clientWidth, [...n.children].every(b=>{const r=b.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1})]})()")
    ok("all 23 tabs fit inside a 390px phone width without sideways scrolling", all(r)); b.close()
