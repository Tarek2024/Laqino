// لاقينو — المرحلة 40: بطاقة إعدادات «طلب مندوب من الصيدليات» في لوحة الإدارة (تبويب واجهة الرئيسية). ملحق مستقل عن admin.html:
// يحقن بطاقته بعد بطاقة المنتجات بـMutationObserver. يعتمد على globals الصفحة: api و esc و okm و fail.
(()=>{
let PD=null,BZ=0;
const card=()=>`<div class="card" id="feat-pd"><h3>طلب مندوب من الصيدليات (زر «اطلب دليفري»)</h3><p>الحالة الحالية: <b>${PD.enabled?'مفعّل':'مطفي'}</b>. الصيدلية المعتمدة تضغط زرًا واحدًا فيستلم أول مندوب متاح الأوردر منها، وينتهي الطلب لحظة الاستلام. بلا أجرة داخل التطبيق.</p><label><input type="checkbox" id="pd-on" ${PD.enabled?'checked':''}> تفعيل الزر لكل الصيدليات المعتمدة</label><label>عمولة الطلب على المندوب (ج، 0 = مجانية)<input id="pd-comm" type="number" min="0" step="0.5" value="${esc(PD.commission)}" style="width:110px"></label><button onclick="savePD()">حفظ</button><div id="pd-msg" role="status"></div></div>`;
function put(){const a=document.getElementById('feat-products');if(!a||document.getElementById('feat-pd'))return;
 if(PD){a.insertAdjacentHTML('afterend',card());return}
 if(BZ)return;BZ=1;api('/admin/provider-delivery').then(r=>{PD=r}).catch(()=>{}).finally(()=>{BZ=0;if(PD)put()})}
window.savePD=async()=>{try{PD=await api('/admin/provider-delivery',{enabled:document.getElementById('pd-on').checked,commission:Number(document.getElementById('pd-comm').value||0)});const o=document.getElementById('feat-pd');if(o)o.outerHTML=card();okm(PD.enabled?'تم تفعيل طلب المندوب من الصيدليات':'تم إيقاف طلب المندوب من الصيدليات')}catch(e){const m=document.getElementById('pd-msg');if(m)m.textContent=String(e);fail(e)}};
const app=document.getElementById('app');if(app){new MutationObserver(put).observe(app,{childList:true,subtree:true});put()}
})();
