#!/bin/bash
# نصب قراردادها (داخل تعریف وام): قالب نسخه‌دار، متغیرها، موتور امن، تولید، وضعیت و تأیید
set -e
ROOT="${1:-/home/ghestine/domains/ghestine.ir/Ghestine}"
HERE="$(cd "$(dirname "$0")" && pwd)"; SRC="$ROOT/src"
[ -d "$SRC" ] || { echo "پوشه src پیدا نشد: $SRC"; exit 1; }
B="$ROOT/.ctr-backup-$(date +%Y%m%d%H%M%S)"; mkdir -p "$B"
DBF=$(grep -rl "class AppDbContext" "$SRC" --include=*.cs | head -1); [ -n "$DBF" ] || { echo "AppDbContext پیدا نشد"; exit 1; }
PG="$SRC/Ghestine.API/Program.cs"; cp "$PG" "$B/Program.cs.bak"; cp "$DBF" "$B/AppDbContext.cs.bak"; echo "بکاپ: $B"
BE=$(grep -rl "class BaseEntity" "$SRC" --include=*.cs | head -1); [ -n "$BE" ] || { echo "کلاس BaseEntity پیدا نشد."; exit 1; }
grep -q "Guid Id" "$BE" || { echo "BaseEntity کلید Guid ندارد ($BE)."; exit 1; }
BENS=$(grep -h "^namespace" "$BE" | head -1 | sed 's/namespace //; s/;//; s/\r//')
DBNS=$(grep -h "^namespace" "$DBF" | head -1 | sed 's/namespace //; s/;//; s/\r//')
grep -rq "class CustomerDocument" "$SRC" --include=*.cs || { echo "ابتدا ماژول core را نصب کنید."; exit 1; }
grep -rq "class CounterParty" "$SRC" --include=*.cs || { echo "ابتدا ماژول ops را نصب کنید."; exit 1; }
grep -rq "class TenantMiddleware" "$SRC" --include=*.cs || { echo "ابتدا ماژول چندمستاجری (tenancy) را نصب کنید."; exit 1; }
cp "$HERE/files/ContractModule.cs" "$SRC/Ghestine.Domain/Entities/ContractModule.cs"
sed -i "s/^using Ghestine.Domain.Common;/using $BENS;/" "$SRC/Ghestine.Domain/Entities/ContractModule.cs"
mkdir -p "$SRC/Ghestine.API/Contracts"
for f in ContractEngine ContractServices ContractControllers; do cp "$HERE/files/$f.cs" "$SRC/Ghestine.API/Contracts/$f.cs"; sed -i "s/__DBNS__/$DBNS/" "$SRC/Ghestine.API/Contracts/$f.cs"; done
addset(){ grep -q "DbSet<Ghestine.Domain.Entities.$1>" "$DBF" && return 0
  grep -q "protected override void OnModelCreating" "$DBF" || { echo "OnModelCreating پیدا نشد؛ DbSet ها را دستی اضافه کنید"; exit 1; }
  sed -i "0,/protected override void OnModelCreating/s//public DbSet<Ghestine.Domain.Entities.$1> $2 => Set<Ghestine.Domain.Entities.$1>();\\n\\n    protected override void OnModelCreating/" "$DBF"; }
addset ContractTemplate ContractTemplates; addset ContractVariableDef ContractVariableDefs; addset ProductContract ProductContracts; addset GeneratedContract GeneratedContracts; addset ContractEvent ContractEvents
for n in ContractTemplate ContractVariableDef ProductContract GeneratedContract ContractEvent; do grep -q "DbSet<Ghestine.Domain.Entities.$n>" "$DBF" || { echo "درج DbSet $n انجام نشد. بکاپ: $B"; exit 1; }; done
API="$SRC/Ghestine.API/Ghestine.API.csproj"; [ -f "$API" ] || API=$(ls "$SRC"/Ghestine.API/*.csproj | head -1)
grep -q "HtmlSanitizer" "$API" || (cd "$SRC/Ghestine.API" && dotnet add package HtmlSanitizer) || { echo "نصب بسته‌ی HtmlSanitizer انجام نشد (دسترسی nuget؟)"; exit 1; }
cd "$ROOT"
if dotnet build 2>&1 | tee /tmp/ctr-build.log | tail -15 | grep -q "Build succeeded"; then echo "ساخت موفق."; else
  echo "خطای build؛ ۱۵ خط آخر را بفرستید. برگرداندن: cp $B/AppDbContext.cs.bak $DBF"; exit 1; fi
cat <<'MSG'

=== مراحل بعد ===
۱) مایگریشن (بعد از بکاپ دیتابیس):
     dotnet ef migrations add AddContracts -p src/Ghestine.Infrastructure -s src/Ghestine.API
     dotnet ef database update -p src/Ghestine.Infrastructure -s src/Ghestine.API
   ایندکس یکتا پیشنهادی: ContractVariableDefs(TenantId,Key) ، GeneratedContracts(TenantId,Number) ، ContractTemplates(GroupKey,Version).
۲) در appsettings (اختیاری): "Contracts": { "Path": "/home/ghestine/private-contracts" } — پوشه خارج از wwwroot و فقط قابل دسترسی برای کاربر سرویس.
۳) پنل: از منوی «محصولات وام» دکمه‌ی «مدارک و قراردادها» کنار هر طرح.
۴) متغیرهای شرکت (نشانی/تلفن/نام حقوقی) از BrandJson مستأجر خوانده می‌شود: کلیدهای legalName ، phone ، address.
MSG
