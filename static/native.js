/* لاقينو — جسر التطبيق الأصلي (مرحلة 8). ملف واحد مستقل بلا مكتبات.
   لا يفعل شيئًا في المتصفح العادي ولا في الـPWA: يعمل فقط داخل غلاف Capacitor (window.Capacitor.isNativePlatform()).
   يطلب إذن الإشعارات، ينشئ قناة «laqino_alerts»، يسجّل جهاز FCM ويرسل توكنه إلى POST /api/fcm/register بعد تسجيل الدخول،
   ويحذفه عند الخروج (POST /api/fcm/unregister). التوكن من localStorage 't' (نفس ما يستعمله التطبيق). */
(function () {
  var C = window.Capacitor;
  if (window.__laqNative || !C || typeof C.isNativePlatform !== 'function' || !C.isNativePlatform()) return;
  window.__laqNative = 1;
  var P = C.Plugins && C.Plugins.PushNotifications;
  if (!P) return;
  var fcm = '', postedFor = '', busy = false;
  var tok = function () { try { return localStorage.getItem('t') || ''; } catch (e) { return ''; } };
  var post = function (path, t, fc) {
    return fetch('/api/fcm/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + t }, body: JSON.stringify({ token: fc, platform: 'android' }) });
  };
  function sync() {   // يُسجَّل الجهاز مرة لكل (مستخدم، توكن جهاز)؛ 503 = السيرفر لم يفعّل FCM بعد فنعيد المحاولة لاحقًا
    var t = tok(); if (!fcm || !t || busy || postedFor === t + '|' + fcm) return;
    busy = true;
    post('register', t, fcm).then(function (r) { if (r.ok) postedFor = t + '|' + fcm; }).catch(function () {}).then(function () { busy = false; });
  }
  var of = window.fetch;   // عند الخروج: احذف توكن الجهاز قبل أن يُمسح توكن الدخول
  window.fetch = function (u, o) {
    try { if (/\/api\/logout$/.test(String(u && u.url || u)) && fcm && tok()) { post('unregister', tok(), fcm).catch(function () {}); postedFor = ''; } } catch (e) {}
    return of.apply(this, arguments);
  };
  P.addListener('registration', function (r) { fcm = (r && r.value) || ''; sync(); });
  P.addListener('registrationError', function () {});
  P.addListener('pushNotificationReceived', function () { try { if (window.laqNotifRefresh) window.laqNotifRefresh(); } catch (e) {} });
  P.addListener('pushNotificationActionPerformed', function (a) {
    var k = a && a.notification && a.notification.data && a.notification.data.kind;
    location.href = k === 'chat' ? '/market.html#/chats' : '/courier.html';
  });
  Promise.resolve(P.createChannel && P.createChannel({ id: 'laqino_alerts', name: 'تنبيهات لاقينو', importance: 5, visibility: 1, vibration: true })).catch(function () {})
    .then(function () { return P.checkPermissions(); })
    .then(function (p) {   // شرح قبل نافذة النظام (perm.js)؛ «مش دلوقتي» = لا نطلب الآن ونسأل بعد 3 أيام
      if (p.receive !== 'prompt') return p;
      var ex = window.LaqPerm ? window.LaqPerm.explain('notif') : Promise.resolve(true);
      return ex.then(function (ok) { return ok ? P.requestPermissions() : p; });
    })
    .then(function (p) { if (p.receive === 'granted') return P.register(); })
    .catch(function () {});
  setInterval(sync, 15000);   // الدخول يحدث بعد فتح التطبيق: نلتقطه خلال ثوانٍ
  addEventListener('storage', sync);
})();
