FROM node:22-slim

WORKDIR /app

# 复制 package 文件
COPY package*.json ./

# 安装依赖
RUN npm ci || npm install

# 复制源码
COPY . .

# 暴露端口
EXPOSE 5173

# 启动开发服务器
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
