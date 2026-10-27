using System.Text.Json;
using Ghestine.Domain.Entities;
using Ghestine.API.Tenancy;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using __DBNS__;
namespace Ghestine.API.Contracts;

public record TemplateIn(string Title, string Type, string? IssuerParty, List<string>? Parties, string? Description, string? UsageConditions, Guid? CounterPartyId, bool Restricted, string? HeaderHtml, string? BodyHtml, string? FooterHtml, DateTime? ValidFrom, DateTime? ValidTo, string? ChangeNote);
public record VarIn(string Key, string Label, string DataType, string Source, string? Path, bool Required, string? Format, string? Sensitivity, string? DefaultValue, string? Validation);
public record LinkIn(Guid GroupKey, string Stage, bool Required, string? Condition, bool RequiresReview, int SortOrder);
public record GenIn(Guid UserId, Guid ProductId, decimal Amount, int Months, Guid? LoanId, string? Stage, bool DryRun, Guid? PreviousId);
public record NoteIn(string? Note);

/// قالب‌های قرارداد. مدیریت از داخل فرم تعریف وام (بخش «مدارک و قراردادها») انجام می‌شود.
[ApiController, Route("api/v1/admin/contract-templates"), Authorize(Roles = "Admin,SuperAdmin")]
public class ContractTemplatesController : ControllerBase
{
    private readonly AppDbContext _db; private readonly Ghestine.API.Core.ICardCrypto _c; private readonly IConfiguration _cfg;
    public ContractTemplatesController(AppDbContext db, Ghestine.API.Core.ICardCrypto c, IConfiguration cfg) { _db = db; _c = c; _cfg = cfg; }
    static readonly string[] Types = { "Company", "Bank", "Financier", "Guarantee", "Other" };
    IQueryable<ContractTemplate> Q() { var q = _db.Set<ContractTemplate>().Where(t => t.TenantId == this.Tid()); return this.IsSuper() ? q : q.Where(t => !t.Restricted); }
    object Row(ContractTemplate t) => new { t.Id, t.GroupKey, t.Version, t.Title, t.Type, t.IssuerParty, t.Status, t.Restricted, t.CounterPartyId, t.ValidFrom, t.ValidTo, t.CreatedOn, t.PublishedAt, hasSample = t.SampleFileName != "" };

    [HttpGet] public async Task<IActionResult> List(CancellationToken ct)
    { var all = await Q().OrderByDescending(t => t.Version).ToListAsync(ct); return Ok(all.OrderBy(t => t.Title).ThenByDescending(t => t.Version).Select(Row)); }
    [HttpGet("{id:guid}")] public async Task<IActionResult> One(Guid id, CancellationToken ct)
    { var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound(); return Ok(new { t.Id, t.GroupKey, t.Version, t.Title, t.Type, t.IssuerParty, parties = Parse(t.PartiesJson), t.Description, t.UsageConditions, t.CounterPartyId, t.Restricted, t.HeaderHtml, t.BodyHtml, t.FooterHtml, t.SampleFileName, t.Status, t.ChangeNote, t.ValidFrom, t.ValidTo, t.CreatedOn, t.ApprovedAt, t.PublishedAt }); }
    static List<string> Parse(string j) { try { return JsonSerializer.Deserialize<List<string>>(j) ?? new(); } catch { return new(); } }

    string? Fill(ContractTemplate t, TemplateIn i)
    {
        if (string.IsNullOrWhiteSpace(i.Title) || i.Title.Length > 160) return "عنوان قرارداد الزامی است";
        if (!Types.Contains(i.Type)) return "نوع قرارداد نامعتبر است";
        if (i.ValidFrom != null && i.ValidTo != null && i.ValidTo < i.ValidFrom) return "بازه‌ی اعتبار نامعتبر است";
        if (i.Restricted && !this.IsSuper()) return "فقط سوپرادمین می‌تواند قالب را «اختصاصی» کند";
        t.Title = i.Title.Trim(); t.Type = i.Type; t.IssuerParty = i.IssuerParty.Cut(160); t.PartiesJson = JsonSerializer.Serialize((i.Parties ?? new()).Take(10).Select(p => p.Cut(80))); t.Description = i.Description.Cut(600); t.UsageConditions = i.UsageConditions.Cut(600);
        t.CounterPartyId = i.CounterPartyId; t.Restricted = i.Restricted; t.HeaderHtml = CtU.Clean(i.HeaderHtml); t.BodyHtml = CtU.Clean(i.BodyHtml); t.FooterHtml = CtU.Clean(i.FooterHtml); t.ValidFrom = i.ValidFrom; t.ValidTo = i.ValidTo; t.ChangeNote = i.ChangeNote.Cut(300);
        return null;
    }
    [HttpPost] public async Task<IActionResult> Create(TemplateIn i, CancellationToken ct)
    {
        var t = new ContractTemplate { TenantId = this.Tid(), GroupKey = Guid.NewGuid(), Version = 1, CreatedBy = this.Uid() }; var e = Fill(t, i); if (e != null) return BadRequest(new { message = e });
        _db.Add(t); await _db.SaveChangesAsync(ct); return Ok(new { t.Id, t.GroupKey });
    }
    [HttpPut("{id:guid}")] public async Task<IActionResult> Update(Guid id, TemplateIn i, CancellationToken ct)
    {
        var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound();
        if (t.Status != "Draft") return Conflict(new { message = "فقط پیش‌نویس قابل ویرایش است. برای تغییر، نسخه‌ی جدید بسازید." });
        var e = Fill(t, i); if (e != null) return BadRequest(new { message = e }); await _db.SaveChangesAsync(ct); return Ok(new { problems = await Problems(t, ct) });
    }
    async Task<List<string>> Problems(ContractTemplate t, CancellationToken ct)
    {
        var defs = await ContractSeed.DefsAsync(_db, this.Tid(), ct); var p = new List<string>();
        foreach (var (name, html) in new[] { ("متن", t.BodyHtml), ("سربرگ", t.HeaderHtml), ("پابرگ", t.FooterHtml) }) p.AddRange(ContractEngine.Validate(html, defs).Select(x => name + ": " + x));
        if (string.IsNullOrWhiteSpace(System.Text.RegularExpressions.Regex.Replace(t.BodyHtml, "<[^>]*>", "")) ) p.Add("متن قرارداد خالی است");
        return p;
    }
    [HttpPost("{id:guid}/validate")] public async Task<IActionResult> Validate(Guid id, CancellationToken ct)
    { var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound(); return Ok(new { problems = await Problems(t, ct) }); }
    [HttpPost("{id:guid}/new-version")] public async Task<IActionResult> NewVersion(Guid id, CancellationToken ct)
    {
        var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound();
        if (await _db.Set<ContractTemplate>().AnyAsync(x => x.GroupKey == t.GroupKey && x.Status == "Draft", ct)) return Conflict(new { message = "برای این قرارداد پیش‌نویس باز وجود دارد" });
        var max = await _db.Set<ContractTemplate>().Where(x => x.GroupKey == t.GroupKey).MaxAsync(x => x.Version, ct);
        var n = new ContractTemplate { TenantId = t.TenantId, GroupKey = t.GroupKey, Version = max + 1, Title = t.Title, Type = t.Type, IssuerParty = t.IssuerParty, PartiesJson = t.PartiesJson, Description = t.Description, UsageConditions = t.UsageConditions, CounterPartyId = t.CounterPartyId, Restricted = t.Restricted, HeaderHtml = t.HeaderHtml, BodyHtml = t.BodyHtml, FooterHtml = t.FooterHtml, SampleFileName = t.SampleFileName, SamplePath = t.SamplePath, ValidFrom = t.ValidFrom, ValidTo = t.ValidTo, CreatedBy = this.Uid() };
        _db.Add(n); await _db.SaveChangesAsync(ct); return Ok(new { n.Id, n.Version });
    }
    /// تأیید: فقط اگر هیچ مشکلی در قالب نباشد؛ تأییدکننده باید با سازنده فرق داشته باشد (مگر سوپرادمین).
    [HttpPost("{id:guid}/approve")] public async Task<IActionResult> Approve(Guid id, CancellationToken ct)
    {
        var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound(); if (t.Status != "Draft") return Conflict(new { message = "فقط پیش‌نویس تأیید می‌شود" });
        var p = await Problems(t, ct); if (p.Count > 0) return UnprocessableEntity(new { message = "قالب مشکل دارد", problems = p });
        if (t.CreatedBy == this.Uid() && !this.IsSuper()) return StatusCode(403, new { message = "تأیید باید توسط فرد دیگری انجام شود" });
        t.Status = "Approved"; t.ApprovedBy = this.Uid(); t.ApprovedAt = DateTime.UtcNow; await _db.SaveChangesAsync(ct); return Ok();
    }
    [HttpPost("{id:guid}/publish")] public async Task<IActionResult> Publish(Guid id, CancellationToken ct)
    {
        var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound(); if (t.Status != "Approved") return Conflict(new { message = "ابتدا قالب باید تأیید شود" });
        foreach (var o in await _db.Set<ContractTemplate>().Where(x => x.GroupKey == t.GroupKey && x.Status == "Published").ToListAsync(ct)) o.Status = "Archived";
        t.Status = "Published"; t.PublishedAt = DateTime.UtcNow; await _db.SaveChangesAsync(ct); return Ok();
    }
    [HttpPost("{id:guid}/archive")] public async Task<IActionResult> Archive(Guid id, CancellationToken ct)
    { var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound(); if (t.Status == "Archived") return Ok(); t.Status = "Archived"; await _db.SaveChangesAsync(ct); return Ok(); }
    /// پیش‌نمایش با داده‌ی نمونه (هیچ داده‌ی واقعی استفاده نمی‌شود).
    [HttpPost("{id:guid}/preview")] public async Task<IActionResult> Preview(Guid id, CancellationToken ct)
    {
        var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound();
        var defs = await ContractSeed.DefsAsync(_db, this.Tid(), ct); var c = ContractSeed.Sample(defs);
        string R(string h, List<object> o) { var r = ContractEngine.Render(h, defs, c.Get, c.Table); o.AddRange(r.Errors); return r.Html; }
        var errs = new List<object>(); var body = R(t.BodyHtml, errs); var hd = R(t.HeaderHtml, errs); var ft = R(t.FooterHtml, errs);
        return Ok(new { html = ContractSeed.Page(t.Title, hd, body, ft), errors = errs });
    }
    [HttpPost("{id:guid}/sample"), RequestSizeLimit(6_000_000)] public async Task<IActionResult> UploadSample(Guid id, IFormFile file, CancellationToken ct)
    {
        var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null) return NotFound();
        if (file == null || file.Length == 0 || file.Length > 5_000_000) return BadRequest(new { message = "فایل حداکثر ۵ مگابایت" });
        var ext = Path.GetExtension(file.FileName).ToLowerInvariant(); if (ext is not (".pdf" or ".docx" or ".doc")) return BadRequest(new { message = "فقط PDF یا Word" });
        byte[] b; using (var ms = new MemoryStream()) { await file.CopyToAsync(ms, ct); b = ms.ToArray(); }
        var okSig = ext == ".pdf" ? b.Length > 4 && b[0] == 0x25 && b[1] == 0x50 && b[2] == 0x44 && b[3] == 0x46 : ext == ".docx" ? b.Length > 4 && b[0] == 0x50 && b[1] == 0x4B : b.Length > 4 && b[0] == 0xD0 && b[1] == 0xCF;
        if (!okSig) return BadRequest(new { message = "محتوای فایل با پسوند نمی‌خواند" });
        var dir = _cfg["Contracts:Path"] ?? "/home/ghestine/private-contracts"; Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, Guid.NewGuid().ToString("N") + ".bin"); await System.IO.File.WriteAllBytesAsync(path, _c.ProtectBytes(b), ct);
        t.SampleFileName = Path.GetFileName(file.FileName).Cut(200); t.SamplePath = path; await _db.SaveChangesAsync(ct); return Ok();
    }
    [HttpGet("{id:guid}/sample")] public async Task<IActionResult> Sample(Guid id, CancellationToken ct)
    {
        var t = await Q().FirstOrDefaultAsync(x => x.Id == id, ct); if (t == null || t.SamplePath == "" || !System.IO.File.Exists(t.SamplePath)) return NotFound();
        Response.Headers["X-Content-Type-Options"] = "nosniff"; Response.Headers.CacheControl = "private, no-store";
        var ext = Path.GetExtension(t.SampleFileName).ToLowerInvariant(); var ct2 = ext == ".pdf" ? "application/pdf" : "application/octet-stream";
        return File(_c.UnprotectBytes(await System.IO.File.ReadAllBytesAsync(t.SamplePath, ct)), ct2, "contract-sample" + ext);
    }
}

[ApiController, Route("api/v1/admin/contract-variables"), Authorize(Roles = "Admin,SuperAdmin")]
public class ContractVariablesController : ControllerBase
{
    private readonly AppDbContext _db; public ContractVariablesController(AppDbContext db) => _db = db;
    static readonly string[] Types = { "text", "number", "money", "date" }, Sources = { "applicant", "document", "loan", "party", "system", "custom" };
    [HttpGet] public async Task<IActionResult> List(CancellationToken ct) { await ContractSeed.DefsAsync(_db, this.Tid(), ct); return Ok(await _db.Set<ContractVariableDef>().Where(x => x.TenantId == this.Tid()).OrderBy(x => x.Key).ToListAsync(ct)); }
    /// متغیرهای پیش‌فرض جاافتاده (مثلاً بعد از به‌روزرسانی) را بدون دست‌زدن به متغیرهای موجود اضافه می‌کند.
    [HttpPost("sync-defaults")] public async Task<IActionResult> SyncDefaults(CancellationToken ct)
    {
        var have = (await _db.Set<ContractVariableDef>().Where(x => x.TenantId == this.Tid()).Select(x => x.Key).ToListAsync(ct)).ToHashSet(); var n = 0;
        foreach (var d in ContractSeed.Defaults.Where(d => !have.Contains(d.Key))) { _db.Add(new ContractVariableDef { TenantId = this.Tid(), Key = d.Key, Label = d.Label, DataType = d.DataType, Source = d.Source, Path = d.Path, Required = d.Required, Format = d.Format, Sensitivity = d.Sensitivity }); n++; }
        await _db.SaveChangesAsync(ct); return Ok(new { added = n });
    }
    string? Check(VarIn i)
    {
        if (!System.Text.RegularExpressions.Regex.IsMatch(i.Key ?? "", "^[a-z][a-z0-9_]{1,59}$")) return "شناسه باید حروف کوچک انگلیسی، عدد و _ باشد";
        if (string.IsNullOrWhiteSpace(i.Label)) return "نام نمایشی الزامی است"; if (!Types.Contains(i.DataType) || !Sources.Contains(i.Source)) return "نوع یا منبع نامعتبر است";
        if (i.Source == "custom" && string.IsNullOrWhiteSpace(i.DefaultValue)) return "منبع «ثابت» مقدار می‌خواهد"; if (i.Source != "custom" && string.IsNullOrWhiteSpace(i.Path)) return "مسیر منبع الزامی است";
        if (i.Source == "custom" && i.Sensitivity == "Sensitive") return "متغیر حساس نباید مقدار ثابت داشته باشد";
        if (!string.IsNullOrEmpty(i.Validation)) { try { System.Text.RegularExpressions.Regex.IsMatch("", i.Validation); } catch { return "regex اعتبارسنجی نامعتبر است"; } }
        return null;
    }
    void Fill(ContractVariableDef d, VarIn i) { d.Label = i.Label.Trim().Cut(120); d.DataType = i.DataType; d.Source = i.Source; d.Path = (i.Path ?? "").Trim().Cut(60); d.Required = i.Required; d.Format = i.Format.Cut(40); d.Sensitivity = i.Sensitivity == "Sensitive" ? "Sensitive" : "Normal"; d.DefaultValue = i.DefaultValue.Cut(300); d.Validation = i.Validation.Cut(200); }
    [HttpPost] public async Task<IActionResult> Create(VarIn i, CancellationToken ct)
    {
        var e = Check(i); if (e != null) return BadRequest(new { message = e }); if (await _db.Set<ContractVariableDef>().AnyAsync(x => x.TenantId == this.Tid() && x.Key == i.Key, ct)) return Conflict(new { message = "این شناسه قبلاً هست" });
        var d = new ContractVariableDef { TenantId = this.Tid(), Key = i.Key }; Fill(d, i); _db.Add(d); await _db.SaveChangesAsync(ct); return Ok();
    }
    [HttpPut("{id:guid}")] public async Task<IActionResult> Update(Guid id, VarIn i, CancellationToken ct)
    {
        var d = await _db.Set<ContractVariableDef>().FirstOrDefaultAsync(x => x.Id == id && x.TenantId == this.Tid(), ct); if (d == null) return NotFound();
        i = i with { Key = d.Key }; var e = Check(i); if (e != null) return BadRequest(new { message = e }); Fill(d, i); await _db.SaveChangesAsync(ct); return Ok();
    }
    [HttpDelete("{id:guid}")] public async Task<IActionResult> Delete(Guid id, CancellationToken ct)
    {
        var d = await _db.Set<ContractVariableDef>().FirstOrDefaultAsync(x => x.Id == id && x.TenantId == this.Tid(), ct); if (d == null) return NotFound();
        var tok = "{{" + d.Key; if (await _db.Set<ContractTemplate>().AnyAsync(t => t.TenantId == this.Tid() && t.Status != "Archived" && (t.BodyHtml.Contains(tok) || t.HeaderHtml.Contains(tok) || t.FooterHtml.Contains(tok)), ct)) return Conflict(new { message = "این متغیر در قالب‌های فعال استفاده شده است" });
        _db.Remove(d); await _db.SaveChangesAsync(ct); return NoContent();
    }
}

/// مدارک و قراردادهای لازم هر طرح وام (از داخل فرم تعریف وام).
[ApiController, Route("api/v1/admin/loan-products/{productId:guid}/contracts"), Authorize(Roles = "Admin,SuperAdmin")]
public class ProductContractsController : ControllerBase
{
    private readonly AppDbContext _db; public ProductContractsController(AppDbContext db) => _db = db;
    static readonly string[] Stages = { "Application", "Approval", "Disbursement" };
    [HttpGet] public async Task<IActionResult> Get(Guid productId, CancellationToken ct)
    {
        var links = await _db.Set<ProductContract>().Where(x => x.TenantId == this.Tid() && x.ProductId == productId).OrderBy(x => x.SortOrder).ToListAsync(ct);
        var gk = links.Select(l => l.GroupKey).ToList(); var ts = await _db.Set<ContractTemplate>().Where(t => t.TenantId == this.Tid() && gk.Contains(t.GroupKey) && t.Status != "Archived").ToListAsync(ct);
        return Ok(links.Select(l => { var t = ts.Where(x => x.GroupKey == l.GroupKey).OrderByDescending(x => x.Version).FirstOrDefault(); var pub = ts.FirstOrDefault(x => x.GroupKey == l.GroupKey && x.Status == "Published"); return new { l.GroupKey, l.Stage, l.Required, l.Condition, l.RequiresReview, l.SortOrder, title = t?.Title, type = t?.Type, publishedVersion = pub?.Version, latestStatus = t?.Status }; }));
    }
    [HttpPut] public async Task<IActionResult> Put(Guid productId, List<LinkIn> items, CancellationToken ct)
    {
        if (!await _db.Set<LoanProduct>().AnyAsync(p => p.Id == productId && p.TenantId == this.Tid(), ct)) return NotFound(); items ??= new();
        if (items.Count > 20 || items.GroupBy(i => i.GroupKey).Any(g => g.Count() > 1)) return BadRequest(new { message = "فهرست قراردادها نامعتبر یا تکراری است" });
        var defs = await ContractSeed.DefsAsync(_db, this.Tid(), ct);
        foreach (var i in items)
        {
            if (!Stages.Contains(i.Stage)) return BadRequest(new { message = "مرحله‌ی نامعتبر" });
            if (!await _db.Set<ContractTemplate>().AnyAsync(t => t.TenantId == this.Tid() && t.GroupKey == i.GroupKey, ct)) return BadRequest(new { message = "قالب پیدا نشد" });
            var ce = ContractEngine.ConditionErrors(i.Condition ?? "", defs); if (ce != null) return BadRequest(new { message = "شرط نامعتبر: " + string.Join("، ", ce) });
        }
        _db.RemoveRange(await _db.Set<ProductContract>().Where(x => x.TenantId == this.Tid() && x.ProductId == productId).ToListAsync(ct));
        var n = 0; foreach (var i in items) _db.Add(new ProductContract { TenantId = this.Tid(), ProductId = productId, GroupKey = i.GroupKey, Stage = i.Stage, Required = i.Required, Condition = (i.Condition ?? "").Trim().Cut(300), RequiresReview = i.RequiresReview, SortOrder = n++ });
        await _db.SaveChangesAsync(ct); return Ok();
    }
}

/// قراردادهای تولیدشده: تولید، بررسی، تأیید، ارائه. متن نهایی هرگز ویرایش نمی‌شود.
[ApiController, Route("api/v1/admin/contracts"), Authorize(Roles = "Admin,SuperAdmin")]
public class ContractsAdminController : ControllerBase
{
    private readonly AppDbContext _db; public ContractsAdminController(AppDbContext db) => _db = db;
    static readonly HashSet<string> Final = new() { "Signed", "Rejected", "Expired", "Cancelled" };

    async Task Ev(Guid cid, string action, string? note = null) { _db.Add(new ContractEvent { TenantId = this.Tid(), ContractId = cid, ActorId = this.Uid(), Action = action, Note = note.Cut(300), Ip = this.Ip() }); await _db.SaveChangesAsync(); }
    static async Task ExpireStale(AppDbContext db, Guid tid, CancellationToken ct)
    { var now = DateTime.UtcNow; foreach (var c in await db.Set<GeneratedContract>().Where(x => x.TenantId == tid && (x.Status == "Presented" || x.Status == "AwaitingSignature") && x.ExpiresAt != null && x.ExpiresAt < now).ToListAsync(ct)) { c.Status = "Expired"; db.Add(new ContractEvent { TenantId = tid, ContractId = c.Id, Action = "Expired" }); } await db.SaveChangesAsync(ct); }

    [HttpGet] public async Task<IActionResult> List([FromQuery] string? status, [FromQuery] Guid? userId, CancellationToken ct)
    {
        await ExpireStale(_db, this.Tid(), ct); var q = _db.Set<GeneratedContract>().Where(c => c.TenantId == this.Tid());
        if (!string.IsNullOrEmpty(status)) q = q.Where(c => c.Status == status); if (userId != null) q = q.Where(c => c.UserId == userId);
        return Ok(await q.OrderByDescending(c => c.CreatedOn).Take(300).Select(c => new { c.Id, c.Number, c.Title, c.Stage, c.Status, c.UserId, c.ProductId, c.LoanId, c.TemplateVersion, c.PreviousId, c.CreatedOn, c.PresentedAt, c.SignedAt, c.ExpiresAt }).ToListAsync(ct));
    }
    [HttpGet("{id:guid}/events")] public async Task<IActionResult> Events(Guid id, CancellationToken ct) => Ok(await _db.Set<ContractEvent>().Where(e => e.TenantId == this.Tid() && e.ContractId == id).OrderBy(e => e.At).Select(e => new { e.At, e.Action, e.Note, e.ActorId, e.Ip }).ToListAsync(ct));
    [HttpGet("{id:guid}/values")] public async Task<IActionResult> Values(Guid id, CancellationToken ct) { var c = await _db.Set<GeneratedContract>().FirstOrDefaultAsync(x => x.Id == id && x.TenantId == this.Tid(), ct); return c == null ? NotFound() : Ok(JsonSerializer.Deserialize<JsonElement>(c.ValuesJson)); }
    /// متن نهایی (فقط برای نمایش در iframe با sandbox). هر مشاهده ثبت می‌شود.
    [HttpGet("{id:guid}/html")] public async Task<IActionResult> Html(Guid id, CancellationToken ct)
    {
        var c = await _db.Set<GeneratedContract>().FirstOrDefaultAsync(x => x.Id == id && x.TenantId == this.Tid(), ct); if (c == null) return NotFound();
        if (CtU.Sha(c.Html) != c.BodyHash) return StatusCode(500, new { message = "یکپارچگی متن قرارداد تأیید نشد" });
        await Ev(id, "Viewed"); return HtmlOut(c.Html);
    }
    internal static IActionResult HtmlOut(string html) => new ContentResult { Content = html, ContentType = "text/html; charset=utf-8" };

    /// آیا مدارک و قراردادهای لازم این طرح برای کاربر کامل است؟ (برای اتصال به گردش کار وام)
    [HttpGet("readiness")] public async Task<IActionResult> Readiness([FromQuery] Guid userId, [FromQuery] Guid productId, [FromQuery] Guid? loanId, CancellationToken ct)
    {
        var p = await _db.Set<LoanProduct>().FirstOrDefaultAsync(x => x.Id == productId && x.TenantId == this.Tid(), ct); if (p == null) return NotFound();
        var miss = await MissingDocs(p, userId, ct);
        var links = await _db.Set<ProductContract>().Where(l => l.TenantId == this.Tid() && l.ProductId == productId && l.Required).ToListAsync(ct);
        var have = await _db.Set<GeneratedContract>().Where(c => c.TenantId == this.Tid() && c.UserId == userId && c.ProductId == productId && (loanId == null || c.LoanId == loanId)).ToListAsync(ct);
        var cs = links.Select(l => new { l.GroupKey, l.Stage, state = have.Where(c => c.GroupKey == l.GroupKey && c.Status != "Cancelled" && c.Status != "Rejected" && c.Status != "Expired").Select(c => c.Status).FirstOrDefault() ?? "NotGenerated" }).ToList();
        return Ok(new { documentsOk = miss.Count == 0, missingDocuments = miss, contracts = cs, contractsSigned = cs.All(c => c.state == "Signed") });
    }
    async Task<List<string>> MissingDocs(LoanProduct p, Guid userId, CancellationToken ct)
    {
        var req = new List<string>(); try { foreach (var d in JsonDocument.Parse(p.DocumentsJson).RootElement.EnumerateArray()) if (d.TryGetProperty("required", out var r) && r.ValueKind == JsonValueKind.True && d.TryGetProperty("name", out var n)) req.Add(n.GetString() ?? ""); } catch { }
        var ok = await _db.Set<CustomerDocument>().Where(x => x.TenantId == this.Tid() && x.UserId == userId && x.Status == "Verified").Select(x => x.Kind).ToListAsync(ct);
        return req.Where(k => k.Length > 0 && !ok.Contains(k)).ToList();
    }

    [HttpPost("generate")] public async Task<IActionResult> Generate(GenIn i, CancellationToken ct)
    {
        var tid = this.Tid(); var p = await _db.Set<LoanProduct>().FirstOrDefaultAsync(x => x.Id == i.ProductId && x.TenantId == tid, ct); if (p == null) return NotFound(new { message = "طرح پیدا نشد" });
        var miss = await MissingDocs(p, i.UserId, ct); if (miss.Count > 0) return UnprocessableEntity(new { message = "مدارک لازم تأیید نشده است", missingDocuments = miss });
        var links = await _db.Set<ProductContract>().Where(l => l.TenantId == tid && l.ProductId == i.ProductId && (i.Stage == null || l.Stage == i.Stage)).OrderBy(l => l.SortOrder).ToListAsync(ct);
        if (links.Count == 0) return UnprocessableEntity(new { message = "برای این طرح قراردادی تعریف نشده است" });
        var defs = await ContractSeed.DefsAsync(_db, tid, ct); var now = DateTime.UtcNow.Date; var made = new List<object>(); var problems = new List<object>(); var toSave = new List<(GeneratedContract c, ContractEvent e)>();
        ContractContext? baseCtx = null;
        foreach (var l in links)
        {
            var t = await _db.Set<ContractTemplate>().Where(x => x.TenantId == tid && x.GroupKey == l.GroupKey && x.Status == "Published" && (x.ValidFrom == null || x.ValidFrom <= now) && (x.ValidTo == null || x.ValidTo >= now)).OrderByDescending(x => x.Version).FirstOrDefaultAsync(ct);
            if (t == null) { problems.Add(new { groupKey = l.GroupKey, error = "نسخه‌ی منتشرشده‌ی معتبر ندارد" }); continue; }
            string number; do { number = "C-" + DateTime.UtcNow.ToString("yyyyMMdd") + "-" + System.Security.Cryptography.RandomNumberGenerator.GetInt32(10000, 99999); } while (await _db.Set<GeneratedContract>().AnyAsync(x => x.TenantId == tid && x.Number == number, ct));
            string? err = null; var ctx = await ContractSeed.BuildAsync(_db, tid, new(i.UserId, i.ProductId, i.Amount, i.Months, i.LoanId), t.CounterPartyId, number, t.Version, defs, e => err = e, ct);
            if (ctx == null) return BadRequest(new { message = err });
            baseCtx ??= ctx;
            if (!ContractEngine.EvalCondition(l.Condition, ctx.Get)) continue; // شرط این قرارداد برقرار نیست
            var body = ContractEngine.Render(t.BodyHtml, defs, ctx.Get, ctx.Table); var hd = ContractEngine.Render(t.HeaderHtml, defs, ctx.Get, ctx.Table); var ft = ContractEngine.Render(t.FooterHtml, defs, ctx.Get, ctx.Table);
            var miss2 = body.Missing.Concat(hd.Missing).Concat(ft.Missing).DistinctBy(m => m.Key).ToList(); var errs = body.Errors.Concat(hd.Errors).Concat(ft.Errors).ToList();
            if (miss2.Count > 0 || errs.Count > 0) { problems.Add(new { groupKey = l.GroupKey, title = t.Title, missingVariables = miss2.Select(m => new { key = m.Key, label = m.Label }), errors = errs }); continue; }
            var html = ContractSeed.Page(t.Title, hd.Html, body.Html, ft.Html);
            if (i.DryRun) { made.Add(new { title = t.Title, version = t.Version, html }); continue; }
            var vals = new Dictionary<string, string?>(); foreach (var d in defs.Values) { var v = ctx.Get(d.Key); if (v != null) { var s = ContractEngine.Fmt(v, d); vals[d.Key] = d.Sensitivity == "Sensitive" ? ContractEngine.Mask(s) : s; } }
            var gc = new GeneratedContract { TenantId = tid, UserId = i.UserId, ProductId = i.ProductId, LoanId = i.LoanId, TemplateId = t.Id, GroupKey = t.GroupKey, TemplateVersion = t.Version, Number = number, Title = t.Title, Stage = l.Stage, RequiresReview = l.RequiresReview, Html = html, BodyHash = CtU.Sha(html), ValuesJson = JsonSerializer.Serialize(vals), PreviousId = i.PreviousId, CreatedBy = this.Uid() };
            _db.Add(gc); _db.Add(new ContractEvent { TenantId = tid, ContractId = gc.Id, ActorId = this.Uid(), Action = "Generated", Note = "نسخه‌ی قالب " + t.Version, Ip = this.Ip() }); made.Add(new { gc.Id, gc.Number, title = t.Title, version = t.Version });
        }
        if (problems.Count > 0) { _db.ChangeTracker.Clear(); return UnprocessableEntity(new { message = "تولید قرارداد انجام نشد؛ موارد ناقص را کامل کنید", problems }); } // یا همه ساخته می‌شوند یا هیچ‌کدام
        if (i.PreviousId != null) { var prev = await _db.Set<GeneratedContract>().FirstOrDefaultAsync(x => x.Id == i.PreviousId && x.TenantId == tid, ct); if (prev != null && prev.Status != "Signed" && !Final.Contains(prev.Status)) { prev.Status = "Cancelled"; _db.Add(new ContractEvent { TenantId = tid, ContractId = prev.Id, ActorId = this.Uid(), Action = "Superseded" }); } }
        await _db.SaveChangesAsync(ct); return Ok(new { contracts = made });
    }

    static readonly Dictionary<string, (string from, string to)> Ops = new()
    {
        ["submit"] = ("Draft", "ReadyForReview"), ["return"] = ("ReadyForReview", "Draft"), ["approve"] = ("ReadyForReview", "Approved"),
        ["present"] = ("Approved", "Presented"), ["request-signature"] = ("Presented", "AwaitingSignature"),
    };
    [HttpPost("{id:guid}/{op}")] public async Task<IActionResult> Act(Guid id, string op, NoteIn? n, CancellationToken ct)
    {
        var c = await _db.Set<GeneratedContract>().FirstOrDefaultAsync(x => x.Id == id && x.TenantId == this.Tid(), ct); if (c == null) return NotFound();
        if (op == "cancel") { if (Final.Contains(c.Status)) return Conflict(new { message = "قرارداد نهایی شده است" }); c.Status = "Cancelled"; await _db.SaveChangesAsync(ct); await Ev(id, "Cancelled", n?.Note); return Ok(); }
        if (!Ops.TryGetValue(op, out var t) || c.Status != t.from) return Conflict(new { message = "این اقدام در وضعیت فعلی ممکن نیست" });
        if (op == "approve") { if (c.CreatedBy == this.Uid() && !this.IsSuper()) return StatusCode(403, new { message = "تأیید باید توسط فرد دیگری انجام شود" }); c.ReviewedBy = this.Uid(); c.ReviewedAt = DateTime.UtcNow; }
        if (op == "submit" && !c.RequiresReview) { c.Status = "Approved"; c.ReviewedAt = DateTime.UtcNow; await _db.SaveChangesAsync(ct); await Ev(id, "AutoApproved"); return Ok(); }
        if (op == "present") { c.PresentedAt = DateTime.UtcNow; c.ExpiresAt = DateTime.UtcNow.AddDays(7); }
        c.Status = t.to; await _db.SaveChangesAsync(ct); await Ev(id, op, n?.Note); return Ok();
    }
}

/// قراردادهای خود مشتری: مشاهده، قبول یا رد. فقط قراردادهای ارائه‌شده‌ی خودش.
[ApiController, Route("api/v1/me/contracts"), Authorize]
public class MyContractsController : ControllerBase
{
    private readonly AppDbContext _db; public MyContractsController(AppDbContext db) => _db = db;
    static readonly string[] Visible = { "Presented", "AwaitingSignature", "Signed", "Rejected", "Expired" };
    [HttpGet] public async Task<IActionResult> Mine(CancellationToken ct)
    {
        var u = this.Uid(); if (u == null) return Unauthorized(); var now = DateTime.UtcNow;
        foreach (var c in await _db.Set<GeneratedContract>().Where(x => x.TenantId == this.Tid() && x.UserId == u && (x.Status == "Presented" || x.Status == "AwaitingSignature") && x.ExpiresAt < now).ToListAsync(ct)) { c.Status = "Expired"; _db.Add(new ContractEvent { TenantId = c.TenantId, ContractId = c.Id, Action = "Expired" }); }
        await _db.SaveChangesAsync(ct);
        return Ok(await _db.Set<GeneratedContract>().Where(x => x.TenantId == this.Tid() && x.UserId == u && Visible.Contains(x.Status)).OrderByDescending(x => x.CreatedOn).Select(x => new { x.Id, x.Number, x.Title, x.Status, x.PresentedAt, x.ExpiresAt, x.SignedAt }).ToListAsync(ct));
    }
    async Task<GeneratedContract?> Own(Guid id, CancellationToken ct) { var u = this.Uid(); return await _db.Set<GeneratedContract>().FirstOrDefaultAsync(x => x.Id == id && x.TenantId == this.Tid() && x.UserId == u && Visible.Contains(x.Status), ct); }
    [HttpGet("{id:guid}/html")] public async Task<IActionResult> Html(Guid id, CancellationToken ct)
    {
        var c = await Own(id, ct); if (c == null) return NotFound(); if (CtU.Sha(c.Html) != c.BodyHash) return StatusCode(500, new { message = "یکپارچگی متن قرارداد تأیید نشد" });
        _db.Add(new ContractEvent { TenantId = c.TenantId, ContractId = c.Id, ActorId = this.Uid(), Action = "ViewedByCustomer", Ip = this.Ip() }); await _db.SaveChangesAsync(ct); return ContractsAdminController.HtmlOut(c.Html);
    }
    /// قبول الکترونیکی ساده؛ امضای دیجیتال قانونی نیست. زمان، کاربر، IP و مرورگر ثبت می‌شود.
    [HttpPost("{id:guid}/sign")] public async Task<IActionResult> Sign(Guid id, CancellationToken ct)
    {
        var c = await Own(id, ct); if (c == null) return NotFound(); if (c.Status is not ("Presented" or "AwaitingSignature")) return Conflict(new { message = "این قرارداد قابل امضا نیست" });
        c.Status = "Signed"; c.SignedAt = DateTime.UtcNow; c.SignedIp = this.Ip(); c.SignedUa = Request.Headers.UserAgent.ToString().Cut(200); c.SignatureMethod = "SimpleAccept";
        _db.Add(new ContractEvent { TenantId = c.TenantId, ContractId = c.Id, ActorId = this.Uid(), Action = "Signed", Ip = this.Ip() }); await _db.SaveChangesAsync(ct); return Ok();
    }
    [HttpPost("{id:guid}/reject")] public async Task<IActionResult> Reject(Guid id, NoteIn n, CancellationToken ct)
    {
        var c = await Own(id, ct); if (c == null) return NotFound(); if (c.Status is not ("Presented" or "AwaitingSignature")) return Conflict(new { message = "این قرارداد قابل رد نیست" });
        c.Status = "Rejected"; _db.Add(new ContractEvent { TenantId = c.TenantId, ContractId = c.Id, ActorId = this.Uid(), Action = "Rejected", Note = n.Note.Cut(300), Ip = this.Ip() }); await _db.SaveChangesAsync(ct); return Ok();
    }
}
