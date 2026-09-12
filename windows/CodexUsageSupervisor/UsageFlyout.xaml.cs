using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Input;
using TextBlock = System.Windows.Controls.TextBlock;
using ProgressBar = System.Windows.Controls.ProgressBar;
using Color = System.Windows.Media.Color;

namespace CodexUsageSupervisor;

public partial class UsageFlyout : Window
{
    public UsageFlyout()
    {
        InitializeComponent();
        Deactivated += (_, _) => Hide();
        KeyDown += (_, e) => { if (e.Key == Key.Escape) Hide(); };
        Closing += (_, e) => { e.Cancel = true; Hide(); };
    }

    public void Reveal()
    {
        Show();
        var area = System.Windows.Forms.Screen.FromPoint(System.Windows.Forms.Cursor.Position).WorkingArea;
        var source = PresentationSource.FromVisual(this);
        var transform = source?.CompositionTarget?.TransformFromDevice ?? Matrix.Identity;
        var corner = transform.Transform(new System.Windows.Point(area.Right, area.Bottom));
        var origin = transform.Transform(new System.Windows.Point(area.Left, area.Top));
        Height = Math.Min(640, corner.Y - origin.Y - 20);
        Left = Math.Max(origin.X + 10, corner.X - Width - 12);
        Top = Math.Max(origin.Y + 10, corner.Y - Height - 12);
        Activate();
    }

    internal static double? Percent(JsonNode? window) => window?["used_percent"]?.GetValue<double>();
    internal static string Compact(double value) => value >= 1_000_000 ? $"{value / 1_000_000:0.##}M" : value >= 1000 ? $"{value / 1000:0.#}K" : $"{value:0}";
    private static void SetWindow(JsonNode? data, TextBlock label, TextBlock value, ProgressBar bar, TextBlock reset)
    {
        var percent = Percent(data);
        value.Text = percent is { } p ? $"{p:0.#}%" : "—";
        bar.Value = Math.Clamp(percent ?? 0, 0, 100);
        bar.Foreground = new SolidColorBrush(percent >= 90 ? Color.FromRgb(255, 121, 121) : percent >= 70 ? Color.FromRgb(247, 201, 103) : Color.FromRgb(102, 222, 176));
        var minutes = data?["window_minutes"]?.GetValue<int>() ?? 0;
        if (minutes > 0) label.Text = minutes == 10080 ? "每周" : minutes >= 1440 ? $"{minutes / 1440.0:0.#} 天" : $"{minutes / 60.0:0.#} 小时";
        if (DateTimeOffset.TryParse(data?["resets_at"]?.ToString(), out var timestamp))
        {
            var remaining = timestamp - DateTimeOffset.Now;
            reset.Text = remaining.TotalSeconds <= 0 ? "重置时间已过，等待更新" : $"{timestamp.ToLocalTime():MM/dd HH:mm} 重置 · 剩余 {(int)remaining.TotalHours}小时 {remaining.Minutes}分";
        }
        else reset.Text = percent == null ? "额度数据不可用" : "重置时间未知";
    }

    internal void Update(JsonNode snapshot)
    {
        var limits = snapshot["rate_limits"];
        SetWindow(limits?["primary"], PrimaryLabel, PrimaryValue, PrimaryBar, PrimaryReset);
        SetWindow(limits?["secondary"], SecondaryLabel, SecondaryValue, SecondaryBar, SecondaryReset);
        var today = snapshot["today"]!;
        var minutes = today["focus_minutes"]!.GetValue<int>();
        Today.Text = $"{minutes / 60}h {minutes % 60}m   ·   {today["sessions"]} 任务   ·   {Compact(today["tokens"]!.GetValue<double>())} tokens";
        Recent.Children.Clear();
        foreach (var item in snapshot["recent"]!.AsArray())
        {
            Recent.Children.Add(new TextBlock { Text = item!["name"]!.ToString(), TextTrimming = TextTrimming.CharacterEllipsis, TextWrapping = TextWrapping.NoWrap, Margin = new Thickness(0, 7, 0, 3) });
            Recent.Children.Add(new TextBlock { Text = $"{item["project"]} · {Compact(item["tokens"]!.GetValue<double>())} tokens", Foreground = new SolidColorBrush(Color.FromRgb(139, 155, 170)), FontSize = 11 });
        }
        if (Recent.Children.Count == 0) Recent.Children.Add(new TextBlock { Text = "暂无本地任务", Margin = new Thickness(0, 10, 0, 0) });
        var fresh = snapshot["rate_limits_source"]?.ToString() == "app-server";
        var observed = DateTimeOffset.TryParse(limits?["observed_at"]?.ToString(), out var stamp) ? stamp.ToLocalTime().ToString("MM/dd HH:mm") : "未知";
        Status.Text = fresh ? $"账户实时查询 · {limits?["plan_type"]} · {DateTime.Now:HH:mm:ss} 更新" : $"本地快照（{observed}）· 实时查询失败";
        Status.ToolTip = snapshot["rate_limits_refresh_error"]?.ToString();
    }

    private async void RefreshClick(object sender, RoutedEventArgs e) => await ((App)System.Windows.Application.Current).Refresh();
    private async void SettingsClick(object sender, RoutedEventArgs e) => await ((App)System.Windows.Application.Current).ShowSettings();
    private void HideClick(object sender, RoutedEventArgs e) => Hide();
}
