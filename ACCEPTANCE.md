# AIRETEST 功能治理 · 验收口径（仅本轮 14 条 FR）

> 全部命令在仓库根目录 `E:/xlwang/AIRETEST` 的工作区执行（Windows 下 Python 用 `py` 启动器），不切干净分支、不提交、不推送。
> 定位：1 人本机轻量单机。统一文案见 `ROADMAP.md`；手册见 `AIRETEST使用手册.md` 第 21 章。

| FR | 可执行命令 / 断言 |
|---|---|
| FR-01 | `grep -c "阻断 (block)" frontend/src/pages/QualityGatesPage.tsx` = 0；`grep '_VALID_MODES = {"warn", "log"}' backend/app/api/v1/quality_gates.py` 命中；`py -c "from app.services.quality_gate_service import normalize_gate_mode as n; assert n('block')=='log' and n('warn')=='warn' and n(None)=='log'"`（带 `PYTHONPATH=backend`）；`git diff -- backend/app/services/execution/job_service.py` 无本轮新增行；不达标任务终态仍完成且 `QualityGateResult.passed=false` 可查 |
| FR-02 | `grep "SSH_CONSOLE_ENABLED: bool = False" backend/app/config.py` 命中；`grep "SSH_CONSOLE_ENABLED=false" .env` 命中；带 JWT `POST /api/v1/tools/ssh/test` → 403 且 message 含「SSH_CONSOLE_ENABLED」；`.env` 改 `true` 并重启后不再 403；浏览器验证入口置灰 + 4 项提示条 + 二次确认 |
| FR-03 | `grep -c "URL_ALLOW_PRIVATE: bool = True" backend/app/config.py` = 0；`grep "URL_ALLOW_PRIVATE=false" .env` 命中；前端 `DEFAULT_CONNECTION.allowPrivate === false`；未勾选私网 URL → 422 可读提示，勾选后放行；`PYTHONPATH=backend DATABASE_URL=sqlite:///./qa.db ENVIRONMENT=test py -m pytest backend/tests/services/test_url_policy.py -q` 全绿 |
| FR-04 | `grep -c "AutoAddPolicy" backend/app/api/v1/server_console.py` = 0；未信任新主机连接失败且 message 含 `SHA256:`；填入指纹后成功；`grep -c "log_audit(" backend/app/api/v1/server_console.py` = 1；审计 `after` 含 `{host,port,method,url,ts,result_code}` 且**不含 `password`**；`py -m pytest backend/tests/test_server_console.py -q` 全绿 |
| FR-05 | `grep "LLM_EXTERNAL_ENABLED: bool = False" backend/app/config.py` 命中；`py -c "from app.services.ai_service import AIService,LLMConfig; assert AIService(LLMConfig(api_key='sk-test'))._get_llm() is None"`（`PYTHONPATH=backend`，开关键 False）；`/ai`、`/ai-ops`、3 个知识页共 5 处状态条可见；弹窗列 4 类字段 + 二次确认；`grep -rn "record_invocation" backend/app --include=*.py` 仅 1 处定义 |
| FR-06 | `py -c "from scripts.smoke_frontend_routes import ROUTES,EXPECTED_TOOL_ROUTES; assert len(ROUTES)==51 and len(EXPECTED_TOOL_ROUTES)==12 and set(EXPECTED_TOOL_ROUTES)<=set(ROUTES)"`；`grep -c '"/json-compare"' scripts/smoke_frontend_routes.py` = 0；起服务后 `py scripts/smoke_frontend_routes.py --base-url http://127.0.0.1:5173` → `51/51` |
| FR-07 | `grep -n "## 21" "AIRETEST使用手册.md"` 命中；手册含 12 条 `/tools*` 路径 + 高风险 / 默认关闭 / 私网 / 主机密钥 / 密码仅会话内存 5 项说明；`git diff -- "AIRETEST使用手册.md"` 仅末尾追加 |
| FR-08 | `ROADMAP.md` 含「实验 API / 未启用」「仅 API」；`grep -rn "工作流\|契约中心" frontend/src` 0 命中；`git diff -- frontend/src/routes.tsx` 为空；新增页面 / 路由数 = 0 |
| FR-09 | `grep -c "RAG" backend/app/services/knowledge_service.py` = 0 且 `grep -c "RAG" backend/app/api/v1/knowledge.py` = 0；`grep "当前规则模式无调用记录" frontend/src/pages/AiOpsPage.tsx` 命中；函数名 `search_knowledge` 不变；AI 相关测试全绿 |
| FR-10 | `grep "DEBUG: bool = True"` / `ALLOW_SYNC_EXECUTION: bool = True` / `LLM_MODEL: str = "gpt-4"` 三者仍命中；`git diff -- backend/app/config.py \| grep -c "validate_production_settings"` = 0；启动日志含 3 条提示；手册含 3 条说明 |
| FR-11 | `ROADMAP.md` 存在且 ≤1 页，含定位 / 范围 / 6 议题 / 验收指向 / 两份历史方案「历史方案 · 未采纳」；`git status --short` 中其余 11 份既有 md 无新增 `M` |
| FR-12 | `ACCEPTANCE.md` 存在且仅含 14 条 FR + DoD 检查项；`git diff -- .github/workflows/ci.yml` 为空；未新增 `check_acceptance_sync.py`；4 套 DoD / 60 条清单未收敛 |
| FR-13 | `ROADMAP.md` 三列表 7 行齐全，每行有 `api.ts` / `routes.tsx` 行号证据且全标「仅 API · 无独立入口」；新增页面数 = 0 |
| FR-14 | `grep -c "    safety: 'local'," frontend/src/pages/tools/toolCatalog.tsx` = 10、`grep -c "    safety: 'high-risk',"` = 1（11 张卡，不含类型声明）；`ToolsHubPage` 渲染「本机处理 · 不外发」/「高风险 · 默认关闭」；`data-testid="tool-card-*"` 不变；`npm test -- --run` 76 passed |

## 全量回归基线命令组

```bash
PYTHONPATH=backend DATABASE_URL=sqlite:///./qa.db ENVIRONMENT=test py -m pytest -q          # 781 passed
cd frontend && npm run typecheck && npm test -- --run                                      # exit 0 / 76 passed
cd backend && PYTHONPATH=. DATABASE_URL=sqlite:///./qa_check.db py -m alembic upgrade head && py -m alembic check   # No new upgrade operations detected.（alembic.ini 在 backend/，必须先 upgrade head）
py scripts/smoke_frontend_routes.py --base-url http://127.0.0.1:5173                       # Route smoke passed: 51/51（需先起 backend + frontend）
```

## DoD 检查项

- [ ] **新增页面强制同步**：需求条目（`ACCEPTANCE.md`）/ 手册章节（`AIRETEST使用手册.md`）/ 冒烟清单（`scripts/smoke_frontend_routes.py` 与 `EXPECTED_TOOL_ROUTES`）三处同时更新，否则不予验收。
- [ ] 无新增后端路由 / 前端页面 / lazy 注册 / 数据库迁移 / 依赖 / CI 改动。
- [ ] `job_service.py` 终态逻辑一行不动；`ai_governance.py:11` `record_invocation` 仍仅定义处。
- [ ] 22 项历史未提交业务资产（13 `M` + 9 `??`）状态不翻转；无 `git commit` / `push` / `reset` / `checkout --` / `clean`。
- [ ] 统一文案口径逐字一致：质量评估（仅记录，不阻断执行）/ 规则引擎 · 未接入 LLM · 数据不会外发 / 当前规则模式无调用记录 / 仅 API · 无独立入口 / 实验 API / 未启用 / 本机处理 · 不外发 / 高风险 · 默认关闭 / 服务器控制台未启用引导文案。
