/* DigitalPay — اسکریپت ساخت جدول‌های ماژول‌های جدید (SQL Server)
   تولیدشده از کلاس‌های موجودیت همین بسته. مرجع/راه‌انداز است؛ مسیر اصلی و ایمن برای دیتابیس موجود
   همان مایگریشن EF Core است (dotnet ef migrations add ...). این اسکریپت جدول‌های قدیمی پروژه (کاربران، وام‌ها، اقساط، ...)
   را شامل نمی‌شود چون ساختارشان در دسترس من نبود. فقط روی دیتابیس خالی یا تست اجرا شود، نه روی دیتابیس زنده بدون بکاپ.
   اگر جدول‌ها قبلاً با مایگریشن ساخته شده‌اند، این اسکریپت را اجرا نکنید. */
SET NOCOUNT ON;
GO
CREATE TABLE [dbo].[Tenants] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_Tenants] PRIMARY KEY,
    [Name] nvarchar(120) NOT NULL DEFAULT N'دیجی‌بایل پی',
    [Slug] nvarchar(40) NOT NULL DEFAULT N'default',
    [BrandJson] nvarchar(max) NOT NULL DEFAULT N'{}',
    [IsDefault] bit NOT NULL,
    [IsActive] bit NOT NULL DEFAULT 1,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[TenantDomains] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_TenantDomains] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Host] nvarchar(253) NOT NULL DEFAULT N'',
    [IsPrimary] bit NOT NULL,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[LoanProducts] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_LoanProducts] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Name] nvarchar(120) NOT NULL DEFAULT N'',
    [Slug] nvarchar(40) NOT NULL DEFAULT N'',
    [Description] nvarchar(500) NOT NULL DEFAULT N'',
    [Badge] nvarchar(40) NOT NULL DEFAULT N'',
    [MinAmount] decimal(18,2) NOT NULL,
    [MaxAmount] decimal(18,2) NOT NULL,
    [IntervalDays] int NOT NULL DEFAULT 30,
    [TiersJson] nvarchar(max) NOT NULL DEFAULT N'[]',
    [ConditionsJson] nvarchar(max) NOT NULL DEFAULT N'{}',
    [DocumentsJson] nvarchar(max) NOT NULL DEFAULT N'[]',
    [IsActive] bit NOT NULL DEFAULT 1,
    [SortOrder] int NOT NULL,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
    [InterestMethod] nvarchar(12) NOT NULL DEFAULT N'Monthly',
    [InterestPercent] decimal(18,6) NOT NULL,
    [LateDailyCoef] decimal(18,8) NOT NULL,
    [EarlyDailyCoef] decimal(18,8) NOT NULL,
    [ShowInList] bit NOT NULL DEFAULT 1,
    [SendReminders] bit NOT NULL DEFAULT 1,
    [Title] nvarchar(160) NOT NULL DEFAULT N'',
    [ImageUrl] nvarchar(400) NOT NULL DEFAULT N'',
    [LabelsJson] nvarchar(max) NOT NULL DEFAULT N'[]',
    [FullDescriptionHtml] nvarchar(max) NOT NULL DEFAULT N'',
    [OperationalCostsJson] nvarchar(max) NOT NULL DEFAULT N'[]'
);

GO
CREATE TABLE [dbo].[VirtualCards] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_VirtualCards] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [LoanId] uniqueidentifier NOT NULL,
    [UserId] uniqueidentifier NOT NULL,
    [HolderName] nvarchar(120) NOT NULL DEFAULT N'',
    [Last4] nvarchar(8) NOT NULL DEFAULT N'',
    [Bin] nvarchar(8) NOT NULL DEFAULT N'9101',
    [PanHash] nvarchar(64) NOT NULL DEFAULT N'',
    [PanEnc] nvarchar(max) NOT NULL DEFAULT N'',
    [CvvEnc] nvarchar(max) NOT NULL DEFAULT N'',
    [ExpMonth] int NOT NULL,
    [ExpYear] int NOT NULL,
    [Limit] decimal(18,2) NOT NULL,
    [Spent] decimal(18,2) NOT NULL,
    [PerTxnLimit] decimal(18,2) NOT NULL,
    [Status] nvarchar(20) NOT NULL DEFAULT N'Active',
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[VirtualCardTxns] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_VirtualCardTxns] PRIMARY KEY,
    [CardId] uniqueidentifier NOT NULL,
    [Type] nvarchar(40) NOT NULL DEFAULT N'Charge',
    [Amount] decimal(18,2) NOT NULL,
    [Merchant] nvarchar(120) NOT NULL DEFAULT N'',
    [Reference] nvarchar(80) NOT NULL DEFAULT N'',
    [Note] nvarchar(200) NOT NULL DEFAULT N'',
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[CustomerDocuments] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_CustomerDocuments] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [UserId] uniqueidentifier NOT NULL,
    [LoanId] uniqueidentifier NULL,
    [Kind] nvarchar(80) NOT NULL DEFAULT N'',
    [FileName] nvarchar(200) NOT NULL DEFAULT N'',
    [ContentType] nvarchar(80) NOT NULL DEFAULT N'',
    [StoragePath] nvarchar(300) NOT NULL DEFAULT N'',
    [SizeBytes] bigint NOT NULL,
    [OcrText] nvarchar(max) NULL,
    [FieldsJson] nvarchar(max) NULL,
    [Status] nvarchar(20) NOT NULL DEFAULT N'Pending',
    [ReviewNote] nvarchar(300) NULL,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[OtpChallenges] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_OtpChallenges] PRIMARY KEY,
    [Phone] nvarchar(15) NOT NULL DEFAULT N'',
    [CodeHash] nvarchar(80) NOT NULL DEFAULT N'',
    [Purpose] nvarchar(12) NOT NULL DEFAULT N'login',
    [Ip] nvarchar(45) NOT NULL DEFAULT N'',
    [CreatedAt] datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
    [ExpiresAt] datetime2 NOT NULL,
    [ResendAt] datetime2 NOT NULL,
    [Attempts] int NOT NULL,
    [ConsumedAt] datetime2 NULL,
    [SendStatus] nvarchar(20) NOT NULL DEFAULT N'Pending',
    [SendInfo] nvarchar(200) NULL
);

GO
CREATE TABLE [dbo].[PaymentDeclarations] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_PaymentDeclarations] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [UserId] uniqueidentifier NOT NULL,
    [LoanId] uniqueidentifier NULL,
    [Amount] decimal(18,2) NOT NULL,
    [Method] nvarchar(30) NOT NULL DEFAULT N'CardToCard',
    [Reference] nvarchar(60) NOT NULL DEFAULT N'',
    [PaidAt] datetime2 NOT NULL,
    [Note] nvarchar(300) NOT NULL DEFAULT N'',
    [Status] nvarchar(20) NOT NULL DEFAULT N'Pending',
    [ReviewNote] nvarchar(300) NULL,
    [ReviewedBy] uniqueidentifier NULL,
    [ReviewedAt] datetime2 NULL,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[CounterParties] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_CounterParties] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Name] nvarchar(120) NOT NULL DEFAULT N'',
    [Iban] nvarchar(30) NOT NULL DEFAULT N'',
    [IsActive] bit NOT NULL DEFAULT 1,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[Marketers] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_Marketers] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Name] nvarchar(120) NOT NULL DEFAULT N'',
    [Phone] nvarchar(15) NOT NULL DEFAULT N'',
    [Code] nvarchar(20) NOT NULL DEFAULT N'',
    [CommissionPercent] decimal(18,2) NOT NULL,
    [IsActive] bit NOT NULL DEFAULT 1,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[AppSettings] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_AppSettings] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Key] nvarchar(60) NOT NULL DEFAULT N'',
    [Value] nvarchar(500) NOT NULL DEFAULT N''
);

GO
CREATE TABLE [dbo].[InquiryRequests] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_InquiryRequests] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [UserId] uniqueidentifier NOT NULL,
    [Type] nvarchar(40) NOT NULL DEFAULT N'Credit',
    [Status] nvarchar(20) NOT NULL DEFAULT N'Queued',
    [Result] nvarchar(300) NOT NULL DEFAULT N'',
    [Note] nvarchar(300) NOT NULL DEFAULT N'',
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
    [DoneAt] datetime2 NULL
);

GO
CREATE TABLE [dbo].[PurchaseOrders] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_PurchaseOrders] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [UserId] uniqueidentifier NOT NULL,
    [LoanId] uniqueidentifier NULL,
    [Code] nvarchar(20) NOT NULL DEFAULT N'',
    [MerchantName] nvarchar(120) NOT NULL DEFAULT N'',
    [Amount] decimal(18,2) NOT NULL,
    [Status] nvarchar(20) NOT NULL DEFAULT N'Pending',
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[AuditEntries] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_AuditEntries] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Seq] bigint NOT NULL,
    [UserId] uniqueidentifier NULL,
    [UserName] nvarchar(120) NOT NULL DEFAULT N'',
    [Method] nvarchar(10) NOT NULL DEFAULT N'',
    [Path] nvarchar(300) NOT NULL DEFAULT N'',
    [StatusCode] int NOT NULL,
    [Ip] nvarchar(45) NOT NULL DEFAULT N'',
    [At] datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
    [PrevHash] nvarchar(64) NOT NULL DEFAULT N'',
    [Hash] nvarchar(64) NOT NULL DEFAULT N''
);

GO
CREATE TABLE [dbo].[LedgerAccounts] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_LedgerAccounts] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Code] nvarchar(20) NOT NULL DEFAULT N'',
    [Name] nvarchar(120) NOT NULL DEFAULT N'',
    [Type] nvarchar(12) NOT NULL DEFAULT N'Asset',
    [IsActive] bit NOT NULL DEFAULT 1
);

GO
CREATE TABLE [dbo].[JournalEntries] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_JournalEntries] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Number] bigint NOT NULL,
    [Memo] nvarchar(300) NOT NULL DEFAULT N'',
    [Reference] nvarchar(60) NOT NULL DEFAULT N'',
    [ReversalOf] uniqueidentifier NULL,
    [CreatedBy] uniqueidentifier NULL,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);

GO
CREATE TABLE [dbo].[JournalLines] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_JournalLines] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [EntryId] uniqueidentifier NOT NULL,
    [AccountId] uniqueidentifier NOT NULL,
    [Debit] decimal(18,2) NOT NULL,
    [Credit] decimal(18,2) NOT NULL
);

GO
CREATE TABLE [dbo].[ContractTemplates] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_ContractTemplates] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [GroupKey] uniqueidentifier NOT NULL,
    [Version] int NOT NULL DEFAULT 1,
    [Title] nvarchar(160) NOT NULL DEFAULT N'',
    [Type] nvarchar(20) NOT NULL DEFAULT N'Company',
    [IssuerParty] nvarchar(160) NOT NULL DEFAULT N'',
    [PartiesJson] nvarchar(1000) NOT NULL DEFAULT N'[]',
    [Description] nvarchar(600) NOT NULL DEFAULT N'',
    [UsageConditions] nvarchar(600) NOT NULL DEFAULT N'',
    [CounterPartyId] uniqueidentifier NULL,
    [Restricted] bit NOT NULL,
    [HeaderHtml] nvarchar(max) NOT NULL DEFAULT N'',
    [BodyHtml] nvarchar(max) NOT NULL DEFAULT N'',
    [FooterHtml] nvarchar(max) NOT NULL DEFAULT N'',
    [SampleFileName] nvarchar(200) NOT NULL DEFAULT N'',
    [SamplePath] nvarchar(300) NOT NULL DEFAULT N'',
    [Status] nvarchar(20) NOT NULL DEFAULT N'Draft',
    [ChangeNote] nvarchar(300) NOT NULL DEFAULT N'',
    [ValidFrom] datetime2 NULL,
    [ValidTo] datetime2 NULL,
    [CreatedBy] uniqueidentifier NULL,
    [ApprovedBy] uniqueidentifier NULL,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
    [ApprovedAt] datetime2 NULL,
    [PublishedAt] datetime2 NULL
);

GO
CREATE TABLE [dbo].[ContractVariableDefs] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_ContractVariableDefs] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [Key] nvarchar(60) NOT NULL DEFAULT N'',
    [Label] nvarchar(120) NOT NULL DEFAULT N'',
    [DataType] nvarchar(12) NOT NULL DEFAULT N'text',
    [Source] nvarchar(12) NOT NULL DEFAULT N'system',
    [Path] nvarchar(60) NOT NULL DEFAULT N'',
    [Required] bit NOT NULL,
    [Format] nvarchar(40) NOT NULL DEFAULT N'',
    [Sensitivity] nvarchar(12) NOT NULL DEFAULT N'Normal',
    [DefaultValue] nvarchar(300) NOT NULL DEFAULT N'',
    [Validation] nvarchar(200) NOT NULL DEFAULT N''
);

GO
CREATE TABLE [dbo].[ProductContracts] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_ProductContracts] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [ProductId] uniqueidentifier NOT NULL,
    [GroupKey] uniqueidentifier NOT NULL,
    [Stage] nvarchar(20) NOT NULL DEFAULT N'Approval',
    [Required] bit NOT NULL DEFAULT 1,
    [Condition] nvarchar(300) NOT NULL DEFAULT N'',
    [RequiresReview] bit NOT NULL DEFAULT 1,
    [SortOrder] int NOT NULL
);

GO
CREATE TABLE [dbo].[GeneratedContracts] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_GeneratedContracts] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [UserId] uniqueidentifier NOT NULL,
    [ProductId] uniqueidentifier NOT NULL,
    [LoanId] uniqueidentifier NULL,
    [TemplateId] uniqueidentifier NOT NULL,
    [GroupKey] uniqueidentifier NOT NULL,
    [TemplateVersion] int NOT NULL,
    [Number] nvarchar(30) NOT NULL DEFAULT N'',
    [Title] nvarchar(160) NOT NULL DEFAULT N'',
    [Stage] nvarchar(20) NOT NULL DEFAULT N'Approval',
    [Status] nvarchar(20) NOT NULL DEFAULT N'Draft',
    [RequiresReview] bit NOT NULL DEFAULT 1,
    [Html] nvarchar(max) NOT NULL DEFAULT N'',
    [BodyHash] nvarchar(64) NOT NULL DEFAULT N'',
    [ValuesJson] nvarchar(max) NOT NULL DEFAULT N'{}',
    [PreviousId] uniqueidentifier NULL,
    [CreatedBy] uniqueidentifier NULL,
    [CreatedOn] datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
    [ReviewedBy] uniqueidentifier NULL,
    [ReviewedAt] datetime2 NULL,
    [PresentedAt] datetime2 NULL,
    [ExpiresAt] datetime2 NULL,
    [SignedAt] datetime2 NULL,
    [SignedIp] nvarchar(45) NOT NULL DEFAULT N'',
    [SignedUa] nvarchar(200) NOT NULL DEFAULT N'',
    [SignatureMethod] nvarchar(30) NOT NULL DEFAULT N''
);

GO
CREATE TABLE [dbo].[ContractEvents] (
    [Id] uniqueidentifier NOT NULL CONSTRAINT [PK_ContractEvents] PRIMARY KEY,
    [TenantId] uniqueidentifier NOT NULL,
    [ContractId] uniqueidentifier NOT NULL,
    [At] datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
    [ActorId] uniqueidentifier NULL,
    [Action] nvarchar(30) NOT NULL DEFAULT N'',
    [Note] nvarchar(300) NOT NULL DEFAULT N'',
    [Ip] nvarchar(45) NOT NULL DEFAULT N''
);
GO

/* ایندکس‌های پیشنهادی */
CREATE UNIQUE INDEX [UX_Tenants_Slug] ON [dbo].[Tenants]([Slug]);
CREATE UNIQUE INDEX [UX_TenantDomains_Host] ON [dbo].[TenantDomains]([Host]);
CREATE UNIQUE INDEX [UX_LoanProducts_Tenant_Slug] ON [dbo].[LoanProducts]([TenantId],[Slug]);
CREATE INDEX [IX_CustomerDocuments_User] ON [dbo].[CustomerDocuments]([TenantId],[UserId]);
CREATE UNIQUE INDEX [UX_ContractVariableDefs_Tenant_Key] ON [dbo].[ContractVariableDefs]([TenantId],[Key]);
CREATE UNIQUE INDEX [UX_ContractTemplates_Group_Version] ON [dbo].[ContractTemplates]([GroupKey],[Version]);
CREATE UNIQUE INDEX [UX_GeneratedContracts_Tenant_Number] ON [dbo].[GeneratedContracts]([TenantId],[Number]);
CREATE UNIQUE INDEX [UX_JournalEntries_Tenant_Number] ON [dbo].[JournalEntries]([TenantId],[Number]);
CREATE UNIQUE INDEX [UX_AuditEntries_Tenant_Seq] ON [dbo].[AuditEntries]([TenantId],[Seq]);
CREATE INDEX [IX_ContractEvents_Contract] ON [dbo].[ContractEvents]([ContractId],[At]);
GO
