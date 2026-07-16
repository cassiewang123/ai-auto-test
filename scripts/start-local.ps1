[CmdletBinding()]
param(
    [switch]$SkipFrontend,

    [ValidateRange(15, 300)]
    [int]$WaitSeconds = 90
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "local-runtime.ps1")

try {
    $projectRoot = Get-AiretestProjectRoot
    $backendDir = Join-Path $projectRoot "backend"
    $frontendDir = Join-Path $projectRoot "frontend"
    $envFile = Join-Path $projectRoot ".env"
    $runtimeDir = Join-Path $projectRoot ".runtime"
    $logDir = Join-Path $runtimeDir "logs"
    $backendPidFile = Join-Path $runtimeDir "backend.pid"
    $frontendPidFile = Join-Path $runtimeDir "frontend.pid"

    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        throw "未找到 .env。请执行 Copy-Item .env.example .env，并生成本地密钥。"
    }

    New-Item -ItemType Directory -Path $runtimeDir,$logDir -Force | Out-Null

    $pythonPath = Resolve-AiretestPython
    Write-Host "Python：$pythonPath"

    & $pythonPath -c "import alembic, fastapi, sqlalchemy, uvicorn" 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "后端依赖不完整。请执行：python -m pip install -r backend\requirements.txt"
    }

    $settingsProbe = @"
import sys
sys.path.insert(0, sys.argv[1])
from app.config import get_settings
s = get_settings()
print(s.DATABASE_URL)
print(s.TASK_DISPATCH_MODE)
print(s.ARTIFACT_ROOT)
"@
    Push-Location $projectRoot
    try {
        $settingsOutput = @(& $pythonPath -c $settingsProbe $backendDir)
        if ($LASTEXITCODE -ne 0) {
            throw "无法读取本地配置。"
        }
    }
    finally {
        Pop-Location
    }
    if ($settingsOutput.Count -lt 3) {
        throw "本地配置输出不完整。"
    }
    $databaseUrl = [string]$settingsOutput[0]
    $dispatchMode = [string]$settingsOutput[1]

    if (-not $databaseUrl.StartsWith("sqlite")) {
        throw "轻量模式要求 DATABASE_URL 使用 SQLite，当前值为：$databaseUrl"
    }
    if ($dispatchMode -ne "local") {
        throw "轻量模式要求 TASK_DISPATCH_MODE=local，当前值为：$dispatchMode"
    }

    $migrationUrl = $databaseUrl
    if ($databaseUrl.StartsWith("sqlite:///./")) {
        $relativePath = $databaseUrl.Substring("sqlite:///".Length)
        $databasePath = [System.IO.Path]::GetFullPath(
            (Join-Path $projectRoot $relativePath)
        )
        $migrationUrl = "sqlite:///" + $databasePath.Replace("\", "/")
    }

    $previousDatabaseUrl = $env:DATABASE_URL
    $env:DATABASE_URL = $migrationUrl
    try {
        Write-Host "正在升级 SQLite 数据库..."
        Push-Location $backendDir
        try {
            & $pythonPath -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) {
                throw "Alembic 迁移失败，退出码：$LASTEXITCODE"
            }
        }
        finally {
            Pop-Location
        }

        $backend = Get-AiretestManagedProcess -PidFile $backendPidFile `
            -CommandMarker "backend\run_server.py"
        if ($backend.Exists -and $backend.Managed) {
            Write-Host "后端已运行，PID：$($backend.ProcessId)"
        }
        else {
            if (Test-AiretestPortInUse -Port 8000) {
                throw "端口 8000 已被非 AIRETEST 进程占用。"
            }
            Remove-Item -LiteralPath $backendPidFile -Force `
                -ErrorAction SilentlyContinue

            $backendOut = Join-Path $logDir "backend.out.log"
            $backendErr = Join-Path $logDir "backend.err.log"
            $backendProcess = Start-Process -FilePath $pythonPath `
                -ArgumentList @("backend\run_server.py") `
                -WorkingDirectory $projectRoot `
                -WindowStyle Hidden `
                -RedirectStandardOutput $backendOut `
                -RedirectStandardError $backendErr `
                -PassThru
            Set-Content -LiteralPath $backendPidFile `
                -Value $backendProcess.Id -Encoding ascii
            Write-Host "后端启动中，PID：$($backendProcess.Id)"
        }

        if (-not (Wait-AiretestHttp -Uri "http://127.0.0.1:8000/health/ready" `
            -TimeoutSeconds $WaitSeconds)) {
            $errorTail = if (Test-Path -LiteralPath (Join-Path $logDir "backend.err.log")) {
                (Get-Content -LiteralPath (Join-Path $logDir "backend.err.log") `
                    -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
            }
            else {
                ""
            }
            throw "后端未在 $WaitSeconds 秒内就绪。$([Environment]::NewLine)$errorTail"
        }

        if (-not $SkipFrontend) {
            $nodePath = Resolve-AiretestNode -PythonPath $pythonPath
            $viteEntry = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
            if (-not (Test-Path -LiteralPath $viteEntry -PathType Leaf)) {
                $npmPath = Resolve-AiretestNpm -NodePath $nodePath
                Write-Host "正在安装前端依赖..."
                Push-Location $frontendDir
                try {
                    & $npmPath ci
                    if ($LASTEXITCODE -ne 0) {
                        throw "npm ci 失败，退出码：$LASTEXITCODE"
                    }
                }
                finally {
                    Pop-Location
                }
            }

            $frontend = Get-AiretestManagedProcess -PidFile $frontendPidFile `
                -CommandMarker "vite.js"
            if ($frontend.Exists -and $frontend.Managed) {
                Write-Host "前端已运行，PID：$($frontend.ProcessId)"
            }
            else {
                if (Test-AiretestPortInUse -Port 5173) {
                    throw "端口 5173 已被非 AIRETEST 进程占用。"
                }
                Remove-Item -LiteralPath $frontendPidFile -Force `
                    -ErrorAction SilentlyContinue

                $frontendOut = Join-Path $logDir "frontend.out.log"
                $frontendErr = Join-Path $logDir "frontend.err.log"
                $frontendProcess = Start-Process -FilePath $nodePath `
                    -ArgumentList @(
                        $viteEntry,
                        "--host", "127.0.0.1",
                        "--port", "5173",
                        "--strictPort"
                    ) `
                    -WorkingDirectory $frontendDir `
                    -WindowStyle Hidden `
                    -RedirectStandardOutput $frontendOut `
                    -RedirectStandardError $frontendErr `
                    -PassThru
                Set-Content -LiteralPath $frontendPidFile `
                    -Value $frontendProcess.Id -Encoding ascii
                Write-Host "前端启动中，PID：$($frontendProcess.Id)"
            }

            if (-not (Wait-AiretestHttp -Uri "http://127.0.0.1:5173" `
                -TimeoutSeconds $WaitSeconds)) {
                throw "前端未在 $WaitSeconds 秒内就绪，请检查 .runtime\logs。"
            }
        }
    }
    finally {
        $env:DATABASE_URL = $previousDatabaseUrl
    }

    Write-Host ""
    Write-Host "AIRETEST 轻量单机模式已启动："
    if (-not $SkipFrontend) {
        Write-Host "  前端：http://localhost:5173"
    }
    Write-Host "  后端：http://localhost:8000"
    Write-Host "  API 文档：http://localhost:8000/docs"
    Write-Host "  数据库：$migrationUrl"
    Write-Host "  日志：$logDir"
}
catch {
    Write-Host ""
    Write-Host ("[错误] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
