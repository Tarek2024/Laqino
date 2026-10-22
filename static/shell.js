/* لاقينو — App Shell (المرحلة 21). ملف واحد مستقل بلا مكتبات، لتطبيق العميل (index.html) فقط.
   يلفّ الدالة العامة go() دون تغيير منطقها:
   • الهيدر: عنوان الصفحة + زر رجوع في الصفحات الفرعية (الجرس من notif.js يبقى كما هو).
   • حفظ موضع التمرير لكل تبويب، وانتقال قصير، والضغط على التبويب النشط يرجع لأعلى.
   • زر الرجوع في الجهاز: يقفل لوحة المنطقة أولًا ثم يرجع للرئيسية بدل الخروج من التطبيق.
   • شريط «مفيش اتصال»، وToast عام (window.laqToast)، وسحب للتحديث، وشارات التبويب.
   لا يعمل على أي صفحة ليست body.app. أي فشل هنا لا يكسر التطبيق: كل شيء داخل try. */
(function () {
  'use strict';
  var B = document.body;
  if (!B || !B.classList.contains('app') || window.__laqShell) return;
  window.__laqShell = 1;
  var $ = function (i) { return document.getElementById(i); };
  var safe = function (f) { try { return f(); } catch (e) { } };
  var curTab = function () { return typeof tab !== 'undefined' ? tab : 0; };
  var TT = {
    0: ['لاقينو', 'ابعت… والباقي علينا'], 1: ['سوق لاقينو', 'بيع واشتري جنب بيتك'], 2: ['التوصيل', 'ابعت أي حاجة والمندوب يوصلها'],
    3: ['حسابي', 'بياناتك وطلباتك'], 4: ['الخدمات الطبية', 'أدوية وصيدليات وأطباء ومعامل'], 5: ['نتائج البحث', 'ابحث في كل لاقينو'], 6: ['الخدمات المحلية', 'مقدّمو خدمات في منطقتك']
  };

  /* ---------- Toast ---------- */
  var tEl = null, tTimer = 0;
  window.laqToast = function (msg, ms) {
    safe(function () {
      if (!tEl) { tEl = document.createElement('div'); tEl.className = 'lq-toast'; tEl.setAttribute('role', 'status'); tEl.setAttribute('aria-live', 'polite'); B.appendChild(tEl); }
      tEl.textContent = msg; void tEl.offsetWidth; tEl.classList.add('on');
      clearTimeout(tTimer); tTimer = setTimeout(function () { tEl.classList.remove('on'); }, ms || 2200);
    });
  };

  /* ---------- الهيدر ---------- */
  var hd = document.querySelector('header.bar'), hb = null, hs = null, bk = null;
  if (hd) {
    hb = hd.querySelector('.wm b'); hs = hd.querySelector('.wm small');
    bk = document.createElement('button'); bk.type = 'button'; bk.className = 'bk'; bk.setAttribute('aria-label', 'رجوع للرئيسية');
    bk.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
    bk.addEventListener('click', function () { window.go(0); });
    hd.insertBefore(bk, hd.firstChild);
    var ob = document.createElement('div'); ob.className = 'offbar'; ob.setAttribute('role', 'status'); ob.textContent = 'مفيش اتصال — بتشوف آخر بيانات محفوظة'; hd.appendChild(ob);
  }
  function paintHead(t) {
    var x = TT[t] || TT[0];
    B.classList.toggle('sub', t !== 0);
    if (hb) hb.textContent = x[0];
    if (hs) hs.textContent = x[1];
    safe(function () { document.title = t === 0 ? 'لاقينو' : x[0] + ' — لاقينو'; });
  }

  /* ---------- الاتصال ---------- */
  var net = function () { B.classList.toggle('off', navigator.onLine === false); };
  addEventListener('offline', function () { net(); window.laqToast('انقطع الاتصال'); });
  addEventListener('online', function () { net(); window.laqToast('رجع الاتصال'); });
  net();

  /* ---------- go(): تمرير + انتقال + سجل المتصفح ---------- */
  var og = window.go, SP = {}, pushedTab = false, pushedSheet = false, skip = 0;
  var back = function () { skip++; history.back(); };
  window.go = async function (t) {
    var prev = window._lt, sw = prev !== undefined && prev !== t;
    if (sw) SP[prev] = window.pageYOffset || 0;
    paintHead(t);
    if (t === 0 && pushedTab) { pushedTab = false; back(); }
    if (t !== 0 && !pushedTab && sw) { pushedTab = true; safe(function () { history.pushState({ lq: 1 }, ''); }); }
    var r = await og.apply(this, arguments);
    if (sw) {
      var y = SP[t] || 0;
      if (y) requestAnimationFrame(function () { window.scrollTo(0, y); });
      var v = $('v'); if (v) { v.classList.remove('vt'); void v.offsetWidth; v.classList.add('vt'); }
    }
    dedupe(t);
    paintBadges();
    return r;
  };
  /* عنوان الصفحة يظهر في الهيدر؛ نخفي تكراره (h2) داخل المحتوى إن طابقه حرفيًا — العنوان الفرعي يبقى */
  function dedupe(t) {
    safe(function () {
      var h = document.querySelector('#v>.ph>h2'), x = TT[t];
      if (h) h.hidden = !!(x && t !== 0 && h.textContent.trim() === x[0]);
    });
  }
  var nav = document.querySelector('body.app>nav');
  if (nav) nav.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('button');
    if (b && b.classList.contains('on') && (window.pageYOffset || 0) > 40) window.scrollTo({ top: 0, behavior: 'smooth' });
  }, true);

  /* ---------- لوحة المنطقة + زر الرجوع ---------- */
  var oo = window.openRg, oc = window.closeRg, rgAtOpen = 0;
  if (oo) window.openRg = function () {
    rgAtOpen = typeof R !== 'undefined' ? R : 0;
    if (!pushedSheet) { pushedSheet = true; safe(function () { history.pushState({ lq: 2 }, ''); }); }
    return oo.apply(this, arguments);
  };
  if (oc) window.closeRg = function () {
    if (pushedSheet) { pushedSheet = false; back(); }
    var changed = typeof R !== 'undefined' && R && R !== rgAtOpen;
    var r = oc.apply(this, arguments);
    if (changed) window.laqToast('تم تغيير المنطقة');
    return r;
  };
  addEventListener('popstate', function () {
    if (skip > 0) { skip--; return; }
    if (pushedSheet) { pushedSheet = false; if (oc) oc(); return; }
    if (pushedTab) { pushedTab = false; og(0); paintHead(0); }
  });

  /* ---------- سحب للتحديث ---------- */
  var ptr = document.createElement('div'); ptr.className = 'lq-ptr'; ptr.setAttribute('aria-hidden', 'true');
  ptr.innerHTML = '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 11-2.6-5.9"/><path d="M20 4v5h-5"/></svg>'; B.appendChild(ptr);
  var sy = 0, dy = 0, pulling = false;
  var ind = function (px) { ptr.style.opacity = px > 8 ? Math.min(1, px / 70) : 0; ptr.style.transform = 'translateY(' + (px > 0 ? Math.min(px, 90) * .6 - 30 : -30) + 'px) rotate(' + px * 3 + 'deg)'; };
  addEventListener('touchstart', function (e) {
    var tg = e.target, t0 = e.touches && e.touches[0];
    pulling = !!t0 && (window.pageYOffset || 0) <= 0 && !B.classList.contains('lock') && !(tg.closest && tg.closest('input,textarea,select,.sheet,.lqn-p'));
    if (pulling) { sy = t0.clientY; dy = 0; }
  }, { passive: true });
  addEventListener('touchmove', function (e) {
    if (!pulling) return;
    dy = e.touches[0].clientY - sy;
    if (dy < 0 || (window.pageYOffset || 0) > 0) { pulling = false; ind(0); return; }
    ind(dy);
  }, { passive: true });
  addEventListener('touchend', function () {
    var fire = pulling && dy > 80 && navigator.onLine !== false; pulling = false;
    if (!fire) { ind(0); return; }
    ptr.classList.add('go'); ptr.style.opacity = 1; ptr.style.transform = 'translateY(14px)';
    window._sk = 0;
    Promise.resolve(window.go(curTab())).catch(function () { }).then(function () { setTimeout(function () { ptr.classList.remove('go'); ind(0); window.laqToast('تم التحديث', 1400); }, 350); });
  });

  /* ---------- شارات التبويب (من إشعارات غير مقروءة؛ لا تُنشئ مسارات API جديدة) ---------- */
  var nbs = {};
  function badge(btnId, dot) {
    var b = $(btnId); if (!b) return null;
    var pl = b.querySelector('.pl'); if (!pl) return null;
    var el = pl.querySelector('.nb'); if (!el) { el = document.createElement('span'); el.className = 'nb' + (dot ? ' dot' : ''); el.hidden = true; el.setAttribute('aria-hidden', 'true'); pl.appendChild(el); }
    return el;
  }
  function paintBadges() {
    nbs.souq = nbs.souq || badge('t1', true); nbs.me = nbs.me || badge('t3', false);
    var c = window.__laqUnread || { chat: 0, me: 0 };
    if (nbs.souq) nbs.souq.hidden = !(c.chat > 0) || curTab() === 1;
    if (nbs.me) { nbs.me.hidden = !(c.me > 0); nbs.me.textContent = c.me > 99 ? '99+' : c.me; }
  }
  var KS = { chat: 'chat', souq: 'chat', orders: 'me', medical: 'me', svc: 'me', svcjob: 'me' };
  function pollBadges() {
    var tk = ''; safe(function () { tk = localStorage.getItem('t') || ''; });
    if (!tk || document.hidden || navigator.onLine === false) { if (!tk) { window.__laqUnread = { chat: 0, me: 0 }; paintBadges(); } return; }
    fetch('/api/notifications?limit=50', { headers: { Authorization: 'Bearer ' + tk } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j) return;
        var a = Array.isArray(j) ? j : (j.items || j.notifications || j.rows || []), c = { chat: 0, me: 0 };
        a.forEach(function (n) { if (n.read_at || n.read || n.is_read) return; var g = KS[n.kind]; if (g) c[g]++; });
        window.__laqUnread = c; paintBadges();
      }).catch(function () { });
  }
  setInterval(pollBadges, 45000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) pollBadges(); });

  paintHead(curTab()); paintBadges(); pollBadges();
})();
