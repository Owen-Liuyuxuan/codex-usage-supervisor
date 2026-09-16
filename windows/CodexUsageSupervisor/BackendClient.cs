using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;

namespace CodexUsageSupervisor;

internal sealed class BackendClient : IDisposable
{
    private Process? process;
    private readonly SemaphoreSlim gate = new(1);
    private readonly string root = AppContext.BaseDirectory;

    private void Start()
    {
        if (process is { HasExited: false }) return;
        var config = JsonNode.Parse(File.ReadAllText(Path.Combine(root, "backend.json")))!;
        var info = new ProcessStartInfo(config["python"]!.GetValue<string>())
        {
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true,
            RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8,
            StandardInputEncoding = new UTF8Encoding(false), StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = root
        };
        info.ArgumentList.Add("-u");
        info.ArgumentList.Add("-m");
        info.ArgumentList.Add("codex_usage_supervisor.windows_backend");
        info.Environment["PYTHONPATH"] = Path.Combine(root, "backend");
        process = Process.Start(info) ?? throw new IOException("无法启动 Python 后端");
        process.ErrorDataReceived += (_, _) => { };
        process.BeginErrorReadLine();
    }

    public async Task<JsonNode> Call(string method, JsonNode? settings = null)
    {
        await gate.WaitAsync();
        try
        {
            Start();
            var request = new JsonObject { ["method"] = method };
            if (settings != null) request["settings"] = settings.DeepClone();
            await process!.StandardInput.WriteLineAsync(request.ToJsonString());
            await process.StandardInput.FlushAsync();
            using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(2));
            var line = await process.StandardOutput.ReadLineAsync(timeout.Token);
            var response = JsonNode.Parse(line ?? throw new IOException("后端连接已关闭"))!;
            if (response["error"] is { } error) throw new IOException(error.ToString());
            return response["result"]!.DeepClone();
        }
        catch { Stop(); throw; }
        finally { gate.Release(); }
    }

    private void Stop()
    {
        if (process == null) return;
        try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
        catch (InvalidOperationException) { }
        process.Dispose(); process = null;
    }
    public void Dispose() => Stop();
}
