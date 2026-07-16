# AIRETEST 自动化测试平台 · 使用手册

> 版本：v2.0 ｜ 更新日期：2026-07-10

---

## 目录

- [1 平台概述](#1-平台概述)
- [2 快速开始](#2-快速开始)
- [3 功能模块详解](#3-功能模块详解)
  - [3.1 仪表盘](#31-仪表盘)
  - [3.2 API 测试](#32-api-测试)
  - [3.3 UI 测试](#33-ui-测试)
  - [3.4 性能测试](#34-性能测试)
  - [3.5 测试报告与度量](#35-测试报告与度量)
  - [3.6 环境与变量管理](#36-环境与变量管理)
  - [3.7 知识工程](#37-知识工程)
  - [3.8 系统管理](#38-系统管理)
- [4 高级功能](#4-高级功能)
- [5 API 参考速查](#5-api-参考速查)
- [6 常见问题](#6-常见问题)

---

## 1 平台概述

AIRETEST 是一站式自动化测试平台，覆盖 **API 测试、UI 测试、性能测试** 三大领域，集成 AI 辅助、知识工程、CI/CD 链路，支持从用例编写到报告生成的完整闭环。

**技术栈**

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13 · FastAPI · SQLAlchemy 2.0 · SQLite/MySQL |
| 前端 | React 19 · TypeScript 6 · Ant Design 6 · Vite 8 |
| 测试引擎 | requests · Playwright · Locust · Pillow |
| 图表 | recharts · chart.js |

**功能全景图**

```
┌─────────────────────────────────────────────────────┐
│                   AIRETEST 测试平台                   │
├──────────┬──────────┬──────────┬──────────┬─────────┤
│ API 测试  │ UI 测试   │ 性能测试  │ 知识工程  │ 系统管理 │
├──────────┼──────────┼──────────┼──────────┼─────────┤
│ 接口调试   │ 用例管理   │ 压测场景   │ 缺陷模式库 │ 用户管理  │
│ 用例管理   │ 测试套件   │ 性能报告   │ 业务规则库 │ 角色管理  │
│ 测试计划   │ 元素对象库  │ 实时仪表盘  │ 接口知识库 │ API Token│
│ 接口导入   │ 视觉回归   │ SLA 告警   │           │ CI/CD    │
│ 数据驱动   │ JUnit 输出  │ 趋势对比   │           │ 通知管理  │
│ Mock 服务 │           │ 服务器监控  │           │ 定时任务  │
│ 接口文档   │           │           │           │         │
│ 覆盖率看板 │           │           │           │         │
│ AI 助手   │           │           │           │         │
└──────────┴──────────┴──────────┴──────────┴─────────┘
```

---

## 2 快速开始

### 2.1 环境要求

| 组件 | 版本要求 |
|---|---|
| Python | ≥ 3.13 |
| Node.js | ≥ 20.19（推荐 22.12+） |
| 操作系统 | Windows / macOS / Linux |

### 2.2 启动后端

```bash
cd backend

# 安装依赖（首次）
pip install -r requirements.txt

# 启动服务
python run_server.py
```

> **Windows 用户注意**：必须使用 `run_server.py` 启动，而非直接 `uvicorn` 命令。该脚本会处理 Python 3.13 + Windows 的 asyncio 兼容性问题（WinError 10038）。

后端启动后：
- 服务地址：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 2.3 启动前端

```bash
cd frontend

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev
```

前端启动后访问 http://localhost:5173

### 2.4 首次登录

平台**无预置默认账号**，首次使用需注册：

1. 访问 http://localhost:5173，页面自动跳转到登录页
2. 点击「注册」链接，填写用户名、邮箱、密码
3. **首个注册的用户自动成为超级管理员**
4. 注册成功后返回登录页，输入凭据登录

> 如果系统中已有 `admin / admin123` 账号，可直接使用该凭据登录。

### 2.5 创建第一个项目

1. 登录后进入「项目管理」页面
2. 点击「新建项目」，输入项目名称和描述
3. 项目创建后即可在该项目下创建用例、环境等资源

---

## 3 功能模块详解

### 3.1 仪表盘

**路径**：`/dashboard`

平台首页，展示全局统计概览：
- 环境总数、用例总数、测试计划数
- 最近创建的 5 条测试用例
- 快捷入口

### 3.2 API 测试

API 测试是平台核心模块，覆盖接口调试、用例管理、测试计划、导入、文档等全流程。

#### 3.2.1 接口定义

**路径**：`/api-list`

管理所有接口定义，支持两种视图切换：

- **项目视图**：按项目分组的列表，展示方法、URL、分组、状态
- **目录树视图**：左侧多级目录树（按 `group_path` 解析），右侧选中分组的接口列表，右键支持「移动到分组」

操作：运行、查看历史、下载定义

#### 3.2.2 接口文档

**路径**：`/api-docs`

类 Swagger UI 的接口在线文档浏览：
- 选择项目后按分组展示接口卡片
- 每张卡片显示：HTTP 方法标签（颜色区分）、URL、标题、描述
- 可折叠查看 headers / params / body 示例
- 点击「试一下」跳转到接口调试页并自动预填参数

#### 3.2.3 接口调试

**路径**：`/quick-test`

单接口快速调试器，支持完整的请求配置：

**请求配置**
- 方法：GET / POST / PUT / PATCH / DELETE
- URL、Headers、Params、Body（JSON / Form / Multipart）
- 文件上传

**认证快捷配置**（Tab 面板）
| 类型 | 配置项 |
|---|---|
| 无 | — |
| Bearer Token | Token 值 |
| OAuth2 | Token 值 |
| API Key | Key 名、Value、位置（Header / Query） |
| Basic Auth | 用户名、密码 |

**前后置脚本**（Tab 面板）
- **前置脚本**：在请求发送前执行自定义 Python 代码
  - 可访问 `variables` 字典修改变量
  - 沙箱限制：禁止 `import os/subprocess/sys`、`open`、`eval`、`exec`，禁止访问 `__class__`/`__bases__`/`__subclasses__` 等危险属性
- **后置脚本**：在响应接收后执行
  - 可访问 `response`（状态码、响应体、响应头）和 `variables`

**会话 Cookie**（Tab 面板）
- 自动捕获响应的 `Set-Cookie`，存储到会话
- 后续请求自动携带 Cookie 头
- 支持手动查看和清除 Cookie

**前置请求**（Tab 面板）
- 配置依赖请求链，在主请求前依次执行
- 支持从前置请求的响应中提取变量

**断言**
- 状态码断言
- JSONPath 断言
- Header 断言
- 响应时间断言
- JSON Schema 断言

**变量提取**
- JSONPath 提取
- 正则提取
- Header 提取

**保存为用例**：调试完成后可保存到接口用例库，保存时会携带认证配置、Cookie、前后置脚本、重试配置等全部参数。

#### 3.2.4 用例管理

**路径**：`/test-cases`

接口测试用例的完整 CRUD 管理：

**用例编辑**（Modal + Tabs 布局）
- **基本信息** Tab：标题、方法、URL、分组路径、项目、标记
- **请求配置** Tab：Headers、Params、Body、断言规则、变量提取
- **失败重试** Tab：
  - 重试次数（0-10）：执行失败时自动重试的次数
  - 重试间隔（0-300 秒）：每次重试之间的等待时间
- **前后置脚本** Tab：前置脚本、后置脚本（Python 代码编辑器）
- **数据库断言** Tab：
  - 为用例配置 DB 断言规则（SQL 查询 + 预期值 + 比较操作符）
  - 支持在线测试断言（需选择环境）
  - 断言类型：等于、不等于、大于、小于、包含、存在

**批量操作**
- 拖拽排序
- 复制用例
- 上下移动
- 按环境执行

#### 3.2.5 测试计划

**路径**：`/test-plans`

将多个用例组合为测试计划，支持批量执行：

| 执行模式 | 说明 |
|---|---|
| 顺序执行 | 按用例顺序依次执行，前序用例失败不影响后续 |
| 并行执行 | 所有用例同时执行 |
| 压力执行 | 模拟并发负载执行 |

操作：创建计划 → 添加用例 → 执行 → 查看结果

#### 3.2.6 数据驱动

**路径**：`/test-data`

支持 CSV / JSON 格式的参数化数据集：
- 一个用例可绑定多个数据集
- 执行时自动遍历数据集行，每行作为一组变量注入用例
- 变量引用语法：`${变量名}`

#### 3.2.7 接口导入

**路径**：`/import`

支持三种导入方式：

| 方式 | 说明 |
|---|---|
| OpenAPI / Swagger | 从 URL 或 JSON 文本导入，支持 OpenAPI 2.0 / 3.0 |
| HAR 抓包 | 上传 .har 文件，自动解析，支持域名/方法筛选后勾选导入 |
| 抓包捕获 | 实时捕获浏览器请求（需配置代理） |

#### 3.2.8 Mock 服务

**路径**：`/mock-service`

配置接口的 Mock 响应：
- 按 URL + Method 匹配
- 自定义响应状态码、Headers、Body
- 支持延迟响应模拟慢接口

#### 3.2.9 AI 助手

**路径**：`/ai`

基于 LLM 的智能测试辅助：
- **用例生成**：输入接口描述或选择已有接口，AI 自动生成测试用例（含断言、边界值、异常场景）
- **批量导入**：AI 生成的用例可一键导入到用例库
- 支持的来源类型：interface（已有接口）、har（HAR 文件）、description（文字描述）

> 需在配置文件中设置 `OPENAI_API_KEY` 和 `LLM_BASE_URL`。

### 3.3 UI 测试

基于 Playwright 的 UI 自动化测试，支持多浏览器、视觉回归、测试套件管理。

#### 3.3.1 UI 用例管理

**路径**：`/ui-test-cases`

**用例配置**
- 浏览器：Chrome / Firefox / Edge
- 视口尺寸：桌面 / 平板 / 手机
- 步骤编排：可视化步骤列表

**支持的步骤类型**（13 种）

| 步骤 | 参数 | 说明 |
|---|---|---|
| navigate | url | 页面导航 |
| click | selector | 点击元素 |
| input | selector, value | 输入文本 |
| assert | selector, expected | 元素断言 |
| wait | selector / time | 等待元素或时间 |
| screenshot | name | 截图 |
| select | selector, value | 下拉选择 |
| press | key | 按键 |
| hover | selector | 悬停 |
| drag | source, target | 拖拽 |
| scroll | selector, direction, amount | 滚动 |
| upload | selector, file_path | 文件上传 |
| download | selector, save_path | 文件下载 |

**视觉回归**
- 为用例设置「基线截图」
- 执行时自动对比当前截图与基线
- 差异分数 ≤ 阈值（默认 0.1）视为通过
- 生成差异图（红色高亮不同区域）
- 支持从最近一次运行截图设置基线

**执行选项**
- 截图：每步自动截图
- 录像：全程录像

#### 3.3.2 测试套件

**路径**：`/ui-test-suites`

将多个 UI 用例组合为套件批量执行：
- 创建套件 → 选择用例 → 执行
- 执行记录以时间线展示
- 支持导出 JUnit XML 报告

#### 3.3.3 元素对象库

**路径**：`/ui-elements`

集中管理 UI 元素定位器：
- 定位方式：CSS / XPath / ID / Name
- 支持复制定位值
- 按项目分组管理

#### 3.3.4 执行记录

**路径**：`/ui-test-records`

查看所有 UI 测试执行历史：
- 按项目 / 状态 / 时间范围筛选
- 查看每步截图和详情
- 导出 JUnit XML（用于 CI/CD 集成）

#### 3.3.5 日志查询

**路径**：`/ui-test-logs`

查看 UI 测试执行日志，支持按用例、时间、级别筛选。

### 3.4 性能测试

基于 Locust 的性能压测平台，支持多种压测模式、实时监控、SLA 告警和趋势对比。

#### 3.4.1 压测场景

**路径**：`/perf-tests`

**压测模式**（4 种）

| 模式 | 说明 | 配置参数 |
|---|---|---|
| 稳定 (steady) | 恒定用户数负载 | 用户数、Spawn Rate、持续时间 |
| 阶梯 (ramp) | 逐步加压 | 起始用户数、阶梯步长、每阶段时间、最大用户数 |
| 峰值 (peak) | 瞬间达到峰值后保持再下降 | 峰值用户数、保持时间 |
| 自定义 (custom) | 自定义曲线 | Stages 列表（每阶段：持续时间、用户数、Spawn Rate） |

**SLA 阈值配置**
- P95 响应时间阈值（毫秒）
- 错误率阈值（0-1）
- 最小 RPS 阈值

压测结束后自动评估 SLA，生成通过 / 失败 / 警告状态。

#### 3.4.2 性能报告

**路径**：`/perf-reports`

**报告内容**
- 响应时间统计：P50 / P90 / P95 / P99
- 吞吐量（RPS）趋势图
- 错误率趋势图
- SLA 状态徽章

**服务器监控**（抽屉面板）
- CPU 使用率折线图
- 内存使用率折线图
- 磁盘 IO 读写速率
- 网络收发流量

**趋势对比**（Tab 面板）
- 选择 2-5 次历史压测结果
- 对比表格：RPS、P95、P99、错误率、CPU 峰值
- 多场景折线图对比

#### 3.4.3 实时仪表盘

**路径**：`/perf-dashboard`

压测运行时的实时监控面板：
- 6 个实时数字卡片：当前用户数 / 瞬时 RPS / 总请求数 / 失败请求数 / 平均响应时间 / 错误率
- 4 个实时折线图：RPS 趋势 / 平均响应时间 / 错误率 / 活跃用户数
- 每 2 秒自动刷新
- 压测完成后自动停止轮询并展示最终结果

### 3.5 测试报告与度量

#### 3.5.1 测试报告

**路径**：`/reports`

- 测试运行列表，含通过 / 失败 / 错误统计
- Chart.js 饼图和趋势图
- 详情查看：每个用例的请求/响应/断言结果
- 数据库断言结果面板
- **导出**：支持导出 HTML 报告（浏览器可打印为 PDF）

#### 3.5.2 覆盖率看板

**路径**：`/coverage`

接口覆盖率质量度量：
- 总覆盖率（环形进度图）
- 按 HTTP 方法的覆盖分布（柱状图）
- 按分组的覆盖率表格
- 最近执行的覆盖率趋势

#### 3.5.3 历史记录

**路径**：`/history`

所有接口调用的历史记录：
- 按状态码 / 方法 / URL 筛选
- 统计概览
- 请求/响应详情查看

#### 3.5.4 定时任务

**路径**：`/scheduled-tasks`

基于 Cron 表达式的定时执行：
- 创建定时任务（选择测试计划 + Cron 表达式）
- 启用 / 停用
- 手动触发执行
- 查看执行结果历史

### 3.6 环境与变量管理

#### 3.6.1 环境管理

**路径**：`/environments`

管理不同测试环境的配置：

| 配置项 | 说明 |
|---|---|
| 名称 | 环境标识（如：开发、测试、生产） |
| Base URL | 环境基础地址 |
| 环境变量 | Key-Value 键值对，执行时自动注入 |
| 数据库配置 | 数据库类型、地址、端口、库名、用户名、密码（用于 DB 断言） |
| Cookie | 环境级 Cookie 列表（name / value / domain / path） |

#### 3.6.2 变量管理

**路径**：`/variables`

全局/工作空间级变量管理：

| 作用域 | 说明 |
|---|---|
| global | 全局变量，所有项目共享 |
| workspace | 工作空间变量，绑定到特定项目 |

**变量类型**：string / number / boolean / json

**变量优先级**（高 → 低）：临时变量（运行参数） > 环境变量 > 全局变量

**引用语法**：`${变量名}`

### 3.7 知识工程

沉淀测试经验，形成可复用的知识库。

#### 3.7.1 缺陷模式库

**路径**：`/knowledge/defects`

| 字段 | 选项 |
|---|---|
| 类型 | error（错误处理）/ boundary（边界值）/ security（安全）/ performance（性能）/ logic（逻辑） |
| 严重等级 | P0 / P1 / P2 |
| 描述 | 缺陷模式描述、触发条件、预期行为 |
| 关联用例 | 可关联到具体测试用例 |

#### 3.7.2 业务规则库

**路径**：`/knowledge/rules`

| 字段 | 选项 |
|---|---|
| 类型 | validation（校验）/ business_flow（业务流程）/ data_integrity（数据完整性）/ security（安全） |
| 优先级 | 高 / 中 / 低 |
| 规则内容 | 规则描述、验证方法、适用范围 |

#### 3.7.3 接口知识库

**路径**：`/knowledge/interfaces`

按 HTTP 方法组织的接口知识文档：
- 接口设计说明
- 业务语义
- 测试要点
- 标签分类

### 3.8 系统管理

#### 3.8.1 用户管理

**路径**：`/users`

- 用户 CRUD、启用/停用
- 为用户分配角色
- 字段：用户名、邮箱、是否激活、是否超管、角色列表

#### 3.8.2 角色管理

**路径**：`/roles`

- 角色 CRUD
- 权限预设：

| 权限标识 | 说明 |
|---|---|
| user:read / user:manage | 用户查看 / 管理 |
| role:read / role:manage | 角色查看 / 管理 |
| project:read / project:manage | 项目查看 / 管理 |
| testcase:read / testcase:manage | 用例查看 / 管理 |

#### 3.8.3 API Token

**路径**：`/api-tokens`

用于 CI/CD 和外部系统调用 API 的令牌管理：
- 作用域：`test-cases:execute` / `test-plans:execute` / `ci:trigger`
- 创建时一次性展示明文 Token（后续不可查看）
- 支持吊销

#### 3.8.4 CI/CD 集成

**路径**：`/ci-cd`

| 功能 | 说明 |
|---|---|
| Webhook 配置 | 配置事件钩子（如 test_run.completed） |
| 手动触发 | 手动触发 CI 流水线 |
| 事件类型 | 测试运行完成、用例失败等 |

#### 3.8.5 通知管理

**路径**：`/notifications`

- 通知渠道配置（邮件 / Webhook / 钉钉等）
- 通知规则（触发条件 + 通知渠道）
- 通知日志查看

#### 3.8.6 项目管理

**路径**：`/projects`

- 项目 CRUD
- 统计各项目下用例数
- 项目是其他资源（用例、环境、变量等）的归属主体

---

## 4 高级功能

### 4.1 变量替换引擎

平台支持在 URL、Headers、Params、Body 中使用变量引用：

```
https://${host}/api/v1/users/${user_id}
```

**变量来源与优先级**（高 → 低）：

1. **临时变量**：执行时传入的运行参数
2. **变量提取**：前置请求或前置脚本中提取的变量
3. **环境变量**：当前执行环境的变量配置
4. **全局变量**：`/variables` 页面配置的全局/工作空间变量

### 4.2 前后置脚本

```python
# 前置脚本示例：生成时间戳签名
import time
timestamp = str(int(time.time()))
variables["timestamp"] = timestamp
variables["sign"] = "md5_" + timestamp + "_secret"

# 后置脚本示例：校验响应并提取 token
if response["status_code"] == 200:
    data = response["json"]
    if data.get("code") == 0:
        variables["token"] = data["data"]["access_token"]
    else:
        raise Exception("登录失败: " + str(data))
```

**沙箱安全限制**：
- 禁止：`import os`、`import subprocess`、`import sys`、`open()`、`eval()`、`exec()`、`__import__()`
- 禁止访问双下划线属性：`__class__`、`__bases__`、`__subclasses__`、`__globals__`、`__builtins__`、`__mro__`
- 允许：基础 Python 语法、`time`、`json`、`re`、`math`、`variables` 字典

### 4.3 数据库断言

在用例执行后自动验证数据库状态：

```sql
-- 断言用户注册后数据库中确实新增了记录
SELECT COUNT(*) FROM users WHERE username = '${username}'
```

| 比较操作 | 说明 |
|---|---|
| 等于 | 查询结果等于预期值 |
| 不等于 | 查询结果不等于预期值 |
| 大于 | 查询结果大于预期值 |
| 小于 | 查询结果小于预期值 |
| 包含 | 查询结果包含预期值 |
| 存在 | 查询结果不为空 |

### 4.4 视觉回归测试

```工作流
设置基线截图 → 执行用例 → 自动对比 → 生成差异图 → 判定通过/失败
```

- 差异分数范围：0（完全相同）~ 1（完全不同）
- 默认阈值：0.1（即 10% 以下的像素差异视为通过）
- 差异图：不同区域以红色高亮标记

### 4.5 JUnit XML 集成

UI 测试支持导出标准 JUnit XML 报告，可无缝集成到 CI/CD 系统：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="LoginSuite" tests="5" failures="1" errors="0" time="23.4">
  <testcase name="登录成功" classname="LoginSuite" time="2.1"/>
  <testcase name="密码错误" classname="LoginSuite" time="3.2">
    <failure message="Expected error message">...</failure>
  </testcase>
</testsuite>
```

---

## 5 API 参考速查

### 5.1 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/login` | 登录，返回 JWT |
| POST | `/api/v1/auth/register` | 注册（首个用户自动成为超管） |
| GET | `/api/v1/auth/me` | 获取当前用户信息 |

### 5.2 核心资源

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/v1/projects` | 项目列表/创建 |
| GET/PUT/DELETE | `/api/v1/projects/{id}` | 项目详情/更新/删除 |
| GET/POST | `/api/v1/test-cases` | 用例列表/创建 |
| GET/PUT/DELETE | `/api/v1/test-cases/{id}` | 用例详情/更新/删除 |
| GET/POST | `/api/v1/test-plans` | 测试计划列表/创建 |
| GET/POST | `/api/v1/environments` | 环境列表/创建 |
| GET/POST | `/api/v1/variables` | 全局变量列表/创建 |

### 5.3 执行引擎

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/execution/run` | 执行单次请求（支持重试、脚本、Cookie） |
| POST | `/api/v1/execution/run-multipart` | 执行 Multipart 请求（文件上传） |
| POST | `/api/v1/execution/cases/{case_id}/run` | 执行已保存的用例 |

### 5.4 UI 测试

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/v1/ui-test-cases` | UI 用例列表/创建 |
| POST | `/api/v1/ui-test-cases/{id}/run` | 执行 UI 用例 |
| GET/POST | `/api/v1/ui-test-suites` | UI 套件列表/创建 |
| POST | `/api/v1/ui-test-suites/{id}/run` | 执行 UI 套件 |
| GET | `/api/v1/ui-test-records/{id}/junit` | 导出 JUnit XML |
| GET/POST | `/api/v1/visual-regression/baselines` | 视觉基线管理 |

### 5.5 性能测试

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/v1/perf-tests` | 压测场景列表/创建 |
| POST | `/api/v1/perf-tests/{id}/run` | 启动压测 |
| GET | `/api/v1/perf-tests/{id}/realtime` | 实时指标（轮询） |
| GET | `/api/v1/perf-tests/{id}/metrics` | 服务器监控数据 |
| GET | `/api/v1/perf-tests/{id}/results/{rid}/sla` | SLA 评估详情 |
| GET | `/api/v1/perf-tests/trends` | 趋势对比 |
| GET | `/api/v1/perf-tests/{id}/history` | 历史结果 |

### 5.6 报告与度量

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/reports` | 测试报告列表 |
| GET | `/api/v1/report-export/{run_id}/html` | 导出 HTML 报告 |
| GET | `/api/v1/report-export/{run_id}/pdf` | 导出 PDF 报告 |
| GET | `/api/v1/coverage` | 接口覆盖率统计 |

### 5.7 导入与知识

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/import/preview-har` | HAR 文件预览 |
| POST | `/api/v1/import/har` | HAR 文件导入 |
| POST | `/api/v1/import/openapi` | OpenAPI 导入 |
| GET/POST | `/api/v1/knowledge/defects` | 缺陷模式管理 |
| GET/POST | `/api/v1/knowledge/rules` | 业务规则管理 |
| GET/POST | `/api/v1/knowledge/interfaces` | 接口知识管理 |

### 5.8 系统管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/v1/users` | 用户管理 |
| GET/POST | `/api/v1/roles` | 角色管理 |
| GET/POST | `/api/v1/api-tokens` | API Token 管理 |
| GET/POST | `/api/v1/ci/webhooks` | CI/CD Webhook |
| GET/POST | `/api/v1/notifications/channels` | 通知渠道 |

> 完整 API 文档请访问 http://localhost:8000/docs

---

## 6 常见问题

### Q1: Windows 启动后端报 WinError 10038

**原因**：Python 3.13 在 Windows 上的 asyncio 模块与 WinSock 初始化冲突。

**解决**：使用 `python run_server.py` 启动，该脚本会先初始化 WinSock 再设置 SelectorEventLoop。

### Q2: Node.js 版本过低导致前端无法启动

**原因**：Vite 8 要求 Node.js ≥ 20.19 或 22.12+。

**解决**：升级 Node.js 到最新 LTS 版本。可下载便携版解压使用，无需覆盖安装。

### Q3: 前端页面显示空白或报错

**排查步骤**：
1. 确认后端已启动：访问 http://localhost:8000/health
2. 确认前端已启动：访问 http://localhost:5173
3. 强制刷新浏览器：`Ctrl + Shift + R`
4. 检查浏览器控制台（F12）是否有错误

### Q4: 数据库字段缺失报错

**原因**：模型新增了字段但 SQLite 未自动添加列。

**解决**：运行迁移脚本：
```bash
cd backend
python migrations/add_perf_enhancements.py
python migrations/add_test_case_script_fields.py
```

### Q5: Playwright UI 测试无法执行

**原因**：未安装浏览器内核。

**解决**：
```bash
playwright install chromium
```

### Q6: 如何切换到 MySQL 数据库

在 `backend/` 目录创建 `.env` 文件：
```env
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/airetest
```

### Q7: 前后置脚本执行报错

**检查项**：
1. 脚本是否使用了被禁用的关键字（`import os`、`open` 等）
2. 脚本是否访问了双下划线属性（`__class__` 等）
3. 脚本中的变量引用是否正确（`variables["key"]`）

### Q8: 压测实时仪表盘数据不更新

**检查项**：
1. 确认压测场景已关联测试用例
2. 确认压测状态为 `running`
3. 仪表盘每 2 秒轮询一次，等待片刻
4. 压测完成后会自动停止轮询

---

## 附录：配置项速查

| 配置项 | 默认值 | 说明 |
|---|---|---|
| APP_NAME | AI Test Platform | 应用名称 |
| DATABASE_URL | sqlite:///./aitest.db | 数据库连接 |
| SECRET_KEY | dev-secret-change-in-production | JWT 密钥（生产环境务必修改） |
| ACCESS_TOKEN_EXPIRE_MINUTES | 1440 (24h) | Token 有效期 |
| OPENAI_API_KEY | (空) | LLM 密钥 |
| LLM_MODEL | gpt-4 | LLM 模型 |
| REDIS_URL | redis://localhost:6379/0 | Redis（可选） |
| DEBUG | True | 调试模式 |

> 配置通过环境变量或 `backend/.env` 文件设置。
