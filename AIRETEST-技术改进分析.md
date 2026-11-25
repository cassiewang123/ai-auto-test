# AIRETEST 技术改进分析

> 分析日期：2026-09-09
> 分析范围：基于当前仓库源码、配置、文档与测试结构。
> 判断原则：项目已有 React 19、Vite、Ant Design、FastAPI、SQLAlchemy、Alembic、Playwright、Locust、Celery 等基础，主要问题不是“换一套框架”，而是补齐生产化架构、业务闭环、数据/任务治理、可观测性、前端工程和 AI 评测链路。

## 1. 结论摘要

AIRETEST 的功能面已经比较宽，当前最值得投入的优先级如下：

1. P0：把任务执行从“进程内线程 + 内存实时数据”推进到可恢复、可观测的队列/工作流体系。
2. P0：把默认数据库和部署形态从“开发版 SQLite + 开发 Dockerfile”整理成可上生产、可迁移、可备份的数据与部署方案。
3. P1：打通工作流、质量门禁、缺陷、通知、报告、覆盖率之间的业务闭环，而不是继续增加孤立模块。
4. P1：补齐可观测性、API 合约、E2E 测试、依赖审计和前端统一数据层。
5. P2：升级 AI 能力形态：从单点 Prompt + 规则 fallback，演进到模型网关、结构化输出、RAG、评测和成本治理。
6. P2：做仓库卫生与工程纪律清理，删除无关文件、缓存/数据库残留，并逐步把静态检查从“非阻断”提升为“阻断门禁”。

## 2. 当前代码中可直接看到的结构性问题

### 2.1 默认任务中心依赖进程内线程

证据：

- `backend/app/services/execution/job_dispatcher.py` 支持 `celery`、`local`、`eager` 三种模式。
- 默认模式是本地线程执行，任务状态和线程对象保存在 `JobDispatcher._local_tasks` 类级字典中。
- API 进程重启后，未完成的任务没有本地恢复机制，现有文档也明确承认 local 线程随 API 重启中断。

改进方向：

- 轻量模式可以保留本地线程，但必须有进程退出前的持久化标记、恢复扫描或重启补偿，避免任务“永久 queued/running”。
- 完整模式应把 Celery 做成真正的生产队列：配置死信队列、自动重试、退避、任务超时、心跳、Worker 丢失检测、Celery Flower 监控。
- 如果后续要把 DAG 工作流、定时任务、门禁联动做成正式能力，建议评估 Temporal、Prefect 或基于 Redis Streams 的调度平台，而不是继续手写状态机加线程。

### 2.2 性能实时数据存在内存中

证据：

- `backend/app/services/perf_runner.py` 调用 `perf_realtime.init_run`，实时指标写入内存存储。
- 单进程本地调试可用，但多 Worker、Docker 扩展、API 重启后会出现实时指标丢失和不可共享问题。

改进方向：

- 使用 Redis Streams/Redis Pub-Sub、WebSocket Gateway 或 SSE 做实时指标通道。
- 数据库只保存最终结果和采样快照，实时流不依赖 API 进程内存。
- 前端实时页面对接一个可重连事件通道，避免依赖“DB 轮询 + WebSocket 读库”。

### 2.3 执行状态与业务事件没有形成统一事件总线

证据：

- 已有 `execution_jobs`、`job_events`、`job_artifacts` 模型。
- 质量门禁目前主要靠手工 `POST /quality-gates/{id}/evaluate` 触发。
- 工作流、缺陷、通知、覆盖率尚未统一订阅任务完成事件，平台现状文档也把这些列为简化实现。

改进方向：

- 设计“任务终态事件”作为核心事件源，例如 `job.completed`、`job.failed`、`gate.passed`、`gate.failed`。
- 使用事务性 Outbox：任务状态和待发布事件写在同一事务，事件发布器再推送到 Redis Streams/NATS/Kafka。
- 质量门禁、通知、报告刷新、缺陷自动创建都成为事件消费者。
- 不要在每个 API 端点中分别硬编码联动逻辑。

### 2.4 API 层存在大量手写 JSON 转换和弱类型

证据：

- `backend/app/api/v1/workflows.py`、`quality_gates.py`、`defects.py` 中存在 `_dump_json`、`_parse_json`、`_serialize` 这类手写转换。
- `defects.py` 等模块直接返回 `PageResponse[dict]` 或 dict 列表，弱化了 Pydantic 响应模型。
- 后端已有 21 个 schema 文件，但业务模块增长后没有严格执行“路由薄、服务厚、DTO 明确”的分层。

改进方向：

- 每个模型响应都提供明确的 Pydantic Response DTO，禁止路由层返回裸 dict。
- 把 JSON Text 字段的读写收敛到模型 helper 或 repository，而不是每个 API 文件重复 `json.dumps`/解析。
- 引入 Repository 或 Service 模式，让测试可以直接覆盖业务逻辑，不用每次都启动 FastAPI TestClient。
- 路由模块只负责参数校验、鉴权、分页、调用服务和响应包装。

### 2.5 前端数据层缺少统一缓存和状态方案

证据：

- `frontend/src/services/api.ts` 是单一大文件，包含很多 `any` 类型。
- `frontend/src/contexts/WorkspaceContext.tsx` 使用 `useEffect` 手动拉取项目和环境，页面刷新后还要重新请求。
- 大量页面大概率各自管理 loading/error/data，缺少缓存失效、重试、防抖和乐观更新机制。

改进方向：

- 引入 TanStack Query 作为服务端状态层，统一缓存、重试、失效、后台刷新和 mutation 后失效。
- 页面组件只消费 query/mutation hooks，不再在 useEffect 中手写请求生命周期。
- 从后端 OpenAPI 生成前端类型和 API Client，例如 `openapi-typescript` 加 Axios wrapper，或 `openapi-fetch`。
- 清理 `any`，统一 `ApiResponse`、分页类型、错误类型。
- 工作区级“项目/环境”属于高频全局选择器，可以保留 Context，但底层仍应使用 Query 缓存。

### 2.6 前端路由与页面已多但工程化仍不足

证据：

- `frontend/src/App.tsx` 一次性静态导入 41 个页面组件。
- 所有页面进入首屏 bundle 或主要 chunk，页面规模继续增长后会越来越慢。
- 前端测试目前主要覆盖布局、认证和少量页面。

改进方向：

- 使用 React Router 的 lazy 路由 + `React.lazy` + Suspense，按 API 测试、UI 测试、性能测试、系统管理做代码分割。
- 使用 Vite 的 manualChunks 对 antd、echarts/chart.js、业务路由做拆分。
- 对高频列表页引入 TanStack Table 或统一表格封装，处理分页、排序、筛选、行选择和批量操作。
- 增加 E2E 测试，覆盖登录、建项目、建环境、Quick Test、执行 API/UI 用例、查看任务和报告。

### 2.7 认证仍是 localStorage JWT

证据：

- `frontend/src/contexts/AuthContext.tsx` 和 `frontend/src/services/http.ts` 都把 access token 放 localStorage。
- WebSocket 任务流目前需要 token 通过查询参数传递，安全性较弱。

改进方向：

- 将 JWT 放在 HttpOnly Secure Cookie，或至少实现短时 access token + refresh token 方案。
- WebSocket 改用 `Sec-WebSocket-Protocol` 子协议承载短时 token，或先通过 REST 换取一次性握手票据，不再把长期 token 放 URL query。
- 如果平台要进入企业使用，建议接入 OIDC/SSO，例如 Keycloak、Authentik、Azure AD、企业微信/钉钉/飞书，并保留本地账号作为管理员兜底。
- 增加 MFA/WebAuthn、密码策略、登录失败限速、账户锁定的现代安全选项。

### 2.8 部署形态偏开发环境

证据：

- `frontend/Dockerfile` 最终命令是 `npx vite`，也就是在容器中运行开发服务器。
- `backend/Dockerfile` 未使用多阶段构建，也未使用非 root 用户。
- CI 中 Ruff 和 mypy 是 `continue-on-error`，当前只是报告不是阻断门禁。

改进方向：

- 前端生产镜像改为 `npm run build` + Nginx/Caddy 静态托管，配置 gzip/brotli、缓存头和 SPA fallback。
- 后端生产镜像使用多阶段安装依赖，缩小镜像体积；以非 root 用户运行；浏览器/浏览器驱动只进入 UI Runner 镜像或按需下载。
- 使用 `uv` 或 PEP 依赖锁文件固定后端依赖；Python requirements 现在使用范围版本，CI 可复现性较弱。
- CI 中静态检查和类型检查应分阶段从“报告”提升为“阻断”，避免技术债继续积累。

## 3. 结合主流技术框架的功能化改进建议

### 3.1 后端与数据层

当前后端技术栈：FastAPI + Pydantic + SQLAlchemy 2 + Alembic。

推荐补齐但不等于重写：

| 改进点 | 建议方案 |
|---|---|
| 生产数据库 | 推荐 PostgreSQL 作为默认生产库，JSONB、并发、索引和 pgvector 都更合适；Oracle 可作为企业兼容选项保留 |
| 异步访问 | SQLAlchemy async + asyncpg 可提升 I/O 场景，但同步 SQLAlchemy 不必立即推倒重来 |
| 任务队列 | Celery + Redis Streams 适合当前单 Worker/队列；复杂 DAG 再评估 Temporal/Prefect |
| 事件与联动 | Redis Streams 或 NATS + Outbox 模式 |
| 数据迁移 | 把早期 `migrate_add_*.py` 收敛到 Alembic 历史，统一执行路径 |
| 时间字段 | 统一 `DateTime(timezone=True)` 和 UTC 语义，避免 SQLite/Oracle 返回时间不一致 |
| ID 类型 | 统一 UUID/有序 UUID 主键策略，避免字符串拼接 |
| 分页 | 统一 cursor/offset 分页规范；大数据量用 cursor pagination |

### 3.2 前端与 API 协作

当前前端技术栈：React 19 + TypeScript + Vite + Ant Design + React Router + Axios。

主流增强点：

- TanStack Query：统一服务端状态、缓存和 mutation。
- openapi-typescript/openapi-fetch：从 FastAPI OpenAPI 生成类型，解决前后端类型漂移。
- TanStack Table：统一管理列表筛选、排序、分页和批量选择。
- React Router lazy 路由：按功能域拆分 bundle。
- React Hook Form + Zod：统一表单校验，尤其适合几十个业务表单页面。
- MSW 或 Mock Service Worker：让前端测试和本地开发不依赖真实后端。
- Storybook 或组件测试：沉淀关键业务组件；不必一开始全覆盖，优先复用的复杂组件。

### 3.3 可观测性

现状：主要依赖 `.runtime/logs`、数据库中的 JobEvent、截图/运行结果文件。

推荐落地一套低成本可观测性栈：

| 层 | 建议 |
|---|---|
| Trace | OpenTelemetry，FastAPI 到 Celery/执行器之间共享 trace_id、job_id、run_id |
| Metrics | Prometheus + `/metrics`，暴露 API 延迟、任务成功率、队列积压、AI 调用数/成本/延迟 |
| Logs | JSON structured logging，统一 request_id/job_id/user_id，接入 Loki 或现有日志平台 |
| Dashboards | Grafana 仪表盘：执行成功率、失败分布、队列积压、Artifact 大小、数据库增长 |
| Alerting | 任务堆积、后端 ready 失败、门禁失败率、AI 成本突增、磁盘空间告警 |

### 3.4 安全改进

| 安全项 | 现状/风险 | 建议 |
|---|---|---|
| Token 存储 | localStorage | HttpOnly Cookie + refresh token，或短期 access token |
| WebSocket 鉴权 | token 在 URL | Sec-WebSocket-Protocol 或握手票据 |
| Secret 管理 | 开发默认密钥，当前单一版本加密 | Vault/KMS、密钥版本轮换、禁止默认 key 启动 |
| 外部访问 | URL 策略已实现 | 生产默认禁止私网地址，启用 IP/域名级出口代理 |
| 脚本执行 | 已移入子进程 | 使用沙箱/容器/资源限制，生产关闭同步执行 |
| 文件安全 | Artifact 目前文件系统 | S3/MinIO + presigned URL + AV 扫描 + 生命周期清理 |
| 审计 | 已有 audit_logs | 增加不可变审计事件、导出能力和权限变更订阅 |
| 依赖安全 | CI 未明显看到漏洞扫描 | 接入 pip-audit、npm audit、SBOM、Renovate/Dependabot |
| RBAC | 已有项目角色 | 构建“路由/资源操作 -> 最低角色”自动化权限矩阵测试 |

### 3.5 AI 功能升级

现状：

- `backend/app/services/ai_service.py` 使用 LangChain + OpenAI，Prompt 为字符串拼接。
- `ai_governance.py` 记录调用、成本、反馈，但整体仍偏单点能力。
- 平台现状说明也指出 AI 统一治理覆盖、评估与成本控制不足。

建议按以下能力演进：

1. 模型网关层

   - 引入 LiteLLM 或自建 provider 抽象，统一 OpenAI、Azure OpenAI、DeepSeek、Qwen、本地模型等通道。
   - 统一支持流式、结构化输出、工具调用和可观测元数据。

2. 结构化输出

   - 从“返回 Python 代码/JSON 文本”改为 Pydantic Structured Output。
   - 对测试用例生成、断言推荐、UI 步骤规划、失败归因定义明确 Schema。
   - 后端保存生成结果和人工编辑记录，便于评测和反馈。

3. RAG 与知识库

   - 将接口知识、缺陷模式、业务规则、历史失败案例改造成可检索知识源。
   - 数据库可采用 PostgreSQL + pgvector，或 Qdrant/Chroma 等向量库。
   - 提供 chunking、embedding、rerank、引用来源和置信度说明。

4. 评测与闭环

   - 建立黄金数据集：接口描述 -> 测试用例、失败结果 -> 归因、录制步骤 -> UI 计划。
   - 计算生成可执行率、人工采纳率、编辑距离、执行通过率、成本和延迟。
   - 通过 A/B 比较 prompt、模型和参数，不要只看“模型能生成”。
   - 每次 AI 调用都返回 invocation_id，前端允许接受/编辑/拒绝，形成持续评估数据。

5. Agent/工作流化

   - 多步骤 AI 任务应进入统一任务中心，而不是在请求线程里同步等待。
   - 例如“读取接口 -> 生成用例 -> 执行 -> 失败归因 -> 建议修复”使用可恢复 DAG 或 Agent 编排。
   - 涉及修改、发布、外发请求的步骤加入人工审批节点。

### 3.6 测试与质量工程

当前已有较好的 pytest 和前端 Vitest，但缺少跨进程 E2E 和现代契约测试。

| 方向 | 建议 |
|---|---|
| API 合约 | 使用 OpenAPI Schema + 快照校验，或 Schemathesis 对公开 API 做属性测试 |
| E2E | Playwright 在 Docker Compose 全栈环境中跑登录、Quick Test、任务中心核心链路 |
| 数据库迁移测试 | CI 已测 SQLite；增加 PostgreSQL/Oracle 临时实例迁移矩阵 |
| 单元测试 | 对 executor、assertion_engine、JSON compare、权限矩阵增加 property-based 测试 |
| 覆盖率 | 设置后端核心服务 80%+、前端核心页面 smoke 测试的最低阈值 |
| 测试隔离 | 使用 Testcontainers 或 compose profile，避免测试污染本地 SQLite |
| 数据一致性 | 对任务状态机增加“任意终态只能出现一次、事件顺序单调”约束测试 |

### 3.7 部署、CI/CD 与仓库治理

| 方向 | 建议 |
|---|---|
| 开发/生产镜像分离 | frontend dev image 与 static production image 分开 |
| 后端 Worker | 明确 celery worker、API worker、browser runner 的资源限制与启动探针 |
| 配置管理 | 统一 K8s ConfigMap/Secret，Docker Compose 只用于本地 |
| CI | 把 Ruff/mypy 提升为阻断门禁，加入 pytest 覆盖率、OpenAPI 校验、依赖审计、Playwright E2E |
| 发布 | 使用 Conventional Commits/Release Please 自动生成 changelog 和版本 |
| 文件卫生 | 删除 `2.0.0`、根目录/backend 的 `(null)` SogouInput 文件、本地 DB 和运行残留 |
| 文档 | 根目录增加 README 索引，避免 10 份中文文档缺少统一入口 |

## 4. 建议落地路线

### 第一阶段：稳定底座

目标：解决“本地能跑”到“可以正式使用”之间最危险的问题。

本次已落地的 P0 内容：

- 已实现本地任务启动恢复：API 启动时把 local/eager 模式下遗留的 queued/running 任务收敛为 failed，并记录 job.failed 事件。
- 已提供可复用的恢复入口：`recover_interrupted_local_jobs(session_factory=None)`。
- 已补测试：确认 running 任务和 attempt 会被关闭、queued 任务不会永久卡住、Celery 模式任务不受影响。

仍待完成：

- Celery 模式补齐重试、死信、超时、Flower/监控。
- 生产配置禁止默认 Secret，所有默认密码不可启动。
- frontend/backend Dockerfile 改成生产可运行镜像。
- 补 /health/ready、OpenTelemetry trace_id、结构化日志。

### 第二阶段：业务闭环

目标：让质量门禁、缺陷、工作流、通知真正由测试事件驱动。

本次已落地的 P1 内容：

- 已实现任务终态自动质量门禁：API/UI/性能任务进入 succeeded/failed/timed_out 后，按项目启用门禁自动评估。
- 已生成 QualityGateResult，并新增 `job.quality_gates.evaluated` 任务事件，作为后续通知、报告和缺陷联动的事件源。
- 已把门禁规则解析/评估抽到 `backend/app/services/quality_gate_service.py`，API 手动评估与自动评估共用同一套逻辑。
- 已兼容前端当前使用的 `{"metric":"pass_rate","op":">=","value":0.9}` 规则格式，同时保留旧的 `threshold` 字段。
- 已补测试：门禁通过/失败结果、自动事件 payload、任务终态不被门禁失败覆盖。

仍待完成：

- 引入任务终态事件总线/Outbox，让通知、缺陷、报告、覆盖率成为独立消费者。
- 失败任务按规则自动生成缺陷草稿。
- 报告和覆盖率在任务结束后刷新。
- 工作流节点从“模拟执行”接入真实 API/UI/性能任务。

### 第三阶段：前端与 API 工程质量（P2）

目标：减少开发成本和前后端类型漂移。

本次已落地的 P2 内容：

- 已把 `frontend/src/App.tsx` 中 41 个页面从静态导入改为 React Router + React.lazy + Suspense 路由级分包。
- 页面加载时统一显示 Spin fallback，现有登录、AppLayout、权限和路由跳转行为保持不变。
- 已通过验证：TypeScript typecheck、26 个 Vitest 测试、Vite 生产构建；构建产物已按页面拆分为独立 chunk，并新增懒加载路由渲染测试。

仍待完成：

- OpenAPI 生成客户端类型，消除 `api.ts` 中的 `any`。
- TanStack Query 替换页面内手动数据请求。
- 统一表单、表格、错误处理和反馈组件。
- 增加 Playwright E2E 主链路。

### 第四阶段：AI 与高级能力

目标：让 AI 能力可评测、可治理、可复制。

- 模型网关与 Pydantic 结构化输出。
- 向量知识库和 RAG。
- AI 调用评测集。
- 多步骤 AI Agent 接入统一任务中心。
- 接入外部缺陷系统真实同步，如 Jira、禅道、GitLab。

## 5. 不建议立即做的事

- 不急着把 42 个路由模块全部改造成异步 SQLAlchemy。
- 不急着用微服务拆分 backend。
- 不急着引入完整微前端。
- 不急着替换 FastAPI/React/Celery；先补工程闭环，再按瓶颈迁移。
- 不把 AI “Agent 化”放在任务稳定性和评测能力之前。

> 结论：当前项目最需要的不是继续堆页面和模型，而是把已经存在的“任务、事件、门禁、缺陷、报告”做成真正自动联动的系统，并围绕现代工程体系补齐可观测性、类型安全、测试、安全和部署。
