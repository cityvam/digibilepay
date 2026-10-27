DigitalPay — بسته‌ی کامل (فرانت، بک‌اند، دیتابیس)
================================================
پیش از هر چیز، صادقانه:
 ۱) این بسته «افزونه‌ی کامل روی پروژه‌ی ASP.NET موجود شماست»، نه یک پروژه‌ی مستقل. کد پایه‌ی خود پروژه (Ghestine.Domain/Application/Infrastructure/API، جدول‌های کاربران و وام‌ها) هیچ‌وقت در دسترس من نبود؛ پس داخل این زیپ نیست و نام‌فضاهای C# (Ghestine.*) را عوض نکرده‌ام تا نصب‌کننده‌ها روی پروژه‌ی فعلی کار کنند.
 ۲) «دیتابیس واقعی» (فایل .bak با داده) از اینجا ممکن نیست. به‌جایش اسکریپت‌های SQL دیتابیس DigitalPay داده شده؛ ولی فقط جدول‌های ماژول‌های جدید را دارد (۲۲ جدول)، نه جدول‌های قدیمی پروژه. راه ایمن برای دیتابیس فعلی همان مایگریشن EF است.
 ۳) هیچ کد C# این بسته با کامپایلر اجرا نشده (کامپایلر در دسترس من نبود). نصب‌کننده‌ها بعد از نصب dotnet build می‌زنند؛ اگر خطا داد ۱۵ خط آخر را بفرستید.
 ۴) نام «DigitalPay» برای دیتابیس/بسته به‌کار رفته. نام برند نمایشی هر دامنه از تنظیم مستأجر (Tenant) می‌آید و در پنل قابل تغییر است.

ساختار
 database/    01-create-database.sql  02-schema-new-modules.sql  03-seed-default-tenant.sql
 backend/     tenancy, core, security, ops, enterprise, contracts  (هرکدام install.sh دارند)
 frontend/    index.html login.html register.html documents.html contracts.html panel.html
 config/      appsettings.sample.json (بدون راز)
 preview/     پیش‌نمایش‌های HTML
 beta/ و server-run.sh  ابزارهای بررسی روی سرور
 README.txt   جزئیات کامل، وضعیت هر ماژول، محدودیت‌ها (اول آن را بخوانید)

مسیر نصب پیشنهادی (روی سرور آزمایشی، بعد از بکاپ)
 1) apt install -y tesseract-ocr tesseract-ocr-fas
 2) bash install-all.sh /مسیر/پروژه          (۶ ماژول، بکاپ و بازگشت خودکار)
 3) dotnet ef migrations add DigitalPayModules ...  &&  dotnet ef database update
    (اگر دیتابیس را از صفر با نام DigitalPay می‌سازید: اسکریپت‌های ۰۱ تا ۰۳ را به‌ترتیب اجرا کنید و Connection String را عوض کنید.)
 4) فایل‌های frontend را در wwwroot بگذارید (admin.html قدیمی را دست نزنید؛ پنل جدید panel.html است).
 5) Super Admin: bash backend/security/run-tool.sh (راهنما در backend/security/README.txt)

درباره‌ی «بدون JS (noJS)»
 صفحه‌های فعلی (ورود، ثبت‌نام، مدارک، قراردادها، پنل) با جاوااسکریپت کار می‌کنند و بدون JS کار نمی‌کنند. نسخه‌ی بدون‌JS یعنی بازنویسی با فرم‌های HTML ساده و رندر سمت سرور (Razor)؛ این هنوز انجام نشده است.
