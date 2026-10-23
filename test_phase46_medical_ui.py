"""Phase 46 UI regression checks for prescription uploads and medical reply history."""
from pathlib import Path
html=Path(__file__).with_name('static').joinpath('index.html').read_text(encoding='utf-8')

def check(name, ok):
    print(('PASS ' if ok else 'FAIL ') + name)
    if not ok: raise SystemExit(1)

# Camera and gallery remain separate user actions and share the existing preview handler.
check('camera action uses rear-camera capture input', '📷 فتح الكاميرا' in html and 'id="rfc" accept="image/*" capture="environment"' in html and 'onchange="rxPreview(this)"' in html)
check('gallery action remains available and previews before sending', 'اختيار من المعرض' in html and 'id="rf" accept="image/jpeg,image/png,image/webp"' in html and 'id="rx-previews"' in html)
check('prescription upload still uses existing files and medical API routes', "api('/files',{data:b})" in html and "api('/medical/prescriptions',{file_ids:ids,region_id:R,note:$('rn2').value,kind:rxKind})" in html)
# The customer's own prescription history is rendered directly after the upload card.
form_pos=html.find("return note()+sub+`<div class=\"card\"><b>${rxKind")
mine_pos=html.find('`+mine+`<div class="card"><button class="line full"', form_pos)
toggle_pos=html.find("العودة إلى ابعت روشتتك", form_pos)
check('روشتاتي appears immediately after the send form and before the image-kind toggle', form_pos >= 0 and mine_pos > form_pos and toggle_pos > mine_pos)
check('prescription history shows submitted date and actual quote data', 'fDt(x.created_at)' in html and 'rxq(qs[k],x.id,true)' in html and "rsp(x.responses,'prescription',x.id,false)" in html)
check('medicine inquiry history labels pharmacy replies and shows request date', 'استعلاماتي وردود الصيدليات' in html and 'fDt(x.created_at)' in html and "rsp(x.responses,'inquiry',x.id,x.status=='open')" in html)
check('medicine search stays expandable and preserves its existing search action', '<details class="card med-ask"' in html and 'اضغط لفتح البحث أو إغلاقه' in html and "api('/medical/search?q='+encodeURIComponent(sq)+'&region_id='+R)" in html)
check('doctor search remains available through medical tabs', "MT('dr','dr','الأطباء',mt=='dr')" in html and 'async function docs()' in html)
check('medical view polls for new replies only while idle, preserving active form state', "tab===4&&mt==='rx'&&T&&!document.hidden&&!typing()&&!msg&&(!n||!n.value.trim())&&(!q||q.value.trim()===String(window.ms||''))&&!rxChosen.length" in html)
