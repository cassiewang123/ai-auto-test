[CmdletBinding()]
param(
    [switch]$RemoveVolumes,
    [switch]$Distributed,
    [switch]$ObjectStorage
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

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

    throw "未检测到 docker.exe。请先安装 Docker Desktop，并确认 Docker CLI 已加入 PATH 或安装在默认目录。"
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

try {
    $projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    $composeFile = Join-Path $projectRoot "docker-compose.yml"
    $envFile = Join-Path $projectRoot ".env.oracle"

    if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf)) {
        throw "未找到 Compose 文件：$composeFile"
    }

    $dockerPath = Resolve-DockerExecutable
    if (-not (Test-DockerDaemon -DockerPath $dockerPath)) {
        throw "Docker daemon 未启动。停止本地服务需要先启动 Docker Desktop 或对应 Docker Engine。"
    }
    Assert-DockerCompose -DockerPath $dockerPath

    $composeArguments = @(
        "compose",
        "--project-directory", $projectRoot,
        "--file", $composeFile
    )
    if (Test-Path -LiteralPath $envFile -PathType Leaf) {
        $composeArguments += @("--env-file", $envFile)
    }
    else {
        Write-Host "[警告] 未找到 .env.oracle，将使用 Compose 文件中的本地默认值执行停止。" -ForegroundColor Yellow
    }
    if ($Distributed) {
        $composeArguments += @("--profile", "distributed")
    }
    if ($ObjectStorage) {
        $composeArguments += @("--profile", "object-storage")
    }
    $composeArguments += @("down")

    if ($RemoveVolumes) {
        Write-Host "[警告] 将删除 Compose 数据卷，包括本地 Oracle、Redis 和上传数据。" -ForegroundColor Yellow
        $composeArguments += @("--volumes")
    }
    else {
        Write-Host "正在停止 Docker 模式 AIRETEST，本地数据卷将保留..."
    }

    & $dockerPath @composeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose down 执行失败，退出码：$LASTEXITCODE。"
    }

    if ($RemoveVolumes) {
        Write-Host "AIRETEST 已停止，Compose 数据卷已删除。"
    }
    else {
        Write-Host "AIRETEST 已停止，Compose 数据卷已保留。"
    }
}
catch {
    Write-Host ""
    Write-Host ("[错误] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
