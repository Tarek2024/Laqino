// لاقينو — المرحلة 40: بطاقة طلب «استلام من صيدلية» في تطبيق المندوب. ملحق مستقل عن courier.html: يغلّف ordCard فيتولى هذا النوع فقط
// ويترك الطلبات العادية للدالة الأصلية كما هي. يعتمد على globals الصفحة: ST و esc و adv و rel.
(()=>{
if(typeof ordCard!='function')return;
const NXP={assigned:['heading_pickup','أنا في الطريق للصيدلية'],heading_pickup:['completed','استلمت الأوردر من الصيدلية']},orig=ordCard;
ordCard=function(o){if(o.origin_type!=='provider_pickup')return orig(o);const n=NXP[o.status];
return `<div class="k" style="margin-top:8px;text-align:right"><b style="font-size:1rem">#${o.id} — ${esc(ST[o.status]||o.status)}</b> <small>🏪 استلام من صيدلية</small>
<div>الاستلام من: ${esc(o.pickup_text)}</div>${o.dropoff_text?`<div>عنوان العميل: ${esc(o.dropoff_text)}</div>`:''}${o.customer_phone?`<div>الصيدلية — <a href="tel:${esc(o.customer_phone)}">${esc(o.customer_phone)}</a></div>`:''}<div><small>لا أجرة داخل التطبيق لهذا الطلب</small></div>
${n?`<button onclick="adv(${o.id},'${n[0]}')">${n[1]}</button> `:''}${['assigned','heading_pickup'].includes(o.status)?`<button class="s" onclick="rel(${o.id})">تخلّي عن الطلب</button>`:''}</div>`};
})();
