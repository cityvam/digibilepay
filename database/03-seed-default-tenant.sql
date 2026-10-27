/* مستأجر پیش‌فرض و دامنه‌ی اصلی. نام دامنه را با دامنه‌ی خودتان عوض کنید. فقط اگر خالی بود درج می‌کند. */
USE [DigitalPay];
IF NOT EXISTS (SELECT 1 FROM [dbo].[Tenants])
BEGIN
    DECLARE @t uniqueidentifier = NEWID();
    INSERT INTO [dbo].[Tenants]([Id],[Name],[Slug],[BrandJson],[IsDefault],[IsActive]) VALUES (@t, N'دیجی‌بایل پی', N'default', N'{"legalName":"","phone":"","address":""}', 1, 1);
    INSERT INTO [dbo].[TenantDomains]([Id],[TenantId],[Host],[IsPrimary]) VALUES (NEWID(), @t, N'ghestine.ir', 1);
END
GO
