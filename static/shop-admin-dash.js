// لاقينو — م4 (phase-77): لوحة الإدارة لدليفري المحلات (كل المحلات). ملف مستقل بلا اعتماد على globals الصفحة: التوكن من sessionStorage['at'] (كما في notif.js).
// التركيب: سطر واحد في admin.html:  <script src="/pdelivery-admin-dash.js" defer></script>  — يضيف زر «📊 دليفري المحلات» عائمًا؛ أو استدعِ window.sdaOpen() من أي زر/قسم.
(()=>{
if(window.sdaOpen)return;
const ST_RANGES=[['today','اليوم'],['week','أسبوع'],['month','الشهر'],['all','الكل']],SORTS=[['orders','الأكثر أوردرات'],['cancel','أعلى إلغاء'],['late','أعلى تأخير'],['commission','أعلى عمولة']];
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const mn=s=>s==null?'—':s<60?'< دقيقة':Math.round(s/60)+' د',pc=v=>v==null?'—':v+'%';
const tok=()=>{try{return sessionStorage.getItem('at')||''}catch(e){return ''}};
const q$=o=>Object.keys(o).filter(k=>o[k]!=='').map(k=>k+'='+encodeURIComponent(o[k])).join('&');
async function get(p,o){const r=await fetch('/api/admin/shop-delivery/'+p+'?'+q$(o),{headers:{Authorization:'Bearer '+tok()},cache:'no-store'});let j={};try{j=await r.json()}catch(e){}if(!r.ok)throw new Error(j.error||('خطأ '+r.status));return j}
let R='today',FR='',TO='',SORT='orders',box=null;
const g=(s)=>`<div class="pda-g"><div><b>${s.total}</b>أوردر</div><div><b>${s.completed}</b>مكتمل</div><div><b>${s.cancelled}</b>ملغي (${pc(s.cancel_pct)})</div><div><b>${s.abandoned}</b>تخلّي مندوب</div><div><b>${esc(s.price_sum)}</b>إجمالي القيم (ج)</div><div><b>${esc(s.commission)}</b>عمولات محصّلة (ج)</div><div><b>${mn(s.avg_accept_secs)}</b>متوسط القبول</div><div><b>${mn(s.avg_leg_secs)}</b>متوسط التوصيل</div><div><b>${mn(s.avg_total_secs)}</b>متوسط الإجمالي</div><div><b>${pc(s.late_pct)}</b>نسبة التأخير</div><div><b>${s.shops}</b>محل نشط</div><div><b>${s.couriers}</b>مندوب</div></div>`;
const tbl=(h,rows)=>rows.length?`<div class="pda-t"><table><thead><tr>${h.map(x=>'<th>'+x+'</th>').join('')}</tr></thead><tbody>${rows.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')}</tbody></table></div>`:'<small>لا بيانات في هذه الفترة</small>';
function view(d){
 const a=d.alerts,A=[];
 a.cross_shop_phones.forEach(x=>A.push(`<div class="pda-a">🔁 العميل <b dir="ltr">${esc(x.phone)}</b> طلب من ${x.shops.length} محلات (${x.orders} أوردر): ${x.shops.map(esc).join('، ')}</div>`));
 a.frequent_abandoners.forEach(x=>A.push(`<div class="pda-a">🚪 المندوب <b>${esc(x.name)}</b>${x.phone?' <span dir="ltr">'+esc(x.phone)+'</span>':''} تخلّى عن ${x.abandons} أوردرات</div>`));
 return (d.truncated?'<small>تم احتساب أحدث 5000 أوردر فقط</small>':'')+g(d.summary)+`<small>حد التأخير: ${d.late_minutes?d.late_minutes+' د (من الاستلام للتسليم)':'غير مفعّل'}</small>`
 +`<h4>⚠ تنبيهات</h4>${A.length?A.join(''):'<small>لا تنبيهات في هذه الفترة (رقم عند '+a.thresholds.shops+'+ محلات، أو مندوب تخلّى '+a.thresholds.abandons+'+ مرات)</small>'}`
 +'<h4>ترتيب المحلات</h4>'+tbl(['المحل','أوردر','مكتمل','إلغاء','تأخير','عمولة'],d.shops.map(p=>[esc(p.name),p.total,p.completed,pc(p.cancel_pct),pc(p.late_pct),esc(p.commission)]))
 +'<h4>ترتيب المناديب</h4>'+tbl(['المندوب','أوردر','مكتمل','تخلّى','تأخير','متوسط التوصيل'],d.couriers.map(p=>[esc(p.name)+(p.phone?'<br><small dir="ltr">'+esc(p.phone)+'</small>':''),p.total,p.completed,p.abandons_by,pc(p.late_pct),mn(p.avg_leg_secs)]))}
async function load(){if(!box)return;const o=box.querySelector('#sdao');o.textContent='جاري التحميل…';try{const d=await get('dashboard',{range:FR||TO?'':R,from:FR,to:TO,sort:SORT});o.innerHTML=view(d)}catch(e){o.textContent=String(e.message||e)}}
function shell(){box.innerHTML=`<div class="pda-h"><b>📊 دليفري المحلات — كل المحلات</b><button class="pda-x" data-a="close" aria-label="إغلاق">✕</button></div><div class="pda-f">${ST_RANGES.map(a=>`<button data-r="${a[0]}" class="${R==a[0]&&!FR&&!TO?'on':''}">${a[1]}</button>`).join('')}<input type="date" id="sdafr" value="${esc(FR)}" aria-label="من"><input type="date" id="sdato" value="${esc(TO)}" aria-label="إلى"><button data-a="apply">تطبيق</button></div><div class="pda-f"><select id="sdas" aria-label="الترتيب">${SORTS.map(s=>`<option value="${s[0]}"${SORT==s[0]?' selected':''}>${s[1]}</option>`).join('')}</select><button data-a="csv">⬇ CSV</button></div><div id="sdao"></div>`;load()}
async function csv(){try{const d=await get('export',{range:FR||TO?'':R,from:FR,to:TO}),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([d.csv],{type:'text/csv;charset=utf-8'}));a.download='shop-delivery-'+(FR||R)+'.csv';document.body.appendChild(a);a.click();a.remove()}catch(e){alert(e.message||e)}}
function open_(){if(box){box.hidden=!box.hidden;if(!box.hidden)load();return}
 if(!document.getElementById('sda-css')){const l=document.createElement('link');l.id='sda-css';l.rel='stylesheet';l.href='/pdelivery.css';document.head.appendChild(l)}
 box=document.createElement('div');box.className='pda';box.setAttribute('role','dialog');box.setAttribute('aria-label','لوحة دليفري المحلات');document.body.appendChild(box);
 box.addEventListener('click',e=>{const t=e.target.closest('button');if(!t)return;if(t.dataset.r){R=t.dataset.r;FR=TO='';shell()}else if(t.dataset.a=='close')box.hidden=true;else if(t.dataset.a=='apply'){FR=box.querySelector('#sdafr').value;TO=box.querySelector('#sdato').value;if(FR||TO)shell()}else if(t.dataset.a=='csv')csv()});
 box.addEventListener('change',e=>{if(e.target.id=='sdas'){SORT=e.target.value;load()}});shell()}
window.sdaOpen=open_;
})();
