# 5X49 Docker 部署指南

本指南使用 Docker Hub 上的发布镜像，不从当前仓库构建源代码。源码开发步骤见
[README.zh-CN.md](README.zh-CN.md#从源码开发)。

## 启动

要求 Docker Desktop/Engine 和 Docker Compose v2。

```bash
cp .env.example .env
docker compose up -d
```

PowerShell 复制环境模板：

```powershell
Copy-Item .env.example .env
docker compose up -d
```

默认地址：

- 前端：`http://localhost:5549`
- 后端 API：`http://localhost:11548`
- OpenAPI：`http://localhost:11548/docs`

`docker-compose.yml` 是普通用户的规范部署文件；
`docker-compose.release.yml` 保留相同的端口、环境变量和镜像行为，供已有发布流程使用。

## 媒体目录

`.env` 中的 `MEDIA_DIR` 是宿主机路径，Compose 会将其挂载为后端容器中的
`/media`：

```dotenv
# 仓库相对目录
MEDIA_DIR=./media

# Linux / NAS 示例
# MEDIA_DIR=/volume1/video/movies

# Windows Docker Desktop 示例
# MEDIA_DIR=D:/Movies
```

首次打开页面时，Docker 用户应保持应用内媒体目录为 `/media`。页面会检查这个
容器内目录是否存在且可读。修改宿主机映射后需要重新创建容器：

```bash
docker compose up -d --force-recreate
```

## 可选密钥

```dotenv
TMDB_API_KEY=
OPENROUTER_API_KEY=
```

两项都可留空。本地扫描和资料库浏览不依赖它们；TMDB Key 启用在线元数据与
图片刮削，OpenRouter Key 启用 AI 谱系分析。

## 持久化与维护

- `backend_data`：SQLite 数据库、设置和运行状态。
- `${MEDIA_DIR}:/media`：只由用户选择的宿主机目录提供媒体。

常用命令：

```bash
docker compose ps
docker compose logs -f backend frontend
docker compose restart
docker compose pull
docker compose up -d
docker compose down
```

`docker compose down -v` 会删除 `backend_data`，仅在明确不需要数据库和设置时使用。

## 排错

- 前端无法读取资料库：检查 `docker compose ps` 和 `docker compose logs backend`。
- `/media` 不可读：检查宿主机目录存在、共享权限以及 Docker Desktop 文件访问权限。
- 扫描结果为零：确认每部电影位于一级子目录，且包含受支持的视频或 NFO。
- Key 测试失败：不会影响基础资料库；确认环境变量后重新创建 backend 容器。

本部署路径使用远程 `latest` 镜像。镜像 digest 固定和可复现构建不在当前部署契约内。
