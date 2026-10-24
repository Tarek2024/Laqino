# لاقينو — ملف حالة المشروع (PROJECT_STATE.md)

> **الحالة الحالية: الإصدار `phase-50` — كاش الخدمة `laqino-v85`** (المرجع الوحيد: ملف `VERSION`).

> **الحالة الحالية: الإصدار `phase-50` — كاش الخدمة `laqino-v85`** (المرجع الوحيد: ملف `VERSION`). أي رقم إصدار أو كاش أقدم في هذا الملف سجل تاريخي لمراحل سابقة. عدد تبويبات الإدارة الآن 23. مجلد المشروع: `laqino-15`.

> **لمن يقرأ هذا الملف (كلود في حساب جديد):** هذا الملف هو ذاكرتك. اقرأه كاملًا قبل أي تعديل، ثم نفّذ المهمة التالية في قسم «المهام». **بعد كل تعديل حدّث هذا الملف** (قسم «سجل التعديلات» + «المهام» + أي قرار أو فخ جديد) وأرفقه في كل ZIP. لا تفترض شيئًا غير مكتوب هنا: افحص الكود نفسه.

آخر تحديث: **phase-50 — إصلاح عدّاد رفع الملفات العام (أكتوبر 2026)** — دُمج التحديث (المهام 1–6) دمجًا ثلاثيًا فوق الكود الحالي (سوق/صور/تصنيفات الأدمن/تنبيهات المندوب)، وكاش sw.js = `laqino-v27`. السابق: بعد المهمة 6 (إشعارات الإدارة) فوق المهمة 5 (ZIP نهائي مجمّع = 1+2+3+4 + إصلاحات). نسخة الكاش الحالية في sw.js: `laqino-v26` (SHELL يضم `/panel.css` و`/notif.js`).

## 1. ما هو المشروع
تطبيق ويب عربي (RTL) اسمه «لاقينو» لمنطقة محلية في مصر: سوق إعلانات، خدمات طبية (استفسار دواء، روشتات، صيدليات، أطباء، معامل)، خدمات محلية، وتوصيل بمندوبين. يعمل كـ PWA على الهاتف، ويُشغَّل على **Termux** (أندرويد) بالسيرفر نفسه. المالك يطبّق التحديثات يدويًا بفك ZIP فوق مجلد المشروع.

## 2. البنية (تحقق منها بنفسك)
- **`server.py`** (~155KB، ملف واحد): سيرفر بايثون بمكتبة قياسية فقط (`http.server.ThreadingHTTPServer`) + **SQLite**. المسارات داخل `route()` كسلسلة `if method == ... and path == ...`. المعالج الكلاس `H`، الخطأ المخصص `E(status,msg)`، المساعدات: `self.user(c)`، `self.need(u, roles...)`, `self.body()`, `self.send(code, obj)`. `init(admin_phone, admin_pw)` ينشئ المخطط ويرحّل تلقائيًا (CREATE IF NOT EXISTS + ALTER).
- **`notif.py`** (جديد في ZIP 1): الإشعارات. لا يستورد server.py. يُربط بـ 3 أسطر في server.py (`import notif` / `notif.install(c)` داخل `init()` / `if notif.handle(self, c, u, method, path, q): return` بعد `u = self.user(c)`).
- **`static/`**: `index.html` (تطبيق العميل، صفحة واحدة بـ JS مضغوط وتبويبات: 0 رئيسية، 1 سوق، 2 توصيل، 3 حسابي، 4 طبي، 6 خدمات)، `courier.html` (لوحة المندوب)، `pharmacy.html` (لوحة الصيدلية)، `admin.html` (الإدارة، 17 قسمًا)، `app.css` (تصميم تطبيق العميل، متغيرات `--navy:#0f2a5c --orange:#f28c1b ...`، يُكتب بـ `body.app .x`)، `theme.css` (طبقة مشتركة تحوي قواعد `!important` على `main`/`.card`/`header`: `main{max-width:640px!important}` و`main#m{max-width:760px!important}` على ≥1100px)، `panel.css` (تصميم اللوحتين، جديد)، `sw.js` (service worker: شبكة أولًا، لا يخزّن `/api/`، ويحوي Web Push للمندوب)، `offline.html`, `manifest.webmanifest`, `assets/`.
- **الأدوار:** عميل، مندوب (`couriers`، حالات pending/approved/rejected/suspended + `review_reason`)، صيدلية (`providers`، نفس الحالات بلا سبب رفض)، إدارة/موظف. الصيدلية **لا تعيد التقديم بعد الرفض** (409)، المندوب يعيد.
- **جداول أساسية:** users, sessions, regions, delivery_orders, order_offers, order_events, couriers, courier_documents, providers, medicine_inquiries, inquiry_responses, prescriptions, prescription_responses, prescription_access, topup_requests (محفظة المندوب), listings, **notifications** (جديد).
- **أدوات:** `backup_restore.py` (`backup --out DIR --keep N` / `restore --file X.tgz --force`)، `DEPLOY.md`، `STATUS.md`، `testutil.py` (مساعد `apply_docs(call, token)` لتقديم مندوب بوثائق)، `imgutil.py`.
- **لا تُسلَّم أبدًا داخل ZIP:** `laqino.db`، `uploads/`، أي أسرار/مفاتيح، ولا `server.py.bak` أو `.merge-check` أو `check_update` (مجلدات قديمة في الأرشيف الكامل). اسم مجلد المشروع `laqino-phase14` لكن الكود في المرحلة 16+.

## 3. الإشعارات (ZIP 1)
Triggers داخل SQLite تولّد الإشعارات من أي مسار (`ntf_*`). تُعاد كتابتها عند كل تشغيل. `INSERT OR IGNORE` فلا يفشل الإشعار العملية الأصلية. المسارات: `GET /api/notifications?after=&limit=`، `GET /api/notifications/count` (خفيف للاستعلام الدوري)، `POST /api/notifications/read` (`{ids:[..]}` أو `{all:true}`)، `GET /api/my/applications` → `{courier:{status,region_id,reason,created_at,needs_documents}|null, pharmacy:{status,name_ar,region_id,address,created_at}|null}`. الحدود: 200/مستخدم و90 يومًا. حقل `link` قيمه: orders, courier, pharmacy, medical, souq (للجرس لاحقًا). **فخ:** لا تحذف جدول `notifications` يدويًا وتترك الـtriggers (تفشل الكتابات)؛ الإزالة: `python3 notif.py --uninstall laqino.db`. إشعار الصيدلية عند استفسار جديد صار من الكود لا من trigger (`notif.inquiry_created` من server.py؛ المناطق المتداخلة تحتاج CTE) — الخطوة 7.

## 4. الواجهة بعد المهمة 2
في `index.html`: متغير `AP` (من `/api/my/applications`)، دوال `pnlCard/pnls/canApplyCourier/canApplyPharmacy`، كروت `.pnl[data-panel]` في الرئيسية و«حسابي»، ويُحدَّث `AP` عند فتح التبويب 0 أو 3. CSS الكروت في آخر `app.css`.

## 4ب. اللوحتان بعد المهمة 3
- `panel.css` يُحمَّل بعد `theme.css` في `pharmacy.html` و`courier.html` (`<body class="panel pharm|courier">`). نفس هوية التطبيق (ألوان/خطوط/بطاقات 20px/حقول 48px بخط 16px/أزرار 46px). **لا تغيير في JS الوظيفي**: سكربت `courier.html` مطابق بايتًا لما قبل؛ في `pharmacy.html` تغيّر نصّا عنوانين فقط (بطاقة عنوان ← `<h2 class="sec">`).
- الهيدر `header.ph`: رابط «رجوع للتطبيق» (`/`)، شعار + عنوان، ومكان محجوز فارغ **`#ph-end`** لجرس الإشعارات (المهمة 4: ضع الجرس فيه).
- التخطيط: عمود واحد على الهاتف (≤560px)، وعلى ≥900px عمودان بـ CSS columns (`main#m`، أقصى 1080px)؛ بطاقة الحالة في أول لوحة المندوب وعناوين الأقسام في الصيدلية `column-span:all`؛ صفحات البطاقة الوحيدة (دخول/تقديم) عمود واحد 520px عبر `:has()`. **فخ:** لأن theme.css يستخدم `!important` على `main#m` يجب أن تبقى قواعد `main` في panel.css بصيغة `body.panel main#m{...!important}`.
- شاشة اللوحة تُعاد رسمها كل 5 ثوانٍ (`load()` في courier.html)؛ أي عنصر تضيفه داخل `#m` سيُمسح، فضع الجرس في الهيدر لا في `main`.

## 4ج. جرس الإشعارات بعد المهمة 4
- `static/notif.js` ملف واحد مستقل (يحقن CSS بنفسه). يقرأ التوكن من `localStorage['t']`، يركّب الجرس في `#ph-end` (اللوحتان) وإلا **زرًا عائمًا** أعلى يسار الشاشة (التطبيق). استعلام `/api/notifications/count` كل 30ث (والأمامية فقط) وعند العودة للتبويب؛ أول استعلام لا ينبّه. عند ارتفاع العدد: `?after=<آخر id>` ثم تنبيه (toast + اهتزاز) ويظهر العدد في عنوان الصفحة `(n)`. النقر على إشعار: يعلّم مقروءًا ثم ينتقل حسب `link` (orders/medical/souq → `/`، courier → `/courier.html`، pharmacy → `/pharmacy.html`). `window.laqNotifRefresh()` لإعادة التشغيل بعد دخول/خروج.
- **شكل الاستجابة (تحقّقت منه من notif.py الحقيقي):** count → `{unread,latest_id}`؛ القائمة → `{items:[{id,kind,title,body,link,ref_type,ref_id,created_at(ثوانٍ epoch),read_at}],unread,latest_id}`. الجرس يقرأ هذه الحقول (ويتسامح مع أسماء بديلة). الاختبار نفسه ما زال على API وهمي بنفس الشكل، لا على server.py.
- `index.html`: الجرس يُركَّب في `header.bar` (بعد زر المنطقة) والسكربت مضاف قبل `</body>`. بدون `#ph-end` ولا `header.bar` يعود زرًا عائمًا. أزرار `body.panel button` في panel.css تفرض ألوانها، لذا قواعد القائمة في notif.js بـ`!important` عمدًا.
- **فخ:** `hidden` لا يعمل على عنصر له `display` في CSS؛ لذلك `.lqn[hidden]{display:none!important}`.

## 5. قواعد العمل الثابتة (من المالك)
1. كل ZIP = ملفات التحديث فقط، لا نسخة كاملة، لا قواعد بيانات ولا أسرار.
2. الملف المشترك (مثل `sw.js` و`server.py`) يُسلَّم **بنسخته الكاملة المحدّثة**؛ الأحدث يحل محل الأقدم بلا دمج. عند أي تعديل على الواجهة: ارفع رقم الكاش في `sw.js` (`laqino-vNN`).
3. README قصير في كل ZIP: الملفات، أمر النسخة الاحتياطية، خطوات التطبيق، التراجع، **ما اتجرّب فعلًا وما لم يُجرَّب** (بصدق).
4. الردود بالعربية المصرية، قصيرة، تبدأ بالنتيجة. المالك على الهاتف.
5. لا تدّعِ نجاح شيء لم تشغّله.

## 6. كيف تختبر
- الاختبارات `test_*.py` ملفات مستقلة، كلٌّ يشغّل سيرفرًا على **قاعدة مؤقتة** (`LAQINO_DB` و`LAQINO_UPLOADS` من بيئة مؤقتة + فحص عزل `ISOLATION BROKEN`) ويطبع `PASS/FAIL`. شغّلها واحدًا واحدًا (`for t in test_*.py`) داخل نسخة من المشروع، لا على القاعدة الحقيقية.
- اختبارات المتصفح: Playwright + Chromium (متاحان في بيئة كلود)، حجم هاتف 390×844، `service_workers="block"`، وتجاهل أخطاء الخطوط الخارجية (`ERR_NAME_NOT_RESOLVED`) لأن البيئة بلا إنترنت. `LAQINO_SHOTS=dir` يحفظ اللقطات.
- مجموع الفحوص عند آخر تشغيل: 1031 ناجحًا في 50 ملفًا (48 ملفًا كاملًا).
- نصائح بيئة: الـshell هو `sh` (لا brace expansion)، ولا تضع backticks في heredoc غير محمي بعلامات اقتباس، وشغّل المهام الطويلة بـ `setsid nohup`.

## 7. اختبارات فاشلة مسبقًا (قبل أي تعديل منّا) — تُعالج في المهمة 5
- `test_phase16_compat.py`: بند «service worker bumped to laqino-v19» (يتوقع v19؛ الحالي v23). المعالجة: تحديث التوقع لقراءة الإصدار الحالي.
- `test_phase9_courier_ui.py`: بند «no token shows login prompt» — **السبب محقَّق:** الاختبار قديم؛ يتوقع نص «سجّل الدخول» بينما `authView()` تعرض «تسجيل دخول المندوب». المعالجة في المهمة 5: غيّر التوقع إلى «تسجيل دخول المندوب». ملاحظة: دالة `ok` فيه تخرج عند أول فشل، فبقية بنوده (21 بندًا) لا تُنفَّذ أصلًا حتى يُصلَح؛ جُرّبت بنسخة مؤقتة مصحَّحة فنجحت كلها على اللوحة قبل المهمة 3 وبعدها.

## 8. المهام (بالترتيب)
| # | المهمة | الحالة |
|---|---|---|
| 1 | الإشعارات: notif.py + 3 أسطر في server.py + `test_notifications.py` | ✅ منتهية (ZIP 1، 56 فحصًا) |
| 2 | كروت اللوحات حسب الدور + إخفاء التقديم (index.html, app.css, sw.js) | ✅ منتهية (ZIP 2، اختبار متصفح) |
| 3 | إعادة تصميم `pharmacy.html` و`courier.html` (panel.css + sw.js) | ✅ منتهية (ZIP 3، اختبار متصفح هاتف وكمبيوتر) |
| 4 | جرس الإشعارات `notif.js` في التطبيق واللوحتين | ✅ منتهية (في الـZIP النهائي؛ اختبار الجرس على API وهمي بشكل notif.py الحقيقي لا على server.py) |
| 5 | الإقفال (✅ منتهية): تشغيل كل الاختبارات مع الجديدة، إصلاح التعارض (بما فيها القسم 7)، ZIP نهائي واحد مجمّع + `README_UPDATE.md` (الدمج على Termux، النسخ الاحتياطي، التراجع، نتائج فعلية). | ⏳ |

## 9. سجل التعديلات
- **phase-23 (استيراد Excel):** `bulk_import.py` وحدة مستقلة (بلا مكتبات؛ zipfile+xml) تُربط بسطرين في `server.py` (`import` + `bulk_import.handle` بعد `lsocial.handle` + حقن `norm_ar/audit` بعد تعريف `norm_ar`). مسارات `/api/admin/import/{template,preview,commit}` (admin فقط). بطاقة في `admin.html` تُلحَق أسفل تبويبي doctors وlabs عبر تغليف `V.doctors`/`V.labs` (لا تغيير في دواليهما). الجديد غير منشور افتراضيًا، المكرر يُتخطّى، التحديث يملأ غير الفارغ فقط، التنفيذ معاملة واحدة. **فخ:** Excel يحذف الصفر الأول من الأرقام (يُصلَح في `_phone`) ولا يكتب الصفوف الفارغة (نحترم `r` لرقم الصف الحقيقي). **لم يُنفَّذ بعد:** زر «حجز»/شات مباشر مع الطبيب أو المعمل (يحتاج ربط حساب مستخدم بالطبيب/المعمل مثل `service_providers.owner_user_id` وجدول محادثات جديد لأن `chat_threads` مرتبط بـ`listings`).
- **phase-22 (أكتوبر 2026) — الموقع الموحد:** `static/location.js` (جديد، يتحمل في index.html بعد native.js وقبل shell.js)، أعمدة `regions.lat/lng` و`delivery_orders.dropoff_lat/lng`، `POST /api/location/resolve`، `POST /api/admin/regions/<id>/coords`. **قرارات/فخاخ:** (1) لا watchPosition أبدًا؛ (2) الموقع يحدد المنطقة تلقائيًا فقط إن لم يكن للمستخدم منطقة، وإلا اقتراح؛ (3) المحافظات لا تُختار تلقائيًا (R دائمًا مركز/قرية)؛ (4) إحداثيات المناطق فارغة حتى تضيفها الإدارة — لم تُخترع؛ (5) الخادم يفرض CSP بلا unsafe-eval فاختبارات المتصفح تستعمل polling عبر evaluate لا wait_for_function؛ (6) docs/phases يجب أن يبقى متصلًا 1..9 (release_check) فوثيقة المرحلة في docs/steps. اختبارات: `test_phase22_location.py` و`test_phase22_location_browser.py`. فشلان قديمان معروفان: `test_phase16_compat` (22 قسمًا) و`test_phase2_products` (بند واجهة).
- **خارطة الخطوات (أكتوبر 2026):** أُضيف `docs/ROADMAP.md` (المنتهي: الخطوتان 1–2؛ الباقي: 3–9 من قائمة المالك) بلا تغيير كود. **قاعدة:** كل تسليم = مشروع كامل + تحديث ROADMAP.md.
- **م9 (أكتوبر 2026):** بلا تغيير كود تشغيلي: `release_check.py` + `test_phase9_release_smoke.py` + `VERSION` + README/DEPLOY/env.example. نتيجة: 72 ملف اختبار. التفاصيل `docs/phases/phase-09-README.md`.
- **م8 دفعة 1 (أكتوبر 2026):** `fcm.py` + `static/native.js` + `android/` + ربط 6 أسطر في server.py؛ كاش v40؛ `_push_to_users(..., native=True, kind=...)`؛ المندوب مؤهَّل للإيقاظ بـWeb Push أو FCM. لم يُبنَ APK. التفاصيل `docs/phases/phase-08-README.md`.
- **ZIP 1 (الإشعارات):** +`notif.py`، `server.py` (3 أسطر)، +`test_notifications.py`. جدول ومسارات وtriggers. اختُبر ترحيل قاعدة قديمة والتراجع للسيرفر القديم.
- **ZIP 2 (كروت اللوحات):** `index.html`, `app.css`, `sw.js` (v22→v23), +`test_task2_role_cards.py`. الكروت وإخفاء التقديم.
- **ZIP 3 (إعادة تصميم اللوحتين):** `static/pharmacy.html`, `static/courier.html` (شكل فقط)، +`static/panel.css`، `static/sw.js` (v23→v24 وإضافة panel.css إلى SHELL)، +`test_task3_panels_browser.py` (48 فحصًا بهاتف 390×844 وكمبيوتر 1280×800 وشاشة 320px، مع نقرات فعلية على الوظائف).
- **ZIP 4 (جرس الإشعارات):** +`static/notif.js`، `static/pharmacy.html` و`static/courier.html` (إضافة `<script src="/notif.js" defer>` فقط)، `static/panel.css` (بلا تغيير)، `static/sw.js` (v24→v25 وإضافة notif.js)، +`test_task4_notif_bell.py` (74 فحصًا، Chromium، API وهمي).
- **الإقفال (المهمة 5):** دُمجت ZIP 1-4 فوق أرشيف المشروع الكامل (كان قبل المهمة 1، sw=v22). `static/index.html` فيه الآن سكربت notif.js. أُصلح `test_phase16_compat.py` (يقرأ إصدار sw الحالي ≥19) و`test_phase9_courier_ui.py` (يتوقع «تسجيل دخول المندوب»). في `test_task2_role_cards.py` و`test_task3_panels_browser.py` أُضيفت استثناءات لرسائل شبكة بيئية (`ERR_TUNNEL_CONNECTION_FAILED`، `status of 404` المحاكى، وتحذير Chrome عن `navigator.vibrate` قبل أول لمسة من كود المندوب القديم). جرس notif.js لا يهتز قبل تفاعل المستخدم. **النتيجة: 51 ملف اختبار كلها تنجح (1123 سطر PASS، 0 فشل).**
- **دمج المشروع الكامل (تسليم واحد):** الأساس = `.merge-check/laqino` (النسخة التي بُني عليها التحديث) • «ours» = الكود الحالي • «theirs» = التحديث. `git merge-file` لـserver.py/index.html/admin.html/courier.html/pharmacy.html دون تعارض؛ تعارضات يدوية في app.css (أُبقي الطرفان)، sw.js (SHELL من التحديث + v27 + منطق push الحالي)، واختبارين (أُخذ إصلاح التحديث). **Dockerfile كان لا ينسخ notif.py** فأُصلح (+`test_docker_modules.py`). أُعيدت `testutil.py` و`imgutil.py` و5 اختبارات وملفي ignore كانت ناقصة من الأرشيف الكامل. قاعدة البيانات الحقيقية لم تُلمس وغير مرفقة. `market.html` لا يحوي جرس الإشعارات ولا هو في SHELL (لم يكن في نطاق التحديث). `docs/` المشار إليه في README_HISTORY.md غير موجود في الأرشيف المستلم.
- **فخ بيئي:** في بيئة كلود الخطوط الخارجية تفشل بـ`ERR_TUNNEL_CONNECTION_FAILED` (لا `NAME_NOT_RESOLVED`)، فأي اختبار متصفح يعدّ أخطاء الكونسول يجب أن يستثنيها.
- **المهمة 6 (إشعارات الإدارة):** triggers جديدة في `notif.py` (VERSION=2): لكل حساب `role IN ('admin','staff')` إشعار عند: انضمام مندوب/صيدلية جديد أو إعادة تقديم (status→pending)، طلب شحن جديد، إعلان جديد pending. `kind='admin.*'` و`link='admin:<قسم>'` (couriers/providers/topups/listings). `notif.js` يعمل في `admin.html` (التوكن من `sessionStorage['at']`، يركّب الجرس في `<header>`)، والنقر على إشعار يفتح القسم عبر `tab=<قسم>;shell()`. `admin.html` فيه سكربت notif.js؛ sw=v26. `test_task6_admin_notifs.py` (سيرفر حقيقي + admin.html الحقيقي). **فخ:** السيرفر الحقيقي يفرض CSP بلا `unsafe-eval` فلا تستخدم `page.wait_for_function` بنص في اختبارات admin.html (استخدم wait_for_selector). **لا إشعار للإدارة عن:** استفسارات/روشتات، طلبات التوصيل، اعتراضات (disputed). **النتيجة: 52 ملف اختبار، 1164 فحصًا، 0 فشل.**

- **الخطوة 1 (أكتوبر 2026):** صور الشات (`chat.py`، عمود `chat_messages.file_id`)، واجهة market.html وadmin.html، تسجيل `chat.admin_view`/`chat.admin_view_image` في audit_log، كاش v41، VERSION=`phase-09s1`. اختبارات جديدة: `test_step1_chat_images.py` و`test_step1_chat_images_browser.py`. التفاصيل: `docs/steps/step-01-chat-images.md`. **فخ:** الصور لا تُعرض بـ`<img src>` مباشرة لأن التوكن في ترويسة Authorization؛ تُجلب بـfetch ثم blob.
- **الخطوة 2 (أكتوبر 2026):** توسيع طلب الخدمة: عنوان/موعد/ميزانية/صور (حتى 3)، والحالات الـ11 (`open, awaiting_quotes, quotes_received, provider_selected, accepted, on_the_way, in_progress, done, cancelled, disputed, expired`) بخريطة انتقالات واحدة `NEXT` في `svc.py`، سجل أحداث `service_request_events`، انتهاء تلقائي بعد 14 يومًا، `POST /api/my/service-jobs/<id>/progress`. **إعادة بناء جدول `service_requests` تلقائيًا مرة واحدة** (قيد CHECK). كاش v42، VERSION=`phase-09s2`. **تغيّر سلوك:** قبول المقدم يضع `accepted` (كان `in_progress`). **قرار:** الحالات الـ11 لم تكن مكتوبة في أي مكان فاعتُمد اقتراح افتراضي (مالك المشروع لم يحدد) — عدّلها من `STATUSES/NEXT/LABELS`. الحالات 2–4 تُفعَّل في الخطوة 3، و`disputed` في الخطوة 6. العنوان والصور لا يراهما مقدم قبل القبول. اختبارات: `test_step2_service_requests.py` (100) و`test_step2_service_requests_browser.py` (15)، وكل الـ76 ملف اختبار exit 0. التفاصيل: `docs/steps/step-02-service-requests.md`. **فخ:** اختبارات المتصفح لصفحة الإدارة تحتاج دخولًا من الواجهة (التوكن في `sessionStorage['at']` لا `localStorage`).
- **الخطوة 3 (أكتوبر 2026):** عروض أسعار الخدمات في `svc.py`: جدولا `service_request_invites` و`service_quotes` (حالات العرض pending/approved/rejected/selected/not_selected/withdrawn)، أعمدة `dispute_reason/disputed_by/disputed_at`. المسار: open → awaiting_quotes (العميل يوزّع على مقدمين) → quotes_received (الإدارة تعتمد عرضًا) → provider_selected (العميل يختار) → accepted (المقدم يؤكد؛ تنكشف بيانات العميل). القبول المباشر باقٍ لطلب `open` فقط. اعتذار/مهلة `SELECT_TTL_DAYS`=2/فك ربط ← يرجع لمرحلة العروض. النزاع: فتح (عميل/مقدم، `DISPUTE_WINDOW_DAYS`=7) وحسم الإدارة `done/cancelled` بسبب. لا أرقام هاتف في نص العرض (`_phone_in`). كاش v43، VERSION=`phase-09s3`. اختبارات: `test_step3_quotes.py` و`test_step3_quotes_browser.py`؛ كل المشروع 78 ملفًا exit 0 (2034 PASS). **فخ:** `window.sqs` في `index.html` لبحث السوق، فاختيار العرض اسمه `sqsel`. **فخ:** فك ربط حساب مقدم يعيد طلباته الجارية إلى `open` (سلوك قديم، ليس مرتبطًا بالعروض). التفاصيل: `docs/steps/step-03-service-quotes.md`.
- **الخطوة 5 (أكتوبر 2026):** التقييم في `svc.py`: أعمدة `service_ratings.comment/updated_at/hidden` وجدول `service_rating_reports` (يحمل نسخة النجوم والتعليق وقت البلاغ بلا FK على التقييم كي يبقى أثره بعد الحذف)؛ تعديل/حذف العميل، بلاغ مالك المقدم، قرار الإدارة (`hide/dismiss/restore`)، و`GET /api/services/<id>/ratings` العلني (في `server.py`). `rating_of` يستثني المخفي. كاش v45، VERSION `phase-09s5`. التفاصيل: `docs/steps/step-05-ratings.md`.
- **الخطوة 4 (أكتوبر 2026):** الروشتات في `rx.py`: جدولا `rx_images` (حتى 5 صور؛ `prescriptions.file_id` = الغلاف) و`rx_seen` (اطّلاع الصيدلية)، وأعمدة `prescription_responses.review/review_reason/reviewed_at/reviewed_by` مع triggers `ntf_rxresp_ins/upd` (أي رد جديد أو معدَّل = `pending` + إشعار للإدارة). العميل لا يرى ولا يطلب توصيلًا من رد غير معتمد. مسارات الإدارة: `GET /api/admin/rx/responses`، `POST /api/admin/rx/responses/<rx>/<pharmacy>/review`، `GET /api/admin/rx/tracking`. `stage` يُحسب (review/at_pharmacies/quoted/closed). كاش v44، VERSION=`phase-09s4`. التفاصيل: `docs/steps/step-04-prescriptions.md`.

- **الخطوة 7 (أكتوبر 2026):** `notif.py` (VERSION=3): triggers `ntf_adm_order_disputed` و`ntf_pharm_order_disputed`، ودالتا `inquiry_created` (للصيدليات المعتمدة في المناطق المتداخلة) و`prescription_pending` (للإدارة إن لم توجَّه الروشتة) تُستدعيان من `server.py` بعد إنشاء الاستفسار/الروشتة، best-effort. VERSION=`phase-09s7`، كاش v45 بلا تغيير. اختبار جديد `test_step7_notifs.py`؛ عُدّل `test_notifications.py` (الصيدلية 3 إشعارات). التفاصيل: `docs/steps/step-07-notifications.md`.

## إضافات فوق الخطوة 7
- **م8ب (أكتوبر 2026):** `lsocial.py` (مفضلة/بلاغات إعلانات) + `market.html` + `admin.html` + ربط في server.py + كاش v41 + VERSION=phase-09b. `docs/phases/phase-08b-README.md`.
- **سوق الصيدليات** (`exchange.py` + قسم في `pharmacy.html` + تبويب في `admin.html`): `docs/steps/step-07b-pharmacy-exchange.md`.
- **دُمجت النسختان** (خطوات 1–7 + سوق الصيدليات) مع النسخة `phase-09c` (المفضلة والإبلاغ عن إعلانات السوق `lsocial.py`): الإصدار `phase-09s7x`، كاش `laqino-v47`.


## تحديث واجهات أكتوبر 2026 (هذه الحزمة)
- تعديل `static/index.html`: بطاقات اختصار للخدمات الطبية وتسمية «سعّر روشتة» مع إبقاء المسارات والمنطق الحاليين.
- تعديل `static/app.css`: تحسين بطاقات الرئيسية والطبي واستجابة الشاشات الصغيرة.
- تعديل `static/sw.js`: رفع الكاش إلى `laqino-v48`.
- «المنتجات» الطبية مستقلة عن سوق الإعلانات وفق وحدتي `products.py` و`market.py`.
- النواقص: لا توجد حاليًا إعدادات موحّدة مثبتة في الكود لترتيب/إظهار بطاقات الرئيسية من لوحة الإدارة؛ لم تُضف لتجنب إنشاء مصدر إعدادات مكرر. لم يتم اختبار التطبيق بمتصفح حي أو على هاتف حقيقي.

## UI redesign continuation — phase 2 (2026-10-18)
- Added shared responsive/visual consistency rules in `static/theme.css` for the existing customer, pharmacy, admin, and courier pages.
- Added isolated visual polish for standalone `static/market.html`.
- Bumped Service Worker cache to `laqino-v49`.
- Added `test_phase17_responsive_ui.py` and documented actual checks/results in `README_UPDATE.md`.
- Verified: phase17 static responsive checks, phase12 home UI checks, phase11 category checks, phase16 courier-wallet checks, Python compile, inline index JS syntax.
- Browser/device visual QA remains unperformed because Chromium is unavailable. Admin-configurable home-card visibility/order is still a separate unfinished task; the existing admin category center is not that system.
- Added a dedicated homepage tile for the independent medical products feature, preserving the existing products view/route and keeping it distinct from marketplace listings. Updated `test_phase12_home_ui.py`; the test passes with five section cards.
- Added a dedicated homepage tile for the independent medical products feature, preserving the existing products view/route and keeping it distinct from marketplace listings. Updated `test_phase12_home_ui.py`; the test passes with five section cards.

## المرحلة 18 — إدارة أقسام الصفحة الرئيسية
- أُضيفت واجهة «الأقسام والواجهة» في لوحة الإدارة للتحكم في اسم كل بطاقة ووصفها وظهورها وترتيبها.
- أُضيف المسار `GET /api/home-sections` للقراءة العامة و`POST /api/home-sections` للحفظ بصلاحية الإدارة فقط، مع تحقق من المعرّفات والحدود وعدم تكرار الترتيب.
- تُحفظ الإعدادات في جدول `settings` الحالي تحت المفتاح `home_sections_v1`، دون إنشاء جدول جديد أو تعديل بيانات المستخدمين والطلبات.
- الرئيسية تقرأ الإعدادات عند فتحها وتستخدم روابط الأقسام ومعرّفاتها الأصلية؛ عند تعذر تحميل الإعدادات ترجع إلى القيم الافتراضية.
- تم تحديث إصدار Service Worker إلى `laqino-v50`.
- الاختبارات المنفذة: `test_phase17_responsive_ui.py` و`test_phase12_home_ui.py` و`test_phase18_home_sections.py`، بالإضافة إلى فحص صياغة Python وJavaScript.
- لم يتم اختبار المتصفح الحقيقي أو المقاسات بصريًا؛ لا تعتبر هذه المرحلة اعتمادًا نهائيًا للإنتاج.
- **phase-30 (أكتوبر 2026) — الإعلان المميز:** `listings.featured_until` (ALTER بعد `market.migrate`)، `GET/POST /api/admin/featured*` و`POST /api/admin/listings/{id}/feature`، `featured` و`featured=1` في `GET /api/listings`، قسم مميز في `market.html` وقسم إدارة في `admin.html`. حد أقصى متزامن (`settings.featured_max`، افتراضي 6). التفاصيل: `README_UPDATE.md`.
- **phase-29 (أكتوبر 2026) — واجهة السوق 3D:** تعديل `static/market.html` فقط (CSS إضافي `lagino-market-3d` + ظهور تدريجي للصور + معرض صور بالسحب/التكبير + شارة «جديد الآن»). لا تغيير في السيرفر. التفاصيل: `README_UPDATE.md`.
- **phase-28 (أكتوبر 2026) — العمولة عند التسليم + توصيل بلا مناطق:** `charge_commission` عند `arrived→awaiting_confirmation` (idempotent)، `wallet_free` لا يحجز المخصوم، `reverse-commission` يعمل على completed/awaiting_confirmation/disputed/cancelled (يدوي بسبب)، `/api/courier/wallet` يرجّع `available` و`held`. `POST /api/delivery/orders` بلا `region_id` ولا سعر منطقة (`default_delivery_region`)؛ التوزيع يضيف مناديب المناطق الفرعية. التفاصيل: `README_UPDATE.md`.
- **phase-27 (أكتوبر 2026) — أجرة يقترحها العميل:** `delivery_orders.offer_fee` (اختياري). `POST /api/delivery/orders` يقبل `offer_fee` (رقم موجب ≤ 100000 وإلا 400؛ فارغ = التدفق القديم) ويخزّنه ويجعل `fee` الابتدائية = سعر العميل والعمولة تُحسب منه. `POST /api/courier/orders/<id>/accept`: بلا `counter` وبوجود `offer_fee` ← `fare_status='approved'` فورًا (+ audit `order.fare_accepted_offer`)، وبـ`{"counter":true}` ← `draft` والمندوب يكمل بمسار `/fare` الحالي. رفض العميل يعيد الطلب للباقين و`offer_fee` ثابت. `offer_fee` يُرجَع في قوائم العميل والمندوب (تغيّر عقد؛ عُدّل اختبارا `test_phase10_dispatch` و`test_phase9_step4_ui`). الواجهة: حقل `#of` في فورم `index.html`، وزرّا «قبول بـX ج» / «قبول وتعديل السعر» في `courier.html`. كاش v60. اختبارات: `test_phase27_customer_offer.py` و`test_phase27_customer_offer_browser.py`. **فخ:** فورم التوصيل يُفتح بـ`go(2)` لا بتبويب سفلي (لا `#t2` في الشريط). **غير مغطّى:** طلبات الصيدلية (`/api/medical/delivery`) بلا حقل سعر للعميل، وإشعار المندوب لا يذكر السعر.

- **phase-32 (أكتوبر 2026) — كارت السوق يفتح التفاصيل:** في `index.html` كارت `.card.ad` في تبويب السوق (دالة `souq()`) صار `onclick="oad(event,id)"` ويذهب إلى `/market.html#/l/<id>` (يتجاهل الضغط على الأزرار/الروابط داخله)، مع وسم عدد الصور. كاش v64. اختبار `test_phase32_souq_card_opens.py`. التفاصيل: `README_UPDATE.md`.

- **phase-33 (أكتوبر 2026) — ترتيب ردود الصيدليات:** `index.html` فقط: `qsrt/isrt` (دوال ترتيب) تفرز تسعيرات الروشتة وردود الاستعلام من الأرخص (الجزئي وغير المتوفر آخرًا) وعلامة «الأرخص» للاستعلام؛ `md()` بعد نجاح طلب التوصيل يعمل `go(3)` (حسابي ← طلباتي). كاش v65. اختبار `test_phase33_replies_sorted.py`. **الباقي من خطة تبويب الطبي:** صفحة الطلب المستقلة، كروت «طلباتك» بالحالات، أعلى الشاشة (ابعت روشتتك / اسأل عن دواء)، اختصارات أطباء/معامل/منتجات، وعدّاد الردود الجديدة على أيقونة «الطبي» (يحتاج حالة «اتشاف» في قاعدة البيانات). التفاصيل في `README_UPDATE.md`.

- **phase-34 (أكتوبر 2026) — «طلباتك» في الطبي:** `index.html` + `app.css`: `rqInfo/myreq` (كروت الحالة o/b/w/g وزر «السابقة»)، `mo/mb/mdet` (صفحة الطلب؛ المتغير `mview` يُصفَّر عند تبديل التبويب الفرعي)، تُحقن `rq` في `medMain` تحت `sub`. القوائم القديمة باقية. كاش v66. اختبار `test_phase34_my_requests.py`. **الباقي:** أعلى الشاشة (ابعت روشتتك/اسأل عن دواء)، اختصارات أطباء/معامل/منتجات، عدّاد الردود الجديدة (يحتاج «اتشاف» في DB)، فتح صفحة الطلب من الإشعار. **فخ:** الكارت الأزرق لا يعرف حالة طلب التوصيل نفسه.

- **phase-35 (أكتوبر 2026) — أعلى الطبي:** `index.html` + `app.css`: `.rxbig` (زرّان كبيران بدل `.seg2`؛ الأول `pri` برتقالي) ، وفي `med()` عند `mt=='rx'` ولا يوجد `mview` يُنقل صف `.mtabs` إلى آخر الصفحة بصيغة `.mtabs.sm` تحت عنوان «خدمات تانية» (وفي باقي التبويبات يبقى فوق كالسابق). اختبار `test_phase35_med_top.py`. **الباقي:** عدّاد الردود الجديدة على أيقونة «الطبي» (يحتاج «اتشاف» في DB)، وفتح صفحة الطلب من الإشعار. ملاحظة: `test_phase20_ui_polish` يعتمد على `.mtabs .mt` وغياب `.seg2` فلا تُسمِّ العناصر بغير ذلك.

- **phase-38 (أكتوبر 2026) — بروفايل المندوب:** `couriers.avatar_file_id` (صورة يضبطها المندوب فقط عبر `POST /api/courier/avatar`)، `GET /api/couriers/<id>/profile|photo` بصلاحية (المندوب/الإدارة/عميل بأجرة مقترحة منه)، شاشة `#cpv` في `index.html` تُفتح من `.cpm` في كارت الطلب (`cpm/cpo/cpc`)، وكارت `.pfc` في `courier.html`. كاش v70. اختبار `test_phase38_courier_profile.py`. **فخ:** لا تستخدم صورة `courier_documents` كأفاتار (ممنوع بالسيرفر). لا history/pushState للشاشة عمدًا لأن `shell.js` يفسّر popstate كرجوع للرئيسية.

## تحديث phase-39 — دمج فرع phase-36 فوق phase-38
- أُضيف (دون استبدال أي شيء من phase-38): صفحات `/privacy` `/terms` `/contact` `/delete-account`، حذف الحساب بإخفاء الهوية (`account.py`، `POST /api/me/delete`، `users.deleted_at`)، شرح الأذونات (`static/perm.js`)، أدوات أندرويد (`android/tools`، Capacitor 8)، تصحيح الدومين إلى `laqino.tech`.
- **فخ تم حله:** `couriers.avatar_file_id` (م38) يمنع حذف ملف صورة المندوب عند حذف حسابه؛ `account.py` يفك الربط أولًا (`test_phase39_delete_with_avatar.py`).
- `test_ui_page_harness.js` صار يوفّر `location/history/MutationObserver/URL` (كان سبب فشل 17 اختبار واجهة). كاش v71. التفاصيل: `README_UPDATE.md`.

## تحديث اختبارات phase-48 (23 أكتوبر 2026) — بعد تقرير الاختبارات الشامل
- **الإصدار والكاش لم يتغيرا** (`phase-48` / `laqino-v84`)؛ تغيّر ملفان في `static/` فقط (إصلاح سباق، انظر أدناه). الـ SW شبكة أولًا فلا حاجة لرفع الكاش.
- **تحديث اختبارات قديمة (السلوك الحالي هو المقصود):**
  - `test_phase3_rx.py`: بند الدواء صار يحمل `item_status` فالمقارنة لم تعد تطابقًا تامًا.
  - `test_phase33_replies_sorted.py` و`test_phase34_my_requests.py`: الردود تُرتَّب بالحالة فقط (متوفر ← يحتاج تأكيد ← غير متوفر) وليس بالسعر، وشارة «الأرخص» أُزيلت قصدًا (سطر «أزيلت شارات الأرخص» أعلاه). أي توثيق أقدم يقول «من الأرخص» تاريخي. دالة `qsrt` ترتّب بالاكتمال فقط (مستقر).
  - `test_phase22_location_browser.py`: تحديد الموقع داخل أي قرية تابعة لمركز الرياض يرجّع **مركز الرياض (3)** عمدًا (`resolve_region` في server.py، slug `eg-kfs-riyad`)، لا القرية.
  - `test_phase35_med_top.py` و`test_step4_rx_browser.py`: حقل `#rf` مخفي بالتصميم (أزرار كاميرا/معرض) فالانتظار صار `state="attached"`. تم التحقق من مسار رفع 3 صور بلا متصفح (File/FileReader وهميان ضد سيرفر حقيقي): نجح.
  - `test_whatsapp_verify_ui.py`: `auth()` في index.html صارت تسجيل دخول فقط؛ التسجيل في `register.html`. أُعيدت كتابة جزء التسجيل على مسار API (start ← تأكيد الأدمن ← status ← register ← login). استعادة كلمة المرور ما زالت عبر `vfs/vfp` في index.html.
- **إصلاح سباق (كود حقيقي):** `poll` في `static/register.html` و`vfp` في `static/index.html` كانا يقرآن `verification`/`VF` بعد `await`؛ إلغاء المستخدم أثناء الطلب كان يعطي TypeError (null). صار يُحفظ المرجع قبل الانتظار ويُعاد فحصه بعده.
- **لم يُجرَّب بعد:** اختبارات Playwright (المتصفح محجوب في بيئة التطوير)، الأجهزة الحقيقية (FCM وWeb Push وواتساب Meta وiOS/Safari وDocker).


## phase-49 — إصلاح رفع صور «ابعت روشتتك» (2026-10-24)
- حد الصور صار 5 لكل طلب في `rx.py` والواجهة؛ الخادم يرفض 6 صور في الطلب الواحد.
- واجهة الروشتة تضغط الصورة عبر `imgShrink` وتحوّلها إلى JPEG قبل الرفع، وتُبقي حد الخادم 4MB كحماية أخيرة.
- عدّاد الملفات العامة يستثني صور الروشتات المرتبطة في `prescriptions` و`rx_images`، دون حذف أي بيانات.
- تحديث كاش Service Worker إلى `laqino-v85` (`VERSION`: `phase-49`).
- تم التحقق بنجاح من `python -m py_compile server.py rx.py`، و`test_step4_rx.py`، و`test_phase46_medical_ui.py`، و`test_phase49_rx_upload_limits.py`. Playwright تجاوز فحص المتصفح الحي لأن بيئة الحاوية تحجب localhost.


## phase-50 — إصلاح حصة رفع الصور العامة
- السبب: عدّاد `files` كان يستثني صور الروشتات والشات والسوق والخدمات، لكنه لا يستثني مستندات المندوب وصورة بروفايله، كما لم يشمل كل جداول الصور المرتبطة بالميزات.
- الحل: لا تدخل الملفات المرتبطة بميزة (مستندات/بروفايل المندوب، صور الإعلانات والمنتجات والتبادل، صور الأطباء والمعامل، الروشتات، الشات والخدمات) في الحصة المؤقتة العامة ذات 20 ملفًا. الملفات المؤقتة غير المرتبطة تظل خاضعة للحد. لا تُحذف أي بيانات، ولا يتغير كاش الواجهة لأن التعديل خادمي فقط.
- الاختبارات: `test_phase50_upload_quota.py`, `test_phase49_rx_upload_limits.py`, `test_step4_rx.py`, `test_step1_chat_images.py`, `test_step2_service_requests.py` نجحت.
