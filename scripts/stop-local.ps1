[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

try {
    $projectRoot = Get-AiretestProjectRoot
    $runtimeDir = Join-Path $projectRoot ".runtime"

    Stop-AiretestManagedProcess `
        -PidFile (Join-Path $runtimeDir "frontend.pid") `
        -CommandMarker "vite.js" `
        -DisplayName "前端"
    Stop-AiretestManagedProcess `
        -PidFile (Join-Path $runtimeDir "backend.pid") `
        -CommandMarker "backend\run_server.py" `
        -DisplayName "后端及本地任务子进程"
    Remove-Item -LiteralPath (Join-Path $runtimeDir "frontend.mode") `
        -Force -ErrorAction SilentlyContinue

    Write-Host "SQLite 数据库和 Artifact 已保留。"
}
catch {
    Write-Host ""
    Write-Host ("[错误] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
