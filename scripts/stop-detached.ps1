[CmdletBinding()]
param(
    [int[]]$Ports = @(8001, 5173)
)

# 停止由 scripts\start-detached.ps1 启动的 AIRETEST 前后端。
#
# 通过监听端口定位进程，并校验它确实是本项目的 run_server.py / vite.js，
# 不会误杀其它 Python / Node 程序。

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

$projectRoot = Get-AiretestProjectRoot
$markers = @("run_server.py", "vite.js")
$stopped = 0

foreach ($port in $Ports) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $listener) {
        Write-Host "端口 $port 未被占用。"
        continue
    }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" `
        -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        continue
    }

    $commandLine = [string]$process.CommandLine
    $isProjectService = $false
    foreach ($marker in $markers) {
        if ($commandLine.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $isProjectService = $true
        }
    }
    if (-not $isProjectService) {
        Write-Host "[跳过] 端口 $port 被 $($process.Name)（PID $($process.ProcessId)）占用，" `
            -NoNewline
        Write-Host "但不是 AIRETEST 服务。" -ForegroundColor Yellow
        continue
    }

    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        Write-Host "已停止 $($process.Name)（PID $($process.ProcessId)，端口 $port）"
        $stopped += 1
    }
    catch {
        Write-Host "[警告] 无法停止 PID $($process.ProcessId)：$($_.Exception.Message)" `
            -ForegroundColor Yellow
    }
}

# 清理 PID 文件，避免 start-local.ps1 读到过期内容
foreach ($pidFile in @("backend.pid", "frontend.pid")) {
    $path = Join-Path $projectRoot (Join-Path ".runtime" $pidFile)
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}

if ($stopped -eq 0) {
    Write-Host "没有找到正在运行的 AIRETEST 服务。"
}
else {
    Write-Host "已停止 $stopped 个服务。"
}
