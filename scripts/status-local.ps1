[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

try {
    $projectRoot = Get-AiretestProjectRoot
    $runtimeDir = Join-Path $projectRoot ".runtime"
    $logDir = Join-Path $runtimeDir "logs"
    $databasePath = Join-Path $projectRoot "airetest-lite.db"
    $artifactPath = Join-Path $projectRoot "backend\.uploads"

    $backend = Get-AiretestManagedProcess `
        -PidFile (Join-Path $runtimeDir "backend.pid") `
        -CommandMarker "backend\run_server.py"
    $frontend = Get-AiretestManagedProcess `
        -PidFile (Join-Path $runtimeDir "frontend.pid") `
        -CommandMarker "vite.js"

    $backendText = if ($backend.Exists -and $backend.Managed) {
        "运行中（PID $($backend.ProcessId)）"
    }
    elseif ($backend.Exists) {
        "PID 文件已被其他进程复用"
    }
    else {
        "未运行"
    }
    $frontendText = if ($frontend.Exists -and $frontend.Managed) {
        "运行中（PID $($frontend.ProcessId)）"
    }
    elseif ($frontend.Exists) {
        "PID 文件已被其他进程复用"
    }
    else {
        "未运行"
    }

    $backendReady = Test-AiretestHttp -Uri "http://127.0.0.1:8000/health/ready"
    $frontendReady = Test-AiretestHttp -Uri "http://127.0.0.1:5173"

    Write-Host "AIRETEST 轻量单机状态："
    Write-Host "  后端进程：$backendText"
    Write-Host "  后端 Ready：$backendReady"
    Write-Host "  前端进程：$frontendText"
    Write-Host "  前端页面：$frontendReady"

    if (Test-Path -LiteralPath $databasePath -PathType Leaf) {
        $database = Get-Item -LiteralPath $databasePath
        Write-Host "  SQLite：$($database.FullName)（$($database.Length) bytes）"
    }
    else {
        Write-Host "  SQLite：尚未创建"
    }
    Write-Host "  Artifact：$artifactPath"
    Write-Host "  日志目录：$logDir"

    if (-not $backendReady) {
        exit 1
    }
}
catch {
    Write-Host ""
    Write-Host ("[错误] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
