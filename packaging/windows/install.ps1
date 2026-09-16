param([switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
$dotnet = if ($dotnetCommand) { $dotnetCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Microsoft/dotnet/dotnet.exe' }
if (!(Test-Path -LiteralPath $dotnet)) {
    $installer = Join-Path $env:TEMP 'codex-supervisor-dotnet-install.ps1'
    Invoke-WebRequest 'https://dot.net/v1/dotnet-install.ps1' -OutFile $installer
    & $installer -Channel 10.0 -InstallDir (Join-Path $env:LOCALAPPDATA 'Microsoft/dotnet') -NoPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install .NET SDK' }
}
$python = (Get-Command python -ErrorAction Stop).Source
& $python -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ required' }
$installRoot = Join-Path $env:LOCALAPPDATA 'Programs/CodexUsageSupervisor'
if (Get-Process CodexUsageSupervisor -ErrorAction SilentlyContinue) { throw 'Please exit Codex Usage Supervisor before reinstalling.' }
& $dotnet publish (Join-Path $repoRoot 'windows/CodexUsageSupervisor/CodexUsageSupervisor.csproj') -c Release -r win-x64 --self-contained true -o $installRoot
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
$backend = Join-Path $installRoot 'backend'
New-Item -ItemType Directory -Force $backend | Out-Null
Copy-Item -LiteralPath (Join-Path $repoRoot 'src/codex_usage_supervisor') -Destination $backend -Recurse -Force
@{ python = $python } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $installRoot 'backend.json')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Codex Usage Supervisor.lnk'))
$shortcut.TargetPath = Join-Path $installRoot 'CodexUsageSupervisor.exe'
$shortcut.WorkingDirectory = $installRoot
$shortcut.Save()
$startMenu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Codex Usage Supervisor.lnk'
Copy-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Codex Usage Supervisor.lnk') -Destination $startMenu -Force
Write-Output "Installed to $installRoot"
if (!$NoLaunch) { Start-Process -FilePath (Join-Path $installRoot 'CodexUsageSupervisor.exe') -WindowStyle Hidden }
