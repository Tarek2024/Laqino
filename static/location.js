/* لاقينو — الموقع الموحد (المرحلة 22). ملف واحد مستقل بلا مكتبات، يتحمّل بعد السكربت الرئيسي في index.html.
   المبادئ:
   • طلب واحد للموقع (getCurrentPosition) عند فتح التطبيق، لا تتبّع مستمر (لا تتبّع إطلاقًا).
   • الإحداثيات تُحفظ على جهاز المستخدم فقط (localStorage['laq_loc']). السيرفر يستلمها في مكانين فقط: /api/location/resolve
     (لتحويلها لمنطقة، ولا يخزّنها) وطلب التوصيل إذا اختار المستخدم إرفاقها (يراها المندوب بعد قبول الطلب فقط).
   • نظام اختيار المنطقة اليدوي (المحافظة ← المركز ← القرية) كما هو. عند رفض الإذن أو تعذّر الموقع لا يتغير أي شيء في التطبيق.
   • الموقع يُحوَّل لمنطقة تلقائيًا فقط إذا لم يكن المستخدم قد اختار منطقة؛ وإلا يُعرض الاقتراح ولا يُفرض (إلا بضغطة «حدّد موقعي»).
   API: window.LaqLoc = { get, fresh, request, clear, mapUrl, pinFields, state } */
(function () {
  'use strict';
  if (window.LaqLoc) return;
  var KEY = 'laq_loc', ASK = 'laq_loc_ask', DENY = 'laq_loc_deny';
  var STALE_MS = 30 * 60 * 1000;      // بعدها نحدّث الموقع مرة واحدة عند فتح التطبيق/العودة إليه (لو الإذن ممنوح أصلًا)
  var PIN_FRESH_MS = 10 * 60 * 1000;  // أقصى عمر لموقع نرفقه بطلب توصيل دون تحديث
  var C = window.Capacitor, native = !!(C && typeof C.isNativePlatform === 'function' && C.isNativePlatform());
  var NG = native && C.Plugins && C.Plugins.Geolocation;

  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function read() {
    try { var o = JSON.parse(lsGet(KEY) || 'null'); if (o && isFinite(o.lat) && isFinite(o.lng) && o.ts) return o; } catch (e) {}
    return null;
  }
  function write(o) { lsSet(KEY, o ? JSON.stringify(o) : null); }
  function toast(m) { try { if (window.laqToast) window.laqToast(m); } catch (e) {} }
  function curR() { try { return typeof R !== 'undefined' ? (+R || 0) : 0; } catch (e) { return 0; } }
  function paintChip() { try { if (typeof chip === 'function') chip(); } catch (e) {} }
  function typing() { var a = document.activeElement; return !!(a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)); }

  /* ---------- الإذن والقراءة ---------- */
  function permState() {
    if (NG && NG.checkPermissions) {
      return NG.checkPermissions().then(function (p) {
        var s = p && (p.location || p.coarseLocation);
        return s === 'granted' ? 'granted' : s === 'denied' ? 'denied' : 'prompt';
      }).catch(function () { return 'unknown'; });
    }
    if (navigator.permissions && navigator.permissions.query) {
      return navigator.permissions.query({ name: 'geolocation' }).then(function (r) { return r.state; }).catch(function () { return 'unknown'; });
    }
    return Promise.resolve('unknown');
  }
  function getPos() {   // مرة واحدة فقط. يرفض بـ {code: unsupported|insecure|denied|timeout|unavailable}
    return new Promise(function (ok, no) {
      var web = function () {
        if (window.isSecureContext === false) return no({ code: 'insecure' });
        if (!navigator.geolocation) return no({ code: 'unsupported' });
        navigator.geolocation.getCurrentPosition(function (p) {
          ok({ lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy });
        }, function (e) {
          no({ code: e && e.code === 1 ? 'denied' : e && e.code === 3 ? 'timeout' : 'unavailable' });
        }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
      };
      if (NG && NG.getCurrentPosition) {   // غلاف أندرويد (Capacitor): إذن نظام التشغيل الأصلي
        Promise.resolve(NG.checkPermissions ? NG.checkPermissions() : { location: 'granted' }).catch(function () { return {}; })
          .then(function (p) {   // شرح قبل نافذة النظام (perm.js) عند أول طلب فقط
            var s = p && (p.location || p.coarseLocation);
            if (s === 'granted' || s === 'denied' || !window.LaqPerm) return true;
            return window.LaqPerm.explain('location');
          })
          .then(function (ok) { if (!ok) throw { message: 'later' }; return NG.requestPermissions ? NG.requestPermissions() : 0; })
          .then(function () { return NG.getCurrentPosition({ enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }); })
          .then(function (p) { ok({ lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy }); })
          .catch(function (e) { if (e && e.message === 'later') no({ code: 'later' }); else if (/denied|permission/i.test(String(e && (e.message || e)))) no({ code: 'denied' }); else web(); });
      } else web();
    });
  }
  function resolve(lat, lng) {   // → {region|null} أو null عند فشل الاتصال (نبقي الإحداثيات ولا نغيّر المنطقة)
    var ctl = window.AbortController ? new AbortController() : null, t = ctl && setTimeout(function () { ctl.abort(); }, 8000);
    return fetch('/api/location/resolve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lat: lat, lng: lng }), signal: ctl ? ctl.signal : undefined })
      .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }).then(function (j) { if (t) clearTimeout(t); return j; });
  }

  /* ---------- ربطه بنظام المنطقة الحالي ---------- */
  var suggested = {};
  async function applyRegion(region, explicit) {
    if (!region) return 'none';
    var cur = curR();
    if (cur === region.id) { if (!lsGet('rgn')) { lsSet('rgn', region.name_ar); paintChip(); } return 'same'; }
    if (!cur || explicit) {
      if (typeof window.setR !== 'function') return 'none';
      await window.setR(region.id);                       // نفس مسار الاختيار اليدوي: يحفظ R وحساب المستخدم
      lsSet('rgn', region.name_ar); paintChip();
      toast('تم تحديد منطقتك: ' + region.name_ar);
      if (typeof window.go === 'function' && typeof tab !== 'undefined' && !typing()) window.go(tab);   // تحديث الشاشة الحالية بالمنطقة الجديدة
      return 'set';
    }
    if (!suggested[region.id]) { suggested[region.id] = 1; toast('موقعك الحالي في «' + region.name_ar + '». اضغط على المنطقة بالأعلى لو عايز تغيّرها.'); }
    return 'suggest';
  }

  /* ---------- الطلب (مرة واحدة لكل استدعاء) ---------- */
  var inflight = null;
  function request(opts) {
    opts = opts || {};
    if (inflight) return inflight;
    lsSet(ASK, '1');
    inflight = getPos().then(function (p) {
      lsSet(DENY, null); lastReason = '';
      return resolve(p.lat, p.lng).then(function (j) {
        var state = j && (j.state === 'clear' || j.state === 'ambiguous' || j.state === 'unspecified') ? j.state : (j && j.region ? 'clear' : 'unspecified');
        var reg = state === 'clear' && j && j.region ? j.region : null, old = read();
        window._regionSuggestion = { state: state, region: reg || null };
        var loc = { lat: +p.lat.toFixed(6), lng: +p.lng.toFixed(6), acc: Math.round(p.acc || 0), ts: Date.now(), state: state,
                    rid: reg ? reg.id : (j ? 0 : (old && old.rid) || 0), rn: reg ? reg.name_ar : (j ? '' : (old && old.rn) || '') };
        write(loc);
        return applyRegion(reg, !!opts.explicit).catch(function () { return 'none'; }).then(function (act) {
          paintSheet(); paintPin();
          return { ok: true, loc: loc, region: reg, action: act };
        });
      });
    }, function (e) {
      if (e && e.code === 'denied') lsSet(DENY, '1');
      lastReason = (e && e.code) || 'unavailable';
      paintSheet(); paintPin();
      return { ok: false, reason: (e && e.code) || 'unavailable' };
    }).then(function (r) { inflight = null; return r; }, function () { inflight = null; return { ok: false, reason: 'unavailable' }; });
    return inflight;
  }

  function fresh(maxAge) { var l = read(); return l && Date.now() - l.ts <= (maxAge || PIN_FRESH_MS) ? l : null; }
  function clear() { write(null); lsSet(DENY, null); pin = null; paintSheet(); paintPin(); }
  function mapUrl(lat, lng) { return 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(lat + ',' + lng); }

  /* ---------- لوحة المنطقة: زر «حدّد موقعي» + حالة ---------- */
  var REASON = {
    denied: 'إذن الموقع مرفوض. تقدر تفعّله من إعدادات المتصفح/التطبيق، أو اختار منطقتك يدويًا من القوائم.',
    unsupported: 'جهازك أو متصفحك مش بيدعم تحديد الموقع. اختار منطقتك يدويًا.',
    insecure: 'تحديد الموقع محتاج اتصال آمن (HTTPS). اختار منطقتك يدويًا.',
    later: 'تمام. تقدر تحدد موقعك في أي وقت بزر «حدّد موقعي»، أو اختار منطقتك يدويًا من القوائم.',
    timeout: 'تعذّر تحديد موقعك في الوقت المناسب. جرّب تاني أو اختار منطقتك يدويًا.',
    unavailable: 'تعذّر تحديد موقعك الآن. جرّب تاني أو اختار منطقتك يدويًا.'
  };
  var lastReason = '';
  function ago(ts) { var m = Math.max(0, Math.round((Date.now() - ts) / 60000)); return m < 1 ? 'دلوقتي' : m < 60 ? 'من ' + m + ' دقيقة' : 'من ' + Math.round(m / 60) + ' ساعة'; }
  function paintSheet() {
    var t = document.getElementById('lq-loc-t'), clr = document.getElementById('lq-loc-clr'), go = document.getElementById('lq-loc-go');
    if (!t) return;
    var l = read(), msg;
    if (l) {
      msg = l.state === 'ambiguous' ? 'موقعك قريب من أكثر من منطقة محتملة. اختار المركز/المنطقة يدويًا من القوائم.' : l.state === 'unspecified' ? 'اتحدد موقعك لكن لم يمكن ربطه بمنطقة معتمدة. اختار المركز/المنطقة يدويًا من القوائم.' : (l.rn ? 'موقعك الحالي: ' + l.rn : 'اتحدد موقعك، بس مفيش منطقة مسجّلة قريبة منه — اختار منطقتك من القوائم.') + ' · آخر تحديث ' + ago(l.ts);
    } else if (lastReason) msg = REASON[lastReason] || REASON.unavailable;
    else if (lsGet(DENY)) msg = REASON.denied;
    else msg = 'ممكن نحدد منطقتك تلقائيًا بالـGPS. الموقع بيتحفظ على جهازك بس ومابنتتبّعكش.';
    t.textContent = msg; if (clr) clr.hidden = !l; if (go) go.disabled = false;
  }
  function injectSheet() {
    if (document.getElementById('lq-loc')) return paintSheet();
    var g = document.getElementById('g'); if (!g || !g.parentNode) return;
    var d = document.createElement('div'); d.id = 'lq-loc'; d.className = 'lql';
    d.innerHTML = '<div class="lql-t n" id="lq-loc-t" role="status"></div><div class="lql-b"><button type="button" id="lq-loc-go" class="s">📍 حدّد موقعي تلقائيًا</button><button type="button" id="lq-loc-clr" class="line" hidden>امسح موقعي من الجهاز</button></div>';
    g.parentNode.insertBefore(d, g);
    document.getElementById('lq-loc-go').onclick = function () {
      var b = this; b.disabled = true; var t = document.getElementById('lq-loc-t'); if (t) t.textContent = 'جارٍ تحديد موقعك…';
      lastReason = '';
      request({ explicit: true }).then(function (r) {
        if (!r.ok) lastReason = r.reason;
        else { var n = document.getElementById('rn'); if (n && r.region) n.textContent = 'تم اختيار: ' + r.region.name_ar; }
        paintSheet();
      });
    };
    document.getElementById('lq-loc-clr').onclick = function () { lastReason = ''; clear(); toast('تم مسح موقعك من الجهاز'); };
    paintSheet();
  }

  /* ---------- شاشة التوصيل: يملأ «عنوان التسليم» تلقائيًا (قابل للتغيير) ---------- */
  var pin = null, AUTO = 'موقعي الحالي (GPS)';
  function pinFields() { return pin ? { dropoff_lat: pin.lat, dropoff_lng: pin.lng } : {}; }
  function paintPin() {
    var box = document.getElementById('lq-dl'); if (!box) return;
    var dr = document.getElementById('dr'), l = pin;
    box.textContent = '';
    var line = document.createElement('div'); line.className = 'lql-t n'; line.setAttribute('role', 'status');
    var row = document.createElement('div'); row.className = 'lql-b';
    var mk = function (txt, cls, fn) { var b = document.createElement('button'); b.type = 'button'; b.className = cls; b.textContent = txt; b.onclick = fn; row.appendChild(b); return b; };
    if (l) {
      line.textContent = '📍 موقع التسليم محدّد على الخريطة' + (l.acc ? ' (دقة تقريبية ' + l.acc + ' م)' : '') + ' وهيتبعت للمندوب بعد ما يقبل الطلب. تقدر تعدّل العنوان المكتوب أو تشيل الدبوس.';
      mk('تحديث موقعي', 'line', function () { this.disabled = true; usePin(true); });
      mk('تحديد يدوي', 'line', function () {
        pin = null; var d = document.getElementById('dr'); if (d) { if (d.value === AUTO) d.value = ''; d.focus(); } paintPin();
      });
    } else {
      line.textContent = lastPinReason ? (REASON[lastPinReason] || REASON.unavailable) : 'اكتب عنوان التسليم، أو استخدم موقعك الحالي.';
      mk('📍 استخدم موقعي الحالي', 'line', function () { this.disabled = true; usePin(true); });
    }
    box.appendChild(line); box.appendChild(row);
  }
  var lastPinReason = '';
  function setPinFrom(l) {
    pin = { lat: l.lat, lng: l.lng, acc: l.acc || 0 };
    var dr = document.getElementById('dr'); if (dr && !dr.value.trim()) dr.value = AUTO;
    lastPinReason = ''; paintPin();
  }
  function usePin(force) {   // يستخدم الموقع المحفوظ إن كان حديثًا، وإلا يطلب قراءة جديدة (مرة واحدة)
    var l = !force && fresh(PIN_FRESH_MS);
    if (l) return setPinFrom(l);
    return request({}).then(function (r) { if (r.ok) setPinFrom(r.loc); else { lastPinReason = r.reason; pin = null; paintPin(); } });
  }
  function decorateDelivery() {
    var rt = document.querySelector('#v .rt'), dr = document.getElementById('dr');
    if (!rt || !dr || document.getElementById('lq-dl')) return;
    var box = document.createElement('div'); box.id = 'lq-dl'; box.className = 'lql';
    rt.parentNode.insertBefore(box, rt.nextSibling);
    pin = null; lastPinReason = ''; paintPin();
    // لا نطلب إذنًا جديدًا هنا تلقائيًا إلا لو سبق طلبه (المستخدم لم يرفض): لو فيه موقع حديث نستخدمه فورًا
    var l = fresh(PIN_FRESH_MS);
    if (l) return setPinFrom(l);
    permState().then(function (s) { if (s === 'granted' && !pin && document.getElementById('lq-dl') === box) usePin(false); });
  }

  /* ---------- أنماط ---------- */
  var st = document.createElement('style');
  st.textContent = '.lql{margin:8px 0 10px}.lql-t{font-size:.9rem;line-height:1.7;margin-bottom:8px}.lql-b{display:flex;gap:8px;flex-wrap:wrap}.lql-b button{flex:1 1 auto}.lql-b[hidden],.lql button[hidden]{display:none}';
  document.head.appendChild(st);

  /* ---------- تركيب: نلفّ openRg وgo دون تغيير سلوكهما ---------- */
  var oo = window.openRg;
  if (typeof oo === 'function') window.openRg = function () { var r = oo.apply(this, arguments); injectSheet(); return r; };
  var og = window.go;
  if (typeof og === 'function') window.go = async function (t) {
    var r = await og.apply(this, arguments);
    try { if (t === 2) decorateDelivery(); } catch (e) {}
    return r;
  };

  /* ---------- بدء التشغيل: طلب واحد عند فتح التطبيق + تحديث بعد 30 دقيقة عند العودة (بدون تتبع) ---------- */
  function boot() {
    injectSheet();
    setTimeout(function () {
      permState().then(function (s) {
        var l = read();
        if (s === 'denied') { lsSet(DENY, '1'); paintSheet(); return; }
        if (s === 'granted') { if (!l || Date.now() - l.ts > STALE_MS) request({}); return; }
        if (!lsGet(ASK)) request({});   // أول مرة فقط: نظهر نافذة إذن المتصفح مرة واحدة. بعد كده الزر اليدوي «حدّد موقعي» هو الطريق.
      });
    }, 700);
  }
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) return;
    var l = read(); if (!l || Date.now() - l.ts <= STALE_MS) return;
    permState().then(function (s) { if (s === 'granted') request({}); });
  });

  window.LaqLoc = { get: read, fresh: fresh, request: request, clear: clear, mapUrl: mapUrl, pinFields: pinFields, state: permState };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
