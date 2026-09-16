# Windows 版本

原生 WPF 托盘应用，共用原项目的 Python 统计和账户查询代码。无需 API key，沿用本机 Codex 登录。仅查询账户额度，不发起模型任务。

## 安装与启动

在项目根目录运行：

```powershell
./packaging/windows/install.ps1
```

需要 Python 3.10+。脚本自动安装缺失的 .NET 10 SDK 到当前用户目录，发布自带 .NET 运行时的 win-x64 应用，无需管理员权限。Python 使用安装时检测到的解释器，没有额外 Python 库或 NuGet 库。当前不包含可迁移到另一台电脑的 Python 运行时。

程序安装到 `%LOCALAPPDATA%\Programs\CodexUsageSupervisor`，桌面和开始菜单有快捷方式。默认启动显示用量浮窗；右键托盘可刷新、打开设置或退出。Windows 可能把图标放在任务栏的隐藏图标区域，可手动拖到可见区域。

- 图标数字是短窗口的**已用百分比**，绿 / 黄 / 红对应低于 70%、70–89%、90% 以上。
- 灰色数字表示账户查询失败后使用的本地历史快照；`?` 表示不可用。
- 点击图标查看两个额度窗口、重置时间、今日活动和最近五个任务。
- 设置中可修改数据目录、刷新间隔，以及选择登录自动启动（默认关闭）。
- 单实例运行；关闭浮窗只是收起，右键“退出”才停止监控。
- 本地 token 和专注时间是估算值，不是账单。任务名来自本地会话索引，界面不展示完整对话内容。

设置保存在 `%APPDATA%\codex-usage-supervisor\settings.json`。优先使用 `CODEX_HOME` 作为默认数据目录；更改目录后账户查询也使用该目录。可用 `CODEX_EXECUTABLE` 指定原生 Codex 可执行文件。自动发现 Codex 桌面版、PATH 和 npm 包中的 Windows 原生二进制。

## 架构与恢复

WPF 使用 Windows Forms NotifyIcon 提供动态托盘图标；WPF 和 Python 通过私有 stdin/stdout JSON 行通信，不监听网络端口。后端按请求刷新，缓存未更改会话文件。账户请求有 8 秒超时，UI 后端请求有 2 分钟超时；异常后下次刷新重启后端。正常退出会回收整个子进程树。客户端保持响应，不在 UI 线程解析日志。

Linux D-Bus 入口保持原状，GI 只在启动 D-Bus 时导入。`service --once` 和 Windows 后端无需 GI。

## 验证与开发

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -v
& "$env:LOCALAPPDATA/Microsoft/dotnet/dotnet.exe" build windows/CodexUsageSupervisor -c Release
```

安装后可运行 `CodexUsageSupervisor.exe --smoke-test`：从真实后端读取数据，渲染浮窗到安装目录中的 `smoke-test.png` 并退出；`smoke-test.txt` 记录数据来源和连接结果。先退出已运行的实例。该图像可能包含本地任务名称，仅用于本地验证。

重新安装前先从托盘退出。卸载：`./packaging/windows/uninstall.ps1`，保留个人设置以及 Python/.NET SDK。

当前是本机安装脚本版本，没有 MSIX、代码签名或自动更新。多显示器定位按鼠标所在屏幕工作区；混合 DPI、任务栏自动隐藏等组合仍需实际使用验证。
