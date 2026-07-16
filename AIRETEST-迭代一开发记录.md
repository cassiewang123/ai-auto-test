# AIRETEST 迭代一开发记录

> 启动日期：2026-07-15  
> 最近更新：2026-07-16  
> 目标：执行真实性和个人轻量单机运行底座  
> 当前状态：默认轻量模式已完成本机运行验收

## 0. 范围调整

平台仅供所有者本人在本机使用，不以生产发布、多人并发或公网服务为目标。

- 默认模式使用 SQLite、FastAPI、Vite 和本地线程调度。
- 默认模式不依赖 Docker、Oracle、Redis 或 Celery Worker。
- Oracle/Redis/Celery、分布式 Worker 和 MinIO 作为可选完整模式保留。
- 已完成的生产安全守卫和项目权限代码继续保留，不为单机模式做破坏性回退。

默认 `.env` 的权威配置为：

```dotenv
DATABASE_URL=sqlite:///./airetest-lite.db
TASK_DISPATCH_MODE=local
ARTIFACT_ROOT=.uploads
```

## 1. 迭代目标

1. API、UI Case、UI Suite、Performance 通过统一任务中心真实执行。
2. 默认本地模式可以不依赖容器和外部基础设施启动。
3. 任务取消、超时、失败、日志和结果真实可追踪。
4. 通知、报告、历史和 CI/CD 资源完成项目权限审计。
5. SQLite Schema 由 Alembic 管理，并可重复启动。
6. 建立后端/前端自动验证和本地一键启停入口。

## 2. 并行工作流

| 工作流 | 责任范围 | 状态 | 主交付 |
|---|---|---|---|
| EXEC | 统一任务中心、UI/性能真实执行 | 已完成 | 四类任务真实执行 |
| SEC | 脚本隔离、同步执行限制、本地 Runner 取消 | 已完成 | 安全执行边界 |
| AUTH | 通知、报告、历史、CI/CD 权限 | 已完成 | 项目级权限审计 |
| LOCAL/OPS | SQLite、本机进程、PID、日志和健康检查 | 已完成 | 无 Docker 轻量启动 |
| ORA/OPS | Oracle、Redis、Compose 和分布式验收 | 可选模式 | 完整模式入口 |
| FE | 任务中心状态、日志、取消、重试、产物 | 已完成 | 任务中心前端闭环 |
| QA/CI | 后端/前端自动验证 | 已完成 | 可重复质量检查 |

## 3. 默认轻量模式事实

- `scripts/start-local.ps1` 直接启动 Python/FastAPI 和 Node/Vite。
- `scripts/stop-local.ps1` 根据 PID 和进程命令行停止本地进程。
- `scripts/status-local.ps1` 检查 PID、后端 ready、前端、SQLite 和目录状态。
- SQLite migration 已完成。
- 后端与前端健康检查已通过。
- SQLite revision 为 `a7d9e2c4f610`，共 54 张表。
- 服务只监听 `127.0.0.1:8000` 和 `127.0.0.1:5173`。
- Artifact 默认写入 `backend/.uploads`。
- 本次验收管理员凭据保存于 `.runtime/initial-admin.txt`；全新数据库也可通过
  前端注册首个管理员。

四类真实 local job 验收结果：

| 类型 | Job ID | 状态与证据 |
|---|---|---|
| API Case | `66c5b38b-ae6a-4a18-bc9a-4453f91eaac3` | `succeeded`，5 个事件 |
| UI Case | `b616c144-6a52-4364-bb0f-59ff772e690c` | `succeeded`，screenshot + trace |
| UI Suite | `12d00a7e-3ee3-4eb0-b909-90fba591263c` | `succeeded`，screenshot + report |
| Performance | `dd3c4bb6-5c05-4db1-ad1b-a84d96ee81a2` | `succeeded`，3 requests/3 success，report |

API Case 事件为 `job.created`、`job.dispatched`、`job.started`、`job.log` 和
`job.completed`。这些结果证明四类默认本地执行都不是占位成功。

## 4. 集成约束

1. `JobService._run()` 返回的状态只能是 `succeeded`、`failed` 或
   `timed_out`，不能用占位成功表示未执行。
2. 真实执行结果必须写入 `ExecutionAttempt`、`ExecutionJob` 和
   `JobEvent`。
3. UI/性能执行产生的截图、视频、Trace、报告必须通过
   `JobArtifact` 或明确的兼容字段关联到任务。
4. 取消任务不能覆盖已经发生的 `cancelled` 状态。
5. 默认个人模式允许 `TASK_DISPATCH_MODE=local`；生产安全限制继续禁止生产环境
   静默降级到线程或 eager。
6. 项目权限检查必须在创建任务、查看任务、查看结果和触发外部集成时成立。
7. 不允许为了通过测试而绕过真实执行器、权限校验或 Alembic migration。

## 5. 本地线程模式限制

- API 进程重启会中断当前进程内正在运行的任务。
- 运行中任务没有跨进程接管、租约恢复或自动重投递。
- 本地线程取消不能等同于分布式 Worker 的进程级强制终止。
- 本地模式适合个人、低并发和可接受手工重试的场景。
- 需要独立 Worker、Redis 队列或分布式恢复时，使用可选完整模式。

这些限制是当前单机范围的明确边界，不作为默认模式未完成项。

## 6. 本地集成结果

- 后端全量：`675 passed, 38 warnings`。
- SQLite migration：revision `a7d9e2c4f610`，54 张表。
- 后端 `127.0.0.1:8000` 与前端 `127.0.0.1:5173`：健康。
- 前端 typecheck：通过。
- ESLint：`0 errors`，`740 existing warnings`。
- Vitest：`5 passed`。
- Vite build：通过，保留 `2.43MB` chunk warning。
- Playwright 浏览器登录：成功从 `/login` 进入 `/dashboard`；保留一条 Ant
  Design 静态 message 上下文 warning。
- 四类真实 local job：全部 `succeeded`，任务 ID和产物见上表。
- 本地启动、停止和状态脚本：已切换为无 Docker 模式。
- 可选完整模式脚本：`start-docker.ps1`、`stop-docker.ps1`、
  `status-docker.ps1`。
- Windows UI 失败根因已修复：`backend/run_server.py` 不再强制 Selector event
  loop，保留默认 Proactor。

## 7. 迭代一完成标准

- [x] 四类任务都有真实执行路径。
- [x] UI 和性能任务不会在未执行时返回成功。
- [x] 任务取消、超时、失败、重试和事件可追踪。
- [x] 默认 `.env` 使用 SQLite 和 local dispatch。
- [x] SQLite migration 完成。
- [x] 后端和前端健康。
- [x] API、UI Case、UI Suite、Performance 四类 local job 全部成功。
- [x] 本地启动、停止、状态脚本不依赖 Docker。
- [x] 本次验收管理员凭据有明确本地保存位置，新库支持前端注册。
- [x] 前端 typecheck、lint、test、build 可执行。

## 8. 后续工作

默认本地使用不再被以下事项阻塞：

- Windows 重启。
- Docker Desktop 安装。
- Oracle 容器启动。
- Redis/Celery 实机运行。

主线程后续工作：

1. 使用更多真实浏览器场景扩展 UI Case 和 UI Suite 回归。
2. 使用受控目标扩展性能任务和 SLA 验收。
3. 处理或拆分 Vite `2.43MB` chunk warning。
4. 逐步治理 ESLint 740 条存量 warning。
5. 完善 SQLite、`.uploads`、`.runtime` 的备份和清理说明。
6. 按需验收 `.env.oracle` 和 Docker/Oracle 可选完整模式。
