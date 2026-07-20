[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$BackendPort = 8001
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

try {
    $projectRoot = Get-AiretestProjectRoot
    $runtimeDir = Join-Path $projectRoot ".runtime"
    $logDir = Join-Path $runtimeDir "logs"
    $pythonPath = Resolve-AiretestPython
    $pathsJson = & $pythonPath (Join-Path $PSScriptRoot "local_data.py") `
        --project-root $projectRoot paths
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve local data paths."
    }
    $dataPaths = $pathsJson | ConvertFrom-Json
    $databasePath = [string]$dataPaths.database
    $artifactPath = [string]$dataPaths.artifact_root
    $legacyArtifactPath = [string]$dataPaths.legacy_artifact_root
    $backupRoot = [string]$dataPaths.backup_root

    $backend = Get-AiretestManagedProcess `
        -PidFile (Join-Path $runtimeDir "backend.pid") `
        -CommandMarker "backend\run_server.py"
    $frontend = Get-AiretestManagedProcess `
        -PidFile (Join-Path $runtimeDir "frontend.pid") `
        -CommandMarker "vite.js"

    $backendText = if ($backend.Exists -and $backend.Managed) {
        "running (PID $($backend.ProcessId))"
    }
    elseif ($backend.Exists) {
        "PID file belongs to another process"
    }
    else {
        "not running"
    }
    $frontendText = if ($frontend.Exists -and $frontend.Managed) {
        "running (PID $($frontend.ProcessId))"
    }
    elseif ($frontend.Exists) {
        "PID file belongs to another process"
    }
    else {
        "not running"
    }

    $backendReady = Test-AiretestHttp `
        -Uri "http://127.0.0.1:$BackendPort/health/ready"
    $frontendReady = Test-AiretestHttp -Uri "http://127.0.0.1:5173"

    Write-Host "AIRETEST local status:"
    Write-Host "  Backend process: $backendText"
    Write-Host "  Backend URL: http://127.0.0.1:$BackendPort"
    Write-Host "  Backend ready: $backendReady"
    Write-Host "  Frontend process: $frontendText"
    Write-Host "  Frontend ready: $frontendReady"

    if (Test-Path -LiteralPath $databasePath -PathType Leaf) {
        $database = Get-Item -LiteralPath $databasePath
        Write-Host "  SQLite: $($database.FullName) ($($database.Length) bytes)"
    }
    else {
        Write-Host "  SQLite: not created"
    }
    Write-Host "  Artifacts: $artifactPath"
    if (
        $legacyArtifactPath -ne $artifactPath -and
        (Test-Path -LiteralPath $legacyArtifactPath -PathType Container)
    ) {
        Write-Host "  Legacy artifacts: $legacyArtifactPath"
    }
    Write-Host "  Backups: $backupRoot"
    Write-Host "  Logs: $logDir"

    if (-not $backendReady) {
        exit 1
    }
}
catch {
    Write-Host ""
    Write-Host ("[ERROR] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
