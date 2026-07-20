# AIRETEST 本地单机运行指南

本指南面向个人 Windows 电脑上的默认轻量运行模式。默认模式直接启动本机
Python/FastAPI 和 Node/Vite，使用 SQLite 保存业务数据，不依赖 Docker、
Oracle、Redis 或 Celery Worker。

## 1. 默认运行拓扑

默认 `.env` 的关键配置为：

```dotenv
DATABASE_URL=sqlite:///./airetest-lite.db
TASK_DISPATCH_MODE=local
ARTIFACT_ROOT=.uploads
```

默认拓扑：

```text
Browser
  -> Vite http://127.0.0.1:5173
  -> FastAPI http://127.0.0.1:8000
  -> SQLite ./airetest-lite.db
  -> 本地线程任务调度
  -> backend/.uploads 文件产物
```

该模式已经完成 SQLite 迁移，当前 revision 为 `a7d9e2c4f610`，SQLite 共
54 张表（53 张业务表加 `alembic_version`）。后端和前端健康检查通过，只监听
`127.0.0.1:8000` 和 `127.0.0.1:5173`，不会监听局域网网卡。

四类真实任务均以 `dispatch_mode=local` 执行成功：

| 类型 | Job ID | 结果 |
|---|---|---|
| API Case | `66c5b38b-ae6a-4a18-bc9a-4453f91eaac3` | `succeeded`，5 个事件 |
| UI Case | `b616c144-6a52-4364-bb0f-59ff772e690c` | `succeeded`，产物含 screenshot、trace |
| UI Suite | `12d00a7e-3ee3-4eb0-b909-90fba591263c` | `succeeded`，产物含 screenshot、report |
| Performance | `dd3c4bb6-5c05-4db1-ad1b-a84d96ee81a2` | `succeeded`，3 requests/3 success，含 report |

API Case 的 5 个事件为：

```text
job.created
job.dispatched
job.started
job.log
job.completed
```

最终自动化与前端工程基线：

- 后端：`675 passed, 38 warnings`
- 前端 typecheck：通过
- ESLint：`0 errors / 740 existing warnings`
- Vitest：`5 passed`
- Vite build：通过，存在 `2.43MB` chunk warning
- 浏览器登录：Playwright 已从 `/login` 登录并进入 `/dashboard`

登录成功时 Ant Design 当前会输出一条静态 `message` 与动态主题上下文的警告，
不影响登录和页面使用，列入后续前端告警治理。

## 2. 前置条件

1. Windows PowerShell 5.1 或 PowerShell 7。
2. Python 3.13，或满足项目依赖要求的兼容 Python。
3. Node.js 和 npm。脚本会从 PATH、常见默认安装目录和本机便携目录中查找。
4. 本机端口 `5173` 和 `8001` 未被其他程序占用。
5. 项目根目录存在 `.env`。

默认轻量模式不要求安装 Docker Desktop，也不要求启用 WSL、Hyper-V 或
Virtual Machine Platform。Windows 是否等待重启不构成默认启动阻塞。

## 3. 准备配置与依赖

如果 `.env` 不存在：

```powershell
Copy-Item .env.example .env
```

确认以下配置保持为轻量模式：

```dotenv
DATABASE_URL=sqlite:///./airetest-lite.db
TASK_DISPATCH_MODE=local
TASK_FALLBACK_MODE=disabled
AUTO_CREATE_SCHEMA=false
ARTIFACT_ROOT=.uploads
VITE_AIRETEST_MODE=lite
```

首次准备 Python 依赖时：

```powershell
python -m pip install -r backend\requirements.txt
python -m pip install .\test-engine
```

首次准备前端依赖时：

```powershell
Set-Location frontend
npm ci
Set-Location ..
```

`start-local.ps1` 会检查 Python、Node、后端依赖、前端依赖和端口状态。仅当
`frontend/node_modules` 缺失时才需要 npm 执行 `npm ci`。依赖缺失时应按脚本
给出的路径和命令修复，不需要转向 Docker 模式。

## 4. 启动

在项目根目录执行：

```powershell
.\scripts\start-local.ps1
```

默认使用 `lite` 菜单，只展示个人单机常用功能。需要临时查看全部团队治理功能时：

```powershell
.\scripts\start-local.ps1 -BackendPort 8001 -FrontendMode full
```

再次执行 `-FrontendMode lite` 可切回轻量菜单。切换模式时只会重启本项目管理的
Vite 进程，不会停止其他程序。

脚本直接执行以下流程：

1. 检查 `.env`、Python、Node/npm 和本地依赖。
2. 检查 PID 文件以及 `5173`、`8001` 端口占用。
3. 使用默认 SQLite URL 执行 Alembic migration。
4. 启动 `backend/run_server.py`。
5. 启动本地 Vite。
6. 写入 PID 文件和日志。
7. 等待后端 ready 与前端 HTTP 健康。

启动成功后访问：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8001`
- API 文档：`http://127.0.0.1:8001/docs`

本机 `8000` 端口由 C-Lodop 使用，不属于 AIRETEST，本项目的本地启动和停止脚本
不会操作该端口。

`backend/run_server.py` 已不再强制 `WindowsSelectorEventLoopPolicy`，Windows
继续使用默认 Proactor event loop，UI 任务的 WinSock 失败根因已修复。

当前已完成验收的本地数据库，其管理员账号信息保存在：

```text
.runtime/initial-admin.txt
```

该文件包含本地管理员凭据，只供所有者本人读取，不应提交到版本库、截图或发送
给他人。创建全新 SQLite 数据库时，可在前端登录页选择“注册首个管理员”。

## 5. 查看状态

```powershell
.\scripts\status-local.ps1
```

状态脚本应显示：

- 后端与前端 PID 是否存在且命令行身份匹配。
- 后端 `http://127.0.0.1:8001/health/ready`。
- 前端 HTTP 状态。
- SQLite 数据库路径和文件大小。
- Artifact 与日志目录。

迁移 revision 可单独检查：

```powershell
$env:DATABASE_URL='sqlite:///E:/xlwang/AIRETEST/airetest-lite.db'
Set-Location backend
python -m alembic current
Set-Location ..
```

后端和前端均健康后，才视为轻量模式可用。

## 6. 停止

```powershell
.\scripts\stop-local.ps1
```

停止脚本根据 PID 文件和进程命令行核对身份，只终止本次 AIRETEST 本地进程，
不删除：

- `airetest-lite.db`
- `.uploads`
- `.runtime/initial-admin.txt`
- 历史日志

PID 文件缺失但端口被其他程序占用时，脚本不应自动结束未知进程。

## 7. 备份、恢复和清理

平台运行时可以直接创建一致性 SQLite 备份：

```powershell
.\scripts\backup-local.ps1
```

备份默认保存到 `.backups\airetest-backup-<时间>`，包含 SQLite、当前
Artifact、兼容的 `backend\.uploads` 历史 Artifact，以及
`.runtime\initial-admin.txt`。清单会记录每个文件的 SHA-256。

恢复必须先停止平台：

```powershell
.\scripts\stop-local.ps1
.\scripts\restore-local.ps1 -BackupPath .\.backups\airetest-backup-20260717-120000
.\scripts\start-local.ps1
```

恢复前会校验备份、创建当前数据的安全备份，并在恢复后执行 Alembic 升级。

清理命令默认只预览 30 天以前的旧备份和临时文件：

```powershell
.\scripts\cleanup-local.ps1
.\scripts\cleanup-local.ps1 -RetentionDays 30 -Apply
```

清理孤立任务 Artifact 时需要先停止平台并显式启用：

```powershell
.\scripts\stop-local.ps1
.\scripts\cleanup-local.ps1 -RetentionDays 30 -IncludeArtifacts -Apply
```

## 8. 日志与运行状态

本地 PID、日志和初始管理员信息位于 `.runtime`。排查问题时优先执行：

```powershell
.\scripts\status-local.ps1
```

再查看状态脚本报告的后端和前端日志。不要以“PID 已创建”作为启动成功依据，
必须同时确认进程仍存活、端口正确且 HTTP 健康。

## 9. 本地线程模式限制

`TASK_DISPATCH_MODE=local` 适合个人轻量使用，但有明确限制：

- 任务在线程中由当前 API 进程调度。
- API 进程重启或被强制结束时，运行中的任务会中断。
- 没有独立 Worker 的任务接管、租约、重投递或分布式恢复。
- 不能把本地线程模式视为高可用或多机执行架构。
- 长时间 UI、性能或脚本任务仍应关注取消、超时和子进程残留。

停止或升级 API 前，应先确认没有重要任务处于 `queued` 或 `running` 状态。

## 10. 可选 Oracle/Docker 完整模式

Oracle、Redis、Celery Worker、可选 MinIO 和分布式 Worker 属于完整模式，不是
默认本地使用的前置条件。

完整模式使用独立配置：

```text
.env.oracle
.env.oracle.example
```

启动、状态和停止命令：

```powershell
.\scripts\start-docker.ps1
.\scripts\status-docker.ps1
.\scripts\stop-docker.ps1
```

完整模式需要 Docker Desktop。Oracle 预检、SQLite 到 Oracle 数据迁移和
分布式 Worker 验收见 `ORACLE部署与迁移.md`。

## 11. 常见问题

### PowerShell 禁止执行脚本

仅为当前 PowerShell 进程放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### Python 未找到或依赖缺失

```powershell
python --version
python -m pip show uvicorn alembic sqlalchemy
python -m pip show airetest-engine
```

优先使用项目虚拟环境或已安装依赖的 Python 3.13。不要使用只会跳转 Microsoft
Store 的 WindowsApps Python 占位程序。

### Node/npm 未找到

```powershell
node --version
npm --version
```

脚本会检查 PATH、常见 Node 安装目录、版本管理器目录和本机便携目录。当前 Vite
版本要求 Node `^20.19.0 || >=22.12.0`。

### 端口冲突

`5173` 或 `8000` 被未知进程占用时，先根据状态脚本报告确认 PID 和命令行。不要
为了启动平台而自动结束身份不明的进程。

### 后端 live 但 ready 失败

这通常表示 SQLite URL、文件权限或 migration 存在问题。确认 `.env` 指向
`sqlite:///./airetest-lite.db`，再查看后端日志。不要改用
`AUTO_CREATE_SCHEMA=true` 绕过 Alembic。

### 任务在重启后中断

这是本地线程模式的已知限制。需要跨进程恢复、独立 Worker 或分布式执行时，改用
可选 Oracle/Docker 完整模式。

### Windows UI 任务出现 WinSock 错误

当前后端入口已经移除强制 Selector event loop 的旧兼容逻辑，保留 Windows
默认 Proactor。不要在启动脚本或环境中重新强制
`WindowsSelectorEventLoopPolicy`。
