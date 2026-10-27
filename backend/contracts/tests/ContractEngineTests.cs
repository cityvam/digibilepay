// تست‌های واحد موتور قرارداد (xUnit). اجرا نشده؛ در پروژه‌ی تست جدا اضافه کنید:
//   dotnet new xunit -n Ghestine.Tests ; dotnet add Ghestine.Tests reference src/Ghestine.API ; dotnet test
using Ghestine.API.Contracts;
using Xunit;
public class ContractEngineTests
{
    static VarDef V(string k, string t = "text", bool req = false, string f = "") => new(k, k, t, "system", k, req, f, "Normal", "", "");
    static Dictionary<string, VarDef> Defs(params VarDef[] d) => d.ToDictionary(x => x.Key);
    static Func<string, object?> G(Dictionary<string, object?> m) => k => m.TryGetValue(k, out var v) ? v : null;

    [Fact] public void ReplacesVariablesAndEncodesHtml()
    { var r = ContractEngine.Render("سلام {{name}}", Defs(V("name")), G(new() { ["name"] = "<b>x</b>" }), null); Assert.Equal("سلام &lt;b&gt;x&lt;/b&gt;", r.Html); }
    [Fact] public void UnknownVariableIsAnErrorNotBlank()
    { var r = ContractEngine.Render("{{nope}}", Defs(V("a")), G(new()), null); Assert.Contains(r.Errors, e => e.Contains("nope")); }
    [Fact] public void RequiredMissingIsReported()
    { var r = ContractEngine.Render("{{a}}", Defs(V("a", req: true)), G(new()), null); Assert.Single(r.Missing); }
    [Fact] public void OptionalMissingIsEmpty()
    { var r = ContractEngine.Render("[{{a}}]", Defs(V("a")), G(new()), null); Assert.Equal("[]", r.Html); Assert.Empty(r.Missing); }
    [Fact] public void IfElseWorks()
    {
        var d = Defs(V("amt", "number")); var t = "{{#if amt >= 100}}big{{else}}small{{/if}}";
        Assert.Equal("big", ContractEngine.Render(t, d, G(new() { ["amt"] = 150m }), null).Html);
        Assert.Equal("small", ContractEngine.Render(t, d, G(new() { ["amt"] = 5m }), null).Html);
    }
    [Fact] public void ConditionDecodesHtmlEntities()
    { var r = ContractEngine.Render("{{#if amt &gt;= 100}}y{{/if}}", Defs(V("amt", "number")), G(new() { ["amt"] = 100m }), null); Assert.Equal("y", r.Html); }
    [Fact] public void AndOrAndNot()
    {
        var d = Defs(V("a"), V("b")); var g = G(new() { ["a"] = "x" });
        Assert.True(ContractEngine.EvalCondition("a == 'x' && !b", g)); Assert.True(ContractEngine.EvalCondition("b || a", g)); Assert.False(ContractEngine.EvalCondition("a != 'x'", g));
    }
    [Fact] public void UnclosedIfIsInvalid()
    { Assert.NotEmpty(ContractEngine.Validate("{{#if a}}x", Defs(V("a")))); }
    [Fact] public void CodeLikeExpressionsAreRejected()
    { Assert.NotEmpty(ContractEngine.Validate("{{#if System.IO.File.Delete('x')}}y{{/if}}", Defs(V("a")))); Assert.NotNull(ContractEngine.ConditionErrors("a; drop table", Defs(V("a")))); }
    [Fact] public void NestingLimit()
    { var t = string.Concat(Enumerable.Repeat("{{#if a}}", 7)) + "x" + string.Concat(Enumerable.Repeat("{{/if}}", 7)); Assert.NotEmpty(ContractEngine.Validate(t, Defs(V("a")))); }
    [Fact] public void InstallmentsAddUpAndLastAbsorbsRemainder()
    {
        var (down, fee, total, rows) = ContractEngine.Calc(10_000_000, 10, 5, 3, 30, new DateTime(2026, 1, 1));
        Assert.Equal(1_000_000, down); Assert.Equal(450_000, fee); Assert.Equal(9_450_000, total); Assert.Equal(total, rows.Sum(r => r.Amount)); Assert.Equal(3, rows.Count);
    }
    [Fact] public void MissingTableIsReported()
    { var r = ContractEngine.Render("{{installments_table}}", Defs(), G(new()), null); Assert.Single(r.Missing); }
    [Fact] public void MaskKeepsLastThree() => Assert.Equal("•••••••899", ContractEngine.Mask("0499370899"));
    [Fact] public void MoneyFormatUsesPersianDigits() => Assert.Equal("۱٬۲۰۰ تومان", ContractEngine.Fmt(1200m, V("m", "money", f: "تومان")));
}
