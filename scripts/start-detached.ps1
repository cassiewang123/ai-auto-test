[CmdletBinding()]
param(
    [switch]$SkipFrontend,

    [ValidateRange(1024, 65535)]
    [int]$BackendPort = 8001,

    [ValidateRange(15, 300)]
    [int]$WaitSeconds = 120
)

# 以「完全脱离控制台」的方式启动 AIRETEST 前后端。
#
# 踩过的两个坑：
#   1. Start-Process 启动的进程是当前进程树的子进程，关掉终端/宿主回收任务时
#      会被一并结束；
#   2. 改用 WMI 拉起 `cmd.exe /c xxx` 后，cmd 会分配控制台，node 挂在该控制台
#      上，控制台被回收时 node 收到 CTRL_CLOSE_EVENT 退出 —— 表现为前端启动
#      成功一段时间后自己没了，日志里却没有任何报错（pythonw 不挂控制台，
#      所以只有前端反复退出）。
#
# 现在统一由 scripts\_spawn_detached.py 以 DETACHED_PROCESS 启动真实程序，
# 子进程既不继承也不新建控制台，因此终端关闭、会话结束都不影响服务。
#
# 用法：
#   powershell -File scripts\start-detached.ps1
#   powershell -File scripts\start-detached.ps1 -SkipFrontend
# 停止：scripts\stop-detached.ps1

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

$projectRoot = Get-AiretestProjectRoot
$runtimeDir = Join-Path $projectRoot ".runtime"
$logDir = Join-Path $runtimeDir "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$pythonPath = Resolve-AiretestPython
$spawnScript = Join-Path $PSScriptRoot "_spawn_detached.py"
if (-not (Test-Path -LiteralPath $spawnScript -PathType Leaf)) {
    throw "缺少启动器：$spawnScript"
}

function Start-DetachedService {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )

    $stdoutLog = Join-Path $logDir "backend.out.log"
    $stderrLog = Join-Path $logDir "backend.err.log"
    if ($DisplayName -eq "前端") {
        $stdoutLog = Join-Path $logDir "frontend.out.log"
        $stderrLog = Join-Path $logDir "frontend.err.log"
    }

    $spawnArgs = @(
        $spawnScript,
        $WorkingDirectory,
        $stdoutLog,
        $stderrLog,
        "--",
        $Executable
    ) + $Arguments

    $output = & $pythonPath @spawnArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$DisplayName 启动失败：$($output -join [Environment]::NewLine)"
    }
    $childPid = ([string]($output | Select-Object -Last 1)).Trim()
    Write-Host "$DisplayName 启动中，PID：$childPid"
}

# ---------------- 后端 ----------------
if (-not (Test-AiretestPortInUse -Port $BackendPort)) {
    $pythonwPath = Join-Path (Split-Path -Parent $pythonPath) "pythonw.exe"
    if (-not (Test-Path -LiteralPath $pythonwPath -PathType Leaf)) {
        $pythonwPath = $pythonPath
    }
    Start-DetachedService -WorkingDirectory $projectRoot `
        -Executable $pythonwPath `
        -Arguments @("backend\run_server.py") `
        -DisplayName "后端"
}
else {
    Write-Host "后端端口 $BackendPort 已在监听，跳过启动。"
}

if (-not (Wait-AiretestHttp -Uri "http://127.0.0.1:$BackendPort/health/ready" `
    -TimeoutSeconds $WaitSeconds)) {
    $tail = if (Test-Path -LiteralPath (Join-Path $logDir "backend.err.log")) {
        (Get-Content -LiteralPath (Join-Path $logDir "backend.err.log") -Tail 20 `
            -ErrorAction SilentlyContinue) -join [Environment]::NewLine
    }
    else { "" }
    throw "后端未在 $WaitSeconds 秒内就绪。$([Environment]::NewLine)$tail"
}

# ---------------- 前端 ----------------
if (-not $SkipFrontend) {
    $frontendDir = Join-Path $projectRoot "frontend"
    if (-not (Test-AiretestPortInUse -Port 5173)) {
        $nodePath = Resolve-AiretestNode -PythonPath $pythonPath
        Start-DetachedService -WorkingDirectory $frontendDir `
            -Executable $nodePath `
            -Arguments @(
                "node_modules\vite\bin\vite.js",
                "--host", "127.0.0.1",
                "--port", "5173",
                "--strictPort"
            ) `
            -DisplayName "前端"
    }
    else {
        Write-Host "前端端口 5173 已在监听，跳过启动。"
    }

    if (-not (Wait-AiretestHttp -Uri "http://127.0.0.1:5173" `
        -TimeoutSeconds $WaitSeconds)) {
        $tail = if (Test-Path -LiteralPath (Join-Path $logDir "frontend.err.log")) {
            (Get-Content -LiteralPath (Join-Path $logDir "frontend.err.log") -Tail 20 `
                -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }
        else { "" }
        throw "前端未在 $WaitSeconds 秒内就绪。$([Environment]::NewLine)$tail"
    }
}

# 清理旧 launcher（曾被 WMI 使用，现已不再需要），避免误导排查
foreach ($stale in @("start-backend.cmd", "start-frontend.cmd", "start-frontend.vbs")) {
    Remove-Item -LiteralPath (Join-Path $runtimeDir $stale) -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "AIRETEST 已以后台方式启动（关闭终端不会停止服务）："
Write-Host "  前端：http://localhost:5173"
Write-Host "  后端：http://localhost:$BackendPort"
Write-Host "  API 文档：http://localhost:$BackendPort/docs"
Write-Host "  日志：$logDir"
