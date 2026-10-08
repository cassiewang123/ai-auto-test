# AIRETEST 项目文件夹内容整理

> 生成日期：2026-10-08  
> 扫描根目录：`E:\xlwang\AIRETEST`  
> 读取范围：项目主体源码、根目录文档、配置、脚本与测试。  
> 统计口径：不逐项展开 `.git`、`node_modules`、`dist`、缓存、日志、本地数据库、运行产物和上传产物。

## 1. 项目定位

AIRETEST 是一个覆盖 **API 测试、UI 测试、性能测试、测试资产管理、报告与覆盖、权限与审计、CI/CD、通知、知识库和 AI 辅助能力** 的测试平台仓库。

仓库同时支持两种运行形态：

| 形态 | 默认组件 | 适用场景 |
|---|---|---|
| 本地轻量模式 | FastAPI + React/Vite + SQLite + 进程内任务调度 | 单机开发、演示和小规模使用 |
| 完整/分布式模式 | Oracle Free + Redis + Celery Worker + Docker + 可选 MinIO | 容器化、分布式执行和生产化验证 |

轻量模式默认端口：

- 后端：FastAPI，默认 `127.0.0.1:8000`；`backend/run_server.py` 默认端口为 `8001`。
- 前端：React + Vite，默认 `127.0.0.1:5173`。
- 数据库：默认 SQLite 文件，如 `airetest-lite.db`。

## 2. 顶层结构

```text
AIRETEST/
├─ .github/                    GitHub Actions 与 CI 说明
├─ ai-test-platform-design/    早期静态页面设计与原型
├─ airetest-improvement-doc/   已生成的改进方案 HTML 文档
├─ backend/                    FastAPI 后端、ORM、服务、迁移与后端测试
├─ frontend/                   React 19 + TypeScript + Vite 前端
├─ scripts/                    本地与 Docker 模式的启停、状态、备份和恢复脚本
├─ test-engine/                独立 API 测试引擎 Python 包
├─ *.md                        项目分析、计划、使用手册和部署文档
├─ docker-compose.yml          完整模式容器编排
├─ pytest.ini                  后端与测试引擎的 pytest 配置
├─ conftest.py                 根级测试路径与调度环境配置
└─ start_frontend.py           仅启动前端 Vite 的开发脚本
```

当前主要代码规模（已排除缓存、构建产物和包初始化文件）：

| 对象 | 数量 |
|---|---:|
| backend API v1 路由模块 | 42 |
| backend ORM 模型文件 | 42 |
| backend Pydantic schema 文件 | 21 |
| backend services 文件（含子目录） | 33 |
| backend Celery/后台任务文件 | 6 |
| backend 执行器文件 | 4 |
| backend 测试文件 | 52 |
| Alembic 迁移版本 | 6 |
| frontend 页面组件 | 41 |
| frontend components 组件 | 5 |
| frontend 测试文件 | 9 |
| test-engine 核心源码 | 4 |
| test-engine 测试文件 | 4 |
| scripts 脚本 | 12 |

## 3. backend/：后端服务

### 3.1 应用入口与核心配置

| 路径 | 说明 |
|---|---|
| `backend/app/main.py` | FastAPI 应用工厂、健康检查、CORS、路由和鉴权注册 |
| `backend/app/config.py` | Pydantic Settings 配置与环境校验 |
| `backend/app/database.py` | SQLAlchemy engine、session 与会话依赖管理 |
| `backend/app/database_types.py` | 跨数据库自定义字段类型 |
| `backend/run_server.py` | Windows 后端启动入口，默认端口 8001 |
| `backend/requirements.txt` | 后端运行与测试依赖 |
| `backend/pyproject.toml` | Ruff、mypy、bandit 等质量工具配置 |
| `backend/lint.ps1` | 后端静态检查脚本 |
| `backend/Dockerfile` | 后端容器镜像，同时用于 API 与 Celery Worker |

### 3.2 分层职责

| 目录 | 职责 |
|---|---|
| `backend/app/api/v1/` | FastAPI 路由层，共 42 个业务路由模块 |
| `backend/app/models/` | SQLAlchemy ORM 模型，共 42 个模型文件 |
| `backend/app/schemas/` | Pydantic 请求、响应与分页模型，共 21 个文件 |
| `backend/app/services/` | 业务服务层，含 `execution/`、`security/`、`ui/` 子包 |
| `backend/app/tasks/` | Celery 应用和后台任务定义 |
| `backend/app/runners/` | 本地进程与脚本执行器封装 |
| `backend/app/core/` | 异常、脱敏和安全基础能力 |
| `backend/app/cli/` | 命令行入口 |

### 3.3 API v1 路由按领域归类

- 基础与系统：`auth`、`users`、`roles`、`api_tokens`、`audit_logs`、`notifications`、`projects`、`environments`、`variables`、`ci_cd`、`scheduled_tasks`
- API 测试资产：`test_cases`、`test_case_versions`、`test_plans`、`test_data`、`import_api`、`capture`、`mock_service`、`db_assertions`
- 执行、任务与结果：`execution`、`history`、`jobs`、`reports`、`report_export`、`coverage`
- UI 测试：`ui_test_cases`、`ui_test_records`、`ui_test_suites`、`ui_elements`、`ui_locators`、`step_library`、`ui_junit`、`visual_regression`
- 性能测试：`performance_tests`
- 工作流与质量协作：`workflows`、`contracts`、`quality_gates`、`defects`、`change_logs`
- AI 与知识：`ai`、`ai_ops`、`knowledge`

### 3.4 数据模型与服务

`backend/app/models/` 覆盖用户权限、项目环境、API 用例、测试计划、测试结果、UI 测试资产、性能测试、任务中心、报告、通知、缺陷、知识库和 AI 调用治理等数据域。

`backend/app/services/` 当前共 33 个服务文件，核心领域如下：

| 领域 | 代表文件 |
|---|---|
| API 测试引擎 | `db_tester.py`、`data_driven_service.py` |
| 任务执行 | `execution/job_dispatcher.py`、`execution/job_service.py`、`execution/job_reporting.py` |
| UI 执行与产物 | `ui/execution_service.py`、`ui/recording_service.py`、`ui/artifact_service.py` |
| 性能执行 | `perf_runner.py`、`perf_realtime.py`、`locust_runner.py` |
| 安全 | `security/` 下的审计、脱敏、加密、URL 策略和 SQL 校验 |
| AI 与知识 | `ai_service.py`、`ai_governance.py`、`knowledge_service.py`、`self_evolution.py` |
| 系统与集成 | `auth_service.py`、`ci_cd_service.py`、`notification_service.py`、`server_monitor.py` |

### 3.5 数据库迁移与辅助脚本

- `backend/alembic/`：Alembic 迁移环境，`versions/` 下当前有 6 个迁移版本。
- `backend/migrations/`：早期 Python 迁移脚本，覆盖性能增强、Phase 4 字段、步骤库、套件并行、用例脚本字段、UI 重试字段和 Token 哈希迁移。
- `backend/scripts/`：Oracle 预检、SQLite 到 Oracle 迁移、已有 Secret 加密。
- `backend/_verify_apis.py` 与根目录 `migrate_*.py`：本地校验与迁移辅助脚本。
- 根目录 `2.0.0`：pip 安装输出残留，已被 `.gitignore` 忽略，不属于源码。

### 3.6 后端测试

`backend/tests/` 当前有 52 个测试文件，覆盖认证授权、API 用例、执行安全、异步任务、CI/CD、通知、报告、覆盖率、数据库断言、性能单位、Oracle 兼容、Secret 加密、UI 录制、服务器监控等。前端测试位于 `frontend/src/test/`。

## 4. frontend/：前端应用

### 4.1 技术栈

React 19、TypeScript、Vite、Ant Design、Axios、React Router、Chart.js、Recharts、Vitest、Testing Library。构建入口为 `frontend/src/main.tsx`，路由入口为 `frontend/src/App.tsx`。

常用命令：

```bash
npm run dev        # 启动 Vite 开发服务器
npm run typecheck  # TypeScript 类型检查
npm run lint       # ESLint
npm run test       # Vitest
npm run build      # 类型检查并生产构建
```

### 4.2 src 结构

| 目录 | 职责 |
|---|---|
| `src/pages/` | 41 个页面组件 |
| `src/components/` | 应用布局、错误边界、导航、控制台窗口、JSON 编辑器 |
| `src/contexts/` | 登录认证与项目/环境工作区状态 |
| `src/services/` | HTTP 客户端、业务 API 和 CI/CD API |
| `src/styles/` | 全局、工作区、性能仪表盘、报告等样式 |
| `src/types/` | TypeScript 类型 |
| `src/utils/` | JSON 与 JSON Compare 工具 |
| `src/test/` | Vitest + Testing Library 测试 |
| `src/assets/`、`public/` | 图片、图标与 favicon |

### 4.3 页面按功能归类

- 通用与系统管理：`Login`、`Dashboard`、`Jobs`、`History`、`Projects`、`Environments`、`GlobalVariables`、`Users`、`Roles`、`ApiTokens`、`CiCd`、`Notifications`、`AuditLogs`
- API 测试：`QuickTest`、`ApiList`、`ApiDocs`、`JsonCompare`、`TestCases`、`TestPlans`、`TestData`、`Import`、`MockService`
- UI 测试：`UiTestCases`、`UiTestSuites`、`UiElements`、`UiTestRecords`、`UiTestLogs`、`StepLibrary`
- 性能测试：`PerformanceTest`、`PerformanceReport`、`PerfDashboard`
- 报告与质量：`Reports`、`Coverage`、`QualityGates`、`Defects`、`ScheduledTasks`
- AI 与知识：`AI`、`AiOps`、`BusinessRules`、`DefectPatterns`、`InterfaceKnowledge`

具体路由见 `frontend/src/App.tsx`，菜单结构见 `frontend/src/components/navigation.tsx`，支持 lite/full 两种模式切换。页面已采用 React Router 懒加载路由分包。

### 4.4 前端工程文件

根目录包含 `package.json`、`package-lock.json`、`tsconfig.json`、`vite.config.ts`、`Dockerfile`、`.eslintrc.cjs`、`.prettierrc`、`start-dev.bat`、`py_npm_install.py`、`registry_proxy.py` 等工程与本地辅助文件。

## 5. test-engine/：独立 API 测试引擎

该目录通过 `pyproject.toml` 安装为 Python 包 `test_engine`，依赖 httpx、sqlglot、jsonpath-ng、jsonschema 等库。

| 文件 | 职责 |
|---|---|
| `test-engine/request_builder.py` | 根据用例配置构建 HTTP 请求 |
| `test-engine/assertion_engine.py` | 执行响应断言 |
| `test-engine/variable_extractor.py` | 从响应中提取变量并写入上下文 |
| `test-engine/executor.py` | 串联请求构建、变量提取和断言执行 |
| `test-engine/tests/` | 断言、执行器、请求构建器和变量提取器单元测试 |

## 6. scripts/：运维与本地辅助脚本

| 文件 | 职责 |
|---|---|
| `scripts/start-local.ps1` | 启动本地前后端 |
| `scripts/stop-local.ps1` | 停止本地运行 |
| `scripts/status-local.ps1` | 查看本地运行状态 |
| `scripts/local-runtime.ps1` | 本地运行辅助函数 |
| `scripts/start-docker.ps1` | 启动 Docker 模式 |
| `scripts/status-docker.ps1` | 查看 Docker 服务状态 |
| `scripts/stop-docker.ps1` | 停止 Docker 服务 |
| `scripts/backup-local.ps1` | 本地数据备份 |
| `scripts/restore-local.ps1` | 本地数据恢复 |
| `scripts/cleanup-local.ps1` | 本地数据与运行产物清理 |
| `scripts/local_data.py` | 本地数据初始化与处理工具 |
| `scripts/smoke_frontend_routes.py` | 前端路由冒烟检查 |

## 7. 部署与 CI 配置

| 路径 | 说明 |
|---|---|
| `docker-compose.yml` | Oracle Free、Redis、可选 MinIO、迁移、后端、前端和 Celery Worker 编排 |
| `.github/workflows/ci.yml` | CI 主流程，覆盖后端测试/迁移与前端检查 |
| `.github/CI.md` | CI 门禁、非阻断项和本地复现说明 |
| `.env.example` | 轻量 SQLite 本地模式配置模板 |
| `.env.oracle.example` | Oracle、Redis、Celery 完整模式配置模板 |
| `.env`、`.env.oracle` | 本地实际配置，可能含敏感值，不应对外分享 |
| `.gitignore` | 忽略数据库、缓存、构建产物、运行目录和本地日志 |
| `pytest.ini` | pytest 收集范围与标记 |
| `conftest.py` | 解决同名 `tests` 包冲突并设置测试调度模式 |

`docker-compose.yml` 的主要服务与 profile：

- 基础服务：`oracle`、`redis`、`migrate`、`backend`、`frontend`、`worker-local`。
- 分布式 Worker：`worker-api`、`worker-ui`、`worker-performance`，由 `distributed` profile 启用。
- 对象存储：`minio`，由 `object-storage` profile 启用。
- 数据卷：`oracle_data`、`redis_data`、`minio_data`、`uploads_data`。

## 8. 根目录文档索引

| 文档 | 内容 |
|---|---|
| `AGENTS.md` | 项目 Git 提交与推送规则 |
| `AIRETEST-平台现状说明.md` | 平台状态、量化基线、架构、成熟度和待办 |
| `AIRETEST-并行开发计划.md` | 迭代分组、并行工作流与开发排期 |
| `AIRETEST-当前平台分析与建设路线.md` | 平台架构分析、问题清单与建设路线 |
| `AIRETEST-本地单机运行指南.md` | 本地安装、启动、停止、日志、备份恢复 |
| `AIRETEST-生产化改造与能力扩展开发设计.md` | 任务中心、权限、安全、扩展模块和部署设计 |
| `AIRETEST-技术改进分析.md` | 基于当前源码的结构性问题、技术选型和落地路线 |
| `AIRETEST-迭代一开发记录.md` | 第一迭代开发范围、集成结果和完成标准 |
| `AIRETEST使用手册.md` | 面向使用者的平台操作手册 |
| `AI测试平台-开发任务拆解.md` | 早期阶段划分和任务拆解 |
| `ORACLE部署与迁移.md` | Oracle 模式的迁移、预检和部署步骤 |
| `AIRETEST-文件夹内容整理.md` | 本文件，仓库结构与文件职责索引 |

## 9. 设计原型与 HTML 交付物

| 目录 | 内容 |
|---|---|
| `ai-test-platform-design/` | 早期静态原型，含 dashboard、quick-test、test-cases、ai-assistant 页面、设计说明和生成树 |
| `airetest-improvement-doc/` | 改进方案 HTML 文档 |
| `.trae-html-share-packages/` | 上述 HTML 文档的 zip 分享包 |

这些目录属于设计或交付材料，不是后端与前端运行代码的主体。

## 10. 本地数据、缓存与运行产物

以下路径通常是运行、构建或缓存产物，建议不要提交到版本库：

| 路径 | 内容 |
|---|---|
| `.backups/` | 本地备份与历史 SQLite、任务 Artifact |
| `.runtime/` | PID、日志、截图、前端/后端冒烟结果、UI review 图片 |
| `.uploads/`、`backend/uploads/` | 上传文件、任务截图、Trace ZIP 等执行产物 |
| `frontend/node_modules/`、`frontend/dist/` | npm 依赖与前端构建输出 |
| `.mypy_cache/`、`.ruff_cache/`、`.pytest_cache/`、`__pycache__/` | Python 检查与测试缓存 |
| 根目录与 `backend/` 下的 `*.db*` | SQLite 本地运行数据库及其 WAL/SHM 文件 |
| 根目录与 `backend/` 下的 `(null)/` | SogouInput Picface Cloud 二进制文件，与项目无关，可在确认后清理 |

## 11. 建议阅读顺序

1. 先阅读 `AIRETEST-平台现状说明.md`，了解平台整体状态和量化基线。
2. 使用平台前阅读 `AIRETEST使用手册.md` 与 `AIRETEST-本地单机运行指南.md`。
3. 查看 `backend/app/main.py` 与 `frontend/src/App.tsx`，快速确认前后端入口和路由全景。
4. 按需求进入 `backend/app/api/v1/`、`backend/app/services/` 或 `frontend/src/pages/` 查找对应模块。
5. 调整数据库或部署时，参考 `backend/alembic/`、`backend/scripts/`、`ORACLE部署与迁移.md` 与 `docker-compose.yml`。
6. 规划技术升级时，阅读 `AIRETEST-技术改进分析.md` 和 `AIRETEST-生产化改造与能力扩展开发设计.md`。

## 12. 维护说明

本文件只记录结构与职责，不替代源码、接口文档和部署文档。目录数量会随迭代变化，建议在以下情况更新：

- 新增后端业务域、前端页面或 Celery Worker 类型。
- 新增根目录运行脚本、迁移目录或部署 profile。
- 根目录文档发生增删或职责调整。
- 本地运行形态从 SQLite 轻量模式切换为 Oracle、Redis 或 MinIO 完整模式。
