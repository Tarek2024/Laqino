// Service worker: caches only the static app shell. /api/* is NEVER cached (live data, tokens, private files).
const V = "laqino-v107", SHELL = ["/", "/register.html", "/courier.html", "/pharmacy.html", "/admin.html", "/assets/logo.jpg", "/assets/mascot.jpg", "/assets/icon-192.png", "/manifest.webmanifest", "/offline.html", "/theme.css", "/app.css", "/panel.css", "/notif.js", "/native.js", "/perm.js", "/location.js", "/market.html", "/market-enhancements.css", "/market-enhancements.css?v=3", "/shell.css", "/shell.js", "/assets/mascot-cut.webp", "/pdelivery.js", "/pdelivery.css", "/pdelivery-admin.js", "/pdelivery-courier.js"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V && k !== "laqino-meta").map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;
  // network first, fall back to cache, then to the offline page for navigations
  e.respondWith(fetch(r).then(res => { if (res.ok) { const cp = res.clone(); caches.open(V).then(c => c.put(r, cp)); } return res; })
    .catch(() => caches.match(r).then(m => m || (r.mode === "navigate" ? caches.match("/offline.html") : Response.error()))));
});

// Web Push: the push carries no data (privacy). On every push the worker asks the server for COUNTS only (POST /api/push/state):
//   pending = delivery orders still waiting for THIS device's courier, chat = unread chat messages (Phase 4), courier = is the account an approved courier.
// pending>0 -> loud, repeating order alert (always wins); pending==0 and chat>0 -> a plain chat notification; both 0 -> the order was taken/cancelled/expired, so the alert is cleared.
// If the server cannot be reached the worker fails OPEN and shows the order alert (a missed order is worse than a spurious alert) -- except on a device whose account was last
// seen as NOT a courier (hint cached below), which gets a neutral notification instead.
const ALERT_TAG = "laqino-order", CHAT_TAG = "laqino-chat", MEDICAL_TAG = "laqino-medical", ICON = "/assets/icon-192.png", META_CACHE = "laqino-meta", META_KEY = "/__laqino_meta";
const metaGet = async () => { try { const r = await (await caches.open(META_CACHE)).match(META_KEY); return r ? await r.json() : null; } catch (_) { return null; } };
const metaSet = async o => { try { await (await caches.open(META_CACHE)).put(META_KEY, new Response(JSON.stringify(o), { headers: { "Content-Type": "application/json" } })); } catch (_) {} };
self.addEventListener("push", e => {
  e.waitUntil((async () => {
    let pending = null, chat = 0, medical = 0, notCourier = false;  // pending null = unknown
    try {
      const sub = await self.registration.pushManager.getSubscription();
      if (sub) {
        const r = await fetch("/api/push/state", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: sub.endpoint }), cache: "no-store" });
        if (r.ok) { const j = await r.json(); pending = j.pending; chat = j.chat || 0; medical = j.medical || 0; if (typeof j.courier === "boolean") await metaSet({ courier: j.courier }); }
      }
    } catch (_) {}
    if (pending === null) { const m = await metaGet(); notCourier = !!m && m.courier === false; }
    const clear = async () => { for (const n of await self.registration.getNotifications({ tag: ALERT_TAG })) n.close(); };
    const cs = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const onScreen = path => cs.some(c => c.visibilityState === "visible" && new URL(c.url).pathname === path);
    const courierOnScreen = onScreen("/courier.html");
    if (courierOnScreen) { await clear(); if (medical === 0 && chat === 0) return; pending = 0; }  // suppress courier alert, but still show medical/chat updates
    const medicalNote = () => self.registration.showNotification("لاقينو — تحديث طبي", { body: medical > 1 ? "لديك " + medical + " تحديثات بخصوص طلباتك الطبية" : "لديك تحديث بخصوص طلبك الطبي", tag: MEDICAL_TAG, renotify: true, icon: ICON, badge: ICON, dir: "rtl", lang: "ar", data: { url: "/" } });
    const chatNote = n => self.registration.showNotification(n > 1 ? "لاقينو — رسائل جديدة" : "لاقينو — رسالة جديدة", { body: n > 1 ? n + " رسائل جديدة في سوق لاقينو" : "لديك رسالة جديدة في سوق لاقينو", tag: CHAT_TAG, renotify: true, icon: ICON, badge: ICON, dir: "rtl", lang: "ar", data: { url: "/market.html#/chats" } });
    if (pending === null && notCourier) { if (onScreen("/market.html")) return; return chatNote(chat); }  // offline + known non-courier: never show a courier alert
    if (pending === 0) {  // browsers require a visible notification per push
      if (medical > 0) { await clear(); return medicalNote(); }
      if (chat > 0) { await clear(); if (onScreen("/market.html")) return; return chatNote(chat); }
      await self.registration.showNotification("لاقينو", { body: "لا توجد طلبات متاحة الآن", tag: ALERT_TAG, silent: true, icon: ICON, dir: "rtl", lang: "ar" });
      await new Promise(r => setTimeout(r, 2500)); await clear(); return;
    }
    await self.registration.showNotification("لاقينو — طلب توصيل جديد", { body: pending > 1 ? pending + " طلبات توصيل تنتظر قبولك" : "افتح التطبيق لمشاهدة الطلب وقبوله", tag: ALERT_TAG, renotify: true, requireInteraction: true, icon: ICON, badge: ICON, dir: "rtl", lang: "ar", vibrate: [500, 200, 500, 200, 500, 200, 900], data: { url: "/courier.html" } });
    if (medical > 0) await medicalNote();  // do not hide a medical update behind a simultaneous courier alert
    return;
  })());
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/courier.html", path = new URL(url, location.origin).pathname;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(cs => {
    const c = cs.find(x => new URL(x.url).pathname === path);
    return c ? c.focus() : self.clients.openWindow(url);
  }));
});
