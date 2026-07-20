[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,

    [string]$BackupRoot = ".backups"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

try {
    $projectRoot = Get-AiretestProjectRoot
    $runtimeDir = Join-Path $projectRoot ".runtime"
    $backend = Get-AiretestManagedProcess `
        -PidFile (Join-Path $runtimeDir "backend.pid") `
        -CommandMarker "backend\run_server.py"
    $frontend = Get-AiretestManagedProcess `
        -PidFile (Join-Path $runtimeDir "frontend.pid") `
        -CommandMarker "vite.js"
    if (($backend.Exists -and $backend.Managed) -or
        ($frontend.Exists -and $frontend.Managed)) {
        throw "Run .\scripts\stop-local.ps1 before restoring data."
    }

    $pythonPath = Resolve-AiretestPython
    $tool = Join-Path $PSScriptRoot "local_data.py"
    $resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path

    & $pythonPath $tool --project-root $projectRoot `
        --backup-root $BackupRoot verify $resolvedBackup
    if ($LASTEXITCODE -ne 0) {
        throw "Backup verification failed."
    }

    Write-Host "Creating a pre-restore safety backup..."
    & $pythonPath $tool --project-root $projectRoot `
        --backup-root $BackupRoot backup
    if ($LASTEXITCODE -ne 0) {
        throw "The pre-restore safety backup failed."
    }

    & $pythonPath $tool --project-root $projectRoot `
        --backup-root $BackupRoot restore $resolvedBackup
    if ($LASTEXITCODE -ne 0) {
        throw "Local data restore failed."
    }

    Push-Location (Join-Path $projectRoot "backend")
    try {
        & $pythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "The post-restore database migration failed."
        }
    }
    finally {
        Pop-Location
    }

    Write-Host "Restore completed. Run .\scripts\start-local.ps1."
}
catch {
    Write-Host ""
    Write-Host ("[ERROR] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
