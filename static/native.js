/* لاقينو — جسر إشعارات Android الأصلي عبر Capacitor.
   لا يعمل في المتصفح أو PWA. يسجل FCM بعد تسجيل الدخول ويحافظ على Web Push كما هو. */
(function () {
  var C = window.Capacitor;
  if (!C || typeof C.isNativePlatform !== 'function' || !C.isNativePlatform() || window.__laqNativeBooted) return;

  function getPlugin() {
    var p = C.Plugins && C.Plugins.PushNotifications;
    if (!p && typeof C.registerPlugin === 'function') {
      try { p = C.registerPlugin('PushNotifications'); } catch (e) {}
    }
    return p && typeof p.addListener === 'function' ? p : null;
  }

  function boot() {
    if (window.__laqNativeBooted) return true;
    var P = getPlugin();
    if (!P) return false;
    window.__laqNativeBooted = true;

    var fcm = '', postedFor = '', busy = false;
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
      if (!fcm || !token || busy || postedFor === token + '|' + fcm) return;
      busy = true;
      post('register', token, fcm)
        .then(function (r) { if (r.ok) postedFor = token + '|' + fcm; })
        .catch(function () {})
        .then(function () { busy = false; });
    }

    function ensurePermissionAndRegistration() {
      if (!tok() || permissionBusy || Date.now() - lastPermissionCheck < 4000) return;
      permissionBusy = true;
      lastPermissionCheck = Date.now();
      Promise.resolve(P.checkPermissions())
        .then(function (p) {
          if (p.receive === 'prompt' && !permissionAsked) {
            permissionAsked = true;
            var explain = window.LaqPerm ? window.LaqPerm.explain('notif') : Promise.resolve(true);
            return explain.then(function (ok) { return ok ? P.requestPermissions() : p; });
          }
          return p;
        })
        .then(function (p) {
          if (p && p.receive === 'granted' && !registerStarted) {
            registerStarted = true;
            return P.register().catch(function (e) {
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
          postedFor = '';
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
        '/market.html#/chats': '/market.html#/chats'
      };
      var target = allowed[data.url] || ({
        chat: '/market.html#/chats',
        order: '/courier.html',
        medical: '/',
        product: '/pharmacy.html',
        shop: '/shop.html'
      }[data.kind] || '/');
      window.location.assign(target);
    });

    try {
      Promise.resolve(P.createChannel && P.createChannel({
        id: 'laqino_alerts', name: 'تنبيهات لاقينو',
        importance: 5, visibility: 1, vibration: true
      })).catch(function () {});
    } catch (e) {}

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
