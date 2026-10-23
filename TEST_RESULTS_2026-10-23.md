# تقرير الاختبارات الشامل — 23 أكتوبر 2026

## الملخص

- عدد ملفات الاختبار التي شُغّلت: **130** (كل ملف في عملية منفصلة لعزل إعدادات وقواعد البيانات المؤقتة).
- **101 ملف نجح** بعد إعادة تشغيل الملفات التي تجاوزت مهلة التنفيذ، وتحديث 5 تأكيدات قديمة لا تتوافق مع السلوك الحالي المقصود.
- **26 اختبار واجهة محجوب بيئيًا**: Playwright لم يجد متصفحه المرفق؛ وبعد توجيه تجربة منفصلة إلى Chromium النظام، منع النظام التنقل إلى `localhost` برسالة `ERR_BLOCKED_BY_ADMINISTRATOR`. لا تُعد هذه نجاحات للواجهة ولا دليلًا على فشل التطبيق.
- **3 اختبارات تخطّت فحص المتصفح صراحةً** بسبب قيود المتصفح/البيئة.
- لا يوجد نشر على الإنتاج، وظل `rx_claim_mode=0` افتراضيًا.

## الاختبارات التي أعيد تشغيلها بعد تجاوز المهلة

- `test_courier_documents_ui.py` — **PASS** (18.8 ثانية): PASS success message shown; PASS admin page lists the documents with labels; PASS legacy request without documents is flagged; ALL PASSED
- `test_phase11_labs_ui.py` — **PASS** (22.6 ثانية): PASS global search returns the labs section; PASS 'show all' opens the labs sub-tab with the query; PASS admin labs tab renders form + list with publish state; ALL PASSED
- `test_phase11_search_ui.py` — **PASS** (31.3 ثانية): PASS 'show all' for dr opens its section without errors; PASS 'show all' for rx opens its section without errors; PASS doctors 'show all' pre-fills the box and runs the doctor search; ALL PASSED
- `test_phase11_services_ui.py` — **PASS** (27.9 ثانية): PASS 'show all' for services opens the services tab with the query; PASS doctor WhatsApp link (shown after the reveal) uses the 20 country code (wa.me/201099999999); PASS admin services tab renders types + providers with publish state; ALL PASSED
- `test_phase16_courier_accounts.py` — **PASS** (36.4 ثانية): PASS auto-refresh pauses while a form is open (HOLD) so typed data/files are not wiped; PASS admin asks for a reason on reject/suspend; PASS service worker version >=v22; ALL OK
- `test_phase9_close_orders_ui.py` — **PASS** (20.7 ثانية): PASS settings tab shows auto-confirm hours (default 24); PASS auto-confirm hours saved from UI; PASS courier page shows disputed order in history with its label, no action buttons; ALL PASSED
- `test_whatsapp_verify_ui.py` — **PASS** (21.3 ثانية): PASS reset with invalid phone shows an error, no WhatsApp step; PASS admin tab lists pending phones with a code box, never the code; PASS admin confirms with the code from the message; it leaves the pending list; ALL PASSED

## تأكيدات قديمة تم تحديثها ثم اجتازت الاختبار

- `test_phase10_ui.py` — نجح بعد تحديث التوقع: admin dispatch heading text now matches the current UI label.
- `test_phase22_location.py` — نجح بعد تحديث التوقع: location resolver response now explicitly includes state=unspecified.
- `test_phase3_rx.py` — نجح بعد تحديث التوقع: customer UI test now verifies comparison/close wiring and confirms no cheapest badge is displayed.
- `test_phase4_chat.py` — نجح بعد تحديث التوقع: push-state test now expects the medical unread count added in phase 15, including zero for unknown endpoints.
- `test_phase6.py` — نجح بعد تحديث التوقع: initial settings test now expects safe disabled RX routing defaults added in phase 1.

## اختبارات الواجهة التي تعذر إكمالها

تعذّر إكمال رحلة المتصفح في هذه الملفات بسبب قيود المتصفح/التنقل المحلي، وليس بسبب تأكيد وظيفي فاشل داخل الرحلة:

- `test_exchange_browser.py`
- `test_phase15_admin_nav.py`
- `test_phase20_ui_polish.py`
- `test_phase21_app_shell.py`
- `test_phase22_location_browser.py`
- `test_phase23_import_browser.py`
- `test_phase25_fare_browser.py`
- `test_phase26_live_tracker_browser.py`
- `test_phase27_customer_offer_browser.py`
- `test_phase30_featured.py`
- `test_phase32_souq_card_opens.py`
- `test_phase33_replies_sorted.py`
- `test_phase34_my_requests.py`
- `test_phase35_med_top.py`
- `test_phase36_notif_opens_request.py`
- `test_phase38_courier_profile.py`
- `test_phase8_native_browser.py`
- `test_phase8b_listing_social.py`
- `test_step1_chat_images_browser.py`
- `test_step2_service_requests_browser.py`
- `test_step3_quotes_browser.py`
- `test_step5_ratings_browser.py`
- `test_task2_role_cards.py`
- `test_task3_panels_browser.py`
- `test_task4_notif_bell.py`
- `test_task6_admin_notifs.py`

## اختبارات صرّحت بالتخطي

- `test_phase16_ui_browser.py` — SKIP browser tests (Chromium not installed: run `playwright install chromium`)
- `test_phase4_browser.py` — SKIP browser tests (Chromium not installed)
- `test_step4_rx_browser.py` — SKIP browser UI checks (container browser policy blocks localhost navigation)

## قائمة كل ملفات الاختبار ونتيجتها

| ملف الاختبار | النتيجة | ملاحظة |
|---|---|---|
| `test_backup_restore.py` | PASS | PASS missing archive file is a clear error; PASS server still opens the restored database; ALL PASSED |
| `test_courier_documents.py` | PASS | PASS resubmission replaced old documents (2, no selfie); PASS approved courier works end to end (wallet endpoint); ALL PASSED |
| `test_courier_documents_ui.py` | PASS | PASS success message shown; PASS admin page lists the documents with labels; PASS legacy request without documents is flagged; ALL PASSED |
| `test_deploy.py` | PASS | PASS WAL enabled; PASS expired sessions purged; ALL PASSED |
| `test_docker_modules.py` | PASS | PASS Dockerfile copies every local module the server needs (missing: none); PASS every sw.js SHELL path exists in static/ (bad: none); ALL PASSED |
| `test_exchange.py` | PASS | PASS XSS-looking title is stored as text (UI escapes with esc()); PASS init() is idempotent (second install keeps data); ALL PASSED |
| `test_exchange_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_notifications.py` | PASS | PASS prune keeps <= cap and drops >90d rows; SKIP rollback-with-old-server checks: old server copy not found (/mnt/data/laqino_phase17_work/server.orig.py). Put it there or set LAQINO_OLD_SERVER=/path/to/old/server.py; ALL RUNNABLE NOTIFICATION CHECKS PASSED (rollback section skipped) |
| `test_password_reset.py` | PASS | PASS UI chp(): change password through the real page script; PASS UI shows server error message for a bad code; ALL OK |
| `test_phase1.py` | PASS | PASS region persisted; PASS role cannot be self-assigned; ALL PASSED |
| `test_phase10_dispatch.py` | PASS | PASS admin settings validated and applied; PASS heartbeat endpoint keeps courier online; ALL OK |
| `test_phase10_doctors.py` | PASS | PASS search q injection-safe; PASS admin actions audited; ALL OK |
| `test_phase10_push.py` | PASS | PASS courier ordering for himself is not woken for own order; PASS unsubscribe removes only own subscription; ALL OK |
| `test_phase10_ui.py` | PASS | passed after updating stale assertion: admin dispatch heading text now matches the current UI label |
| `test_phase11_categories.py` | PASS | PASS market chips: only the non-empty category + 'الكل'; PASS publish form still offers every active category (can post into an empty one), never the inactive one; ALL PASSED |
| `test_phase11_labs.py` | PASS | PASS admin list shows state; changes audited; PASS survives restart (data in SQLite); ALL PASSED |
| `test_phase11_labs_ui.py` | PASS | PASS global search returns the labs section; PASS 'show all' opens the labs sub-tab with the query; PASS admin labs tab renders form + list with publish state; ALL PASSED |
| `test_phase11_nav_ui.py` | PASS | PASS services hub holds delivery + local services, no script errors; PASS delivery view keeps the Services tab highlighted; ALL PASSED |
| `test_phase11_rx_no_pharmacy_notification.py` | PASS | PASS customer is notified when initial routing has no eligible pharmacy; PASS repeated routing does not duplicate the notification |
| `test_phase11_search_ui.py` | PASS | PASS 'show all' for dr opens its section without errors; PASS 'show all' for rx opens its section without errors; PASS doctors 'show all' pre-fills the box and runs the doctor search; ALL PASSED |
| `test_phase11_security.py` | PASS | PASS balance credited once (100); PASS approve vs reject race: one winner, balance consistent; ALL PASSED |
| `test_phase11_services.py` | PASS | PASS changes are audited; PASS survives restart (data in SQLite); ALL PASSED |
| `test_phase11_services_ui.py` | PASS | PASS 'show all' for services opens the services tab with the query; PASS doctor WhatsApp link (shown after the reveal) uses the 20 country code (wa.me/201099999999); PASS admin services tab renders types + providers with publish state; ALL PASSED |
| `test_phase12_home_ui.py` | PASS | PASS products remain accessible from the medical tabs (only when the admin flag is on); PASS no standalone products homepage card or config key; ALL PASSED |
| `test_phase12_rx_full_quote_closes_claim.py` | PASS | PASS full quote approval ends the active claimant route immediately; PASS unrelated access is revoked while active delivery access is preserved |
| `test_phase13_rx_worker_lease.py` | PASS | PASS shared-database worker lease prevents overlapping sweep ownership; PASS lease can be renewed and acquired after expiry |
| `test_phase13_window_ids.py` | PASS | PASS window.ms is initialised before its first read; PASS window.rc is initialised before its first read; PASS window.sq is initialised before its first read |
| `test_phase14_hardening.py` | PASS | PASS a strong password creates the admin; PASS existing admin is not re-checked (upgrades keep working); PASS install.sh generates a 24-char hex password (passes the check) |
| `test_phase14_rx_deadline_notifications.py` | PASS | PASS total-deadline processing notifies customer once; PASS expired claim with no eligible alternative notifies customer once |
| `test_phase15_admin_nav.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase15_rx_medical_push.py` | PASS | PASS push state returns unread medical count only; PASS FCM medical payload is generic and contains no prescription details; PASS RX notification hook is called with minimal identifiers |
| `test_phase16_admin_courier_wallet.py` | PASS | PASS admin page has wallet button and handler, uses esc(); PASS service worker version bumped to >=v19; ALL OK |
| `test_phase16_compat.py` | PASS | PASS mobile tab-wrap fix kept (nav flex-wrap:wrap, buttons shrink-wrap); PASS service worker cache version is current (laqino-vNN, >= v19); SKIP browser tests (Chromium not installed: run `playwright install chromium`) |
| `test_phase16_courier_accounts.py` | PASS | PASS auto-refresh pauses while a form is open (HOLD) so typed data/files are not wiped; PASS admin asks for a reason on reject/suspend; PASS service worker version >=v22; ALL OK |
| `test_phase16_images.py` | PASS | PASS customers are still capped at 20 files; PASS real JPEG accepted; PASS JPEG served as image/jpeg |
| `test_phase16_migration.py` | PASS | PASS old published doctor and lab unchanged in public lists; PASS old prescription image cannot be hijacked as a doctor photo (409); PASS old non-photo files are not deleted by photo replacement |
| `test_phase16_topup_safeguards.py` | PASS | PASS admin topups tab has settings form; PASS service worker version >=v20; ALL OK |
| `test_phase16_ui_browser.py` | SKIP | SKIP browser tests (Chromium not installed: run `playwright install chromium`) |
| `test_phase16_wallet_adjust.py` | PASS | PASS courier UI shows adjustment with escaped reason; PASS service worker version >=v21; ALL OK |
| `test_phase17_admin_claim_toggle.py` | PASS | PASS claim mode remains disabled by default and can be explicitly enabled by admin; PASS invalid claim mode rejected and changes audited; PASS admin UI exposes an explicit confirmation before enabling |
| `test_phase17_responsive_ui.py` | PASS | PASS static/admin.html loads the shared theme; PASS static/courier.html loads the shared theme; ALL PASSED |
| `test_phase18_home_sections.py` | PASS | PASS public config is sorted by configured order; PASS duplicate order is rejected without changing settings; ALL PASSED |
| `test_phase1_search.py` | PASS | PASS UI: /search failing shows one error section; other sections still render; PASS sw.js cache version >=v28 and caches market.html; ALL PASSED |
| `test_phase2.py` | PASS | PASS hidden category and fields gone; PASS admin still sees hidden; ALL PASSED |
| `test_phase20_ui_polish.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase21_app_shell.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase22_delivery_cycle.py` | PASS | PASS the online markaz courier sees the village order; PASS and can accept it; ALL PASSED |
| `test_phase22_expiry_categories.py` | PASS | PASS auto-seed is idempotent; PASS admin-deleted category is not recreated; ALL PASSED |
| `test_phase22_location.py` | PASS | passed after updating stale assertion: location resolver response now explicitly includes state=unspecified |
| `test_phase22_location_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase23_import.py` | PASS | PASS manual add + publish still works exactly as before; PASS manual lab add still works; ALL PASS |
| `test_phase23_import_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase25_fare.py` | PASS | PASS re-init keeps admin edits and adds no duplicates; PASS legacy assigned order (fare_status default) still advances; ALL PASS |
| `test_phase25_fare_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase26_live_tracker_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase27_customer_offer.py` | PASS | PASS commission stays 5 after direct accept; PASS insufficient wallet cannot accept offered order (402); ALL PASS |
| `test_phase27_customer_offer_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase28_commission_and_delivery.py` | PASS | PASS in-progress order: balance same, held 4, available = balance-4; PASS admin courier wallet agrees; ALL PASS |
| `test_phase2_products.py` | PASS | PASS flag off: pharmacy still manages its offers; PASS flag on again: data intact; ALL PASSED |
| `test_phase3.py` | PASS | PASS my listings isolated; PASS owner deletes; ALL PASSED |
| `test_phase30_featured.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase30_fts_search.py` | PASS | PASS index is rebuilt automatically if it drifted; PASS same count both ways (1); ALL PASSED |
| `test_phase30_login_lockout.py` | PASS | PASS a different IP is unaffected by that spray; PASS idle connection is closed by the server within the timeout (2.0s); ALL PASSED |
| `test_phase30_push_resume.py` | PASS | PASS one sweep push (no native FCM) goes to subscribed users; PASS no subscribers -> no sweep, order still re-armed; ALL PASSED |
| `test_phase31_hardening.py` | PASS | PASS valid login still works; PASS empty body still handled; ALL PASSED |
| `test_phase32_delete_account.py` | PASS | PASS courier deletion succeeds; PASS courier docs + files purged, courier suspended; ALL OK |
| `test_phase32_souq_card_opens.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase33_contact.py` | PASS | PASS footer link on /privacy; PASS footer link on /terms; PASS footer link on /delete-account |
| `test_phase33_replies_sorted.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase34_my_requests.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase34_permissions.py` | PASS | PASS index.html loads perm.js before native.js; PASS courier.html loads perm.js before native.js; PASS sw.js caches perm.js |
| `test_phase35_capacitor8.py` | PASS | PASS market header respects safe-area-inset-top; PASS README_ANDROID mentions API 36 + Node 22 + JDK 21; PASS no CHANGE-ME left in android/ |
| `test_phase35_med_top.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase36_aab_prep.py` | PASS | PASS لا مفاتيح فعلية داخل android/; PASS README_ANDROID يشرح خطوات 7 و8; ALL 21 PASS |
| `test_phase36_notif_opens_request.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase38_courier_profile.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase39_delete_with_avatar.py` | PASS | PASS file record gone; PASS file removed from disk; PASS courier suspended and unavailable |
| `test_phase3_rx.py` | PASS | passed after updating stale assertion: customer UI test now verifies comparison/close wiring and confirms no cheapest badge is displayed |
| `test_phase4.py` | PASS | PASS customer cancels assigned order; PASS cancelled not re-offered; ALL PASSED |
| `test_phase4_browser.py` | SKIP | SKIP browser tests (Chromium not installed) |
| `test_phase4_chat.py` | PASS | passed after updating stale assertion: push-state test now expects the medical unread count added in phase 15, including zero for unknown endpoints |
| `test_phase4_chat_ui.py` | PASS | PASS blocked thread shows stopped notice to the other side; PASS anonymous opening chat route asks to log in; ALL PASSED |
| `test_phase4_sw_push.py` | PASS | PASS no subscription behaves as before (fail-open order alert); old server without chat field behaves as idle; PASS notification click opens the url carried by the notification (default courier page); ALL PASSED |
| `test_phase5.py` | PASS | PASS accepts o2 once balance suffices; PASS cancel after assign charges no commission; ALL PASSED |
| `test_phase5_services.py` | PASS | PASS notification link 'svc' is routed; PASS svc.py copied by Dockerfile and service worker bumped; ALL PASSED |
| `test_phase6.py` | PASS | passed after updating stale assertion: initial settings test now expects safe disabled RX routing defaults added in phase 1 |
| `test_phase6_provider_accounts.py` | PASS | PASS UI: admin owner-link control wired; PASS UI: notification link svcjob + cache >= v37; ALL PASS |
| `test_phase6_rx_claim_worker.py` | PASS | PASS periodic worker ticks and closes per-tick DB connections |
| `test_phase6b_ratings.py` | PASS | PASS UI: rate control + escaped stars in index; PASS UI: provider panel and admin show rating; ALL PASS |
| `test_phase7.py` | PASS | PASS audit records admin actions; PASS reports computed from real data; ALL PASSED |
| `test_phase7_overview.py` | PASS | PASS Dockerfile copies overview.py; cache >= v39; SKIP browser tests (Chromium not installed); ALL PASS |
| `test_phase7_rx_notifications.py` | PASS | PASS terminal notification is customer-scoped and idempotent |
| `test_phase8.py` | PASS | PASS order list says not rated yet; PASS order list says rated after rating; ALL PASSED |
| `test_phase8_fcm.py` | PASS | PASS android skeleton: appId, https server.url, cleartext off; PASS no secrets shipped (google-services.json / service account); ALL PASSED |
| `test_phase8_native_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase8_rx_claim_concurrency.py` | PASS | PASS concurrent claims serialize to one active pharmacy; PASS expired claim transfers image access to the next pharmacy only |
| `test_phase8b_listing_social.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_phase9.py` | PASS | PASS other user cannot delete file; PASS owner deletes image; request closed, pharmacy loses access; ALL PASSED |
| `test_phase9_admin_cats.py` | PASS | PASS settings tab shows the stock-freshness card with default 24; PASS saved from the UI and reflected; ALL PASSED |
| `test_phase9_close_orders.py` | PASS | PASS no duplicate commission rows anywhere; PASS courier stats count auto/admin completed orders; ALL PASSED |
| `test_phase9_close_orders_ui.py` | PASS | PASS settings tab shows auto-confirm hours (default 24); PASS auto-confirm hours saved from UI; PASS courier page shows disputed order in history with its label, no action buttons; ALL PASSED |
| `test_phase9_contact.py` | PASS | PASS courier page: active order shows customer name + phone link; PASS courier page: ended orders (disputed/completed/cancelled) show no customer phone; ALL PASSED |
| `test_phase9_courier_ui.py` | PASS | PASS release via UI returns order to searching; PASS single commission entry overall; ALL PASSED |
| `test_phase9_fixes.py` | PASS | PASS success resets counter for others; PASS after window/reset, correct login works; ALL PASSED |
| `test_phase9_limits.py` | PASS | PASS deleting a prescription image frees a slot; PASS 429 carries an Arabic error message; ALL PASSED |
| `test_phase9_location_resolution.py` | PASS | PASS GPS clear/ambiguous/unspecified states; PASS index startup does not call undefined suggestRegionFromGPS |
| `test_phase9_medical_delivery.py` | PASS | PASS UI creates the order; tab then shows it instead of the button; PASS pharmacy page lists delivery refs with medicine, no customer identity; ALL PASSED |
| `test_phase9_region_fixes.py` | PASS | PASS 30h-old stock is fresh under a 48h window; PASS 30h-old stock is stale under a 24h window; ALL PASSED |
| `test_phase9_release_smoke.py` | PASS | PASS data survives restart (same users can log in); PASS weak admin password refuses to start on a fresh database (exit != 0); ALL PASSED |
| `test_phase9_step4_ui.py` | PASS | PASS medical tab links to the pharmacy page; PASS pharmacy page is served; ALL PASSED |
| `test_register_limit.py` | PASS | PASS rows older than 24h are pruned; PASS throttle_clear empties table; ALL PASSED |
| `test_setup_initial.py` | PASS | PASS --overwrite updates; PASS no users created; ALL PASSED |
| `test_step1_chat_images.py` | PASS | PASS sw never caches /api/ responses (chat images stay private); PASS Dockerfile still copies chat.py; ALL PASSED |
| `test_step1_chat_images_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_step2_service_requests.py` | PASS | PASS indexes were recreated; PASS API works on the migrated table; ALL OK |
| `test_step2_service_requests_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_step3_quotes.py` | PASS | PASS step-2 database gains dispute columns without losing rows; PASS step-2 database gains quote tables; ALL OK |
| `test_step3_quotes_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_step4_rx.py` | PASS | PASS old DB: legacy response grandfathered as approved (migration idempotent); PASS old DB: new response becomes pending; ALL OK |
| `test_step4_rx_browser.py` | SKIP | SKIP browser UI checks (container browser policy blocks localhost navigation) |
| `test_step5_ratings.py` | PASS | PASS UI: admin has rating reports section; PASS UI: cache bumped to >= v45; ALL PASS |
| `test_step5_ratings_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_step7_notifs.py` | PASS | PASS API dispute notified admin and the order's pharmacy; PASS inquiry still created when notifications table is gone; ALL PASS |
| `test_task2_role_cards.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_task3_panels_browser.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_task4_notif_bell.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_task6_admin_notifs.py` | BLOCKED (browser environment) | Playwright browser binary was missing; system Chromium launches but navigation to localhost is blocked by environment policy (ERR_BLOCKED_BY_ADMINISTRATOR). |
| `test_whatsapp_verify.py` | PASS | PASS manual confirmation audited; PASS then the customer registers; ALL PASSED |
| `test_whatsapp_verify_ui.py` | PASS | PASS reset with invalid phone shows an error, no WhatsApp step; PASS admin tab lists pending phones with a code box, never the code; PASS admin confirms with the code from the message; it leaves the pending list; ALL PASSED |
| `testutil.py` | PASS | no output |

## فحوصات إضافية

- `python -m py_compile *.py` — نجح قبل بدء جولة الاختبارات وبعد تحديثات الاختبارات.
- `node test_phase16_sw_medical_push.js` — نجح (حالتا التنبيه الطبي مع تنبيه التوصيل).
- الاختبارات الطبية الأساسية للحجز، انتهاء المهلة، إعادة التوزيع، صلاحيات الصور، الإشعارات، وتفعيل المسار: اجتازت الاختبارات المخصصة لها.

## الخطوة التالية

لتأكيد اختبارات الواجهة، يلزم تشغيل المجموعة في بيئة تسمح بفتح Chromium والتنقل إلى خادم الاختبار المحلي. لا تفعّل المسار الجديد على الإنتاج قبل هذا التحقق.
