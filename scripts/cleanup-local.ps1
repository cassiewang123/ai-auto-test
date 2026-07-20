[CmdletBinding()]
param(
    [ValidateRange(1, 3650)]
    [int]$RetentionDays = 30,

    [switch]$IncludeArtifacts,

    [switch]$Apply,

    [string]$BackupRoot = ".backups"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

try {
    $projectRoot = Get-AiretestProjectRoot
    if ($Apply -and $IncludeArtifacts) {
        $runtimeDir = Join-Path $projectRoot ".runtime"
        $backend = Get-AiretestManagedProcess `
            -PidFile (Join-Path $runtimeDir "backend.pid") `
            -CommandMarker "backend\run_server.py"
        if ($backend.Exists -and $backend.Managed) {
            throw "Run .\scripts\stop-local.ps1 before cleaning artifacts."
        }
    }

    $pythonPath = Resolve-AiretestPython
    $arguments = @(
        (Join-Path $PSScriptRoot "local_data.py"),
        "--project-root", $projectRoot,
        "--backup-root", $BackupRoot,
        "cleanup",
        "--retention-days", [string]$RetentionDays
    )
    if ($IncludeArtifacts) {
        $arguments += "--include-artifacts"
    }
    if ($Apply) {
        $arguments += "--apply"
    }

    & $pythonPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Local data cleanup failed with exit code $LASTEXITCODE."
    }
    if (-not $Apply) {
        Write-Host "Preview only. Add -Apply to remove the listed items."
    }
}
catch {
    Write-Host ""
    Write-Host ("[ERROR] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
