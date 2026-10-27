using System.Globalization;
using System.Net;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Ganss.Xss;
using Ghestine.Domain.Entities;
using Ghestine.API.Tenancy;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using __DBNS__;
namespace Ghestine.API.Contracts;

static class CtU
{
    public static Guid? Uid(this ControllerBase c) => Guid.TryParse(c.User.FindFirstValue(ClaimTypes.NameIdentifier) ?? c.User.FindFirstValue("sub"), out var g) ? g : null;
    public static bool IsSuper(this ControllerBase c) => c.User.IsInRole("SuperAdmin");
    public static string Ip(this ControllerBase c)
    {
        var ra = c.HttpContext.Connection.RemoteIpAddress; var s = ra?.ToString() ?? "";
        if (ra != null && IPAddress.IsLoopback(ra)) { var h = c.Request.Headers["X-Real-IP"].ToString(); if (IPAddress.TryParse(h, out var p)) s = p.ToString(); }
        return s.Length > 45 ? s[..45] : s;
    }
    public static string Cut(this string? s, int n) { s ??= ""; return s.Length <= n ? s : s[..n]; }
    public static string Sha(string s) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(s))).ToLowerInvariant();

    static readonly HtmlSanitizer San = Make();
    static HtmlSanitizer Make()
    {
        var s = new HtmlSanitizer(); s.AllowedTags.Clear(); s.AllowedAttributes.Clear(); s.AllowedCssProperties.Clear(); s.AllowedSchemes.Clear(); s.AllowedClasses.Clear();
        foreach (var t in "p div span h1 h2 h3 h4 b strong i em u br hr ul ol li table thead tbody tfoot tr th td img blockquote sub sup small".Split(' ')) s.AllowedTags.Add(t);
        foreach (var a in "class style dir align colspan rowspan src alt width height".Split(' ')) s.AllowedAttributes.Add(a);
        foreach (var c in "text-align font-size font-weight font-style text-decoration color background-color direction line-height margin margin-top margin-bottom margin-right margin-left padding padding-top padding-bottom padding-right padding-left border border-top border-bottom border-right border-left border-collapse width height min-height page-break-before page-break-after page-break-inside".Split(' ')) s.AllowedCssProperties.Add(c);
        s.AllowedSchemes.Add("data"); s.AllowDataAttributes = false;
        foreach (var c in "sig sig-line stamp clause fixed var-clause center right left small-note".Split(' ')) s.AllowedClasses.Add(c);
        return s;
    }
    static readonly Regex BadSrc = new(@"\ssrc\s*=\s*""(?!data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]{1,400000}"")[^""]*""", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    /// پاک‌سازی HTML قالب با فهرست مجاز. توکن‌های {{...}} متن عادی‌اند و دست‌نخورده می‌مانند.
    public static string Clean(string? html) => BadSrc.Replace(San.Sanitize(html ?? ""), "");
}

/// ساخت مقدارهای متغیرها از منابع معتبر: پرونده‌ی کاربر، مدارک تأییدشده، طرح و محاسبه‌ی سرور، مستأجر/تأمین‌کننده و سیستم.
public class ContractContext
{
    public Dictionary<string, object?> Raw = new(); public List<Installment> Table = new(); public Dictionary<string, VarDef> Defs = new();
    public object? Get(string key)
    {
        if (!Defs.TryGetValue(key, out var d)) return null;
        if (d.Source == "custom") return string.IsNullOrEmpty(d.DefaultValue) ? null : d.DefaultValue;
        var v = Raw.TryGetValue(d.Source + ":" + d.Path, out var x) ? x : null;
        if (v is string s && d.Validation.Length > 0) { try { if (!Regex.IsMatch(s, d.Validation, RegexOptions.None, TimeSpan.FromMilliseconds(50))) return null; } catch { return null; } }
        return v;
    }
}

public static class ContractSeed
{
    static VarDef V(string k, string l, string t, string s, string p, bool req = false, string f = "", string sens = "Normal") => new(k, l, t, s, p, req, f, sens, "", "");
    public static readonly VarDef[] Defaults =
    {
        V("applicant_name","نام و نام خانوادگی متقاضی","text","applicant","FullName",true),
        V("applicant_national_code","کد ملی متقاضی","text","applicant","NationalCode",true,"","Sensitive"),
        V("applicant_phone","شماره تماس متقاضی","text","applicant","PhoneNumber"),
        V("applicant_email","ایمیل متقاضی","text","applicant","Email"),
        V("applicant_father_name","نام پدر (از مدرک تأییدشده)","text","document","fatherName"),
        V("applicant_birth_date","تاریخ تولد (از مدرک تأییدشده)","text","document","birthDate"),
        V("product_name","نام طرح وام","text","loan","product_name",true),
        V("loan_amount","مبلغ وام","money","loan","amount",true,"تومان"),
        V("loan_down_payment","مبلغ پیش‌پرداخت","money","loan","down_payment",false,"تومان"),
        V("loan_fee_percent","درصد کارمزد","number","loan","fee_percent",false,"درصد"),
        V("loan_months","تعداد اقساط","number","loan","months",true),
        V("loan_interest_percent","درصد بهره","number","loan","interest_percent",false,"درصد"),
        V("loan_late_coef","ضریب دیرکرد روزانه","number","loan","late_coef"),
        V("loan_early_coef","ضریب زودکرد روزانه","number","loan","early_coef"),
        V("loan_installment_amount","مبلغ هر قسط","money","loan","installment_amount",true,"تومان"),
        V("loan_total_fees","مجموع کارمزد","money","loan","total_fees",false,"تومان"),
        V("loan_total_repay","مبلغ کل بازپرداخت","money","loan","total_repay",true,"تومان"),
        V("loan_first_due","تاریخ اولین سررسید","date","loan","first_due",true),
        V("loan_interval_days","فاصله‌ی اقساط (روز)","number","loan","interval_days"),
        V("company_name","نام شرکت","text","party","company_name",true),
        V("company_phone","تلفن شرکت","text","party","company_phone"),
        V("company_address","نشانی شرکت","text","party","company_address"),
        V("supplier_name","نام تأمین‌کننده/بانک","text","party","supplier_name"),
        V("supplier_iban","شبای تأمین‌کننده","text","party","supplier_iban"),
        V("contract_number","شماره قرارداد","text","system","number",true),
        V("contract_date","تاریخ تولید قرارداد","date","system","created_date",true),
        V("contract_version","نسخه‌ی قالب","number","system","template_version"),
        V("request_id","شناسه‌ی درخواست","text","system","request_id"),
    };

    static readonly string[] UserProps = { "FullName", "NationalCode", "PhoneNumber", "Phone", "Email", "FirstName", "LastName" };

    public static async Task<Dictionary<string, VarDef>> DefsAsync(AppDbContext db, Guid tid, CancellationToken ct)
    {
        var rows = await db.Set<ContractVariableDef>().Where(x => x.TenantId == tid).ToListAsync(ct);
        if (rows.Count == 0)
        {
            foreach (var d in Defaults) db.Add(new ContractVariableDef { TenantId = tid, Key = d.Key, Label = d.Label, DataType = d.DataType, Source = d.Source, Path = d.Path, Required = d.Required, Format = d.Format, Sensitivity = d.Sensitivity });
            await db.SaveChangesAsync(ct); rows = await db.Set<ContractVariableDef>().Where(x => x.TenantId == tid).ToListAsync(ct);
        }
        return rows.ToDictionary(r => r.Key, r => new VarDef(r.Key, r.Label, r.DataType, r.Source, r.Path, r.Required, r.Format, r.Sensitivity, r.DefaultValue, r.Validation));
    }

    public record LoanReq(Guid UserId, Guid ProductId, decimal Amount, int Months, Guid? LoanId);
    /// null یعنی درخواست نامعتبر؛ پیام خطا در err.
    public static async Task<ContractContext?> BuildAsync(AppDbContext db, Guid tid, LoanReq r, Guid? counterPartyId, string number, int templateVersion, Dictionary<string, VarDef> defs, Action<string> err, CancellationToken ct)
    {
        var c = new ContractContext { Defs = defs };
        var p = await db.Set<LoanProduct>().FirstOrDefaultAsync(x => x.Id == r.ProductId && x.TenantId == tid, ct); if (p == null) { err("طرح وام پیدا نشد"); return null; }
        if (r.Amount < p.MinAmount || r.Amount > p.MaxAmount) { err("مبلغ خارج از بازه‌ی طرح است"); return null; }
        JsonElement? tier = null;
        try { foreach (var t in JsonDocument.Parse(p.TiersJson).RootElement.EnumerateArray()) if (t.GetProperty("months").GetInt32() == r.Months) tier = t.Clone(); } catch { }
        if (tier == null) { err("تعداد اقساط برای این طرح مجاز نیست"); return null; }
        var fee = tier.Value.TryGetProperty("feePercent", out var f) ? f.GetDecimal() : 0; var dp = tier.Value.TryGetProperty("downPaymentPercent", out var d) ? d.GetDecimal() : 0;
        var start = DateTime.UtcNow.Date; var (down, feeAmt, total, rows) = ContractEngine.Calc(r.Amount, dp, fee, r.Months, p.IntervalDays, start);
        c.Table = rows;
        c.Raw["loan:product_name"] = p.Name; c.Raw["loan:amount"] = r.Amount; c.Raw["loan:down_payment"] = down; c.Raw["loan:fee_percent"] = fee; c.Raw["loan:months"] = r.Months;
        c.Raw["loan:installment_amount"] = rows[0].Amount; c.Raw["loan:total_fees"] = feeAmt; c.Raw["loan:total_repay"] = total + down; c.Raw["loan:first_due"] = rows[0].Due; c.Raw["loan:interval_days"] = p.IntervalDays; c.Raw["loan:interest_percent"] = p.InterestPercent; c.Raw["loan:late_coef"] = p.LateDailyCoef; c.Raw["loan:early_coef"] = p.EarlyDailyCoef;
        // متقاضی: فقط از موجودیت کاربر و فقط فیلدهای مجاز (هرگز رمز/توکن)
        var ut = db.Model.GetEntityTypes().FirstOrDefault(e => e.ClrType.GetProperty("PasswordHash") != null || e.ClrType.GetProperty("NormalizedUserName") != null)?.ClrType;
        if (ut != null)
        {
            var u = await db.FindAsync(ut, new object[] { r.UserId }, ct);
            if (u == null) { err("کاربر پیدا نشد"); return null; }
            foreach (var n in UserProps) { var pr = ut.GetProperty(n); if (pr != null) c.Raw["applicant:" + n] = pr.GetValue(u)?.ToString(); }
            if (!c.Raw.ContainsKey("applicant:FullName") || c.Raw["applicant:FullName"] == null) { var fn = c.Raw.GetValueOrDefault("applicant:FirstName") + " " + c.Raw.GetValueOrDefault("applicant:LastName"); c.Raw["applicant:FullName"] = fn.Trim(); }
        }
        // مدارک تأییدشده (آخرین مورد هر نوع)
        var docs = await db.Set<CustomerDocument>().Where(x => x.TenantId == tid && x.UserId == r.UserId && x.Status == "Verified").OrderBy(x => x.CreatedOn).ToListAsync(ct);
        foreach (var doc in docs) try
            {
                if (string.IsNullOrEmpty(doc.FieldsJson)) continue; var root = JsonDocument.Parse(doc.FieldsJson).RootElement; var fl = root.TryGetProperty("fields", out var ff) ? ff : root;
                foreach (var pr in fl.EnumerateObject()) if (pr.Value.ValueKind == JsonValueKind.String) { c.Raw["document:" + pr.Name] = pr.Value.GetString(); if (pr.Name == "fullName" && !(c.Raw.GetValueOrDefault("applicant:FullName") is string s0 && s0.Length > 0)) c.Raw["applicant:FullName"] = pr.Value.GetString(); if (pr.Name == "nationalCode" && !(c.Raw.GetValueOrDefault("applicant:NationalCode") is string s1 && s1.Length > 0)) c.Raw["applicant:NationalCode"] = pr.Value.GetString(); }
            }
            catch { }
        // شرکت (مستأجر) و تأمین‌کننده
        var tn = await db.Set<Tenant>().FirstOrDefaultAsync(x => x.Id == tid, ct); string name = tn?.Name ?? "", phone = "", addr = "";
        try { var b = JsonDocument.Parse(tn?.BrandJson ?? "{}").RootElement; if (b.TryGetProperty("legalName", out var ln) && ln.ValueKind == JsonValueKind.String && ln.GetString()!.Length > 0) name = ln.GetString()!; if (b.TryGetProperty("phone", out var ph)) phone = ph.GetString() ?? ""; if (b.TryGetProperty("address", out var ad)) addr = ad.GetString() ?? ""; } catch { }
        c.Raw["party:company_name"] = name; c.Raw["party:company_phone"] = phone; c.Raw["party:company_address"] = addr;
        if (counterPartyId != null) { var cp = await db.Set<CounterParty>().FirstOrDefaultAsync(x => x.Id == counterPartyId && x.TenantId == tid, ct); if (cp != null) { c.Raw["party:supplier_name"] = cp.Name; c.Raw["party:supplier_iban"] = cp.Iban; } }
        c.Raw["system:number"] = number; c.Raw["system:created_date"] = DateTime.UtcNow; c.Raw["system:template_version"] = templateVersion; c.Raw["system:request_id"] = (r.LoanId ?? r.UserId).ToString("N")[..10];
        return c;
    }

    /// نمونه‌ی ثابت برای پیش‌نمایش ادیتور (بدون هیچ داده‌ی واقعی).
    public static ContractContext Sample(Dictionary<string, VarDef> defs)
    {
        var c = new ContractContext { Defs = defs }; var (_, _, _, rows) = ContractEngine.Calc(12_000_000, 10, 6, 4, 30, DateTime.UtcNow.Date); c.Table = rows;
        var s = new Dictionary<string, object?> { ["applicant:FullName"] = "علی رضایی", ["applicant:NationalCode"] = "0499370899", ["applicant:PhoneNumber"] = "09120000000", ["applicant:Email"] = "sample@example.com", ["document:fatherName"] = "محمد", ["document:birthDate"] = "1370/01/01", ["loan:product_name"] = "اقساط ۴ ماهه", ["loan:amount"] = 12_000_000m, ["loan:down_payment"] = 1_200_000m, ["loan:fee_percent"] = 6m, ["loan:months"] = 4, ["loan:installment_amount"] = rows[0].Amount, ["loan:total_fees"] = 648_000m, ["loan:total_repay"] = 12_648_000m, ["loan:first_due"] = rows[0].Due, ["loan:interval_days"] = 30, ["party:company_name"] = "شرکت نمونه", ["party:company_phone"] = "02100000000", ["party:company_address"] = "تهران، نشانی نمونه", ["party:supplier_name"] = "بانک نمونه", ["party:supplier_iban"] = "IR062960000000100324200001", ["system:number"] = "C-نمونه-00000", ["system:created_date"] = DateTime.UtcNow, ["system:template_version"] = 1, ["system:request_id"] = "SAMPLE0001" };
        foreach (var kv in s) c.Raw[kv.Key] = kv.Value; return c;
    }

    public static string Page(string title, string header, string body, string footer)
    {
        var css = "*{box-sizing:border-box}body{margin:0;font-family:Vazirmatn,Tahoma,'B Nazanin',serif;font-size:13.5px;line-height:2;color:#111;direction:rtl;background:#fff}table.pg{width:100%;border-collapse:collapse}table.pg>thead>tr>td,table.pg>tfoot>tr>td{padding:6px 0}table.pg>tbody>tr>td{padding:8px 0;vertical-align:top}h1,h2,h3{margin:.6em 0 .3em}table.inst{width:100%;border-collapse:collapse;margin:8px 0}table.inst th,table.inst td{border:1px solid #444;padding:4px 8px;text-align:center}.sig{display:inline-block;min-width:200px;margin:18px 12px;text-align:center;border-top:1px solid #333;padding-top:6px}.stamp{display:inline-block;width:110px;height:110px;border:1px dashed #888;border-radius:50%;text-align:center;line-height:110px;color:#888;margin:8px}@page{size:A4;margin:16mm 14mm;@bottom-center{content:counter(page)}}@media print{body{background:none}}";
        return "<!doctype html><html lang=\"fa\" dir=\"rtl\"><head><meta charset=\"utf-8\"><title>" + WebUtility.HtmlEncode(title) + "</title><style>" + css + "</style></head><body><table class=\"pg\"><thead><tr><td>" + header + "</td></tr></thead><tbody><tr><td>" + body + "</td></tr></tbody><tfoot><tr><td>" + footer + "</td></tr></tfoot></table></body></html>";
    }
}
