// لاقينو — المرحلة 40: بطاقة طلب «استلام من صيدلية» في تطبيق المندوب. ملحق مستقل عن courier.html: يغلّف ordCard فيتولى هذا النوع فقط
// ويترك الطلبات العادية للدالة الأصلية كما هي. يعتمد على globals الصفحة: ST و esc و adv و rel.
(()=>{
if(typeof ordCard!='function')return;
const NXP={assigned:['heading_pickup','أنا في الطريق للصيدلية'],heading_pickup:['picked_up','استلمت الأوردر من الصيدلية'],picked_up:['heading_customer','أنا في الطريق للعميل'],heading_customer:['completed','سلّمت الأوردر للعميل ✓']},orig=ordCard;  // م2 (phase-75): الدورة تمتد حتى التسليم للعميل
const NXC=o=>o.status=='heading_customer'?`if(confirm('تأكيد: سلّمت الأوردر للعميل؟'))adv(${o.id},'completed')`:`adv(${o.id},'${NXP[o.status][0]}')`;  // التسليم النهائي بتأكيد لمنع الضغط بالخطأ
const NXS={assigned:['heading_pickup','أنا في الطريق للمحل'],heading_pickup:['picked_up','استلمت الأوردر من المحل'],picked_up:['heading_customer','أنا في الطريق للعميل'],heading_customer:['completed','سلّمت الأوردر للعميل ✓']};  // م79: «من المحل» بنفس مسار الصيدلية (4 خطوات حتى التسليم للعميل)
const shopCard=function(o){const n=NXS[o.status];
return `<div class="k" style="margin-top:8px;text-align:right"><b style="font-size:1rem">#${o.id} — ${esc(ST[o.status]||o.status)}</b> <small>🏪 استلام من محل</small>
<div>الاستلام من: ${esc(o.pickup_text)}</div>${o.dropoff_text?`<div>عنوان العميل: ${esc(o.dropoff_text)}</div>`:''}${o.pd_cust_phone?`<div>رقم العميل — <a href="tel:${esc(o.pd_cust_phone)}">${esc(o.pd_cust_phone)}</a></div>`:''}${o.pd_price!=null?`<div>سعر الأوردر: <b>${esc(o.pd_price)} ج</b></div>`:''}${o.pd_note?`<div>التفاصيل: ${esc(o.pd_note)}</div>`:''}${o.customer_phone?`<div>المحل — <a href="tel:${esc(o.customer_phone)}">${esc(o.customer_phone)}</a></div>`:''}<div><small>لا أجرة داخل التطبيق لهذا الطلب</small></div>
${n?`<button onclick="${NXC(o).replace(/"/g,'&quot;')}">${n[1]}</button> `:''}${['assigned','heading_pickup'].includes(o.status)?`<button class="s" onclick="rel(${o.id})">تخلّي عن الطلب</button>`:''}</div>`};
ordCard=function(o){if(o.origin_type==='shop_pickup')return shopCard(o);if(o.origin_type!=='provider_pickup')return orig(o);const n=NXP[o.status];
return `<div class="k" style="margin-top:8px;text-align:right"><b style="font-size:1rem">#${o.id} — ${esc(ST[o.status]||o.status)}</b> <small>🏪 استلام من صيدلية</small>
<div>الاستلام من: ${esc(o.pickup_text)}</div>${o.dropoff_text?`<div>عنوان العميل: ${esc(o.dropoff_text)}</div>`:''}${o.pd_cust_phone?`<div>رقم العميل — <a href="tel:${esc(o.pd_cust_phone)}">${esc(o.pd_cust_phone)}</a></div>`:''}${o.pd_price!=null?`<div>سعر الأوردر: <b>${esc(o.pd_price)} ج</b></div>`:''}${o.pd_note?`<div>التفاصيل: ${esc(o.pd_note)}</div>`:''}${o.customer_phone?`<div>الصيدلية — <a href="tel:${esc(o.customer_phone)}">${esc(o.customer_phone)}</a></div>`:''}<div><small>لا أجرة داخل التطبيق لهذا الطلب</small></div>
${n?`<button onclick="${NXC(o).replace(/"/g,'&quot;')}">${n[1]}</button> `:''}${['assigned','heading_pickup'].includes(o.status)?`<button class="s" onclick="rel(${o.id})">تخلّي عن الطلب</button>`:''}</div>`};
})();
