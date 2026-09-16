$ErrorActionPreference = 'Stop'
if (Get-Process CodexUsageSupervisor -ErrorAction SilentlyContinue) { throw 'Please exit Codex Usage Supervisor first.' }
$expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs/CodexUsageSupervisor'))
if (Test-Path -LiteralPath $expected) {
    $resolved = (Resolve-Path -LiteralPath $expected).Path
    if ($resolved -ne $expected -or (Get-Item -LiteralPath $resolved).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected installation path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Remove-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name CodexUsageSupervisor -ErrorAction SilentlyContinue
foreach ($link in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Codex Usage Supervisor.lnk'), (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Codex Usage Supervisor.lnk'))) {
    if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link }
}
Write-Output 'Uninstalled. Personal settings and Python/.NET installations are preserved.'
