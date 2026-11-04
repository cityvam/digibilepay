#!/bin/bash
# نصب آسان DigitalPay. روی سرور (SSH یا ترمینال DirectAdmin) فقط همین یک دستور را بزنید:
#   bash digitalpay-setup.sh            ← نصب مرحله‌به‌مرحله‌ی ترمینالی (پرسش y/N)
#   bash digitalpay-setup.sh --web      ← لینک موقت مرورگر می‌دهد و نصب با دکمه انجام می‌شود
# اگر زیپ را نیاورده‌اید: فایل digitalpay-project.zip را کنار همین فایل بگذارید؛ اسکریپت خودش باز می‌کند.
set -e
D="$(cd "$(dirname "$0")" && pwd)"; ROOT="${ROOT:-/home/ghestine/domains/ghestine.ir/Ghestine}"
if [ ! -f "$D/install-all.sh" ] && [ -f "$D/digitalpay-project.zip" ]; then command -v unzip >/dev/null || { echo "ابتدا: apt install -y unzip"; exit 1; }; unzip -oq "$D/digitalpay-project.zip" -d "$D/DigitalPay"; D="$D/DigitalPay"; fi
[ -f "$D/install-all.sh" ] || { echo "فایل‌های نصب پیدا نشد"; exit 1; }
if [ "$1" = "--web" ]; then command -v python3 >/dev/null || { echo "python3 لازم است: apt install -y python3"; exit 1; }; exec python3 "$D/setup-web.py" "$ROOT" "${PORT:-8765}"; fi
exec bash "$D/server-run.sh" "$ROOT"
