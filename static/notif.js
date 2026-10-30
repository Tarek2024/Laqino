/* لاقينو — جرس الإشعارات (مهمة 4). ملف واحد مستقل، بلا مكتبات.
   يعتمد على: GET /api/notifications/count ، GET /api/notifications?after=&limit= ، POST /api/notifications/read
   التوكن من localStorage 't'. يُركَّب في #ph-end (اللوحتان) أو زرّ عائم أعلى الشاشة (التطبيق). */
(function () {
  if (window.__laqNotif) return; window.__laqNotif = 1;
  var POLL = 30000, LIM = 30, T = '', open = false, unread = 0, items = [], maxId = 0, timer = 0, busy = false, first = true;
  var LINKS = { orders: ['/', 'طلبات التوصيل'], courier: ['/courier.html', 'لوحة المندوب'], pharmacy: ['/pharmacy.html', 'لوحة الصيدلية'], shop: ['/shop.html', 'لوحة المحل'], shoporders: ['/shop.html#o', 'طلبات المحل'], medical: ['/', 'الخدمات الطبية'], souq: ['/', 'السوق'], chat: ['/market.html#/chats', 'محادثات السوق'], svc: ['/', 'طلبات الخدمات'], svcjob: ['/', 'شغل الخدمات'] };
  var ADM = location.pathname === '/admin.html';   // لوحة الإدارة تحفظ توكنها في sessionStorage['at']
  var tok = function () { try { return (ADM ? sessionStorage.getItem('at') : localStorage.getItem('t')) || ''; } catch (e) { return ''; } };
  var esc = function (x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var api = function (p, body) {
    return fetch('/api' + p, { method: body === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + T }, body: body === undefined ? undefined : JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw j.error || r.status; return j; }); });
  };
  var num = function (j) { if (typeof j === 'number') return j; j = j || {}; var v = j.unread != null ? j.unread : j.count != null ? j.count : j.n != null ? j.n : j.unread_count; return +v || 0; };
  var arr = function (j) { return Array.isArray(j) ? j : (j && (j.items || j.notifications || j.rows)) || []; };
  var isRead = function (n) { return !!(n.read || n.is_read || n.read_at); };
  var title = function (n) { return n.title || n.text || n.message || n.body || 'إشعار جديد'; };
  var body = function (n) { return n.title && (n.body || n.message || n.text) ? (n.body || n.message || n.text) : ''; };

  var css = '.lqn[hidden]{display:none!important}.lqn{position:relative;display:inline-flex;align-items:center;font-family:inherit;direction:rtl}' +
    '.lqn.fl{position:fixed;top:calc(10px + env(safe-area-inset-top));left:12px;z-index:60}' +
    '.lqn{flex:none}.lqn-b{position:relative;box-sizing:border-box!important;flex:none;width:44px!important;min-width:44px!important;height:44px!important;min-height:44px!important;margin:0!important;padding:0!important;border:0;border-radius:50%!important;background:#ffffff26!important;color:#fff!important;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;touch-action:manipulation}' +
    '.lqn.fl .lqn-b{background:#0f2a5c!important;box-shadow:0 2px 10px #0003}' +
    '.lqn-b:active{background:#ffffff40!important}.lqn-b:focus-visible{outline:3px solid #f28c1b;outline-offset:2px}' +
    '.lqn-b svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}' +
    '.lqn-c{position:absolute;top:-2px;inset-inline-end:-2px;min-width:20px;height:20px;padding:0 5px;box-sizing:border-box;border-radius:10px;background:#f28c1b;color:#fff;font:700 .72rem/20px inherit;text-align:center;border:2px solid #0f2a5c}' +
    '.lqn-p{position:fixed;top:calc(62px + env(safe-area-inset-top));inset-inline:10px;margin-inline:auto;width:auto;max-width:380px;max-height:min(70vh,520px);display:flex;flex-direction:column;background:#fff;color:#14203a;border:1px solid #d6deed;border-radius:18px;box-shadow:0 12px 40px #0a1d4455;z-index:70;overflow:hidden;font-size:.95rem;line-height:1.55}' +
    '@media(min-width:600px){.lqn-p{inset-inline-start:auto;inset-inline-end:max(14px,calc((100vw - 1080px)/2));margin-inline:0;width:380px}}' +
    '.lqn-h{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 14px;background:#eef2f8;border-bottom:1px solid #d6deed}' +
    '.lqn-h b{font-size:1.02rem;color:#0f2a5c}.lqn-p .lqn-h button{min-height:40px;margin:0!important;padding:0 12px;border:0;border-radius:10px!important;background:transparent!important;color:#0f2a5c!important;font:600 .85rem inherit;cursor:pointer}' +
    '.lqn-l{overflow:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain}' +
    '.lqn-p .lqn-i{display:block;width:100%;text-align:start;margin:0!important;padding:12px 14px;border:0;border-bottom:1px solid #eef2f8;border-radius:0!important;background:#fff!important;color:#14203a!important;font:inherit;cursor:pointer;min-height:56px}' +
    '.lqn-p .lqn-i.u{background:#fff7ec!important;border-inline-start:4px solid #f28c1b}.lqn-p .lqn-i:active{background:#eef2f8!important}' +
    '.lqn-i b{display:block;color:#14203a}.lqn-i span{display:block;color:#5b6783;font-size:.85rem}.lqn-i small{color:#8a94ab;font-size:.75rem}' +
    '.lqn-e{padding:26px 14px;text-align:center;color:#5b6783}' +
    '.lqn-t{position:fixed;top:calc(70px + env(safe-area-inset-top));inset-inline:12px;margin-inline:auto;max-width:360px;z-index:80;padding:12px 16px;border-radius:14px;background:#0f2a5c;color:#fff;box-shadow:0 8px 28px #0a1d4466;font-weight:600;cursor:pointer;animation:lqin .25s ease}' +
    '@keyframes lqin{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.lqn-t{animation:none}}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  var root = document.createElement('div'); root.className = 'lqn'; root.hidden = true;
  root.innerHTML = '<button class="lqn-b" type="button" aria-haspopup="dialog" aria-expanded="false" aria-label="الإشعارات"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9a6 6 0 0 1 12 0c0 6 2 7.5 2 7.5H4S6 15 6 9z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg><span class="lqn-c" hidden>0</span></button>';
  var btn = root.firstChild, badge = btn.querySelector('.lqn-c'), pan = null;
  btn.addEventListener('click', function (e) { e.stopPropagation(); open ? close() : openPanel(); });

  function mount() {
    var h = document.getElementById('ph-end') || document.querySelector('header.bar') || (ADM && document.querySelector('header'));
    if (h) { h.appendChild(root); root.classList.remove('fl'); } else { root.classList.add('fl'); document.body.appendChild(root); }
  }
  function paintBadge() {
    badge.hidden = unread <= 0; badge.textContent = unread > 99 ? '99+' : unread;
    btn.setAttribute('aria-label', unread > 0 ? 'الإشعارات — ' + unread + ' غير مقروء' : 'الإشعارات');
    var t = document.title.replace(/^\(\d+\+?\)\s*/, ''); document.title = unread > 0 ? '(' + (unread > 99 ? '99+' : unread) + ') ' + t : t;
  }
  function ago(s) {
    var d = typeof s === 'number' || /^\d+$/.test(String(s)) ? new Date(+s * 1000) : new Date(String(s || '').replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(String(s || '')) ? '' : 'Z')); if (isNaN(d)) return '';
    var m = Math.round((Date.now() - d) / 60000); if (m < 1) return 'الآن'; if (m < 60) return 'منذ ' + m + ' دقيقة'; if (m < 1440) return 'منذ ' + Math.round(m / 60) + ' ساعة'; return 'منذ ' + Math.round(m / 1440) + ' يوم';
  }
  function paintList() {
    if (!pan) return; var l = pan.querySelector('.lqn-l');
    l.innerHTML = items.length ? items.map(function (n, i) {
      return '<button type="button" class="lqn-i' + (isRead(n) ? '' : ' u') + '" data-i="' + i + '"><b>' + esc(title(n)) + '</b>' + (body(n) ? '<span>' + esc(body(n)) + '</span>' : '') + '<small>' + esc(ago(n.created_at)) + '</small></button>';
    }).join('') : '<div class="lqn-e">لا توجد إشعارات</div>';
    pan.querySelector('.all').hidden = unread <= 0;
  }
  function openPanel() {
    open = true; btn.setAttribute('aria-expanded', 'true');
    pan = document.createElement('div'); pan.className = 'lqn-p'; pan.setAttribute('role', 'dialog'); pan.setAttribute('aria-label', 'الإشعارات');
    pan.innerHTML = '<div class="lqn-h"><b>الإشعارات</b><button type="button" class="all">تعليم الكل كمقروء</button></div><div class="lqn-l" aria-live="polite"><div class="lqn-e">جارٍ التحميل…</div></div>';
    document.body.appendChild(pan);
    pan.addEventListener('click', function (e) { e.stopPropagation(); });
    pan.querySelector('.all').addEventListener('click', markAll);
    pan.querySelector('.lqn-l').addEventListener('click', function (e) { var b = e.target.closest('.lqn-i'); if (b) go(items[+b.dataset.i]); });
    loadList().then(paintList);
  }
  function close() { open = false; btn.setAttribute('aria-expanded', 'false'); if (pan) { pan.remove(); pan = null; } }
  document.addEventListener('click', function () { if (open) close(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && open) { close(); btn.focus(); } });

  function go(n) {
    if (!n) return;
    var done = isRead(n) ? Promise.resolve() : api('/notifications/read', { ids: [n.id] }).then(function () { n.read = 1; unread = Math.max(0, unread - 1); paintBadge(); }).catch(function () {});
    var lk = String(n.link || ''), L = LINKS[lk]; close();
    if (lk.indexOf('admin:') === 0) {                       // إشعار للإدارة: افتح القسم المناسب
      var sec = lk.slice(6);
      return done.then(function () {
        if (ADM && typeof shell === 'function') { try { tab = sec; shell(); } catch (e) {} }
        else if (!ADM) location.href = '/admin.html';
      });
    }
    if (lk === 'medical' && (n.ref_type === 'inquiry' || n.ref_type === 'prescription') && +n.ref_id > 0) {   // رد صيدلية: افتح صفحة الطلب نفسها
      return done.then(function () {
        if (typeof window.laqOpenReq === 'function') window.laqOpenReq(n.ref_type, n.ref_id);
        else location.href = '/#req/' + n.ref_type + '/' + (+n.ref_id);
      });
    }
    done.then(function () { if (L && location.pathname !== L[0]) location.href = L[0]; });
  }
  function markAll() {
    api('/notifications/read', { all: true }).then(function () { items.forEach(function (n) { n.read = 1; }); unread = 0; paintBadge(); paintList(); }).catch(function () {});
  }
  function loadList() {
    return api('/notifications?limit=' + LIM).then(function (j) { items = arr(j); items.forEach(function (n) { if (+n.id > maxId) maxId = +n.id; }); }).catch(function () { items = []; });
  }
  var tt = 0;
  function toast(n) {
    var old = document.querySelector('.lqn-t'); if (old) old.remove(); clearTimeout(tt);
    var d = document.createElement('div'); d.className = 'lqn-t'; d.setAttribute('role', 'status'); d.textContent = title(n); document.body.appendChild(d);
    d.addEventListener('click', function () { d.remove(); go(n); }); tt = setTimeout(function () { d.remove(); }, 6000);
    try { if (navigator.vibrate && (!navigator.userActivation || navigator.userActivation.hasBeenActive)) navigator.vibrate([120, 60, 120]); } catch (e) {}
  }
  function tick() {
    if (busy || !T) return; busy = true;
    api('/notifications/count').then(function (j) {
      var c = num(j), prev = unread; unread = c; paintBadge();
      if (first) { first = false; return loadList(); }                       // أول مرة: نعرف آخر رقم فقط، بلا تنبيه
      if (c > prev || open) return api('/notifications?after=' + maxId + '&limit=' + LIM).then(function (r) {
        var nw = arr(r).filter(function (n) { return +n.id > maxId && !isRead(n); });
        arr(r).forEach(function (n) { if (+n.id > maxId) maxId = +n.id; });
        if (nw.length) { items = nw.concat(items).slice(0, 100); if (!open) toast(nw[nw.length - 1] && nw.reduce(function (a, b) { return +b.id > +a.id ? b : a; })); }
        if (open) return loadList().then(paintList);
      });
    }).catch(function (e) { if (e === 'سجّل الدخول أولًا' || e === 401) { T = ''; root.hidden = true; } }).then(function () { busy = false; });
  }
  function start() {
    T = tok(); if (!T) { root.hidden = true; return; }
    mount(); root.hidden = false; tick(); clearInterval(timer);
    timer = setInterval(function () { if (!document.hidden) { var t = tok(); if (t !== T) { T = t; first = true; unread = 0; maxId = 0; if (!T) { root.hidden = true; paintBadge(); return; } root.hidden = false; } tick(); } }, POLL);
  }
  document.addEventListener('visibilitychange', function () { if (!document.hidden) { var t = tok(); if (t !== T) { start(); return; } tick(); } });
  window.addEventListener('storage', function (e) { if (e.key === 't') start(); });
  try { var _s = Storage.prototype.setItem, _r = Storage.prototype.removeItem;   // دخول/خروج في نفس التبويب
    Storage.prototype.setItem = function (k) { var x = _s.apply(this, arguments); if ((k === 't' && this === window.localStorage) || (k === 'at' && this === window.sessionStorage)) setTimeout(start, 0); return x; };
    Storage.prototype.removeItem = function (k) { var x = _r.apply(this, arguments); if ((k === 't' && this === window.localStorage) || (k === 'at' && this === window.sessionStorage)) setTimeout(start, 0); return x; }; } catch (e) {}
  window.laqNotifRefresh = start;   // استدعِها بعد تسجيل الدخول/الخروج في التطبيق
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
