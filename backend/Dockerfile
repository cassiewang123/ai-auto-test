FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖（Playwright 需要的库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装测试执行引擎
COPY test-engine /tmp/test-engine
RUN pip install --no-cache-dir /tmp/test-engine

# 安装 Playwright 浏览器
RUN playwright install chromium --with-deps

# 复制后端源码
COPY backend/ .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
