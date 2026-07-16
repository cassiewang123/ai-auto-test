[CmdletBinding()]
param(
    [switch]$Distributed,
    [switch]$ObjectStorage,

    [ValidateRange(30, 900)]
    [int]$DockerWaitSeconds = 180
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

function Test-PendingWindowsRestart {
    $rebootKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
    )
    foreach ($key in $rebootKeys) {
        if (Test-Path -LiteralPath $key) {
            return $true
        }
    }

    $sessionManager = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager"
    $pendingRenames = (Get-ItemProperty -LiteralPath $sessionManager `
        -Name PendingFileRenameOperations -ErrorAction SilentlyContinue).PendingFileRenameOperations
    return ($null -ne $pendingRenames)
}

function Resolve-DockerExecutable {
    $command = Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $command) {
        return $command.Path
    }

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
        $candidates += Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramW6432)) {
        $candidates += Join-Path $env:ProgramW6432 "Docker\Docker\resources\bin\docker.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates += Join-Path $env:LOCALAPPDATA "Docker\resources\bin\docker.exe"
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\resources\bin\docker.exe"
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    if (Test-PendingWindowsRestart) {
        throw "未检测到 docker.exe，且 Windows 正在等待重启以完成虚拟化组件配置。请先重启电脑，再安装或启动 Docker Desktop。"
    }

    throw "未检测到 docker.exe。请先安装 Docker Desktop，并确认 Docker CLI 已加入 PATH 或安装在默认目录。"
}

function Resolve-DockerDesktopExecutable {
    $command = Get-Command "Docker Desktop.exe" -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $command) {
        return $command.Path
    }

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
        $candidates += Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramW6432)) {
        $candidates += Join-Path $env:ProgramW6432 "Docker\Docker\Docker Desktop.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates += Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe"
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\Docker Desktop.exe"
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Test-DockerDaemon {
    param([Parameter(Mandatory = $true)][string]$DockerPath)

    & $DockerPath info --format "{{.ServerVersion}}" > $null 2>&1
    return ($LASTEXITCODE -eq 0)
}

function Assert-DockerCompose {
    param([Parameter(Mandatory = $true)][string]$DockerPath)

    & $DockerPath compose version > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "已找到 docker.exe，但 Docker Compose v2 不可用。请更新 Docker Desktop。"
    }
}

function Wait-DockerDaemon {
    param(
        [Parameter(Mandatory = $true)][string]$DockerPath,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $nextReport = 15

    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        if (Test-DockerDaemon -DockerPath $DockerPath) {
            $stopwatch.Stop()
            return
        }

        if ($stopwatch.Elapsed.TotalSeconds -ge $nextReport) {
            Write-Host ("仍在等待 Docker daemon，已等待 {0} 秒..." -f $nextReport)
            $nextReport += 15
        }
        Start-Sleep -Seconds 3
    }

    $stopwatch.Stop()
    throw "等待 Docker daemon 超时（$TimeoutSeconds 秒）。请打开 Docker Desktop 查看启动错误，然后重试。"
}

try {
    $projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    $composeFile = Join-Path $projectRoot "docker-compose.yml"
    $envFile = Join-Path $projectRoot ".env.oracle"
    $envExampleFile = Join-Path $projectRoot ".env.oracle.example"

    if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf)) {
        throw "未找到 Compose 文件：$composeFile"
    }
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        $hint = if (Test-Path -LiteralPath $envExampleFile -PathType Leaf) {
            "请先执行：Copy-Item `"$envExampleFile`" `"$envFile`"，并检查其中的 Oracle 和本地密码。"
        }
        else {
            "请先在项目根目录创建 .env.oracle。"
        }
        throw "未找到本地配置文件：$envFile。$hint"
    }

    $dockerPath = Resolve-DockerExecutable
    Write-Host "Docker CLI：$dockerPath"

    if (-not (Test-DockerDaemon -DockerPath $dockerPath)) {
        $desktopPath = Resolve-DockerDesktopExecutable
        if ([string]::IsNullOrWhiteSpace($desktopPath)) {
            throw "Docker daemon 未启动，且未在默认目录找到 Docker Desktop。请手动启动 Docker Engine 后重试。"
        }

        $desktopProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($null -eq $desktopProcess) {
            Write-Host "Docker daemon 未启动，正在启动 Docker Desktop..."
            Start-Process -FilePath $desktopPath -WindowStyle Hidden | Out-Null
        }
        else {
            Write-Host "Docker Desktop 已启动，正在等待 Docker daemon 就绪..."
        }

        Wait-DockerDaemon -DockerPath $dockerPath -TimeoutSeconds $DockerWaitSeconds
    }

    Assert-DockerCompose -DockerPath $dockerPath

    $composeArguments = @(
        "compose",
        "--project-directory", $projectRoot,
        "--file", $composeFile,
        "--env-file", $envFile
    )
    if ($Distributed) {
        $composeArguments += @("--profile", "distributed")
    }
    if ($ObjectStorage) {
        $composeArguments += @("--profile", "object-storage")
    }
    $composeArguments += @("up", "-d", "--build")
    if ($Distributed) {
        $composeArguments += @("--scale", "worker-local=0")
    }

    Write-Host ""
    Write-Host "正在构建并启动 AIRETEST 本地单机环境..."
    & $dockerPath @composeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up 执行失败，退出码：$LASTEXITCODE。请检查上方构建或容器日志。"
    }

    $psArguments = @(
        "compose",
        "--project-directory", $projectRoot,
        "--file", $composeFile,
        "--env-file", $envFile
    )
    if ($Distributed) {
        $psArguments += @("--profile", "distributed")
    }
    if ($ObjectStorage) {
        $psArguments += @("--profile", "object-storage")
    }
    $psArguments += @("ps")

    Write-Host ""
    & $dockerPath @psArguments

    Write-Host ""
    Write-Host "AIRETEST 本地服务已提交启动："
    Write-Host "  前端：http://localhost:5173"
    Write-Host "  后端：http://localhost:8000"
    Write-Host "  API 文档：http://localhost:8000/docs"
    if ($ObjectStorage) {
        Write-Host "  MinIO Console：http://localhost:9001"
    }
    Write-Host ""
    Write-Host "使用 .\scripts\status-docker.ps1 查看 Docker 服务健康状态。"
}
catch {
    Write-Host ""
    Write-Host ("[错误] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
