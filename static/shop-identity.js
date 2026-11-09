/* phase-83 (م2): هوية المحل في لوحة صاحب المحل — لوجو + غلاف (اختياريين) + تنبيه الأصناف بلا صور + أداة تصغير/معاينة الصور في المتصفح.
   الاستعمال في shop.html (تبويب «المحل»): <div id="shop-identity" data-shop-id="12"></div> ثم <script src="/shop-identity.js" defer></script>
   أو يدويًا: LqShopIdentity.mount(el, shopId). نفس الأداة متاحة لرفع صور الأصناف: LqImg.pick(file,{max:1280}) ← {blob,dataUrl,w,h}، وLqImg.upload(prepared) ← id ملف. */
(function () {
  var T = function () { return localStorage.getItem('t') || ''; };
  var esc = function (x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var api = function (p, b) {
    return fetch('/api' + p, { method: b === undefined ? 'GET' : 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, T() ? { Authorization: 'Bearer ' + T() } : {}), body: b === undefined ? undefined : JSON.stringify(b) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.error || 'تعذّر التنفيذ'); return j; }); });
  };
  /* تصغير الصورة في المتصفح (يحترم اتجاه الصورة) ثم JPEG؛ الصور الأصغر من الحد لا تُكبَّر. الخادم يقبل JPG/PNG حتى 4 ميجا ويمسح الـEXIF. */
  function load(file) {
    if (window.createImageBitmap) return createImageBitmap(file, { imageOrientation: 'from-image' }).catch(function () { return viaImg(file); });
    return viaImg(file);
  }
  function viaImg(file) {
    return new Promise(function (ok, no) { var u = URL.createObjectURL(file), i = new Image(); i.onload = function () { URL.revokeObjectURL(u); ok(i); }; i.onerror = function () { URL.revokeObjectURL(u); no(new Error('الصورة تالفة أو غير مدعومة')); }; i.src = u; });
  }
  function pick(file, o) {
    o = o || {}; var max = o.max || 1280, q = o.quality || 0.85;
    if (!file || !/^image\//.test(file.type || '')) return Promise.reject(new Error('اختار ملف صورة'));
    return load(file).then(function (im) {
      var w = im.width || im.naturalWidth, h = im.height || im.naturalHeight, k = Math.min(1, max / Math.max(w, h)), W = Math.max(1, Math.round(w * k)), H = Math.max(1, Math.round(h * k));
      var cv = document.createElement('canvas'); cv.width = W; cv.height = H; var cx = cv.getContext('2d'); cx.fillStyle = '#fff'; cx.fillRect(0, 0, W, H); cx.drawImage(im, 0, 0, W, H);
      if (im.close) im.close();
      return new Promise(function (ok, no) { cv.toBlob(function (b) { if (!b) return no(new Error('تعذّر تجهيز الصورة')); ok({ blob: b, dataUrl: cv.toDataURL('image/jpeg', q), w: W, h: H, size: b.size }); }, 'image/jpeg', q); });
    });
  }
  function upload(prep) {
    return new Promise(function (ok, no) {
      var fr = new FileReader(); fr.onload = function () { ok(String(fr.result).split(',')[1]); }; fr.onerror = function () { no(new Error('تعذّر قراءة الصورة')); }; fr.readAsDataURL(prep.blob);
    }).then(function (b64) { return api('/files', { data: b64 }); }).then(function (r) { return r.id; });
  }
  window.LqImg = { pick: pick, upload: upload };

  var IDENTITY_URLS = Object.create(null), IDENTITY_PENDING = Object.create(null);
  function privUrl(id) {  // إعادة استخدام نفس التنزيل والـObject URL عند إعادة رسم لوحة المحل
    var key = String(id);
    if (IDENTITY_URLS[key]) return Promise.resolve(IDENTITY_URLS[key]);
    if (!IDENTITY_PENDING[key]) {
      IDENTITY_PENDING[key] = fetch('/api/files/' + encodeURIComponent(key), { headers: T() ? { Authorization: 'Bearer ' + T() } : {} })
        .then(function (r) { if (!r.ok) throw new Error('تعذّر تحميل صورة المحل'); return r.blob(); })
        .then(function (b) { var u = URL.createObjectURL(b); IDENTITY_URLS[key] = u; return u; })
        .then(function (u) { delete IDENTITY_PENDING[key]; return u; }, function (e) { delete IDENTITY_PENDING[key]; throw e; });
    }
    return IDENTITY_PENDING[key];
  }
  var SLOTS = { logo: { key: 'logo_file_id', max: 512, label: 'لوجو المحل', hint: 'مربع أو دائري — 512 بكسل كفاية' }, cover: { key: 'cover_file_id', max: 1600, label: 'غلاف المحل', hint: 'صورة عريضة أفقية' } };
  function mount(el, shopId) {
    if (!el) return; var S = null, pend = {}, busy = 0, msg = '', bad = 0;
    function draw() {
      var w = S ? S.items_without_images : 0;
      el.innerHTML = '<div class="card lqid"><b>هوية المحل</b> <small>(اختياري)</small>' +
        (w > 0 ? '<p class="e" role="alert">⚠️ عندك ' + w + (w == 1 ? ' صنف' : ' أصناف') + ' من غير صور. الأصناف اللي ليها صور بتتباع أكتر — ارفع صورة من تبويب الأصناف.</p>' : '') +
        '<div class="lqid-pv" style="position:relative;margin:8px 0 40px"><div id="lqid-cv" style="aspect-ratio:16/7;border-radius:14px;background:linear-gradient(135deg,#0f2a5c,#2f5fb3);overflow:hidden"></div>' +
        '<div id="lqid-lg" style="position:absolute;right:14px;bottom:-30px;width:64px;height:64px;border-radius:50%;border:3px solid #fff;background:#eef2f9;overflow:hidden"></div></div>' +
        Object.keys(SLOTS).map(function (k) {
          var sl = SLOTS[k], p = pend[k];
          return '<div style="margin:10px 0"><b>' + sl.label + '</b><br><small>' + sl.hint + '</small><br>' +
            (p ? '<img alt="معاينة ' + sl.label + '" src="' + p.dataUrl + '" style="max-width:100%;max-height:140px;border-radius:10px;margin:6px 0"><br><small>' + p.w + '×' + p.h + ' — ' + Math.round(p.size / 1024) + ' ك.ب بعد التصغير</small><br>' +
              '<button data-a="save" data-k="' + k + '"' + (busy ? ' disabled' : '') + '>رفع</button> <button class="line" data-a="cancel" data-k="' + k + '">إلغاء</button>'
              : '<label class="line" style="display:inline-block;padding:8px 14px;border-radius:10px;cursor:pointer">اختيار صورة<input type="file" accept="image/*" data-k="' + k + '" style="display:none"></label>' +
                (S && S[sl.key] ? ' <button class="line" data-a="rm" data-k="' + k + '"' + (busy ? ' disabled' : '') + '>إزالة</button>' : '')) + '</div>';
        }).join('') + (msg ? '<p class="' + (bad ? 'e' : 'okm') + '" role="status">' + esc(msg) + '</p>' : '') + '</div>';
      ['cv', 'lg'].forEach(function (z) {
        var k = z == 'cv' ? 'cover' : 'logo', box = el.querySelector('#lqid-' + z), p = pend[k], id = S && S[SLOTS[k].key];
        if (p) { box.innerHTML = '<img alt="" style="width:100%;height:100%;object-fit:cover" src="' + p.dataUrl + '">'; return; }
        if (id) privUrl(id).then(function (u) { box.innerHTML = '<img alt="" style="width:100%;height:100%;object-fit:cover" src="' + u + '">'; }).catch(function () {});
      });
    }
    function set(k, v) {
      busy = 1; msg = ''; bad = 0; draw(); var b = {}; b[SLOTS[k].key] = v;
      return api('/owner/shops/' + shopId + '/identity', b).then(function (r) { S[SLOTS[k].key] = r[SLOTS[k].key]; delete pend[k]; msg = 'تم الحفظ ✓'; }).catch(function (e) { msg = e.message; bad = 1; }).then(function () { busy = 0; draw(); });
    }
    el.addEventListener('change', function (e) {
      var i = e.target; if (!i || i.type != 'file' || !i.files[0]) return; var k = i.getAttribute('data-k'); msg = ''; bad = 0;
      pick(i.files[0], { max: SLOTS[k].max }).then(function (p) { pend[k] = p; draw(); }).catch(function (er) { msg = er.message; bad = 1; draw(); });
    });
    el.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('button[data-a]'); if (!b || busy) return; var k = b.getAttribute('data-k'), a = b.getAttribute('data-a');
      if (a == 'cancel') { delete pend[k]; draw(); }
      else if (a == 'rm') set(k, null);
      else if (a == 'save') { busy = 1; msg = 'جاري الرفع…'; bad = 0; draw(); upload(pend[k]).then(function (id) { busy = 0; return set(k, id); }).catch(function (er) { busy = 0; msg = er.message; bad = 1; draw(); }); }
    });
    api('/owner/shops').then(function (r) { S = (r.items || []).filter(function (x) { return x.id == shopId; })[0]; if (!S) throw new Error('المحل غير موجود'); draw(); }).catch(function (e) { el.innerHTML = '<p class="e">' + esc(e.message) + '</p>'; });
  }
  window.LqShopIdentity = { mount: mount };
  document.addEventListener('DOMContentLoaded', function () { var e = document.getElementById('shop-identity'); if (e && +e.getAttribute('data-shop-id')) mount(e, +e.getAttribute('data-shop-id')); });
})();
