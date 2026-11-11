"""Static contract: homepage shell is search-first, resilient, and keeps the four sections."""
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parent
html = (ROOT / "static/index.html").read_text(encoding="utf-8")
version = dict(line.split("=",1) for line in (ROOT / "VERSION").read_text().splitlines() if "=" in line)
sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")
def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition: raise AssertionError(name)
def extract(source, start, end):
    a=source.index(start); b=source.index(end,a); return source[a:b]
home=extract(html,"async function home(){","\nlet FG=0")
cards=extract(html,"async function homeSectionCards(","\nasync function home(){")
symbols={k:extract(html,f'<symbol id="{k}"',"</symbol>") for k in ("i3-med","i3-souq","i3-svc","i3-moto")}
check("four original section icons are present", all(symbols.values()))
check("home section builder retains medical, market, local-services, and delivery cards", all(k in cards for k in ("med:","souq:","svc:","dlv:")))
check("local services remains visible as a disabled card when no providers exist", "!svOn" in cards and "x.key!==" not in cards)
check("search renders before managed promo, then section cards", home.index('class="home-search"') < home.index('class="home-promo"') and home.index('class="home-promo"') < home.index('class="tiles"'))
check("home shell is returned without awaiting remote data", "await Promise.allSettled" not in home and "Promise.allSettled([" in home and "return shell;" in home)
check("initial-render emergency fallback and diagnostic logger exist", "home-initial-render" in html and "window.__laqinoHomeLog" in html and "home-hydration-render" in html)
check("managed campaigns are distinct from user marketplace feed", "api('/home-campaigns')" in home and "managedSlides||marketSlides||fallbackPromo" in home)
check("service worker cache and VERSION agree", version.get("cache") in sw)
print("ALL HOMEPAGE CONTRACT CHECKS PASSED")
