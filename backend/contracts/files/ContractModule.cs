using System.ComponentModel.DataAnnotations;
using Ghestine.Domain.Common;
namespace Ghestine.Domain.Entities;

/// قالب قرارداد. هر «خانواده‌ی قالب» (GroupKey) چند نسخه دارد؛ نسخه‌ی منتشرشده تغییر نمی‌کند و ویرایش، نسخه‌ی جدید می‌سازد.
public class ContractTemplate : BaseEntity
{
    public Guid TenantId { get; set; }
    public Guid GroupKey { get; set; }
    public int Version { get; set; } = 1;
    [MaxLength(160)] public string Title { get; set; } = string.Empty;
    [MaxLength(20)] public string Type { get; set; } = "Company";       // Company | Bank | Financier | Guarantee | Other
    [MaxLength(160)] public string IssuerParty { get; set; } = string.Empty;
    [MaxLength(1000)] public string PartiesJson { get; set; } = "[]";   // ["شرکت","بانک",...]
    [MaxLength(600)] public string Description { get; set; } = string.Empty;
    [MaxLength(600)] public string UsageConditions { get; set; } = string.Empty;
    public Guid? CounterPartyId { get; set; }                           // تأمین‌کننده‌ی مرتبط
    public bool Restricted { get; set; }                                // قالب اختصاصی بانک/شریک: فقط سوپرادمین می‌بیند
    public string HeaderHtml { get; set; } = string.Empty;
    public string BodyHtml { get; set; } = string.Empty;
    public string FooterHtml { get; set; } = string.Empty;
    [MaxLength(200)] public string SampleFileName { get; set; } = string.Empty;
    [MaxLength(300)] public string SamplePath { get; set; } = string.Empty;
    [MaxLength(20)] public string Status { get; set; } = "Draft";       // Draft | Approved | Published | Archived
    [MaxLength(300)] public string ChangeNote { get; set; } = string.Empty;
    public DateTime? ValidFrom { get; set; }
    public DateTime? ValidTo { get; set; }
    public Guid? CreatedBy { get; set; }
    public Guid? ApprovedBy { get; set; }
    public DateTime CreatedOn { get; set; } = DateTime.UtcNow;
    public DateTime? ApprovedAt { get; set; }
    public DateTime? PublishedAt { get; set; }
}

/// تعریف متغیر قرارداد. منبع مقدار مشخص است و کاربر نمی‌تواند هنگام تولید، مقدار دلخواه بدهد.
public class ContractVariableDef : BaseEntity
{
    public Guid TenantId { get; set; }
    [MaxLength(60)] public string Key { get; set; } = string.Empty;
    [MaxLength(120)] public string Label { get; set; } = string.Empty;
    [MaxLength(12)] public string DataType { get; set; } = "text";      // text | number | money | date
    [MaxLength(12)] public string Source { get; set; } = "system";      // applicant | document | loan | party | system | custom
    [MaxLength(60)] public string Path { get; set; } = string.Empty;
    public bool Required { get; set; }
    [MaxLength(40)] public string Format { get; set; } = string.Empty;  // پسوند نمایش، مثل «تومان»
    [MaxLength(12)] public string Sensitivity { get; set; } = "Normal"; // Normal | Sensitive
    [MaxLength(300)] public string DefaultValue { get; set; } = string.Empty; // فقط برای منبع custom
    [MaxLength(200)] public string Validation { get; set; } = string.Empty;   // regex اختیاری روی مقدار متنی
}

/// قراردادهای لازم برای یک طرح وام، مرحله‌ی تولید و شرط انتخاب.
public class ProductContract : BaseEntity
{
    public Guid TenantId { get; set; }
    public Guid ProductId { get; set; }
    public Guid GroupKey { get; set; }
    [MaxLength(20)] public string Stage { get; set; } = "Approval";    // Application | Approval | Disbursement
    public bool Required { get; set; } = true;
    [MaxLength(300)] public string Condition { get; set; } = string.Empty; // مثل: loan_amount >= 50000000
    public bool RequiresReview { get; set; } = true;                   // نیاز به تأیید کارشناس پیش از ارائه
    public int SortOrder { get; set; }
}

/// قرارداد تولیدشده برای یک درخواست. متن نهایی (Html) و هش آن پس از تولید هرگز تغییر نمی‌کند.
public class GeneratedContract : BaseEntity
{
    public Guid TenantId { get; set; }
    public Guid UserId { get; set; }
    public Guid ProductId { get; set; }
    public Guid? LoanId { get; set; }
    public Guid TemplateId { get; set; }
    public Guid GroupKey { get; set; }
    public int TemplateVersion { get; set; }
    [MaxLength(30)] public string Number { get; set; } = string.Empty;
    [MaxLength(160)] public string Title { get; set; } = string.Empty;
    [MaxLength(20)] public string Stage { get; set; } = "Approval";
    [MaxLength(20)] public string Status { get; set; } = "Draft";
    public bool RequiresReview { get; set; } = true;
    public string Html { get; set; } = string.Empty;
    [MaxLength(64)] public string BodyHash { get; set; } = string.Empty;
    public string ValuesJson { get; set; } = "{}";                      // مقدارهای حساس ماسک می‌شوند
    public Guid? PreviousId { get; set; }
    public Guid? CreatedBy { get; set; }
    public DateTime CreatedOn { get; set; } = DateTime.UtcNow;
    public Guid? ReviewedBy { get; set; }
    public DateTime? ReviewedAt { get; set; }
    public DateTime? PresentedAt { get; set; }
    public DateTime? ExpiresAt { get; set; }
    public DateTime? SignedAt { get; set; }
    [MaxLength(45)] public string SignedIp { get; set; } = string.Empty;
    [MaxLength(200)] public string SignedUa { get; set; } = string.Empty;
    [MaxLength(30)] public string SignatureMethod { get; set; } = string.Empty; // SimpleAccept | (بعداً) Digital
}

public class ContractEvent : BaseEntity
{
    public Guid TenantId { get; set; }
    public Guid ContractId { get; set; }
    public DateTime At { get; set; } = DateTime.UtcNow;
    public Guid? ActorId { get; set; }
    [MaxLength(30)] public string Action { get; set; } = string.Empty;
    [MaxLength(300)] public string Note { get; set; } = string.Empty;
    [MaxLength(45)] public string Ip { get; set; } = string.Empty;
}
