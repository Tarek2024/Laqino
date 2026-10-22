// شرح الأذونات (المرحلة 34): يشغّل perm.js على DOM مبسّط. التشغيل: node test_phase34_permissions.js
const fs = require('fs'), vm = require('vm');
const store = {}; let appended = null, keyh = null; const btn = {};
const el = { style: {}, setAttribute() {}, querySelector: id => btn[id], set innerHTML(v) {}, parentNode: null };
const doc = { activeElement: null, body: { appendChild(o) { appended = o; o.parentNode = { removeChild() { appended = null; } }; } }, documentElement: {},
  createElement() { return el; }, addEventListener(t, f) { keyh = f; }, removeEventListener() { keyh = null; } };
btn['#laq-perm-y'] = { focus() {} }; btn['#laq-perm-n'] = { focus() {} };
const ctx = { window: {}, document: doc, localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } }, Date, Promise, String };
ctx.window = ctx; vm.createContext(ctx); vm.runInContext(fs.readFileSync('static/perm.js', 'utf8'), ctx);
let n = 0; const ok = (name, c) => { console.log((c ? 'PASS ' : 'FAIL ') + name); if (!c) process.exit(1); n++; };
(async () => {
  ok('LaqPerm exposed', !!ctx.LaqPerm);
  ok('unknown kind passes through', await ctx.LaqPerm.explain('x') === true);
  let p = ctx.LaqPerm.explain('notif'); await Promise.resolve();
  ok('dialog shown', !!appended); btn['#laq-perm-n'].onclick();
  ok('"not now" resolves false', await p === false);
  ok('"not now" stored', !!store['laq_perm_later_notif'] && !store['laq_perm_ok_notif']);
  ok('postponed: no dialog, false', await ctx.LaqPerm.explain('notif') === false && !appended);
  store['laq_perm_later_notif'] = String(Date.now() - 4 * 24 * 3600 * 1000);
  p = ctx.LaqPerm.explain('notif'); await Promise.resolve(); ok('re-asks after 3 days', !!appended);
  btn['#laq-perm-y'].onclick(); ok('accept resolves true', await p === true);
  ok('accepted stored, never shown again', store['laq_perm_ok_notif'] === '1' && await ctx.LaqPerm.explain('notif') === true && !appended);
  p = ctx.LaqPerm.explain('location'); await Promise.resolve(); keyh({ key: 'Escape', preventDefault() {} });
  ok('Escape = not now', await p === false);
  console.log('ALL OK (' + n + ')');
})();
