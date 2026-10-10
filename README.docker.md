# 5X49 Docker 部署指南

本指南使用 Docker Hub 上的发布镜像，不从当前仓库构建源代码。源码开发步骤见
[README.zh-CN.md](README.zh-CN.md#从源码开发)。

## 启动

要求 Docker Desktop/Engine 和 Docker Compose v2。

```bash
cp .env.example .env
mkdir -p media
docker compose up -d
```

PowerShell 复制环境模板：

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force media
docker compose up -d
```

默认地址：

- 前端：`http://localhost:5549`
- 后端 API：`http://localhost:11548`
- OpenAPI：`http://localhost:11548/docs`

`docker-compose.yml` 是普通用户的规范部署文件；
`docker-compose.release.yml` 用于固定版本的 RC 验收，需要显式指定镜像和媒体目录；
默认绑定本机地址、只读媒体。普通配置使用固定容器名；RC 配置支持独立 Compose project。步骤见
[RC 打包与固定镜像部署](docs/rc-distribution.md)。

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

宿主机目录必须在启动前存在（`create_host_path: false` 不会自动创建它）。以上命令
创建默认的 `./media`；使用自定义 `MEDIA_DIR` 时，请先创建或确认该目录。

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

普通部署默认使用远程 `latest` 镜像。需要固定版本、可追溯的 RC 产物和安装恢复验收时，
使用 [RC 分发流程](docs/rc-distribution.md)；该流程生成 digest 固定的部署配置。

## 端口与后端地址

`FRONTEND_PORT`（默认 `5549`）和 `BACKEND_PORT`（默认 `11548`）只修改宿主机
端口，容器内仍为 `3000` 和 `8000`。修改前端端口时，也应同步 `ALLOWED_ORIGINS`。
Compose 前端在运行时使用 `BACKEND_URL=http://backend:8000`，API、事件流和媒体
请求共用此地址。独立运行 standalone 时可在启动 `node server.js` 前设置
`BACKEND_URL`，无需重新构建；未设置时生产默认 `http://backend:8000`，开发默认
`http://127.0.0.1:8000`。旧的 `API_URL` 仅作为未设置 `BACKEND_URL` 时的兼容回退。

后端 watcher 数值环境变量使用整数秒：`WATCH_DEBOUNCE_SECONDS` 默认 5、
`WATCH_INTERVAL_SECONDS` 默认 5、`MEDIA_FILE_STABLE_SECONDS` 默认 15。
允许范围分别为 0–86400、1–86400、0–86400；空值、非法值和越界值使用默认值。
这些变量需要在后端运行环境设置；普通 Compose 模板不自动传递它们。
