// Browserless service-worker test: medical notifications remain visible alongside courier alerts.
const fs = require('fs');
const vm = require('vm');
const handlers = {}; const shown = [];
global.self = {
  addEventListener: (name, fn) => { handlers[name] = fn; },
  registration: {
    pushManager: { getSubscription: async () => ({ endpoint: 'test-endpoint' }) },
    getNotifications: async () => [],
    showNotification: async (title, options) => { shown.push({ title, options }); return true; }
  },
  clients: { matchAll: async () => [] }
};
global.caches = { open: async () => ({ match: async () => null, put: async () => {} }), keys: async () => [], delete: async () => true };
global.fetch = async () => ({ ok: true, json: async () => ({ pending: 1, chat: 0, medical: 2, courier: true }) });
global.location = { origin: 'https://laqino.test' };
global.Response = class { constructor(body, options) { this.body = body; this.options = options; } };
vm.runInThisContext(fs.readFileSync('static/sw.js', 'utf8'));
async function push() { let p; handlers.push({ waitUntil: x => { p = x; } }); await p; }
(async () => {
  await push();
  if (!shown.some(n => n.title.includes('طلب توصيل جديد')) || !shown.some(n => n.title.includes('تحديث طبي'))) throw new Error('medical update was hidden by courier alert: ' + JSON.stringify(shown));
  shown.length = 0;
  self.clients.matchAll = async () => [{ url: 'https://laqino.test/courier.html', visibilityState: 'visible' }];
  await push();
  if (shown.some(n => n.title.includes('طلب توصيل جديد')) || !shown.some(n => n.title.includes('تحديث طبي'))) throw new Error('medical update was hidden while courier page was open: ' + JSON.stringify(shown));
  console.log('PASS medical push shown alongside courier alert');
  console.log('PASS medical push shown while courier page is foregrounded');
})().catch(e => { console.error(e); process.exit(1); });
