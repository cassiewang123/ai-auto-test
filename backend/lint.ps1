# 后端代码质量检查
Write-Host "Running ruff..."
ruff check app/ test-engine/
Write-Host "Running mypy..."
mypy app/ --ignore-missing-imports
Write-Host "Running bandit..."
bandit -r app/ -c pyproject.toml
