# AIRETEST 并行开发计划

## 单机使用范围

自 2026-07-15 起，平台范围确定为个人本机使用，不安排生产发布。自
2026-07-16 起，默认运行拓扑改为 SQLite、FastAPI、Vite 和本地线程调度，
不依赖 Docker、Oracle、Redis 或 Celery Worker。Oracle/Redis/Celery、
三 Worker 分布式模式与 MinIO 作为可选完整模式保留。

## 0. 迭代一完成更新

截至 2026-07-16，迭代一的默认轻量模式和自动化集成已经完成：

- API、UI Case、UI Suite、Performance 均已接入统一任务中心真实执行。
- UI/性能任务不再使用占位成功。
- 用户脚本移到可终止子进程，生产环境拒绝同步执行和本地 fallback。
- 通知、报告、历史和 CI/CD 已补项目级权限边界。
- 默认 SQLite migration、本地 PID/日志/端口管理和健康检查已完成。
- Oracle/Redis/Celery/MinIO Compose 健康检查和静态预检作为可选模式保留。
- 任务中心前端已支持实时日志、轮询降级、取消、重试、错误和 Artifact。
- GitHub Actions 已包含后端、Alembic、前端 typecheck、lint、test 和 build。
- 后端与 test-engine 全量测试：`675 passed, 38 warnings`。
- 前端 typecheck 通过；ESLint `0 errors / 740 existing warnings`；
  Vitest `5 passed`；Vite build 通过并保留 `2.43MB` chunk warning。
- Alembic 空库 `upgrade head`、`check`、`downgrade base` 通过。
- API、UI Case、UI Suite、Performance 四类真实任务均以
  `dispatch_mode=local` 执行成功，终态为 `succeeded`。
- 事件链包含 `job.created`、`job.dispatched`、`job.started`、`job.log` 和
  `job.completed`。
- 后端和前端健康检查通过，Artifact 默认写入 `.uploads`。
- SQLite revision 为 `a7d9e2c4f610`，共 54 张表。
- 本地服务仅监听 `127.0.0.1:8000` 和 `127.0.0.1:5173`。
- Windows UI 失败根因已修复：后端不再强制 Selector event loop，保留默认
  Proactor。

剩余工作转为真实 Playwright 浏览器、性能目标和本地数据备份验收。Oracle、
Redis/Celery、GitHub Actions 与远程仓库不再作为当前迭代阻塞项。

## 1. 当前基线

- 默认 `.env` 使用 `sqlite:///./airetest-lite.db`。
- 默认 `TASK_DISPATCH_MODE=local`、`ARTIFACT_ROOT=.uploads`。
- Alembic 包含 53 张业务表的完整基线。
- 项目、任务和 Artifact 已完成第一阶段安全改造。
- 最终并行集成全量自动化测试：675 passed，38 warnings。
- 全项目 Ruff 和 mypy 存量债务尚未清零；本迭代对变更文件执行 Ruff 和定向
  mypy 门禁，全量类型治理单独排期。
- 本地脚本可发现 Python、Node/npm，直接启动 FastAPI 和 Vite。
- SQLite migration、后端 ready 和前端健康已通过；revision 为
  `a7d9e2c4f610`，共 54 张表。
- 初始管理员凭据保存于 `.runtime/initial-admin.txt`。

当前工作流状态：

| 工作流 | 状态 | 已完成 | 待完成 |
|---|---|---|---|
| LOCAL/OPS | 已完成 | SQLite migration、PID、日志、端口、健康检查 | 备份和清理策略 |
| ORA | 可选模式已完成代码 | Oracle 预检、事务回滚、CLOB/IDENTITY 检查、部署文档 | 按需实库验收 |
| EXEC | 默认模式已验收 | local Dispatcher、四类真实执行、取消、幂等、Artifact | 明确重启中断限制 |
| AUTH | 已完成本迭代 | 主要资源、CI Webhook、通知、历史和报告项目隔离 | 全路由持续审计 |
| SEC | 已完成本迭代 | AES-256-GCM、密码/Cookie/Secret/Webhook URL 加密、快照脱敏、迁移脚本 | 多版本密钥轮换 |
| INT | 已完成默认集成 | SQLite、前后端、TestPlan 项目化、全量测试、迁移链 | 浏览器与性能验收 |

## 2. 总体目标

第一阶段目标是把系统从“同步执行的功能原型”推进到可在个人电脑稳定使用：

1. SQLite 可以重复初始化、迁移和备份。
2. 测试任务默认通过 API 进程内 local 线程真实执行。
3. 所有主要业务资源具备项目级权限隔离。
4. 密码、Cookie、Token 和 Webhook Secret 加密存储。
5. 所有改动具备自动化测试和回归验证。
6. Oracle/Celery 完整模式按需启用，不阻塞默认个人使用。

## 3. 并行工作流

### ORA：可选 Oracle 上线验证

负责人：Oracle 子代理

任务：

- ORA-01：实现 Oracle 连接和权限预检。
- ORA-02：检查 Alembic 当前版本与 head。
- ORA-03：检查 53 张业务表是否完整。
- ORA-04：执行 CLOB JSON 写入和读取验证。
- ORA-05：执行 IDENTITY 主键插入验证。
- ORA-06：所有验证数据通过事务回滚或精确清理。
- ORA-07：完善部署与验收文档。

验收：

- 工具默认不修改已有业务数据。
- 数据库权限不足时返回明确错误。
- 无 Oracle 环境时单元测试可通过 mock 运行。
- 实库运行能够输出逐项检查结果和最终退出码。

### EXEC：默认 local 与可选 Celery 任务中心

负责人：任务中心子代理

任务：

- EXEC-01：创建统一 JobDispatcher。
- EXEC-02：按 API、UI、性能测试分配 Celery 队列。
- EXEC-03：`POST /jobs` 改为创建并投递，不在 API 线程同步执行。
- EXEC-04：Celery Task 使用独立数据库 Session。
- EXEC-05：保存 `celery_task_id`。
- EXEC-06：取消任务时调用 revoke。
- EXEC-07：保留项目权限、幂等键和状态机约束。
- EXEC-08：提供测试环境 eager/local fallback。
- EXEC-09：增加异步投递、Worker 执行和取消测试。

验收：

- 创建任务后立即返回 queued 状态。
- API 请求不等待真实测试执行完成。
- local 线程或可选 Worker 能将 queued 更新为 running 和终态。
- 取消 queued/running 任务会撤销队列任务。
- 无 Redis 的单元测试环境仍可重复运行。
- 四类真实 local job 已验证为 `succeeded`，API 事件链及 UI/性能产物完整。

### AUTH：全资源项目权限

负责人：资源权限子代理

任务：

- AUTH-01：扩展统一资源访问辅助函数。
- AUTH-02：工作流按项目隔离。
- AUTH-03：契约版本按项目隔离。
- AUTH-04：质量门禁按项目隔离。
- AUTH-05：缺陷按项目隔离。
- AUTH-06：API 用例和测试计划按项目隔离。
- AUTH-07：UI 用例、套件、元素和定位器按项目隔离。
- AUTH-08：性能测试按项目隔离。
- AUTH-09：补充跨项目 ID 枚举测试。

角色规则：

| 操作 | 最低角色 |
|---|---|
| 列表、详情 | viewer |
| 执行 | tester |
| 创建、修改 | developer |
| 删除、发布、高风险操作 | admin |
| 删除项目 | owner |

验收：

- 普通用户列表中看不到未加入项目的数据。
- 修改 URL 中的资源 ID 不能越权访问。
- 越权统一返回 403，资源不存在返回 404。
- 超级管理员保留跨项目管理能力。

### SEC：敏感字段加密

负责人：数据安全子代理

任务：

- SEC-01：实现带版本前缀的认证加密服务。
- SEC-02：环境数据库密码加密。
- SEC-03：Cookie value 加密。
- SEC-04：通知渠道 Secret 加密。
- SEC-05：Webhook Secret 加密。
- SEC-06：发送通知和签名时透明解密。
- SEC-07：所有普通响应禁止返回明文。
- SEC-08：实现旧明文数据迁移脚本。
- SEC-09：迁移脚本支持 dry-run 和重复执行。
- SEC-10：生产环境密钥缺失时拒绝运行敏感写入。
- SEC-11：通知与 CI Webhook URL 加密存储、脱敏响应和透明解密。
- SEC-12：执行请求、历史、报告和日志中的 Cookie/Authorization 统一脱敏。
- SEC-13：同步、异步、CI 和数据驱动执行统一加载加密环境 Cookie。

验收：

- 数据库中不出现新增明文密码和 Secret。
- 同一字段可以加密后正常解密使用。
- 错误密钥不能产生伪造明文。
- 已加密数据重复迁移不会二次加密。
- API 响应和日志不包含敏感明文。

## 4. 主线程集成任务

- INT-01：审查每个子代理修改范围。
- INT-02：解决共享配置和导入冲突。
- INT-03：检查默认 SQLite migration 和可选 Oracle 基线一致性。
- INT-04：检查 local dispatch、可选 Celery 与项目权限组合行为。
- INT-05：检查加密数据在通知、Webhook 中的使用链路。
- INT-06：运行完整后端与 test-engine 测试。
- INT-07：运行变更文件 Ruff 和定向 mypy。
- INT-08：执行 Alembic 空库升级和 `alembic check`。
- INT-09：生成可选 Oracle offline SQL。
- INT-10：更新最终实施文档和剩余任务列表。
- INT-11：前端测试计划增加项目筛选、必选归属和同项目用例选择。
- INT-12：安全审计并修复解密后敏感值二次落库或进入响应的问题。

## 5. 依赖关系

```text
SQLite 默认迁移 ───────────┐
                           ├─> 主线程集成 ─> 全量验证
Local 任务调度 ────────────┤
                           │
项目级权限 ────────────────┤
                           │
敏感字段加密 ──────────────┘

Oracle/Celery 完整模式 ─────> 可选验收
```

工作流之间原则上独立，但有以下组合验收：

- local/Celery 创建和取消任务必须继续执行项目权限检查。
- 加密模块不能改变 Oracle CLOB/字符串列的可迁移性。
- 权限过滤不能破坏超级管理员和 CI Token 流程。
- SQLite 默认迁移和可选 Oracle 数据迁移都必须识别加密前后的敏感字段。

## 6. 后续迭代

### 第二迭代：执行安全

- SAFE-01：已完成，移除 API 进程内 `exec`。
- SAFE-02：已完成子进程执行；容器级隔离后续增强。
- SAFE-03：限制 CPU、内存、时间、文件和网络。
- SAFE-04：实现真正可终止的运行进程。
- SAFE-05：增加脚本审计和输出大小限制。
- EXEC-10：已完成，UI Case、UI Suite 和 Performance 接入真实 Runner。
- EXEC-11：默认个人模式使用 local 线程；API 重启会中断运行中任务，且没有
  分布式恢复。
- EXEC-12：可选完整模式增加 Redis 中断、Worker 重启、重复投递和任务超时的
  集成测试。

### 第二迭代：密钥与 Secret 治理

- SEC-14：支持多版本解密、在线重加密和可回滚的密钥轮换。
- SEC-15：为 Environment variables 引入显式 Secret 类型或 Secret 引用，
  禁止依赖字段名猜测敏感值。
- SEC-16：生产与 staging 都拒绝默认加密密钥和默认 JWT Secret。
- SEC-17：将生产密钥迁移到 Secret Manager/KMS，API 与 Worker 只读取引用。
- SEC-18：增加敏感列长度预检和逐行迁移失败报告，避免单条异常回滚整个批次。

### 第二迭代：剩余权限边界

- AUTH-10：已完成，CI Webhook 按 `project_id` 校验角色。
- AUTH-11：已完成，通知渠道使用 workspace/admin 边界，规则按项目隔离。
- AUTH-12：已完成，历史和报告补充归属并禁止跨项目访问。
- AUTH-13：对全部路由执行“是否需要认证、是否需要项目作用域”的自动化清单审计。

### 第三迭代：业务闭环

- FLOW-01：实现真实 DAG 节点调度。
- GATE-01：质量门禁接入任务完成事件。
- CONTRACT-01：扩展请求和响应 Schema 差异分析。
- AI-01：AI 调用统一接入治理统计。
- DEFECT-01：实现 Jira、禅道等外部缺陷同步。

### 第四迭代：前端与工程质量

- FE-01：项目成员管理页面。
- FE-02：已完成任务实时日志、取消、重试、错误和 Artifact 页面。
- FE-03：工作流、契约、门禁、缺陷页面。
- QA-01：修复剩余 Ruff 和 mypy 问题。
- QA-02：已完成前端 lockfile、typecheck、lint、test 和生产构建。
- QA-03：增加 Playwright 端到端测试。
- CI-01：本地 Git `main` 分支和 GitHub Actions 已完成；远程分支保护仍待建立。

## 7. 当前交付顺序

1. 完成 TestPlan 项目字段、历史回填、跨项目隔离和前端项目选择。
2. 完成 Cookie 快照脱敏、Webhook URL 加密和历史明文迁移。
3. 运行四条工作流的定向测试与变更文件静态检查。
4. 在默认 `airetest-lite.db` 执行 Alembic migration 和健康检查。
5. 按需生成 Oracle offline SQL，并更新 Oracle 预检 head 断言。
6. 执行后端与 test-engine 全量测试。
7. 执行真实 API Case local dispatch、前端和状态脚本验收。

个人单机正式使用前必须关闭的验收项：

- SQLite migration 完成，后端和前端健康。
- 四类真实 local job 均为 `succeeded`，事件和产物完整。
- 前端 typecheck、lint、Vitest 和生产构建已通过；浏览器 E2E 仍待补做。
- 本地 `.env` 使用 SQLite、local dispatch、独立 JWT 和字段加密密钥，且不提交
  到 Git。
- `.runtime/initial-admin.txt` 仅供所有者本人读取，不提交到 Git。
- 历史敏感数据迁移脚本先 dry-run，再执行并复核统计。

以下项目仅为可选完整模式验收，不阻塞默认个人使用：

- Oracle 实库迁移和 7 项预检。
- Redis/Celery Worker 投递、取消、超时和重启验证。
- Docker Desktop、分布式 Worker 和 MinIO。

本地集成验证结果：

- 全量测试：`675 passed, 38 warnings`。
- 安全、权限、异步、Oracle 等组合回归：`276 passed`，修正旧安全断言后相关
  定向回归 `104 passed`。
- 最终格式调整后的 TestPlan、脱敏和数据驱动回归：`102 passed`。
- 变更文件 Ruff：通过。
- 定向 mypy：26 个核心 source files 无问题。
- Python compileall：通过。
- SQLite 空库 `upgrade head`、`alembic check`、`downgrade base`：通过。
- 默认 SQLite：revision `a7d9e2c4f610`，54 张表；后端和前端健康。
- 监听边界：仅 `127.0.0.1:8000`、`127.0.0.1:5173`。
- API Case `66c5b38b-ae6a-4a18-bc9a-4453f91eaac3`：`succeeded`，
  5 个 created/dispatched/started/log/completed 事件。
- UI Case `b616c144-6a52-4364-bb0f-59ff772e690c`：`succeeded`，
  screenshot + trace。
- UI Suite `12d00a7e-3ee3-4eb0-b909-90fba591263c`：`succeeded`，
  screenshot + report。
- Performance `dd3c4bb6-5c05-4db1-ad1b-a84d96ee81a2`：`succeeded`，
  3 requests/3 success，report artifact。
- 前端：typecheck 通过，ESLint 0 errors/740 warnings，Vitest 5 passed，
  Vite build 通过并有 2.43MB chunk warning。
- Windows UI 修复：`backend/run_server.py` 使用默认 Proactor，不再强制
  Selector。
- Oracle offline SQL：成功生成，包含 `5fbab72fd965` 基线、
  `c4e7a9b2d1f0` TestPlan revision 和 `a7d9e2c4f610` 权限归属 revision。
- Compose YAML、三类 Worker 和共享 Celery/加密变量静态检查：通过。

## 8. Definition of Done

每个任务完成必须满足：

1. 代码实现完成，不保留无说明的占位逻辑。
2. 权限和敏感数据行为有自动化测试。
3. 相关测试全部通过。
4. 变更文件 Ruff 通过。
5. 新增公共函数具备类型标注。
6. 数据库变化具备 Alembic 迁移或明确无需迁移。
7. 配置项同步更新 `.env.example` 和部署文档。
8. 不降低现有 JWT、项目权限和路径安全规则。
