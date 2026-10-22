from pathlib import Path

ROOT = Path(__file__).parent

def check(cond, message):
    if not cond:
        raise AssertionError(message)
    print('PASS', message)

theme = (ROOT / 'static/theme.css').read_text()
market = (ROOT / 'static/market.html').read_text()
sw = (ROOT / 'static/sw.js').read_text()
check('@media(max-width:430px)' in theme, 'shared responsive rules cover phone widths through 430px')
check('@media(min-width:431px) and (max-width:767px)' in theme, 'shared responsive rules cover small tablets')
check('overflow-x:auto' in theme, 'wide data tables scroll inside their wrappers rather than forcing page overflow')
check('id="lagino-market-polish"' in market, 'standalone marketplace receives its own visual consistency layer')
check('grid-template-columns:repeat(2,minmax(0,1fr))' in market, 'market category/card grids use two responsive columns where matching grid classes exist')
import re
check(int(re.search(r'laqino-v(\d+)', sw).group(1)) >= 51, 'PWA cache version updated for the new stylesheet rules (v51 or newer)')
for name in ('static/index.html','static/pharmacy.html','static/admin.html','static/courier.html'):
    source=(ROOT/name).read_text()
    check('/theme.css' in source, f'{name} loads the shared theme')
print('ALL PASSED')
