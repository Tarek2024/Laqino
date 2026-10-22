/* لاقينو — شرح الأذونات قبل نافذة النظام (المرحلة 33). ملف واحد مستقل بلا مكتبات.
   يُستعمل داخل غلاف أندرويد فقط (native.js وlocation.js)، ولا يغيّر سلوك المتصفح/الـPWA.
   LaqPerm.explain('notif'|'location') → Promise<boolean>: true = تابع إلى نافذة إذن النظام، false = «مش دلوقتي».
   • الموافقة على الشرح تُحفظ فلا يتكرر. «مش دلوقتي» تؤجّل الشرح 3 أيام ثم يُسأل مجددًا (لا إلحاح).
   • لا يطلب أي إذن بنفسه؛ مجرد شرح بنص واضح قبل طلب النظام. */
(function () {
  'use strict';
  if (window.LaqPerm) return;
  var LATER_MS = 3 * 24 * 3600 * 1000;
  var TXT = {
    notif: { icon: '🔔', t: 'تنبيهات لاقينو', b: 'هنبعتلك تنبيه لما يوصلك رد على استفسارك، أو تتغير حالة طلبك، أو توصلك رسالة جديدة (وللمندوب: طلب توصيل جديد في منطقته). التنبيهات عامة بدون بيانات شخصية، وتقدر توقفها في أي وقت من إعدادات الجهاز.' },
    location: { icon: '📍', t: 'تحديد منطقتك', b: 'هنطلب موقعك مرة واحدة عشان نحدد منطقتك ونعرض لك الخدمات والمناديب القريبين منك. الموقع بيتحفظ على جهازك بس، ومفيش تتبّع مستمر. ولو اخترت تضيفه لطلب توصيل، المندوب بيشوفه بعد ما يقبل الطلب فقط. تقدر تمسحه في أي وقت أو تختار منطقتك يدويًا.' }
  };
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  var open = null;
  function explain(kind) {
    var x = TXT[kind];
    if (!x) return Promise.resolve(true);
    if (lsGet('laq_perm_ok_' + kind) === '1') return Promise.resolve(true);
    var later = +lsGet('laq_perm_later_' + kind) || 0;
    if (later && Date.now() - later < LATER_MS) return Promise.resolve(false);
    if (open) return open;
    open = new Promise(function (done) {
      var prev = document.activeElement;
      var o = document.createElement('div');
      o.id = 'laq-perm'; o.setAttribute('role', 'dialog'); o.setAttribute('aria-modal', 'true'); o.setAttribute('aria-labelledby', 'laq-perm-t');
      o.dir = 'rtl';
      o.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(15,42,92,.55);display:flex;align-items:center;justify-content:center;padding:18px;font-family:system-ui,"Segoe UI",Tahoma,sans-serif';
      o.innerHTML = '<div style="background:#fff;color:#1b2540;border-radius:20px;max-width:420px;width:100%;padding:22px 20px 18px;box-shadow:0 10px 40px #0004;line-height:1.8">' +
        '<div style="font-size:2rem;text-align:center" aria-hidden="true">' + x.icon + '</div>' +
        '<h2 id="laq-perm-t" style="margin:.2em 0 .4em;color:#0f2a5c;font-size:1.2rem;text-align:center">' + x.t + '</h2>' +
        '<p style="margin:0 0 16px;font-size:.95rem">' + x.b + '</p>' +
        '<div style="display:flex;flex-direction:column;gap:8px"><button type="button" id="laq-perm-y" style="min-height:46px;border:0;border-radius:12px;background:#f28c1b;color:#fff;font-size:1rem;font-weight:700">تمام، تابع</button>' +
        '<button type="button" id="laq-perm-n" style="min-height:46px;border:1px solid #c8cfe0;border-radius:12px;background:#fff;color:#0f2a5c;font-size:1rem">مش دلوقتي</button></div></div>';
      function finish(ok) {
        document.removeEventListener('keydown', key, true);
        if (o.parentNode) o.parentNode.removeChild(o);
        if (ok) lsSet('laq_perm_ok_' + kind, '1'); else lsSet('laq_perm_later_' + kind, String(Date.now()));
        try { if (prev && prev.focus) prev.focus(); } catch (e) {}
        open = null; done(ok);
      }
      function key(e) { if (e.key === 'Escape') { e.preventDefault(); finish(false); } }
      document.addEventListener('keydown', key, true);
      (document.body || document.documentElement).appendChild(o);
      o.querySelector('#laq-perm-y').onclick = function () { finish(true); };
      o.querySelector('#laq-perm-n').onclick = function () { finish(false); };
      try { o.querySelector('#laq-perm-y').focus(); } catch (e) {}
    });
    return open;
  }
  window.LaqPerm = { explain: explain };
})();
