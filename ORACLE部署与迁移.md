# AIRETEST Oracle 可选完整模式部署与迁移

> 默认个人模式不使用 Oracle、Docker、Redis 或 Celery Worker。默认 `.env`
> 使用 `sqlite:///./airetest-lite.db`、`TASK_DISPATCH_MODE=local` 和
> `ARTIFACT_ROOT=.uploads`，通过 `start-local.ps1`、`status-local.ps1`、
> `stop-local.ps1` 直接运行 Python/FastAPI 与 Node/Vite。
> 当前默认 SQLite revision 为 `a7d9e2c4f610`，物理表共 54 张，其中包括
> `alembic_version`；Oracle 预检中的 53 张表指业务表，不包含版本表。
> 默认后端和前端只监听 `127.0.0.1:8000` 与 `127.0.0.1:5173`。
> `backend/run_server.py` 使用 Windows 默认 Proactor，不再强制 Selector。
>
> 本文只描述按需启用的 Oracle/Docker 完整模式，不构成默认本地使用前置条件。

## 1. 数据库约定

- SQLAlchemy 方言：`oracle+oracledb`
- 默认服务名：`FREEPDB1`
- 应用用户：`airetest`
- 结构管理：仅使用 Alembic
- JSON 字段：由 ORM 序列化为 `Text`，在 Oracle 中落为 `CLOB`
- 支持的 Oracle 版本：具备 `IDENTITY` 列能力的版本

当前平台按个人本机使用设计。Oracle 完整模式使用 `.env.oracle.example` 和
`.env.oracle`，与默认 SQLite `.env` 隔离。实际 `.env.oracle` 应替换 Oracle
管理员密码、Oracle 应用密码、JWT `SECRET_KEY` 和字段加密密钥。已有生产静态
保护继续保留，但生产发布不属于当前范围。

## 2. 可选 Docker/Oracle 完整模式启动

先生成本地配置并执行不连接数据库的静态检查：

```powershell
Copy-Item .env.oracle.example .env.oracle
# 修改 .env.oracle 中所有开发凭据后再继续
python backend/scripts/oracle_preflight.py `
  --static-only `
  --compose-file docker-compose.yml `
  --env-file .env.oracle
docker compose --env-file .env.oracle config --quiet
```

`docker compose config` 会展开环境变量，输出内容可能包含密钥，不要将完整输出
上传到工单或日志平台。`--static-only` 不调用 Docker，也不连接 Oracle，适合在
CI 中作为部署文件检查。

推荐使用完整模式启动脚本完成构建、迁移和启动：

```powershell
.\scripts\start-docker.ps1
```

可选完整模式启动以下服务：

- Oracle
- Redis
- Alembic `migrate`
- Backend
- Frontend
- `worker-local`，以 `concurrency=1` 监听 API、UI、Performance 三个队列

检查状态：

```powershell
.\scripts\status-docker.ps1
```

Compose 健康检查和启动门控如下：

- Oracle：调用镜像内置 `healthcheck.sh`，`migrate` 仅在 Oracle 健康后运行。
- Redis：执行 `redis-cli ping`，API 和 Worker 仅在 Redis 健康后启动。
- Backend：调用 `/health/ready`，该端点当前只检查 Oracle 连接；前端等待
  Backend 健康后启动。
- `worker-local`：向 Worker 自身节点执行 `inspect ping`。
- MinIO：位于 `object-storage` profile，启用后调用 `/minio/health/live`。
  MinIO 当前不作为 Backend 或 Worker 的启动依赖。

Compose 中 API 与 Worker 使用相同的 Oracle、Redis、Celery 队列和
`SECRET_ENCRYPTION_KEY`。容器内 Broker/Backend 地址固定使用
`redis://redis:6379/0`；仅在宿主机直接运行 API 或 Worker 时使用
`.env.oracle` 中的 `redis://localhost:6379/0`。

异步任务本地配置：

```dotenv
TASK_DISPATCH_MODE=celery
TASK_FALLBACK_MODE=disabled
TASK_EAGER_IN_TESTS=true
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_API_QUEUE=airetest.api
CELERY_UI_QUEUE=airetest.ui
CELERY_PERFORMANCE_QUEUE=airetest.performance
CELERY_TASK_ACKS_LATE=true
CELERY_WORKER_PREFETCH_MULTIPLIER=1
CELERY_TERMINATE_SIGNAL=SIGTERM
```

本机 `.env.oracle` 应生成独立 JWT 密钥和 32 字节 URL-safe Base64
字段加密密钥：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将第一条命令输出保存为 `SECRET_KEY`，第二条命令输出保存为
`SECRET_ENCRYPTION_KEY`。API 和所有 Worker 必须始终使用相同的持久密钥；
更换或丢失字段加密密钥会导致已有加密数据无法解密。`.env.oracle` 应由
`.gitignore` 排除，不得将其加入版本库。

静态预检项目包括：

1. 宿主机和 Compose 的 Oracle URL 均使用 `oracle+oracledb` 和
   `service_name`，且 Compose URL 账号密码与 Oracle 应用账号一致。
2. `AUTO_CREATE_SCHEMA=false`，Schema 只由 Alembic 管理。
3. Redis Broker/Result Backend、三类 Celery 队列及 Worker 命令一致。
4. Oracle、Redis、可选 MinIO、Backend 和两种 Worker 拓扑均定义有界
   healthcheck。
5. `migrate`、Backend、前端和 Worker 使用正确的健康/完成条件门控。
6. API 与 Worker 共享 Artifact 卷，且未误接入未实现的 S3/MinIO 配置。
7. 默认密钥、缺失密钥及密钥格式风险。

`WARN` 不改变退出码，适用于明确的本地开发示例；任何 `FAIL` 返回退出码 `1`。
参数、文件解析或本地配置错误返回退出码 `2`。

完整模式单 Worker 静态预检：

```powershell
python backend/scripts/oracle_preflight.py `
  --static-only `
  --worker-topology local `
  --compose-file docker-compose.yml `
  --env-file .env.oracle
```

Oracle 启动后，连同 Celery 节点、队列和并发数执行运行时预检：

```powershell
python backend/scripts/oracle_preflight.py `
  --worker-topology local `
  --check-worker-runtime `
  --env-file .env.oracle
```

分布式拓扑仅在需要时启用，启动脚本会停止默认 Worker，避免重复消费：

```powershell
.\scripts\start-docker.ps1 -Distributed
python backend/scripts/oracle_preflight.py `
  --worker-topology distributed `
  --check-worker-runtime `
  --env-file .env.oracle
```

### Artifact 存储边界（迭代一）

当前应用只实现文件系统型 `ARTIFACT_ROOT`，尚未实现 S3/MinIO Artifact 适配器。
Compose 因此采用以下明确边界：

- Backend 与 `worker-local`/分布式 Worker 固定使用 `/app/uploads`。
- API 和 Worker 共享 `uploads_data:/app/uploads`，保证 Worker 产生的文件可由
  API 读取。
- `ALLOW_DIRECT_FILE_PATHS=false`，业务调用应使用合法 `artifact_id`。
- MinIO 位于 `object-storage` profile，只在显式启用时验收服务存活和独立
  `minio_data:/data` 持久卷。
- `MINIO_ROOT_USER` 和 `MINIO_ROOT_PASSWORD` 仅为 MinIO 服务管理凭据，不是
  应用 Artifact 访问配置。
- `.env.oracle` 中不得添加并宣称 `S3_ENDPOINT`、`S3_ACCESS_KEY`、`S3_SECRET_KEY`
  已生效；这些字段当前不会被应用读取。

将 Artifact 切换到 MinIO 需要后续单独实现对象存储适配、业务访问凭据、Bucket
初始化、迁移和回滚方案，不能只靠 Compose 环境变量完成。

## 3. 外部 Oracle

在独立的 `.env.oracle` 中配置，并在执行命令前注入对应环境变量：

```dotenv
DATABASE_URL=oracle+oracledb://airetest:password@db-host:1521/?service_name=SERVICE_NAME
AUTO_CREATE_SCHEMA=false
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_RECYCLE_SECONDS=1800
```

然后安装依赖并执行迁移：

```powershell
cd backend
pip install -r requirements.txt
python -m alembic upgrade head
```

执行 Oracle 预检。脚本会检查连接、Alembic head、53 张业务表、CLOB JSON
往返和 `job_events.id` 的 `IDENTITY` 插入：

```powershell
python scripts/oracle_preflight.py `
  --oracle-url $env:DATABASE_URL
```

写入冒烟只向 `execution_jobs` 和 `job_events` 插入随机 ID 的探针数据，所有操作
位于同一个未提交事务中，结束后统一回滚并再次查询确认残留为 0。脚本不执行
`UPDATE`、`DELETE`、DDL，也不会覆盖已有业务数据。Oracle 的 `IDENTITY` 序列值
可能因回滚产生正常间隔，但不会留下业务行。

只检查连接和结构、不执行事务写入冒烟时使用：

```powershell
python scripts/oracle_preflight.py `
  --oracle-url $env:DATABASE_URL `
  --skip-transactional-smoke
```

CI 或自动化平台可以读取 JSON 报告：

```powershell
python scripts/oracle_preflight.py `
  --oracle-url $env:DATABASE_URL `
  --json
```

数据库预检退出码约定：`0` 表示全部检查通过，`1` 表示数据库检查未通过，
`2` 表示参数或本地配置错误。输出中的数据库密码始终会被隐藏。

## 4. Oracle 上线预检顺序

建议使用独立应用 Schema，并按以下顺序执行：

```powershell
cd backend
$env:DATABASE_URL="oracle+oracledb://airetest:password@db-host:1521/?service_name=SERVICE_NAME"

# 1. 只读检查连接状态；新 Schema 尚未迁移时，表和版本检查失败是预期结果
python scripts/oracle_preflight.py --skip-transactional-smoke

# 2. 初始化或升级 Schema
python -m alembic upgrade head

# 3. 执行完整安全冒烟
python scripts/oracle_preflight.py
```

完整预检应看到以下项目为 `PASS`：

1. `connection`：Oracle 连接和 `SELECT 1` 正常。
2. `alembic_head`：数据库版本与代码仓库 head 一致。
3. `business_tables`：53 张业务表全部存在。
4. `clob_json_column`：`execution_jobs.config` 为 CLOB。
5. `clob_json_round_trip`：嵌套 JSON 插入和读取一致。
6. `identity_insert`：`job_events.id` 自动生成正整数。
7. `transaction_rollback_cleanup`：探针任务和事件残留行数均为 0。

任何一项 `FAIL` 都应阻止启用 Oracle 完整模式。`SKIP` 仅允许出现在明确使用
`--skip-transactional-smoke` 的只读预检阶段，不影响默认 SQLite/local 模式。

## 5. SQLite 数据迁移

默认轻量模式数据库为 `airetest-lite.db`。迁移到可选 Oracle 完整模式前，先停止
本地 API、备份 SQLite 文件，并保证 Oracle 目标 Schema 已执行：

```powershell
python -m alembic upgrade head
python scripts/oracle_preflight.py
```

执行数据复制：

```powershell
python scripts/migrate_sqlite_to_oracle.py `
  --sqlite ..\airetest-lite.db `
  --oracle-url "oracle+oracledb://airetest:password@localhost:1521/?service_name=FREEPDB1"
```

脚本按外键依赖顺序复制表，并为旧项目补充项目 owner。可通过
`--owner-user-id` 指定 owner 用户。

默认要求 Oracle 业务表为空。只有明确了解重复数据风险时才能使用
`--allow-nonempty`。

数据迁移完成后再次执行完整预检，并核对源库、目标库各业务表行数。预检不会
修改已迁移的数据：

```powershell
python scripts/oracle_preflight.py
```

## 6. 迁移历史说明

原迁移只有空 baseline 和任务表，不足以初始化完整数据库。本次已重建为完整
Oracle 基线。默认 `airetest-lite.db` 继续使用 SQLite Alembic revision；迁移到
Oracle 时不要让目标 Schema 沿用 SQLite 的 `alembic_version`，应创建全新
Oracle Schema 后通过数据迁移脚本复制业务数据。

## 7. 验收

```powershell
python backend/scripts/oracle_preflight.py `
  --static-only `
  --worker-topology local `
  --compose-file docker-compose.yml `
  --env-file .env.oracle
.\scripts\start-docker.ps1
.\scripts\status-docker.ps1

cd backend
python -m alembic current
python -m alembic check
python scripts/oracle_preflight.py `
  --worker-topology local `
  --check-worker-runtime `
  --env-file ..\.env.oracle
python -m pytest tests/test_oracle_compatibility.py tests/test_oracle_preflight.py -q
```

还需人工验证：

1. 记录 Oracle 版本、服务名、应用 Schema 和 Alembic revision。
2. 确认预检报告中的 7 项检查全部为 `PASS`。
3. 确认 53 张业务表存在，且应用账号不依赖 DBA 权限运行。
4. 数据迁移时核对源库和目标库各表行数、中文、空字符串、时间和 CLOB 字段。
5. 创建首个用户并登录。
6. 创建项目，确认创建者自动成为 `owner`。
7. 添加 `viewer`，确认其不能修改项目或取消他人的任务。
8. 创建接口用例任务，确认任务项目与用例项目一致。
9. 使用非法 `artifact_id` 和目录穿越路径，确认请求被拒绝。
10. 短暂中断数据库连接后恢复，确认连接池可以重新建立连接。
11. 确认 Backend 和 `worker-local` 均挂载同一个
    `uploads_data:/app/uploads`。
12. 如启用 MinIO，确认其只挂载独立的 `minio_data:/data`。
13. 确认可选完整模式 `.env.oracle` 的静态预检没有 `FAIL`。

Oracle 完整模式验收失败只阻止使用该完整模式，不影响默认 SQLite/local 模式。
默认模式不需要重启 Windows、安装 Docker Desktop 或等待 Oracle/Redis。
