/* لاقينو — جسر إشعارات Android الأصلي عبر Capacitor.
   لا يعمل في المتصفح أو PWA. يسجل FCM بعد تسجيل الدخول ويحافظ على Web Push كما هو. */
(function () {
  var C = window.Capacitor;
  if (!C || typeof C.isNativePlatform !== 'function' || !C.isNativePlatform() || window.__laqNativeBooted) return;

  function getPlugin() {
    var p = C.Plugins && C.Plugins.PushNotifications;
    if (!p && typeof C.registerPlugin === 'function') {
      try { p = C.registerPlugin('PushNotifications'); } catch (e) { return null; }
    }
    // registerPlugin creates a JS proxy even if the native header has not arrived yet.
    // Do not boot until Capacitor confirms a real native implementation; retry meanwhile.
    if (typeof C.isPluginAvailable === 'function' && !C.isPluginAvailable('PushNotifications')) return null;
    return p && typeof p.addListener === 'function' ? p : null;
  }

  function boot() {
    if (window.__laqNativeBooted) return true;
    var P = getPlugin();
    if (!P) return false;
    window.__laqNativeBooted = true;

    var fcm = '', postedFor = '', attemptedFor = '', busy = false;
    var nextSyncAt = 0, syncRetryDelay = 15000;
    var permissionBusy = false, permissionAsked = false, registerStarted = false;
    var lastPermissionCheck = 0;
    var originalFetch = window.fetch;
    var tok = function () {
      try { return localStorage.getItem('t') || ''; } catch (e) { return ''; }
    };
    var post = function (path, token, deviceToken) {
      return originalFetch.call(window, '/api/fcm/' + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: JSON.stringify({ token: deviceToken, platform: 'android' })
      });
    };

    function sync() {
      var token = tok();
      if (!fcm || !token || busy) return;
      var pair = token + '|' + fcm;
      if (attemptedFor !== pair) {
        attemptedFor = pair;
        nextSyncAt = 0;
        syncRetryDelay = 15000;
      }
      if (postedFor === pair || Date.now() < nextSyncAt) return;
      busy = true;
      post('register', token, fcm)
        .then(function (r) {
          if (r.ok) {
            postedFor = pair;
            nextSyncAt = 0;
            syncRetryDelay = 15000;
          } else {
            nextSyncAt = Date.now() + syncRetryDelay;
            syncRetryDelay = Math.min(syncRetryDelay * 2, 300000);
          }
        })
        .catch(function () {
          nextSyncAt = Date.now() + syncRetryDelay;
          syncRetryDelay = Math.min(syncRetryDelay * 2, 300000);
        })
        .then(function () { busy = false; });
    }

    function permissionDeferred() {
      try {
        var later = Number(localStorage.getItem('laq_perm_later_notif') || 0);
        if (!later) return false;
        if (Date.now() - later < 3 * 24 * 60 * 60 * 1000) return true;
        permissionAsked = false;
      } catch (e) {}
      return false;
    }

    function ensurePermissionAndRegistration() {
      if (!tok() || permissionBusy || Date.now() - lastPermissionCheck < 4000) return;
      permissionBusy = true;
      lastPermissionCheck = Date.now();
      Promise.resolve(P.checkPermissions())
        .then(function (p) {
          var deferred = permissionDeferred();
          if (p.receive === 'prompt' && !deferred && !permissionAsked) {
            permissionAsked = true;
            var explain = window.LaqPerm ? window.LaqPerm.explain('notif') : Promise.resolve(true);
            return explain.then(function (ok) { return ok ? P.requestPermissions() : p; });
          }
          return p;
        })
        .then(function (p) {
          if (p && p.receive === 'granted' && !registerStarted) {
            registerStarted = true;
            return Promise.resolve(P.register()).catch(function (e) {
              registerStarted = false;
              throw e;
            });
          }
        })
        .catch(function () {})
        .then(function () { permissionBusy = false; });
    }

    window.fetch = function (input, options) {
      try {
        var url = String(input && input.url || input);
        if (/\/api\/logout(?:\?|$)/.test(url) && fcm && tok()) {
          post('unregister', tok(), fcm).catch(function () {});
          postedFor = ''; attemptedFor = ''; nextSyncAt = 0; syncRetryDelay = 15000;
        }
      } catch (e) {}
      return originalFetch.apply(this, arguments);
    };

    function listen(event, handler) {
      try {
        var result = P.addListener(event, handler);
        if (result && typeof result.catch === 'function') result.catch(function () {});
      } catch (e) {}
    }

    listen('registration', function (r) {
      fcm = r && r.value || '';
      sync();
    });
    listen('registrationError', function () {
      registerStarted = false;
    });
    listen('pushNotificationReceived', function () {
      try { if (window.laqNotifRefresh) window.laqNotifRefresh(); } catch (e) {}
    });
    listen('pushNotificationActionPerformed', function (a) {
      var data = a && a.notification && a.notification.data || {};
      var allowed = {
        '/': '/',
        '/courier.html': '/courier.html',
        '/pharmacy.html': '/pharmacy.html',
        '/shop.html': '/shop.html',
        '/shop.html#o': '/shop.html#o',
        '/market.html': '/market.html',
        '/market.html#/chats': '/market.html#/chats'
      };
      var target = allowed[data.url] || ({
        chat: '/market.html#/chats',
        order: '/courier.html',
        medical: '/',
        product: '/pharmacy.html',
        inquiry: '/pharmacy.html',
        product_update: '/',
        shop_update: '/',
        order_update: '/',
        market: '/market.html',
        shop: '/shop.html#o'
      }[data.kind] || '/');
      window.location.assign(target);
    });

    try {
      Promise.resolve(P.createChannel && P.createChannel({
        id: 'laqino_alerts', name: 'تنبيهات لاقينو',
        importance: 5, visibility: 1, vibration: true
      })).catch(function () {});
    } catch (e) {}

    /* Android hardware back: keep navigation inside Laqino instead of closing the WebView. */
  var backListenerReady = false;
  function appBack() {
    try {
      var quick = document.getElementById('homeQuickSheet');
      if (quick && !quick.hidden) { if (window.closeHomeQuickSheet) window.closeHomeQuickSheet(); return; }
      var region = document.getElementById('sh');
      if (region && !region.hidden) { if (window.closeRg) window.closeRg(); return; }
      var lightbox = document.getElementById('lb');
      if (lightbox && window.lbclose) { window.lbclose(); return; }

      if (document.body && document.body.classList.contains('app')) {
        var state = history.state || {};
        if (state.lq === 2 && window.closeRg) { window.closeRg(); return; }
        if (window._doctorProfileId || window._labProfileId || window._medicalNavActive || state.lq === 1) {
          if (history.length > 1) { history.back(); return; }
        }
        if (typeof window._lt === 'number' && window._lt !== 0 && typeof window.go === 'function') {
          window.go(0); return;
        }
        if (location.pathname !== '/') { location.assign('/'); return; }
        return; // At the app home screen: consume Back, never exit the app.
      }

      if (location.pathname === '/shops.html' && /^#s\\d+$/.test(location.hash) && typeof window.sback === 'function') {
        window.sback(); return;
      }
      var ref = document.referrer;
      if (ref) {
        try { if (new URL(ref).origin === location.origin && history.length > 1) { history.back(); return; } } catch (_) {}
      }
      if (location.pathname !== '/') location.assign('/');
    } catch (_) {
      try { location.assign('/'); } catch (__) {}
    }
  }
  function setupBackButton() {
    if (backListenerReady) return;
    var A = C.Plugins && C.Plugins.App;
    if (!A && typeof C.registerPlugin === 'function') {
      try { A = C.registerPlugin('App'); } catch (_) {}
    }
    if (typeof C.isPluginAvailable === 'function' && !C.isPluginAvailable('App')) return;
    if (!A || typeof A.addListener !== 'function') return;
    try {
      var listener = A.addListener('backButton', appBack);
      if (listener && typeof listener.catch === 'function') listener.catch(function () {});
      backListenerReady = true;
    } catch (_) {}
  }

  function tick() {
      ensurePermissionAndRegistration();
      sync();
    }
    tick();
    setInterval(tick, 4000);
    addEventListener('storage', tick);
    addEventListener('focus', tick);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) tick();
    });
    return true;
  }

  if (!boot()) {
    var retry = setInterval(function () {
      if (boot()) clearInterval(retry);
    }, 500);
  }
})();
