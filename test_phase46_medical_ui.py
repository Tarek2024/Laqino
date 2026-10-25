"""Phase 46/63 UI regression checks: prescription upload via the single hero button, and medical reply history."""
from pathlib import Path
html=Path(__file__).with_name('static').joinpath('index.html').read_text(encoding='utf-8')

def check(name, ok):
    print(('PASS ' if ok else 'FAIL ') + name)
    if not ok: raise SystemExit(1)

check('hero button opens one image input without capture (device chooser: camera/gallery)', 'class="rxhero" onclick="rxPick()"' in html and 'id="rfp" accept="image/*" multiple onchange="rxPicked(this)"' in html and 'capture=' not in html.split('const rxInp=')[1].split(';')[0])
check('picked images go to a confirm screen with preview, kind toggle, note and send', 'const rxConfirm=' in html and 'راجع الصور قبل الإرسال' in html and 'id="rn2"' in html and 'onclick="rx()"' in html)
check('prescription upload still uses existing files and medical API routes', "api('/files',{data:b})" in html and "api('/medical/prescriptions',{file_ids:ids,region_id:R,note:$('rn2').value,kind:rxKind})" in html)
check('customer request history is shown as «طلباتك» on the home and details keep image delete', 'async function myreq()' in html and "return note()+rxInp()+gsbar('msearch')" in html and 'حذف الصورة ${(x.images.length>1)?(n+1):\'\'}' in html)
check('medicine inquiry history labels pharmacy replies and shows request date', 'استعلاماتي وردود الصيدليات' in html and 'fDt(x.created_at)' in html and "rsp(x.responses,'inquiry',x.id,x.status=='open')" in html)
check('medicine search keeps its existing search action', "api('/medical/search?q='+encodeURIComponent(sq)+'&region_id='+R)" in html and 'async function rxAsk()' in html)
check('doctor search remains available through the services grid and tabs', "MT('dr','dr','الأطباء',mt=='dr')" in html and 'async function docs()' in html)
check('labs tab/card appear only when a lab is published (admin controls visibility)', "${LON?MT('lab','lab','المعامل',mt=='lab'):''}" in html and "${LON?msc('lab'" in html)
check('medical view polls for new replies only while idle, preserving active form state', "tab===4&&mt==='rx'&&T&&!document.hidden&&!typing()&&!msg&&(!n||!n.value.trim())&&(!q||q.value.trim()===String(window.ms||''))&&!rxChosen.length" in html)
print('ALL PASSED')
