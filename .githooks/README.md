# 提交前检查密钥泄漏

本目录存放可共享的 Git 钩子。启用方式（每个克隆执行一次）：

```bash
git config core.hooksPath .githooks
```

启用后 `git commit` 会自动执行 `pre-commit`：

1. **拒绝提交本地环境文件**：`.env`、`.env.*`（`.example` 除外）一律不得进入仓库。
   即使有人用 `git add -f .env` 强制添加也会被拦下。
2. **拒绝提交疑似明文密钥**：扫描暂存区新增的行，命中 `sk-...`、
   `api_key = "..."` 等形态即中止提交。

## 为什么需要它

LLM 的 API Key 属于本机凭据，只应写在本地 `.env`（已被 `.gitignore` 忽略）。
一旦 Key 进入 Git 历史并推送到远程，即使后续删除文件，Key 也已经泄露，
只能吊销重置。这道钩子把问题挡在提交之前。

## 误报处理

确认无误报风险时可跳过：

```bash
git commit --no-verify
```

但如果是真的密钥，请改为：把密钥写入本机 `.env`，代码中通过
`app.config.get_settings()` 读取，而不是硬编码。

## Windows 说明

Git for Windows 自带 sh，可直接执行该钩子。若提示无权限，执行：

```bash
chmod +x .githooks/pre-commit
```
