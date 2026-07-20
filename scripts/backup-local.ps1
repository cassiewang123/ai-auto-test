[CmdletBinding()]
param(
    [string]$BackupRoot = ".backups"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

try {
    $projectRoot = Get-AiretestProjectRoot
    $pythonPath = Resolve-AiretestPython
    & $pythonPath (Join-Path $PSScriptRoot "local_data.py") `
        --project-root $projectRoot `
        --backup-root $BackupRoot `
        backup
    if ($LASTEXITCODE -ne 0) {
        throw "Local data backup failed with exit code $LASTEXITCODE."
    }
}
catch {
    Write-Host ""
    Write-Host ("[ERROR] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
