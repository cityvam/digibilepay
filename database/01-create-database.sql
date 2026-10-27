/* DigitalPay — ساخت دیتابیس. روی دیتابیس موجود (Ghestine) اجرا نکنید؛ برای آن از مایگریشن EF استفاده کنید. */
IF DB_ID(N'DigitalPay') IS NULL
BEGIN
    CREATE DATABASE [DigitalPay] COLLATE Persian_100_CI_AS;  -- نیاز به SQL Server 2019+؛ در غیر این صورت Arabic_100_CI_AS
END
GO
