[CmdletBinding()]
param(
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

function Get-ComposeServiceState {
    param(
        [Parameter(Mandatory = $true)][string]$DockerPath,
        [Parameter(Mandatory = $true)][string[]]$ComposeArguments,
        [Parameter(Mandatory = $true)][string]$ServiceName
    )

    $serviceArguments = @($ComposeArguments)
    $serviceArguments += @("ps", "-q", $ServiceName)
    $containerIds = @(& $DockerPath @serviceArguments 2> $null)
    if ($LASTEXITCODE -ne 0) {
        return "查询失败"
    }

    $containerId = $containerIds |
        Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace([string]$containerId)) {
        return "未运行"
    }

    $inspectOutput = @(& $DockerPath inspect ([string]$containerId) 2> $null)
    if ($LASTEXITCODE -ne 0 -or $inspectOutput.Count -eq 0) {
        return "查询失败"
    }

    try {
        $inspectData = @(($inspectOutput -join [Environment]::NewLine) | ConvertFrom-Json)
        $state = $inspectData[0].State
        $healthProperty = $state.PSObject.Properties["Health"]
        if ($null -ne $healthProperty -and $null -ne $state.Health) {
            return [string]$state.Health.Status
        }
        return [string]$state.Status
    }
    catch {
        return "查询失败"
    }
}

function Get-HttpEndpointState {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSeconds = 5
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return "可访问（HTTP $($response.StatusCode)）"
    }
    catch {
        return "不可访问"
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
        throw "Docker daemon 未启动。请启动 Docker Desktop 后重新查询状态。"
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
        Write-Host "[警告] 未找到 .env.oracle，状态查询将使用 Compose 文件中的本地默认值。" -ForegroundColor Yellow
    }
    if ($Distributed) {
        $composeArguments += @("--profile", "distributed")
    }
    if ($ObjectStorage) {
        $composeArguments += @("--profile", "object-storage")
    }

    Write-Host "Docker Compose 可选完整模式服务："
    $psArguments = @($composeArguments)
    $psArguments += @("ps")
    & $dockerPath @psArguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose ps 执行失败，退出码：$LASTEXITCODE。"
    }

    $backendState = Get-ComposeServiceState -DockerPath $dockerPath `
        -ComposeArguments $composeArguments -ServiceName "backend"
    $frontendState = Get-ComposeServiceState -DockerPath $dockerPath `
        -ComposeArguments $composeArguments -ServiceName "frontend"
    $oracleState = Get-ComposeServiceState -DockerPath $dockerPath `
        -ComposeArguments $composeArguments -ServiceName "oracle"
    $redisState = Get-ComposeServiceState -DockerPath $dockerPath `
        -ComposeArguments $composeArguments -ServiceName "redis"
    $localWorkerState = Get-ComposeServiceState -DockerPath $dockerPath `
        -ComposeArguments $composeArguments -ServiceName "worker-local"

    Write-Host ""
    Write-Host "本地服务摘要："
    Write-Host ("  后端容器：{0}" -f $backendState)
    Write-Host ("  后端 Ready：{0}" -f (Get-HttpEndpointState -Uri "http://localhost:8000/health/ready"))
    Write-Host ("  前端容器：{0}" -f $frontendState)
    Write-Host ("  前端页面：{0}" -f (Get-HttpEndpointState -Uri "http://localhost:5173"))
    Write-Host ("  Oracle：{0}" -f $oracleState)
    Write-Host ("  Redis：{0}" -f $redisState)
    Write-Host ("  worker-local：{0}" -f $localWorkerState)

    if ($ObjectStorage) {
        $minioState = Get-ComposeServiceState -DockerPath $dockerPath `
            -ComposeArguments $composeArguments -ServiceName "minio"
        Write-Host ("  MinIO：{0}" -f $minioState)
    }

    if ($Distributed) {
        foreach ($workerName in @("worker-api", "worker-ui", "worker-performance")) {
            $workerState = Get-ComposeServiceState -DockerPath $dockerPath `
                -ComposeArguments $composeArguments -ServiceName $workerName
            Write-Host ("  {0}：{1}" -f $workerName, $workerState)
        }
    }
}
catch {
    Write-Host ""
    Write-Host ("[错误] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
