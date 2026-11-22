#!/bin/bash
# نصب پشت‌سرهم همه‌ی ماژول‌های بک‌اند. هر مرحله بکاپ می‌گیرد و با خطا متوقف می‌شود.
# استفاده: bash install-all.sh [مسیر_پروژه]
set -e
ROOT="${1:-${DIGIBILEPAY_ROOT:-}}"; H="$(cd "$(dirname "$0")" && pwd)"
[ -n "$ROOT" ] || { echo "مسیر پروژه را به‌صورت آرگومان یا DIGIBILEPAY_ROOT مشخص کنید."; exit 2; }
[ -f "$ROOT/src/Ghestine.API/Ghestine.API.csproj" ] || { echo "پروژهٔ پایه در مسیر $ROOT پیدا نشد؛ نصب متوقف شد."; exit 2; }
echo "### 1/10 چندمستاجری"; bash "$H/backend/tenancy/install.sh" "$ROOT"
echo "### 2/10 هسته (طرح‌ها، کارت مجازی، درگاه، مدارک)"; bash "$H/backend/core/install.sh" "$ROOT"
echo "### 3/10 امنیت ورود (کپچا، OTP)"; bash "$H/backend/security/install.sh" "$ROOT"
echo "### 4/10 عملیات (اعلام واریز، طرف‌حساب‌ها، بازاریاب‌ها، تنظیمات اپ)"; bash "$H/backend/ops/install.sh" "$ROOT"
echo "### 5/10 سازمانی (حسابرسی، دفتر کل، health، پشتیبان خودکار)"; bash "$H/backend/enterprise/install.sh" "$ROOT"
echo "### 6/10 قراردادها (داخل تعریف وام)"; bash "$H/backend/contracts/install.sh" "$ROOT"
echo "### 7/10 دسترسی ریز و رمز دومرحله‌ای"; bash "$H/backend/iam/install.sh" "$ROOT"
echo "### 8/10 زیرساخت عملیاتی (لاگ، صف کار)"; bash "$H/backend/platform/install.sh" "$ROOT"
echo "### 9/10 صندوق اعلان‌ها"; bash "$H/backend/notify/install.sh" "$ROOT"
echo "### 10/10 پشتیبانی و تیکت"; bash "$H/backend/support/install.sh" "$ROOT"
echo "همه‌ی ماژول‌ها ساخته شدند. حالا یک مایگریشن واحد بزنید (بعد از بکاپ دیتابیس):"
echo "  dotnet ef migrations add AddDigibilePayCore -p src/Ghestine.Infrastructure -s src/Ghestine.API"
echo "  dotnet ef database update -p src/Ghestine.Infrastructure -s src/Ghestine.API"
