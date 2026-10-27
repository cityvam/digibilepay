using System.Globalization;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
namespace Ghestine.API.Contracts;

public record VarDef(string Key, string Label, string DataType, string Source, string Path, bool Required, string Format, string Sensitivity, string DefaultValue, string Validation);
public record Installment(int No, DateTime Due, decimal Amount);

/// موتور قالب امن: فقط جایگزینی متغیر، شرط ساده‌ی if/else و جدول اقساط. هیچ کد دلخواهی اجرا نمی‌شود.
/// نحو: {{key}}   {{#if key}}..{{else}}..{{/if}}   {{#if key >= 100 && other == 'x'}}   {{installments_table}}
public static class ContractEngine
{
    abstract record Node;
    sealed record Text(string S) : Node;
    sealed record Var(string Key) : Node;
    sealed record Table() : Node;
    sealed record If(string Expr, List<Node> Yes, List<Node> No) : Node;

    static readonly Regex Tok = new(@"\{\{\s*(.+?)\s*\}\}", RegexOptions.Singleline | RegexOptions.Compiled);
    static readonly Regex KeyRx = new("^[a-z][a-z0-9_]{0,59}$", RegexOptions.Compiled);
    static readonly Regex Atom = new(@"^\s*(!?)\s*([a-z][a-z0-9_]*)\s*(?:(==|!=|>=|<=|>|<)\s*(?:'([^']*)'|""([^""]*)""|(-?\d+(?:\.\d+)?)))?\s*$", RegexOptions.Compiled);
    public const string TableKey = "installments_table";

    static (List<Node>? nodes, List<string> errors) Parse(string body)
    {
        var errors = new List<string>(); if (body.Length > 300_000) { errors.Add("متن قرارداد بیش از حد طولانی است"); return (null, errors); }
        var root = new List<Node>(); var stack = new Stack<(If node, bool inElse)>(); var cur = root; var inElse = false; var pos = 0;
        foreach (Match m in Tok.Matches(body))
        {
            if (m.Index > pos) cur.Add(new Text(body[pos..m.Index])); pos = m.Index + m.Length;
            var t = WebUtility.HtmlDecode(m.Groups[1].Value).Trim();
            if (t.StartsWith("#if "))
            {
                if (stack.Count >= 5) { errors.Add("تودرتویی شرط‌ها بیش از ۵ سطح است"); continue; }
                var expr = t[4..].Trim(); var err = CheckExpr(expr); if (err != null) errors.Add($"شرط «{expr}»: {err}");
                var n = new If(expr, new(), new()); cur.Add(n); stack.Push((n, inElse)); cur = n.Yes; inElse = false;
            }
            else if (t == "else")
            {
                if (stack.Count == 0 || inElse) { errors.Add("else بی‌جا"); continue; }
                cur = stack.Peek().node.No; inElse = true;
            }
            else if (t == "/if")
            {
                if (stack.Count == 0) { errors.Add("/if بی‌جفت"); continue; }
                var (n, wasElse) = stack.Pop(); inElse = wasElse;
                cur = stack.Count == 0 ? root : (wasElse ? stack.Peek().node.No : stack.Peek().node.Yes);
            }
            else if (t == TableKey) cur.Add(new Table());
            else if (KeyRx.IsMatch(t)) cur.Add(new Var(t));
            else errors.Add($"عبارت نامعتبر: {{{{{t}}}}}");
        }
        if (pos < body.Length) cur.Add(new Text(body[pos..]));
        if (stack.Count > 0) errors.Add("یک «#if» بسته نشده است");
        return (errors.Count == 0 ? root : null, errors);
    }

    static string? CheckExpr(string e)
    {
        if (e.Length > 300) return "بیش از حد طولانی";
        foreach (var part in e.Split("||")) foreach (var a in part.Split("&&")) if (!Atom.IsMatch(a)) return "ساختار نامعتبر؛ نمونه‌ی مجاز: key ، !key ، key >= 100 ، key == 'متن'";
        return null;
    }
    static IEnumerable<string> ExprKeys(string e) => e.Split("||").SelectMany(p => p.Split("&&")).Select(a => Atom.Match(a)).Where(m => m.Success).Select(m => m.Groups[2].Value);
    static void Keys(IEnumerable<Node> ns, HashSet<string> set)
    {
        foreach (var n in ns) switch (n) { case Var v: set.Add(v.Key); break; case Table: set.Add(TableKey); break; case If i: foreach (var k in ExprKeys(i.Expr)) set.Add(k); Keys(i.Yes, set); Keys(i.No, set); break; }
    }

    /// بررسی ساختار و متغیرهای ناشناخته (برای ذخیره/تأیید قالب).
    public static List<string> Validate(string body, IDictionary<string, VarDef> defs)
    {
        var (nodes, errors) = Parse(body); if (nodes == null) return errors;
        var set = new HashSet<string>(); Keys(nodes, set);
        foreach (var k in set.Where(k => k != TableKey && !defs.ContainsKey(k)).OrderBy(k => k)) errors.Add("متغیر ناشناخته: " + k);
        return errors;
    }
    public static List<string>? ConditionErrors(string expr, IDictionary<string, VarDef> defs)
    {
        if (string.IsNullOrWhiteSpace(expr)) return null; var e = CheckExpr(expr.Trim()); if (e != null) return new() { e };
        var bad = ExprKeys(expr).Where(k => !defs.ContainsKey(k)).Distinct().Select(k => "متغیر ناشناخته: " + k).ToList(); return bad.Count > 0 ? bad : null;
    }

    public static bool EvalCondition(string expr, Func<string, object?> get)
    {
        if (string.IsNullOrWhiteSpace(expr)) return true;
        return expr.Split("||").Any(p => p.Split("&&").All(a => EvalAtom(a, get)));
    }
    static bool EvalAtom(string a, Func<string, object?> get)
    {
        var m = Atom.Match(a); if (!m.Success) return false; var v = get(m.Groups[2].Value);
        if (!m.Groups[3].Success) { var t = Truthy(v); return m.Groups[1].Value == "!" ? !t : t; }
        var op = m.Groups[3].Value; var lit = m.Groups[4].Success ? m.Groups[4].Value : m.Groups[5].Success ? m.Groups[5].Value : m.Groups[6].Value;
        var isNum = m.Groups[6].Success; bool r;
        if (isNum || op is ">" or "<" or ">=" or "<=")
        {
            if (!TryNum(v, out var x) || !decimal.TryParse(lit, NumberStyles.Number, CultureInfo.InvariantCulture, out var y)) return false;
            r = op switch { "==" => x == y, "!=" => x != y, ">" => x > y, "<" => x < y, ">=" => x >= y, _ => x <= y };
        }
        else { var s = v?.ToString() ?? ""; r = op == "==" ? s == lit : s != lit; }
        return m.Groups[1].Value == "!" ? !r : r;
    }
    static bool Truthy(object? v) => v switch { null => false, string s => s.Length > 0, bool b => b, decimal d => d != 0, int i => i != 0, long l => l != 0, double d => d != 0, _ => true };
    static bool TryNum(object? v, out decimal d) { d = 0; return v switch { decimal x => (d = x) == x, int i => (d = i) == i, long l => (d = l) == l, double f => (d = (decimal)f) == (decimal)f, string s => decimal.TryParse(s, NumberStyles.Number, CultureInfo.InvariantCulture, out d), _ => false }; }

    public record RenderResult(string Html, List<(string Key, string Label)> Missing, List<string> Errors);
    /// تولید متن. هر متغیر اجباری بدون مقدار در Missing می‌آید؛ متغیر ناشناخته در Errors (هرگز بی‌صدا خالی نمی‌شود).
    public static RenderResult Render(string body, IDictionary<string, VarDef> defs, Func<string, object?> get, IReadOnlyList<Installment>? table)
    {
        var (nodes, errors) = Parse(body); var missing = new List<(string, string)>(); var errs = new List<string>(errors);
        if (nodes == null) return new("", missing, errs);
        var sb = new StringBuilder(); var seenMissing = new HashSet<string>();
        void Walk(List<Node> ns)
        {
            foreach (var n in ns) switch (n)
            {
                case Text t: sb.Append(t.S); break;
                case Table: if (table == null || table.Count == 0) { if (seenMissing.Add(TableKey)) missing.Add((TableKey, "جدول اقساط")); } else sb.Append(TableHtml(table)); break;
                case Var v:
                    if (!defs.TryGetValue(v.Key, out var d)) { errs.Add("متغیر ناشناخته: " + v.Key); break; }
                    var val = get(v.Key);
                    if (val == null || (val is string s && s.Length == 0)) { if (d.Required) { if (seenMissing.Add(v.Key)) missing.Add((v.Key, d.Label)); } break; }
                    sb.Append(WebUtility.HtmlEncode(Fmt(val, d))); break;
                case If i: Walk(EvalCondition(i.Expr, get) ? i.Yes : i.No); break;
            }
        }
        Walk(nodes); return new(sb.ToString(), missing, errs);
    }

    static readonly PersianCalendar Pc = new();
    public static string Fa(string s) => new string(s.Select(c => c >= '0' && c <= '9' ? (char)('۰' + c - '0') : c).ToArray());
    public static string Jalali(DateTime d) => Fa($"{Pc.GetYear(d):0000}/{Pc.GetMonth(d):00}/{Pc.GetDayOfMonth(d):00}");
    public static string Fmt(object val, VarDef d)
    {
        var suffix = string.IsNullOrWhiteSpace(d.Format) ? "" : " " + d.Format;
        switch (d.DataType)
        {
            case "date": return val is DateTime dt ? Jalali(dt) : val.ToString() ?? "";
            case "money": case "number":
                if (TryNum(val, out var n)) return Fa(n.ToString(d.DataType == "money" ? "N0" : "0.##", CultureInfo.InvariantCulture).Replace(",", "٬").Replace(".", "٫")) + suffix;
                return val.ToString() ?? "";
            default: return (val.ToString() ?? "") + suffix;
        }
    }
    static string TableHtml(IReadOnlyList<Installment> t)
    {
        var sb = new StringBuilder("<table class=\"inst\"><thead><tr><th>ردیف</th><th>سررسید</th><th>مبلغ قسط (تومان)</th></tr></thead><tbody>");
        foreach (var r in t) sb.Append("<tr><td>").Append(Fa(r.No.ToString())).Append("</td><td>").Append(Jalali(r.Due)).Append("</td><td>").Append(Fa(r.Amount.ToString("N0", CultureInfo.InvariantCulture).Replace(",", "٬"))).Append("</td></tr>");
        return sb.Append("</tbody></table>").ToString();
    }

    /// محاسبه‌ی اقساط: کارمزد = درصد کارمزد پله از مبلغ تأمین‌مالی‌شده (کل مبلغ منهای پیش‌پرداخت)، به‌صورت یکجا و ثابت.
    /// اگر فرمول طرح شما فرق دارد (مثلاً کارمزد ماهانه)، همین تابع را تغییر دهید.
    public static (decimal down, decimal fee, decimal total, List<Installment> rows) Calc(decimal amount, decimal downPct, decimal feePct, int months, int intervalDays, DateTime start)
    {
        var down = Math.Round(amount * downPct / 100m, 0); var fin = amount - down; var fee = Math.Round(fin * feePct / 100m, 0); var total = fin + fee;
        var each = Math.Ceiling(total / months); var rows = new List<Installment>(); decimal left = total;
        for (var i = 1; i <= months; i++) { var a = i == months ? left : Math.Min(each, left); left -= a; rows.Add(new Installment(i, start.AddDays((long)intervalDays * i), a)); }
        return (down, fee, total, rows);
    }
    public static string Mask(string s) => s.Length <= 3 ? new string('•', s.Length) : new string('•', s.Length - 3) + s[^3..];
}
