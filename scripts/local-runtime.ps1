Set-StrictMode -Version 2.0

$script:AiretestProjectRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)

function Get-AiretestProjectRoot {
    return $script:AiretestProjectRoot
}

function Resolve-AiretestPython {
    if (-not [string]::IsNullOrWhiteSpace($env:AIRETEST_PYTHON) -and
        (Test-Path -LiteralPath $env:AIRETEST_PYTHON -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $env:AIRETEST_PYTHON).Path
    }

    $command = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notlike "*WindowsApps*" } |
        Select-Object -First 1
    if ($null -ne $command) {
        return $command.Source
    }

    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    throw "未检测到可用的 Python。请安装 Python 3.13，或设置 AIRETEST_PYTHON。"
}

function Resolve-AiretestNode {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if (-not [string]::IsNullOrWhiteSpace($env:AIRETEST_NODE) -and
        (Test-Path -LiteralPath $env:AIRETEST_NODE -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $env:AIRETEST_NODE).Path
    }

    $command = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $command) {
        return $command.Source
    }

    $candidates = @(
        "E:\wxlsoft\node22\node-v22.12.0-win-x64\node.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $playwrightNode = & $PythonPath -c @"
from pathlib import Path
try:
    import playwright
except ImportError:
    raise SystemExit(1)
print(Path(playwright.__file__).resolve().parent / "driver" / "node.exe")
"@ 2> $null
    if ($LASTEXITCODE -eq 0 -and
        -not [string]::IsNullOrWhiteSpace([string]$playwrightNode) -and
        (Test-Path -LiteralPath ([string]$playwrightNode).Trim() -PathType Leaf)) {
        return (Resolve-Path -LiteralPath ([string]$playwrightNode).Trim()).Path
    }

    throw "未检测到可用的 Node.js。请安装 Node.js 22+，或设置 AIRETEST_NODE。"
}

function Resolve-AiretestNpm {
    param([Parameter(Mandatory = $true)][string]$NodePath)

    $command = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $command) {
        return $command.Source
    }

    $candidate = Join-Path (Split-Path -Parent $NodePath) "npm.cmd"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    $knownNpm = "E:\wxlsoft\node22\node-v22.12.0-win-x64\npm.cmd"
    if (Test-Path -LiteralPath $knownNpm -PathType Leaf) {
        return (Resolve-Path -LiteralPath $knownNpm).Path
    }

    throw "frontend/node_modules 不存在，且未检测到 npm.cmd。请安装 Node.js 22+。"
}

function Get-AiretestManagedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$PidFile,
        [Parameter(Mandatory = $true)][string]$CommandMarker
    )

    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) {
        return [pscustomobject]@{
            Exists = $false
            Managed = $false
            ProcessId = $null
            Name = $null
            CommandLine = $null
        }
    }

    $rawPid = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue).Trim()
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId) -or $processId -le 0) {
        return [pscustomobject]@{
            Exists = $false
            Managed = $false
            ProcessId = $null
            Name = $null
            CommandLine = $null
        }
    }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" `
        -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return [pscustomobject]@{
            Exists = $false
            Managed = $false
            ProcessId = $processId
            Name = $null
            CommandLine = $null
        }
    }

    $commandLine = [string]$process.CommandLine
    return [pscustomobject]@{
        Exists = $true
        Managed = $commandLine.IndexOf(
            $CommandMarker,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
        ProcessId = [int]$process.ProcessId
        Name = [string]$process.Name
        CommandLine = $commandLine
    }
}

function Test-AiretestPortInUse {
    param([Parameter(Mandatory = $true)][int]$Port)

    return $null -ne (
        Get-NetTCPConnection -State Listen -LocalPort $Port `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1
    )
}

function Test-AiretestHttp {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSeconds = 3
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing `
            -TimeoutSec $TimeoutSeconds
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Wait-AiretestHttp {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        if (Test-AiretestHttp -Uri $Uri) {
            $watch.Stop()
            return $true
        }
        Start-Sleep -Seconds 2
    }
    $watch.Stop()
    return $false
}

function Stop-AiretestManagedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$PidFile,
        [Parameter(Mandatory = $true)][string]$CommandMarker,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )

    $process = Get-AiretestManagedProcess -PidFile $PidFile `
        -CommandMarker $CommandMarker
    if (-not $process.Exists) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "$DisplayName 未运行。"
        return
    }
    if (-not $process.Managed) {
        Write-Host "[警告] PID $($process.ProcessId) 不属于 AIRETEST，未终止。" `
            -ForegroundColor Yellow
        return
    }

    $taskkill = "C:\Windows\System32\taskkill.exe"
    & $taskkill /PID $process.ProcessId /T /F > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "$DisplayName 已停止。"
}
