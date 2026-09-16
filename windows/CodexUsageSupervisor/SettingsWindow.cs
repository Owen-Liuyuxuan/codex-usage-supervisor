using Microsoft.Win32;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Button = System.Windows.Controls.Button;
using TextBox = System.Windows.Controls.TextBox;
using CheckBox = System.Windows.Controls.CheckBox;
using Color = System.Windows.Media.Color;
using Brushes = System.Windows.Media.Brushes;

namespace CodexUsageSupervisor;

internal sealed class SettingsWindow : Window
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string RunName = "CodexUsageSupervisor";
    public SettingsWindow(JsonNode settings, Func<JsonNode, Task> save)
    {
        Title = "Codex Usage Supervisor · 设置";
        Width = 460; Height = 380; ResizeMode = ResizeMode.NoResize;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        Background = new SolidColorBrush(Color.FromRgb(18, 28, 38));
        var panel = new StackPanel { Margin = new Thickness(24) };
        Content = panel;
        panel.Children.Add(new TextBlock { Text = "偏好设置", FontSize = 23, Margin = new Thickness(0, 0, 0, 20) });
        panel.Children.Add(new TextBlock { Text = "Codex 数据目录" });
        var home = new TextBox { Text = settings["codex_home"]!.ToString() };
        panel.Children.Add(home);
        panel.Children.Add(new TextBlock { Text = "自动刷新间隔（5–3600 秒）" });
        var interval = new TextBox { Text = settings["refresh_seconds"]!.ToString() };
        panel.Children.Add(interval);
        using var key = Registry.CurrentUser.OpenSubKey(RunKey);
        var startup = new CheckBox { Content = "登录 Windows 后自动启动", IsChecked = key?.GetValue(RunName) != null, Foreground = Brushes.White, Margin = new Thickness(0, 0, 0, 20) };
        panel.Children.Add(startup);
        var button = new Button { Content = "保存", HorizontalAlignment = System.Windows.HorizontalAlignment.Left };
        panel.Children.Add(button);
        button.Click += async (_, _) =>
        {
            if (!int.TryParse(interval.Text, out var seconds) || seconds < 5 || seconds > 3600 || !System.IO.Directory.Exists(home.Text))
            {
                System.Windows.MessageBox.Show("请输入有效的数据目录，以及 5–3600 秒的刷新间隔。", Title); return;
            }
            button.IsEnabled = false;
            try
            {
                settings["codex_home"] = home.Text;
                settings["refresh_seconds"] = seconds;
                await save(settings);
                using var run = Registry.CurrentUser.CreateSubKey(RunKey);
                if (startup.IsChecked == true) run.SetValue(RunName, $"\"{Environment.ProcessPath}\" --background");
                else run.DeleteValue(RunName, false);
                Close();
            }
            catch (Exception error) { System.Windows.MessageBox.Show(error.Message, "保存失败"); }
            finally { button.IsEnabled = true; }
        };
    }
}
