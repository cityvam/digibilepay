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

==== نصب آسان ====
روی سرور (SSH یا ترمینال DirectAdmin) کنار فایل digitalpay-project.zip:
  unzip digitalpay-project.zip && bash DigitalPay/digitalpay-setup.sh --web
یک لینک موقت (توکن تصادفی، قفل روی اولین IP، ۶۰ دقیقه) چاپ می‌شود؛ در مرورگر باز کنید و مراحل را با دکمه اجرا کنید.
بدون --web: همان نصب مرحله‌به‌مرحله در ترمینال.
نکات: HTTP ساده است؛ پورت 8765 را فقط موقت باز کنید و بعد از پایان Ctrl+C بزنید. پیش از مراحل ۴ و ۵ بکاپ دیتابیس بگیرید. کد C# هنوز کامپایل نشده؛ مرحله‌ی نصب خودش build می‌گیرد و خطا را نشان می‌دهد.

==== نسخه‌ی بدون جاوااسکریپت (/nojs) ====
ماژول backend/nojs (مرحله‌ی ۷ از install-all.sh): رندر سمت سرور، بدون هیچ اسکریپت، CSP با default-src 'none'.
صفحات: /nojs (طرح‌ها) ، /nojs/loans/{slug} ، /nojs/admin/login ، /nojs/admin (فهرست و فعال/غیرفعال) ، تعریف وام سه‌تبه (تب با CSS خالص).
امنیت: Antiforgery روی همه‌ی POSTها، توکن در کوکی HttpOnly/Strict، HTML توضیحات با HtmlClean، اعتبارسنجی سمت سرور، تصویر با بررسی magic bytes.
هنوز ندارد: ثبت‌نام/ورود مشتری، اقساط و قراردادهای من، مدیریت قالب قرارداد، کپچا در فرم ورود مدیر. (کامپایل‌نشده.)

بخش مشتری بدون JS (فایل NoJsCustomer.cs): /nojs/login ، /nojs/me (قراردادهای من) ، مشاهده‌ی متن در iframe با sandbox و CSP، قبول (با تیک موافقت) یا رد با دلیل.
نکته: IP امضا پشت nginx فقط با UseForwardedHeaders درست ثبت می‌شود؛ در Program.cs فعالش کنید. ثبت‌نام و اقساط من هنوز در نسخه‌ی بدون JS نیست.

ورود و ثبت‌نام بدون JS (NoJsAuth.cs): کپچای SVG سمت سرور، ثبت‌نام ۳ مرحله‌ای (موبایل+کپچا ← کد پیامکی ← مشخصات).
منطق امنیتی (کپچا، محدودیت تلاش، OTP، تیکت، ساخت کاربر) از همان SecurityController در همان پردازش اجرا می‌شود؛ منطق دوم ساخته نشده.
پیش‌نیاز: ماژول security نصب باشد. اقساط من هنوز در نسخه‌ی بدون JS نیست.

==== دسترسی ریز (RBAC) و رمز دومرحله‌ای (ماژول iam، مرحله ۷) ====
- ۱۵ مجوز ثابت (customers/loans/installments/deposits/documents/contracts/ledger/audit/backups/settings/users)، نقش‌های ترکیبی، ۵ نقش پیش‌فرض (seed-defaults).
- ادمین قدیمی بدون نقش تا وقتی Iam:LegacyAdminFullAccess=true (پیش‌فرض) دسترسی کامل دارد (به‌جز مدیریت نقش‌ها)؛ بعد از تخصیص نقش‌ها false کنید. SuperAdmin همیشه مجاز.
- فقط SuperAdmin می‌تواند مجوز users.manage بدهد؛ تخصیص نقش به خود ممنوع است. همه‌ی تغییرها در زنجیره‌ی حسابرسی ثبت می‌شود (api/v1/admin/iam).
- TOTP طبق RFC 6238: راز رمزنگاری‌شده، پنجره ±۱ گام، ضد بازپخش، ۸ کد بازیابی یک‌بارمصرف (فقط هش)، قفل ۱۵ دقیقه‌ای بعد از ۵ خطا.
- ورود JSON برای مدیر دارای 2FA، HTTP 202 با ticket می‌دهد (login-v2.html و frontend/login.html به‌روز شده‌اند)؛ ورود /nojs هم همین‌طور.
- استفاده در کنترلرها: [RequirePermission("loans.manage")] (using Ghestine.API.Iam). روی کنترلرهای قدیمی خودکار گذاشته نشده. نقشه‌ی پیشنهادی:
  loan-products→loans.manage ، admin/contract-templates و contract-variables→contracts.manage ، approve→contracts.approve ، ledger→ledger.view/post ،
  audit→audit.view ، backups→backups.manage ، admin/documents→documents.review ، deposits/inquiries/orders→deposits.review/loans.view.
- هنوز نیست: اجبار فعال‌سازی 2FA برای همه‌ی مدیران، 2FA برای مشتری در ورود، اعمال مجوزها روی صفحات /nojs/admin وام. تست: backend/iam/tests/TotpTests.cs.

==== زیرساخت عملیاتی (ماژول platform، مرحله ۸) و devops/ ====
- لاگ ساختاریافته‌ی JSON (Serilog) با شناسه‌ی پیگیری X-Request-Id، ماسک کد ملی/موبایل/کارت/توکن/رمز، نگهداری ۳۰ روز. خطای سراسری: پیام کلی + شناسه به کاربر، جزئیات فقط در لاگ.
- صف کار پایدار در دیتابیس (BackgroundJobs): تلاش مجدد با فاصله‌ی افزایشی (۱۵ث تا ۱ ساعت)، کار «مرده» پس از ۶ تلاش، رفع گیرکردن بعد از ری‌استارت، جلوگیری از تکرار با DedupKey. اولین Handler: sms.send. صفحه‌ی /nojs/admin/jobs و api/v1/admin/jobs.
- هنوز نیست: یادآور خودکار اقساط (نیازمند مدل اقساط واقعی)، چند نمونه‌ی همزمان سرور برای صف (الان یک نمونه فرض شده)، Sentry (اختیاری، در پیام نصب).
- devops/ci.yml (ساخت+تست+بررسی راز)، deploy-safe.sh (بکاپ، health check، برگشت خودکار، staging)، offsite-backup.sh (rclone رمزنگاری‌شده + اعتبارسنجی)، nginx.conf.sample (rate limit)، ghestine.service.hardening.conf.
- نکته: خروجی این بخش‌ها روی سرور شما تست نشده؛ deploy-safe.sh را اول روی staging امتحان کنید.

==== پشتیبانی و تیکت (ماژول support، مرحله ۹) ====
- مشتری: /nojs/me/tickets (ساخت تیکت، گفتگو، پاسخ؛ بازشدن مجدد تا ۷ روز بعد از بسته‌شدن). کارشناس: /nojs/admin/tickets با مجوز tickets.manage (فهرست، فیلتر «گذشته از مهلت»، پاسخ، یادداشت داخلی، بستن). API: api/v1/me/tickets و api/v1/admin/tickets.
- SLA اولین پاسخ: عادی ۲۴ ساعت، فوری ۴ ساعت (اولویت فوری فقط برای کارشناس؛ مشتری نمی‌تواند خودش فوری کند). یادداشت داخلی هرگز به مشتری نشان داده نمی‌شود.
- امنیت: متن ساده و HtmlEncode در خروجی، حذف نویسه‌های کنترلی، محدودیت نرخ (۵ تیکت و ۲۰ پیام در ساعت برای هر کاربر)، دسترسی مشتری فقط به تیکت‌های خود، CSRF روی همه‌ی فرم‌ها.
- هنوز نیست: پیوست فایل، اعلان پیامکی/ایمیلی پاسخ (با صف کار قابل اتصال است)، ارجاع به کارشناس دیگر، رضایت‌سنجی، اتصال تیکت به وام/قسط مشخص. تست: backend/support/tests/SupportTests.cs.

==== اعلان‌ها و داشبورد (ماژول notify، مرحله ۹ از ۱۱) ====
- مشتری: /nojs/me/inbox (اعلان‌های خوانده‌نشده با تأکید، «مشاهده» همزمان خوانده‌شدن را ثبت می‌کند، علامت‌گذاری همه). API: api/v1/me/notifications، /count، /{id}/read، /read-all.
- اعلان‌ها فعلاً از دو رویداد ساخته می‌شوند: ارائه‌ی قرارداد به مشتری (یک خط به ContractControllers اضافه می‌شود؛ نسخه‌ی قبلی در پوشه‌ی بکاپ نصب) و پاسخ پشتیبان به تیکت. لینک اعلان فقط مسیر داخلی است (تست واحد دارد).
- داشبورد مدیر: /nojs/admin/dashboard و api/v1/admin/dashboard. گروه‌ها: قراردادها، مدارک، پشتیبانی (میانگین زمان پاسخ اول)، سامانه (صف کار). هر گروه فقط با مجوز مربوط دیده می‌شود. ترتیب نصب: notify قبل از support و nojs.
- هنوز نیست: شاخص‌های مالی (وام‌های فعال، اقساط معوق، مانده‌ی سررسید) چون به مدل وام و قسط واقعی وابسته است؛ اعلان پیامکی/ایمیلی؛ نمایش شمار خوانده‌نشده در منوی بالا.

==== دفتر کل و حسابرسی بدون JS + اصلاح مهم حسابرسی ====
- /nojs/admin/ledger (مجوز ledger.view/ledger.post): تراز آزمایشی با هشدار نامتعادل، آخرین اسناد، سند معکوس، حساب جدید، سند جدید ۶ سطری. ثبت از همان LedgerController (اعتبارسنجی دوطرفه و شماره‌گذاری یکسان).
- /nojs/admin/audit (مجوز audit.view): جست‌وجو در مسیر/کاربر/IP و «بررسی زنجیره» (فقط SuperAdmin).
- اصلاح: فیلتر حسابرسی قبلاً فقط api/v1/admin را ثبت می‌کرد و کارهای ادمین در /nojs/admin ثبت نمی‌شد. حالا هر دو مسیر ثبت می‌شود (EntControllers.cs به‌روز شد؛ اگر ماژول enterprise را قبلاً نصب کرده‌اید، دوباره install-all یا فقط install ماژول enterprise را اجرا کنید).
- هنوز نیست: ثبت خودکار سند از اقساط/واریز (نیازمند مدل وام و قسط واقعی)، دوره‌ی مالی و بستن دوره، گزارش سود و زیان و ترازنامه.


==== تغییر معماری (مهم) ====
«nojs/is.Next» یعنی Next.js. سوءتفاهم‌های قبلی: لایه‌ی بدون-JS روی ASP.NET (بایگانی: docs/deprecated/nojs-aspnet-layer) و فرانت Node.js ساده (بایگانی: docs/deprecated/web-node-frontend).
پشته‌ی نهایی: بک‌اند ASP.NET Core 9 (فقط API) + فرانت‌اند Next.js 15 (web-next/) + ابزارهای Python (setup-web.py، web-next/tools/e2e_smoke.py).
نصب فرانت: sudo bash web-next/install-web.sh   (npm install + next build + سرویس digitalpay-web روی 127.0.0.1:3000؛ nginx را طبق web-next/nginx.snippet تنظیم کنید)
آزمون بدون نصب Next: cd web-next && npm i && npm test   ·   پیش‌نمایش ایستا: npm run preview
هشدار صادقانه: next build/tsc و کامپایل C# هرگز در محیط ساخت این بسته اجرا نشده‌اند؛ اولین اجرا روی سرور شما ممکن است خطای تایپ/کامپایل کوچک نشان دهد.
مسیرها و شکل پاسخ‌ها با کنترلرهای همین بسته (security, contracts, notify, support, ops, core, enterprise, platform, iam) تطبیق داده شده‌اند. هنوز فرض‌شده/ناقص: ثبت درخواست وام توسط مشتری (کد LoanApplication در بسته نیست)، نمایش نام مشتری در فهرست قراردادها (API فقط UserId می‌دهد).
