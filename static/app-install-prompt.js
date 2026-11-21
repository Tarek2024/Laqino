/* Laqino contextual Android app install prompts.
   Website-only: shown after a successful action or meaningful homepage engagement. */
(function () {
  'use strict';
  var KEY = 'laqino_app_prompt_dismissed_at';
  var COOLDOWN = 7 * 24 * 60 * 60 * 1000;
  function isEligible() {
    var ua = navigator.userAgent || '';
    if (!/Android/i.test(ua)) return false;
    try {
      if (window.Capacitor && typeof window.Capacitor.isNativePlatform === 'function' &&
          window.Capacitor.isNativePlatform()) return false;
      if ((window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
          navigator.standalone === true) return false;
      var dismissed = Number(localStorage.getItem(KEY) || 0);
      if (dismissed && Date.now() - dismissed < COOLDOWN) return false;
    } catch (_) {}
    return true;
  }
  function dismiss(el) {
    try { localStorage.setItem(KEY, String(Date.now())); } catch (_) {}
    var card = el && el.closest('.laq-app-tip, .laq-home-install');
    if (card) card.remove();
  }
  function show(kind) {
    if (!isEligible()) return;
    var root = document.getElementById('v');
    if (!root || root.querySelector('.laq-app-tip')) return;
    var copy = kind === 'rx'
      ? 'خليك متابع ردود الصيدليات أول بأول، واعرف تحديثات روشتتك من موبايلك.'
      : 'تابع طلبك بسهولة واستقبل تحديثاته مباشرة على موبايلك.';
    var card = document.createElement('section');
    card.className = 'laq-app-tip';
    card.setAttribute('aria-label', 'تطبيق لاقينو');
    card.innerHTML =
      '<div class="laq-app-tip-copy"><strong>خلّي لاقينو معاك على موبايلك</strong>' +
      '<p></p></div><div class="laq-app-tip-actions">' +
      '<a href="/download" rel="nofollow">نزّل تطبيق لاقينو</a>' +
      '<button type="button" aria-label="إغلاق الاقتراح">مش دلوقتي</button></div>';
    card.querySelector('p').textContent = copy;
    card.querySelector('button').addEventListener('click', function () { dismiss(card); });
    var status = root.querySelector('.okb[role="status"]');
    if (status && status.parentNode) status.insertAdjacentElement('afterend', card);
    else root.insertBefore(card, root.firstChild);
  }
  function home() {
    if (window.__laqHomePromptCleanup) window.__laqHomePromptCleanup();
    if (!isEligible()) return;
    var root = document.getElementById('v');
    var promo = root && root.querySelector('.home-hero .home-promo');
    if (!root || !promo || root.querySelector('.laq-home-install')) return;
    var timer = null, armed = false, done = false;
    var events = ['pointerdown', 'touchstart', 'scroll', 'keydown'];
    function cleanup() {
      if (timer) clearTimeout(timer);
      events.forEach(function (name) {
        root.removeEventListener(name, onEngage, true);
        window.removeEventListener(name, onEngage, true);
      });
      if (window.__laqHomePromptCleanup === cleanup) window.__laqHomePromptCleanup = null;
    }
    function isTyping(target) {
      return !!(target && (target.closest('input,textarea,select,[contenteditable="true"]')));
    }
    function onEngage(event) {
      if (done || !isEligible() || isTyping(event && event.target)) return;
      if (armed) return;
      armed = true;
      timer = setTimeout(function () {
        timer = null;
        if (!isEligible() || window._lt !== 0 || !document.getElementById('v') ||
            !document.querySelector('#v .home-hero .home-promo')) {
          cleanup();
          return;
        }
        if (isTyping(document.activeElement) || document.hidden) {
          armed = false;
          return;
        }
        done = true;
        cleanup();
        var card = document.createElement('aside');
        card.className = 'laq-home-install';
        card.setAttribute('aria-label', 'تثبيت تطبيق لاقينو');
        card.innerHTML =
          '<div class="laq-home-install-copy"><strong>خلّي لاقينو أقرب ليك</strong>' +
          '<small>ثبّت التطبيق وتابع طلباتك وتحديثات الروشتات بسهولة.</small></div>' +
          '<div class="laq-home-install-actions"><a class="laq-home-install-link" href="/download" rel="nofollow">ثبّت لاقينو</a>' +
          '<button class="laq-home-install-close" type="button" aria-label="مش دلوقتي">×</button></div>';
        card.querySelector('a').addEventListener('click', function () {
          try { localStorage.setItem(KEY, String(Date.now())); } catch (_) {}
        });
        card.querySelector('button').addEventListener('click', function () { dismiss(card); });
        promo.insertAdjacentElement('afterend', card);
      }, 8000);
    }
    events.forEach(function (name) {
      root.addEventListener(name, onEngage, true);
      window.addEventListener(name, onEngage, true);
    });
    window.__laqHomePromptCleanup = cleanup;
  }
  var style = document.createElement('style');
  style.textContent = '.laq-app-tip{margin:12px 0;padding:14px;border:1px solid #d7e5f5;border-radius:16px;background:#f5f9ff;color:#17345c;display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.laq-app-tip-copy{flex:1;min-width:190px}.laq-app-tip-copy strong{display:block;font-size:14px}.laq-app-tip-copy p{margin:5px 0 0;font-size:13px;line-height:1.6;color:#52657d}.laq-app-tip-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.laq-app-tip-actions a{display:inline-flex;align-items:center;justify-content:center;padding:9px 13px;border-radius:10px;background:#1457a6;color:#fff;text-decoration:none;font-weight:700;font-size:13px}.laq-app-tip-actions button{border:0;background:transparent;color:#64748b;padding:8px;font:inherit;font-size:12px;cursor:pointer}';
  document.head.appendChild(style);
  window.LaqAppPrompt = { show: show, home: home };
})();