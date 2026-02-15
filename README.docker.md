# 🐳 Docker 部署指南

本指南将帮助你使用 Docker 容器化部署 Film Genealogy Agent。

## 前置要求

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

## 🚀 快速开始

1. **环境配置**

   复制环境变量模板：
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

   编辑 `backend/.env` 填入你的 API Key：
   ```bash
   TMDB_API_KEY=your_key
   OPENROUTER_API_KEY=your_key
   ```

2. **启动服务**

   ```bash
   docker-compose up -d --build
   ```

3. **访问应用**

   - 前端: http://localhost:3000
   - 后端 API: http://localhost:8000
   - API 文档: http://localhost:8000/docs

## 📁 数据持久化

Docker 部署会自动创建以下 Volume 保持数据：

- `sqlite_data`: 数据库文件
- `./media`: 你的电影 NFO 目录（默认映射到宿主机的 `./media`，可在 `docker-compose.yml` 中修改）

## 🛠️ 常用命令

```bash
# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 重建镜像
docker-compose up -d --build
```

## 🌐 生产环境部署建议

1. 修改 `docker-compose.yml` 中的端口映射
2. 使用 Nginx 反向代理处理 HTTPS
3. 在 `backend/.env` 中更新 `ALLOWED_ORIGINS`
4. 在 `frontend/.env` 中更新 `NEXT_PUBLIC_API_URL`

## 📦 发布到 Docker Hub

如果你想将应用发布给他人使用（开箱即用）：

1. **构建并推送镜像**

   编辑 `publish.sh` 确认你的 Docker Hub 用户名，然后运行：
   ```bash
   ./publish.sh
   ```

2. **用户部署**

   用户只需要 `docker-compose.release.yml` 和 `.env`文件即可部署，无需源代码。
   
   ```bash
   # 使用发布版配置启动
   docker-compose -f docker-compose.release.yml up -d
   ```
