#!/bin/sh
# نسخة احتياطية متسقة (قاعدة البيانات + الصور) مع فحص سلامة. الاستخدام:  sh deploy/backup.sh [مجلد النسخ]
# تعمل مع Docker وتحفظ ملف laqino-<وقت>.tgz في المجلد المحدد (الافتراضي: الحالي). جدولها يوميًا بـ cron وانسخها خارج السيرفر.
# بدون Docker:  python3 backup_restore.py backup --out /مسار/النسخ --keep 14
set -e
OUT="${1:-.}"; TS=$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"
docker compose exec -T app python backup_restore.py backup --out /tmp/bk --keep 1 >/dev/null
docker compose exec -T app sh -c 'cat "/tmp/bk/$(ls /tmp/bk | grep -E "^laqino-.*[.]tgz$" | tail -1)"' > "$OUT/laqino-$TS.tgz"
tar tzf "$OUT/laqino-$TS.tgz" >/dev/null || { rm -f "$OUT/laqino-$TS.tgz"; echo "فشل التحقق من الأرشيف" >&2; exit 1; }
echo "تم: $OUT/laqino-$TS.tgz"
