#!/usr/bin/env bash
# تثبيت لاقينو على سيرفر Ubuntu بأمر واحد.
# الاستخدام:  sudo bash deploy/install.sh الدومين رقم_المدير [الرسوم] [العمولة]
# مثال:       sudo bash deploy/install.sh laqino.duckdns.org 01012345678 20 5
set -euo pipefail
cd "$(dirname "$0")/.."
USAGE="usage: sudo bash deploy/install.sh DOMAIN ADMIN_PHONE [FEE=20] [COMMISSION=5]"
DOMAIN="${1:?$USAGE}"; PHONE="${2:?$USAGE}"; FEE="${3:-20}"; COMM="${4:-5}"
[ "$(id -u)" = 0 ] || { echo "شغّل الأمر بـ sudo"; exit 1; }
[[ "$PHONE" =~ ^01[0125][0-9]{8}$ ]] || { echo "رقم المدير غير صحيح (01xxxxxxxxx)"; exit 1; }
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo "الدومين غير صحيح"; exit 1; }
[[ "$FEE" =~ ^[0-9]+(\.[0-9]+)?$ && "$COMM" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "الرسوم والعمولة أرقام فقط"; exit 1; }

# ذاكرة إضافية (swap) للسيرفرات الصغيرة 1GB
if ! swapon --show | grep -q .; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh

# ملف الإعدادات (لا يُستبدل لو موجود)
if [ ! -f .env ]; then
  PW="$(openssl rand -hex 12)"
  cp deploy/env.example .env
  sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|; s|^LAQINO_ADMIN_PHONE=.*|LAQINO_ADMIN_PHONE=$PHONE|; s|^LAQINO_ADMIN_PASSWORD=.*|LAQINO_ADMIN_PASSWORD=$PW|" .env
  chmod 600 .env
  echo "كلمة مرور المدير: $PW   (محفوظة في ملف .env — سجّلها الآن)"
else
  echo ".env موجود، لم يُعدَّل."
fi

docker compose up -d --build
echo "بانتظار تشغيل التطبيق..."
for i in $(seq 1 30); do docker compose exec -T app python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" >/dev/null 2>&1 && break; sleep 2; done
docker compose exec -T app python setup_initial.py --region 3 --fee "$FEE" --commission-type fixed --commission-value "$COMM"
echo
echo "تم. افتح: https://$DOMAIN/healthz  ثم  https://$DOMAIN/admin.html"
echo "(الشهادة تحتاج دقيقة في أول مرة، والدومين لازم يكون موجّهًا لعنوان هذا السيرفر)"
