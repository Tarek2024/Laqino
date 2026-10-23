# نتائج التكامل النهائي phase-48

التاريخ: 2026-10-23
الإصدار: `phase-48` / كاش `laqino-v84`
البيئة: اختبارات محلية على قواعد بيانات مؤقتة. لا توجد عملية نشر أو اتصال بقاعدة الإنتاج.

## بوابة ما قبل النشر
- PASS — `sh deploy/preflight_update.sh`.
- PASS — `check_versions.py`, `release_check.py`, و`py_compile`.
- PASS — `test_phase44_auth_separation.py`.
- PASS — `test_phase45_region_scope.py`.
- PASS — `test_phase46_medical_ui.py`.
- PASS — `test_phase47_rx_missing_items.py` و`test_phase47_rx_schema_migration.py`.
- PASS — `test_phase9_medical_delivery.py`.

## اختبارات التكامل الإضافية
- PASS — `test_step4_rx.py` (رفع الصور المتعددة، اعتماد الردود، الخصوصية، والدليفري).
- PASS — `test_phase8_rx_claim_concurrency.py` و`test_phase12_rx_full_quote_closes_claim.py`.
- PASS — `test_phase13_rx_worker_lease.py`, `test_phase14_rx_deadline_notifications.py`, `test_phase17_admin_claim_toggle.py`.
- PASS — `test_phase22_location.py` و`test_phase22_delivery_cycle.py`.
- PASS — `test_step2_service_requests.py`, `test_phase11_services.py`, `test_phase10_doctors.py`.
- PASS — `test_password_reset.py` و`test_phase30_login_lockout.py`.
- PASS — `test_backup_restore.py` (نسخة احتياطية، تحقق سلامة، استعادة، وحفظ نسخة ما قبل الاستعادة).
- PASS — `test_deploy.py` و`test_docker_modules.py`.
- PASS — `node --check` لسكريبتات `index.html`, `pharmacy.html`, `admin.html`, `location.js`, `sw.js`.

## ما لم يكتمل أو يحتاج بيئة أخرى
- لم يكتمل تشغيل جميع ملفات الاختبار الـ136 في تشغيل واحد. محاولة المسح الشامل علقت في اختبار واجهة منفصل (`test_courier_documents_ui.py`)، وتشغيل مكرر لاختبار البحث العام (`test_phase11_search_ui.py`) انتهت مهلته في إحدى المحاولات رغم نجاح تشغيل سابق. لذلك لا أصف مجموعة الاختبارات كلها بأنها ناجحة؛ الاختبارات المركزة أعلاه هي التي اعتُمدت.
- اختبارات Playwright التي تحتاج Chromium، واختبار الكاميرا الفعلي على هاتف، لم تُنفذ في متصفح/جهاز حقيقي.
- الاختبارات تطبع تحذيرًا بأن `LAQINO_WA_VERIFY!=1` في البيئة المحلية. يجب تفعيل تحقق الهاتف للإنتاج وفق `DEPLOY.md`.
- لم تُؤخذ نسخة من قاعدة الإنتاج من هذه الجلسة ولم يتم النشر. يجب أخذ نسخة احتياطية على السيرفر الفعلي قبل استبدال الملفات.

## قيود وظيفية معلنة
- نطاق مركز الرياض يعتمد على إحداثيات وأنصاف الأقطار الموجودة؛ لا توجد حدود مضلعة رسمية في قاعدة البيانات لتأكيد الحدود الإدارية الدقيقة.
- لا يحتوي المشروع الحالي على OCR؛ قائمة الأصناف المتوقعة تُبنى من أول تسعيرة منظمة تدخلها الصيدلية.
- التوافر الكامل المجمّع من عدة صيدليات لا ينشئ توصيلًا مجمعًا. يبقى التوصيل متاحًا من رد واحد أكد جميع الأصناف المطلوبة، حفاظًا على مسار الدليفري الحالي.
- وضع حجز الروشتات والتوزيع التلقائي مغلق افتراضيًا. يتطلب التفعيل مراجعة الإعدادات واختبارها على staging.

## حالة النشر
**غير منشور على الإنتاج.** راجع `BACKUP_AND_ROLLBACK_PHASE48.md` قبل أي نشر.
