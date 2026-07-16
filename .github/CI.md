# CI 说明

工作流位于 `.github/workflows/ci.yml`，在 `push`、`pull_request` 和手工触发时运行。
后端与前端 Job 相互独立，可并行执行。

## 阻断门禁

后端使用 Ubuntu 和 Python 3.13，按以下顺序执行：

1. 安装 `backend/requirements.txt`。
2. 将 `test-engine/` 安装为 `airetest-engine` 包。
3. 验证 `test_engine` 可在后端导入路径下加载。
4. 从仓库根目录运行完整 `python -m pytest`，同时收集 `backend/tests` 和
   `test-engine/tests`。
5. 在空 SQLite 数据库上执行 Alembic `heads`、`upgrade head`、`check` 和
   `downgrade base`。

前端使用 Node.js 24，在 `frontend/` 下依次执行：

1. `npm ci`
2. `npm run typecheck`
3. `npm run lint -- --quiet`
4. `npm test`
5. `npm run build`

上述任一步骤失败都会使对应 Job 失败。

## 非阻断报告

Ruff、后端 mypy 和已安装 `test_engine` 包的 mypy 检查均保留在后端 Job 中，
但步骤设置了 `continue-on-error`。当前全量静态债务尚未清零，因此这些步骤只
提供日志和 GitHub 注解，不作为合并阻断条件。待存量问题清零后再单独调整为强
门禁。

## 本地复现

后端：

```bash
python -m pip install -r backend/requirements.txt
python -m pip install ./test-engine
PYTHONPATH=backend DATABASE_URL=sqlite:///./ci-test.db python -m pytest

cd backend
DATABASE_URL=sqlite:///./ci-alembic.db python -m alembic upgrade head
DATABASE_URL=sqlite:///./ci-alembic.db python -m alembic check
DATABASE_URL=sqlite:///./ci-alembic.db python -m alembic downgrade base
```

前端：

```bash
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

## 设计假设

- CI 的 Alembic 检查验证迁移链完整性和模型漂移，不替代 Oracle 实库验收。
- 后端测试使用临时 SQLite 数据库，不依赖外部 Oracle、Redis 或 Celery 服务。
- 当前没有在此工作流安装 Playwright 浏览器；浏览器 E2E 应在独立 Job 中接入。
- `npm ci` 要求 `frontend/package-lock.json` 包含完整且与 `package.json` 一致的
  解析结果。工作流不会回退到 `npm install`，锁文件异常应作为前端门禁失败处理。
- Python 依赖当前使用范围版本而非锁文件；CI 缓存只加速安装，不改变解析结果。
