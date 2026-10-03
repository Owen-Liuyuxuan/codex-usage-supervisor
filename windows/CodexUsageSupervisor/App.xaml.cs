using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Threading;
using Forms = System.Windows.Forms;

namespace CodexUsageSupervisor;

public partial class App : System.Windows.Application
{
    private Mutex? mutex;
    private readonly BackendClient backend = new();
    private Forms.NotifyIcon? tray;
    private Icon? icon;
    private UsageFlyout flyout = null!;
    private SettingsWindow? preferences;
    private readonly DispatcherTimer timer = new();
    private bool busy;
    private bool ownsMutex;
    private bool refreshSucceeded;
    [DllImport("user32.dll")] private static extern bool DestroyIcon(IntPtr handle);

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        mutex = new Mutex(true, "Local\\CodexUsageSupervisor.Windows", out ownsMutex);
        if (!ownsMutex) { Shutdown(); return; }
        flyout = new UsageFlyout();
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("打开用量", null, (_, _) => flyout.Reveal());
        menu.Items.Add("刷新", null, async (_, _) => await Refresh());
        menu.Items.Add("设置", null, async (_, _) => await ShowSettings());
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add("退出", null, (_, _) => Shutdown());
        tray = new Forms.NotifyIcon { Visible = true, ContextMenuStrip = menu, Text = "Codex · 正在获取用量" };
        DrawIcon(null, false);
        tray.MouseClick += (_, args) => { if (args.Button == Forms.MouseButtons.Left) { if (flyout.IsVisible) flyout.Hide(); else flyout.Reveal(); } };
        timer.Interval = TimeSpan.FromSeconds(30);
        timer.Tick += async (_, _) => await Refresh();
        timer.Start();
        if (!e.Args.Contains("--background")) flyout.Reveal();
        await Refresh();
        if (e.Args.Contains("--smoke-test"))
        {
            // Verify that a fresh child can be started after connection loss.
            backend.Dispose();
            await Refresh();
            flyout.UpdateLayout();
            var bitmap = new System.Windows.Media.Imaging.RenderTargetBitmap((int)flyout.ActualWidth, (int)flyout.ActualHeight, 96, 96, System.Windows.Media.PixelFormats.Pbgra32);
            bitmap.Render(flyout);
            var encoder = new System.Windows.Media.Imaging.PngBitmapEncoder();
            encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bitmap));
            using (var output = System.IO.File.Create(System.IO.Path.Combine(AppContext.BaseDirectory, "smoke-test.png"))) encoder.Save(output);
            System.IO.File.WriteAllText(System.IO.Path.Combine(AppContext.BaseDirectory, "smoke-test.txt"), tray!.Text + "\n" + flyout.Status.Text + "\n" + flyout.Status.ToolTip);
            Shutdown(refreshSucceeded ? 0 : 1);
        }
    }

    internal async Task Refresh()
    {
        if (busy) return;
        busy = true;
        refreshSucceeded = false;
        flyout.RefreshButton.IsEnabled = false;
        try
        {
            var settings = await backend.Call("settings/read");
            timer.Interval = TimeSpan.FromSeconds(settings["refresh_seconds"]!.GetValue<int>());
            var snapshot = await backend.Call("snapshot");
            flyout.Update(snapshot);
            var percent = UsageFlyout.Percent(snapshot["rate_limits"]?["primary"]);
            var fresh = snapshot["rate_limits_source"]?.ToString() == "app-server";
            var sourceLabel = snapshot["rate_limits_source"]?.ToString() switch
            {
                "app-server" => "账户实时",
                "network-cache" => "账户缓存",
                _ => "本地快照",
            };
            DrawIcon(percent, fresh);
            tray!.Text = percent is { } p ? $"Codex 已用 {p:0.#}% · {sourceLabel}" : "Codex · 额度不可用";
            refreshSucceeded = true;
        }
        catch (Exception error)
        {
            flyout.Status.Text = "刷新失败 · 将自动重试";
            flyout.Status.ToolTip = error.Message;
            DrawIcon(null, false);
            tray!.Text = "Codex · 刷新失败";
        }
        finally { busy = false; flyout.RefreshButton.IsEnabled = true; }
    }

    internal async Task ShowSettings()
    {
        if (preferences != null) { preferences.Activate(); return; }
        try
        {
            var settings = await backend.Call("settings/read");
            preferences = new SettingsWindow(settings, async updated => { await backend.Call("settings/write", updated); await Refresh(); });
            preferences.Closed += (_, _) => preferences = null;
            preferences.Show();
            preferences.Activate();
        }
        catch (Exception error) { System.Windows.MessageBox.Show(error.Message, "无法打开设置"); }
    }

    private void DrawIcon(double? percent, bool fresh)
    {
        using var bitmap = new Bitmap(64, 64);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var color = !fresh ? Color.FromArgb(155, 165, 175) : percent >= 90 ? Color.FromArgb(255, 121, 121) : percent >= 70 ? Color.FromArgb(247, 201, 103) : Color.FromArgb(102, 222, 176);
        using var background = new SolidBrush(Color.FromArgb(18, 28, 38));
        graphics.FillEllipse(background, 1, 1, 62, 62);
        using var pen = new Pen(color, 4);
        graphics.DrawArc(pen, 3, 3, 58, 58, -90, (float)Math.Max(3, Math.Clamp(percent ?? 0, 0, 100) * 3.6));
        using var font = new Font("Segoe UI", percent >= 100 ? 22 : 26, System.Drawing.FontStyle.Bold, GraphicsUnit.Pixel);
        using var brush = new SolidBrush(color);
        using var format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
        graphics.DrawString(percent is { } p ? $"{p:0}" : "?", font, brush, new RectangleF(0, 0, 64, 62), format);
        var handle = bitmap.GetHicon();
        Icon next;
        try { using var temporary = Icon.FromHandle(handle); next = (Icon)temporary.Clone(); }
        finally { DestroyIcon(handle); }
        tray!.Icon = next;
        icon?.Dispose(); icon = next;
    }

    protected override void OnExit(ExitEventArgs e)
    {
        timer.Stop();
        tray?.Dispose(); icon?.Dispose(); backend.Dispose();
        if (ownsMutex) mutex?.ReleaseMutex();
        mutex?.Dispose();
        base.OnExit(e);
    }
}
