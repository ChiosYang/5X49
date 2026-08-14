# Docker 干净安装基线

> 测量日期：2026-08-14
>
> 基线状态：部分完成（静态审查完成；Docker 运行态 smoke 被执行环境阻塞）
>
> 基线提交：`origin/main` @ `4426a6a688dc51390a3acbbdd8e9d7a518847321`
>
> 本报告只记录当前行为和风险，不修复 README、Compose、Dockerfile、端口、应用代码或配置。

## 1. 执行摘要

本次基线在 Codex Desktop 托管的 linked worktree 中执行。工作分支从刚刚 fetch 的
`origin/main` 创建，Local/main 保持只读。静态安装契约、端口、环境变量、镜像来源、
健康检查、无 Key 代码路径和最小 NFO 扫描路径已经审查。

运行态 Docker smoke 未能开始：当前 Windows 执行环境找不到 `docker`、
`docker-compose` 或 `podman`，Docker Desktop 的标准 CLI 路径也不存在。因此没有拉取或
构建镜像，没有启动容器或创建 volume，也没有测得应用启动耗时、实际就绪时间或运行态
访问 URL。按照任务的安全约束，这些结果全部标记为“未验证”，不使用本机开发服务器替代
Docker 结果。

静态审查确认一个直接影响首次安装的问题：README 指示访问
`http://localhost:3000`，但仓库根 `docker-compose.yml` 实际暴露前端端口
`11549`；README 示例中的后端端口是 `8000`，根 Compose 实际暴露 `11548`。

## 2. 执行边界与 Worktree

| 项目 | 结果 |
| --- | --- |
| execution lane | `desktop-app-managed` |
| 当前 Worktree | `C:\Users\Administrator\.codex\worktrees\e8cd\5X49` |
| checkout 类型 | `linked-worktree`（Codex Desktop 托管路径） |
| 初始 HEAD | detached HEAD，`4426a6a688dc51390a3acbbdd8e9d7a518847321` |
| 基线 | `origin/main`，`4426a6a688dc51390a3acbbdd8e9d7a518847321` |
| 工作分支 | `feature/docker-install-baseline`，跟踪 `origin/main` |
| Local/main | `D:\Projects\5X49`；未写入、未切换、未清理 |
| 路线图依据 | 只读读取 `D:\Projects\5X49\docs\product-roadmap.md`；未修改 |
| 第二个 Worktree | 未创建 |
| 任务开始时工作区 | clean；无进行中的 Git 操作 |

`manage-worktree` 预检列出的当前 Worktree Git 目录是
`D:/Projects/5X49/.git/worktrees/5X493`，公共 Git 目录是
`D:/Projects/5X49/.git`。这与 app-managed linked worktree 的执行通道一致。

## 3. 被审查的安装面

本次读取并审查了以下仓库文件：

- `README.md`
- `README.docker.md`
- `setup.sh`
- `docker-compose.yml`
- `docker-compose.release.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- 后端启动、健康检查、设置、扫描、后台任务和数据库路径相关代码
- 前端 rewrite、server-side backend URL 和 SSE 代理相关代码

没有读取任何真实 `.env` 文件、密钥值、用户媒体内容、用户数据库或用户媒体路径。

## 4. 当前安装契约

### 4.1 README 与 Compose 端口

| 来源 | 前端 | 后端 | 结论 |
| --- | --- | --- | --- |
| `README.md` Quick Deploy 示例 | `localhost:3000` | `localhost:8000` | README 明确指示访问前端 `3000` |
| 根 `docker-compose.yml` | `localhost:11549` → 容器 `3000` | `localhost:11548` → 容器 `8000` | 与 README 不一致 |
| `docker-compose.release.yml` | `localhost:3000` → 容器 `3000` | `localhost:8000` → 容器 `8000` | 与 README 示例一致 |
| `README.docker.md` | `localhost:3000` | `localhost:8000` | 与 release Compose 一致，与根 Compose 不一致 |

如果用户在仓库根运行 README 给出的 `docker-compose up -d`，被选中的默认文件是根
`docker-compose.yml`。按配置推导，预期 URL 应为：

- 前端：`http://localhost:11549`
- 后端健康检查：`http://localhost:11548/health`
- 后端 OpenAPI：`http://localhost:11548/docs`
- 通过前端同源代理访问健康检查：`http://localhost:11549/api/health`

以上是配置推导 URL，不是本次实际访问成功的 URL；运行态因 Docker 不可用而未验证。

### 4.2 镜像与构建行为

根 Compose 和 release Compose 都只有 `image:`，没有 `build:`：

- backend：`alicolia/5x49-backend:latest`（release 文件允许通过 `DOCKER_USERNAME` 改用户名）
- frontend：`alicolia/5x49-frontend:latest`（release 文件允许通过 `DOCKER_USERNAME` 改用户名）

因此从仓库运行 `docker compose up -d` 的预期行为是使用本地已有镜像或拉取
`:latest`，而不是从当前 checkout 的 Dockerfile 构建。`README.docker.md` 给出的
`docker-compose up -d --build` 也没有对应的 Compose `build:` 配置，不能把当前提交和
运行镜像绑定起来。

Dockerfile 静态基线：

- backend 基于 `python:3.13-slim`，从 `ghcr.io/astral-sh/uv:latest` 复制 `uv`，安装
  `ffmpeg`，暴露 `8000`，运行 Uvicorn。
- frontend 为多阶段 `node:20-alpine` 构建，运行 `npm ci` 和 `npm run build`，输出
  Next.js standalone，暴露 `3000`。
- 基础镜像、`uv` 和 Compose 应用镜像均未使用 digest 固定。

本次实际镜像结果：

| 项目 | 结果 |
| --- | --- |
| 镜像 pull | 未执行；Docker CLI 不可用 |
| backend build | 未执行；Docker CLI 不可用，且默认 Compose 没有 `build:` |
| frontend build | 未执行；Docker CLI 不可用，且默认 Compose 没有 `build:` |
| multi-architecture manifest | 未验证 |
| 镜像与基线 commit 对应关系 | 无法确认；Compose 使用可移动的 `:latest` |

### 4.3 环境变量与持久化

根 Compose 当前引用：

| 变量 | Compose 默认/用途 | 无值时的静态行为 |
| --- | --- | --- |
| `MEDIA_DIR` | 宿主机 `${MEDIA_DIR:-./media}` 绑定到容器 `/media` | 使用仓库相对目录 `./media`；后端容器内仍固定为 `/media` |
| `TMDB_API_KEY` | 传入 backend，默认空 | 基础 NFO 扫描代码不依赖；TMDB 搜索/刮削调用会缺少凭据 |
| `OPENROUTER_API_KEY` | 传入 backend，默认空 | 设置服务回退到缓存/内置模型列表；实际 AI 调用不可用 |
| `MODEL_NAME` | 默认 `openrouter/pony-alpha` | 仅模型名回退，不提供访问凭据 |
| `API_BASE_URL` | 默认 `https://openrouter.ai/api/v1` | 仅 AI provider URL |
| `ALLOWED_ORIGINS` | 根 Compose 默认 `*` | 后端启用 credentials；同源前端代理通常不依赖跨源 CORS |
| `API_URL` | root frontend 设置为 `http://backend:8000` | SSE route 会读取；其余 server API/rewrite 默认也指向 `backend:8000` |
| `NEXT_PUBLIC_API_URL` | release frontend 默认 `http://localhost:8000` | 当前前端代码未检索到该变量的消费点 |

后端数据写入容器 `/app/data`，由 Compose 命名 volume `backend_data` 持久化。没有设置
显式的全局 volume `name:`，正常情况下 volume 名会受 Compose project name 限定；但是
两个服务同时设置了固定 `container_name`（`5x49-backend`、`5x49-frontend`），容器名不受
project name 隔离。

README 推荐的 `setup.sh` 会交互式生成根 `.env`，默认媒体目录为
`/volume1/video/movies`，并把两个 Key 作为可选输入。脚本没有验证该目录是否存在、是否
可读或是否适合当前宿主机；执行前仍需用户确认媒体目录。README 对 OpenRouter Key 的
“Required”描述与脚本的“Optional”、Compose 的空默认和路线图的“AI 可缺省”目标不一致。

## 5. 健康检查与就绪语义

### 5.1 当前配置

- backend Dockerfile 与两套 Compose 都配置 backend healthcheck。
- 探测命令调用 `requests.get('http://localhost:8000/health')`。
- Compose 参数为 interval `30s`、timeout `10s`、retries `3`，没有 `start_period`。
- `/health` 当前固定返回 `{"status":"healthy"}`。
- frontend 没有 healthcheck。
- frontend 的 `depends_on` 只声明 backend 服务，不使用 `condition: service_healthy`。

### 5.2 能证明与不能证明的内容

当前 `/health` 能在 200 响应时证明 FastAPI 路由可响应，但不检查：

- SQLite 是否可读写、schema 创建或手写迁移是否成功；
- Job runtime 是否工作；
- 媒体目录是否存在、可读或可写；
- TMDB/OpenRouter 是否已配置或可达；
- frontend 是否能访问 backend；
- frontend 自身是否已就绪。

healthcheck Python 命令没有调用 `raise_for_status()`，所以只要请求本身没有抛异常，即使
未来 `/health` 返回非 2xx，命令也可能以 0 退出。运行态健康状态与首次 healthy 时间本次
均未验证。

## 6. 无 TMDB/OpenRouter Key 的降级行为

### 6.1 静态确认

- Compose 显式允许两个 Key 为空。
- 基础应用启动不会在 `FilmHistorian` 构造阶段立即创建 OpenAI client；client 在实际分析
  调用时才创建。
- 无 OpenRouter Key 时，设置服务先尝试缓存，最后返回一个内置模型名列表；这不代表 AI
  调用可成功。
- `GET /settings/test-api-key` 会返回“未配置”的 error 状态，而不是令应用进程退出。
- 无 TMDB Key 时，TMDB 测试/搜索/刮削路径会失败或返回未配置错误。
- NFO 扫描、Library 读取与本地 SQLite 路径在代码上不依赖这两个 Key。

### 6.2 运行态状态

以下均未验证：

- 无 Key 时 backend 容器是否能完成首次启动；
- 无 Key 时 frontend 是否能打开 Library；
- UI 是否清楚区分“基础功能可用”和“TMDB/AI 不可用”；
- 触发 AI、TMDB 搜索或刮削时的实际 HTTP 状态、错误文案和日志脱敏；
- 无 Key 时是否存在意外外部网络请求。

## 7. 最小 NFO 导入可行性

### 7.1 静态确认的输入形态

`NFOScanner` 遍历媒体根目录的一级非隐藏子目录。每个电影目录内按以下优先级找 NFO：

1. 与视频文件同 stem 的 `.nfo`；
2. `movie.nfo`；
3. 按文件名排序后的第一个 `*.nfo`。

存在 NFO 时，即使目录中没有视频文件，扫描器也会尝试解析。最小可识别 XML 可以只包含
`<movie>` 根节点、`<title>` 和 `<year>`；缺少的其他字段有默认值。实际导入流程为：

1. 将电影子目录放在宿主机配置的 `MEDIA_DIR` 下；
2. 容器内路径保持 `/media`；
3. 通过 Settings 页触发扫描，或调用 `POST /library/scan`；
4. API 返回 queued job，而不是同步完成结果；
5. 使用返回的 job ID 查询 `GET /jobs/{job_id}`，再用 `GET /library` 确认条目。

### 7.2 实测状态

Docker 端到端最小 NFO 导入未验证。为了确认是否能在不安装依赖的情况下运行扫描器，执行
了只读导入探测；系统 Python 在导入 `app.services.scanner` 时因缺少 Pillow（`PIL`）失败。
本任务没有为此创建 `.venv` 或安装依赖，因为本机 Python smoke 不能替代 Docker 干净安装
结论。

因此以下测量值仍为空：

- 一部最小 NFO 从 `POST /library/scan` 到 job completed 的耗时；
- `scanned`、`added`、`missing` 的实际结果；
- 导入后 Library 页面/详情页是否可见；
- 重复扫描是否在该镜像版本中保持幂等；
- 只读媒体目录、无视频文件、无 artwork 时的容器行为。

## 8. 实际执行记录与测量值

### 8.1 关键命令

以下命令确实执行过；命令中未输出 `.env` 或任何 Key 值。

```powershell
# 完整读取规则与 Skill
Get-Content -LiteralPath C:\Users\Administrator\agent-dotfiles\skills\manage-worktree\SKILL.md -Raw
Get-Content -LiteralPath C:\Users\Administrator\.codex\worktrees\e8cd\5X49\AGENTS.md -Raw

# Worktree 预检（首次因 sandbox 无权写共享 FETCH_HEAD 失败；批准后重试成功）
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.agents\skills\manage-worktree\scripts\worktree-status.ps1" -Fetch

# 核对并创建任务分支
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git rev-parse --git-dir
git rev-parse --git-common-dir
git switch -c feature/docker-install-baseline origin/main

# 静态安装审查（按文件逐一读取；使用 rg 只搜索跟踪文件和配置引用）
Get-Content -LiteralPath README.md -Raw
Get-Content -LiteralPath docker-compose.yml -Raw
Get-Content -LiteralPath docker-compose.release.yml -Raw
Get-Content -LiteralPath backend/Dockerfile -Raw
Get-Content -LiteralPath frontend/Dockerfile -Raw
Get-Content -LiteralPath setup.sh -Raw
Get-Content -LiteralPath D:\Projects\5X49\docs\product-roadmap.md -Raw
$tracked = git ls-files 'backend/**' 'frontend/**' 'README*' 'docker-compose*.yml'
rg -n --no-heading -S "health|MEDIA_DIR|TMDB_API_KEY|OPENROUTER_API_KEY|API_BASE_URL|ALLOWED_ORIGINS|API_URL|BACKEND_URL|3000|8000|11548|11549|\.nfo" $tracked

# Docker 可用性与安全隔离前置探测
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
docker compose version
docker info --format 'server={{.ServerVersion}} os={{.OperatingSystem}} arch={{.Architecture}}'
docker ps -a --filter "name=^/5x49-backend$" --filter "name=^/5x49-frontend$" --format '{{.ID}} {{.Names}} {{.Status}} {{.Image}}'
Get-Command docker,docker-compose,podman -ErrorAction SilentlyContinue
Test-Path 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
Test-Path 'C:\Program Files\Docker\Docker\resources\bin\com.docker.cli.exe'
Test-Path 'C:\Windows\System32\docker.exe'

# 本机扫描器导入探测
python -c "import sys; sys.path.insert(0, r'backend'); from app.services.scanner import NFOScanner; print('scanner_import=ok')"

# 最终范围与文档校验
git diff --check
git diff --no-index --check -- /dev/null docs/install-baseline.md
git status --short --branch
git rev-list --left-right --count origin/main...HEAD
git -C D:\Projects\5X49 status --short -- docs/product-roadmap.md
Get-Item -LiteralPath D:\Projects\5X49\docs\product-roadmap.md
```

### 8.2 结果与耗时

| 检查 | 实际结果 | 观测耗时 |
| --- | --- | ---: |
| Worktree status + fetch | 成功；linked worktree、detached、clean、base=`origin/main` | 2.3 s（成功重试） |
| 分支创建 | 成功；`feature/docker-install-baseline` 跟踪 `origin/main` | 0.8 s |
| Docker 版本/daemon/容器名探测 | 在第一个 `docker` 调用即失败：命令不可识别；后续同组调用同样不可识别 | 0.9 s |
| Docker/Compose/Podman 可执行文件查询 | 三者均 `NOT_FOUND` | 0.8 s |
| Docker Desktop 标准 CLI 路径 | 三个候选路径均不存在 | 1.1 s |
| 扫描器本机导入探测 | 失败：`ModuleNotFoundError: No module named 'PIL'` | 1.2 s |
| 新报告 whitespace/编码检查 | 未发现 whitespace error 或 Unicode replacement character；Git 仅提示未来可能把 LF 转为 CRLF | 1.0 s |
| 分支范围 | `origin/main...HEAD` 为 `0 0`；唯一状态项是未跟踪的新报告 | 1.1 s |
| Local 路线图只读复核 | 直接文件元数据仍为 39,323 bytes、`2026-08-14 14:02:42`；targeted Git status 因 sandbox 用户触发 dubious ownership 而未执行，未修改全局 Git 配置 | 1.1 s |
| 镜像 pull/build | 未执行 | 未测量 |
| Compose create/start | 未执行 | 未测量 |
| backend 首次响应 | 未验证 | 未测量 |
| backend healthy | 未验证 | 未测量 |
| frontend 首次响应/可用 | 未验证 | 未测量 |
| 无 Key Library 页面 | 未验证 | 未测量 |
| 最小 NFO 导入 | 未验证 | 未测量 |

### 8.3 隔离资源与清理

计划中的隔离方案是唯一 Compose project 名、任务专属临时媒体目录和任务专属数据 volume。
不过根 Compose 固定了两个 `container_name`，仅设置 project name 不能隔离容器名；在执行前
必须先确认这两个名字未被用户占用，或使用只改变容器名的临时 override。由于 Docker CLI
不可用，连冲突查询也无法完成，smoke 在资源创建前停止。

本任务实际创建的 Docker 资源为 0：

- 容器：0
- 镜像：0
- network：0
- volume：0
- Docker 临时媒体/数据目录：0

因此没有执行 Docker 清理，也没有接触用户真实容器、volume、媒体或数据库。

## 9. 问题分级

### Blocker

#### B-01：当前验证环境没有 Docker/Compose

- 证据：命令解析失败；`docker`、`docker-compose`、`podman` 均为 `NOT_FOUND`；Docker
  Desktop 标准 CLI 路径不存在。
- 影响：镜像拉取/构建、容器启动、健康状态、端口访问、无 Key 降级、NFO 导入和耗时均
  无法获得运行态结论。
- 范围：验证环境 blocker，不等同于仓库产品缺陷。

### High

#### H-01：README 与默认根 Compose 的访问端口不一致

- README 指示 `localhost:3000` / `localhost:8000`。
- 根 Compose 实际映射 `11549:3000` / `11548:8000`。
- 用户按 README 在仓库根启动后访问 `3000`，可能直接判断安装失败。

#### H-02：固定 `container_name` 破坏 Compose project 隔离

- 两个 Compose 文件都固定使用 `5x49-backend` 和 `5x49-frontend`。
- 唯一 project name 只能隔离默认 network/volume 名，不能隔离固定容器名。
- 影响 side-by-side 安装、CI、干净 smoke 和已有 5X49 实例；存在名称冲突和误操作风险。

#### H-03：默认安装镜像不能与当前仓库基线建立可复现关系

- Compose 只引用 `:latest`，没有 digest，也没有 `build:`。
- 从 `origin/main` checkout 启动并不代表运行的是该 commit 的代码。
- 基线结果会随远端 tag 移动，无法可靠比较后续回归。

#### H-04：健康检查是进程 liveness，不是产品 readiness

- `/health` 固定返回 healthy，不检查 DB、迁移、job runtime、媒体目录或依赖。
- healthcheck 不校验 HTTP 状态码；frontend 无 healthcheck，且不等待 backend healthy。
- 可能出现 Compose 显示 healthy，但首次导入或前端仍不可用的假阳性。

### Medium

#### M-01：API Key 的安装文案互相矛盾

- README 将 `OPENROUTER_API_KEY` 标为 Required；`setup.sh` 标为 Optional；Compose 默认空；
  路线图要求 TMDB 和 AI provider 可缺省。
- 新用户无法判断无 Key 是否应该能完成基础激活，容易在安装前中止。

#### M-02：`README.docker.md --build` 与 Compose 模型不匹配

- 文档要求 `docker-compose up -d --build`，但 Compose 服务没有 `build:`。
- 用户可能误以为正在验证本地源代码，实际仍使用远端镜像。

#### M-03：前端 backend URL 配置变量不统一

- 根 Compose 设置 `API_URL`；release Compose 设置 `NEXT_PUBLIC_API_URL`。
- rewrite 与 server API 主要读取 `BACKEND_URL` 或使用 `http://backend:8000` 默认值；
  `NEXT_PUBLIC_API_URL` 在当前前端代码中未找到消费点。
- 默认 Compose 网络名称下可能可用，但自定义 backend 地址时配置预期不可靠。

#### M-04：`setup.sh` 默认媒体目录偏向特定 NAS，且不做有效性检查

- 默认值为 `/volume1/video/movies`。
- 脚本生成配置前不验证路径存在性、可读性或 Docker bind 权限。
- 非 Synology/非 Linux 新用户仍需手工理解并修改宿主机目录。

#### M-05：镜像构建输入未固定

- Dockerfile 基础镜像和 `uv:latest` 未固定 digest。
- 即使未来本地构建，同一 commit 在不同日期也可能得到不同依赖层或基础镜像。

### Low

#### L-01：Compose 仍声明旧式顶层 `version: '3.8'`

- 现代 Docker Compose 会忽略该字段并可能输出 warning。
- 一般不阻塞启动，但会给干净安装增加无效噪声。

#### L-02：backend healthy 首次判定粒度较粗

- 30 秒 interval 且无 start period；即使应用很快就绪，Compose healthy 状态也可能晚到下一次
  探测周期。
- 本次未能测量实际影响。

## 10. 必须手工配置或确认的步骤

在当前版本中，干净安装者至少需要完成或确认：

1. 安装并启动 Docker Engine/Desktop 和 Docker Compose。
2. 选择要使用的 Compose 文件；根 Compose 与 release Compose 的宿主端口不同。
3. 将宿主机电影目录设置为 `MEDIA_DIR`；不要把宿主机路径填成容器内 `/media`。
4. 确认媒体目录中每部电影位于一级子目录，并包含可解析 NFO 或受支持的视频文件。
5. 选择是否配置 TMDB 和 OpenRouter Key；不配置时接受 metadata/AI 功能不可用。
6. 启动后使用与所选 Compose 一致的 URL，而不是默认假设 `3000`。
7. 手工触发 Library scan，并等待异步 job 完成；仅收到 queued 响应不等于导入成功。
8. 确认 `backend_data` volume 的备份/删除策略；`docker compose down -v` 会删除数据库数据。

## 11. 未验证项

- 两个 Docker Hub `latest` tag 是否存在、可拉取、支持 AMD64/ARM64。
- backend/frontend Dockerfile 是否能在当前 commit 完整构建。
- 冷缓存与热缓存的 pull/build 时间、镜像大小。
- Compose 在干净主机上的 create/start/healthy 时间。
- `11548`、`11549`、`8000`、`3000` 是否在目标主机空闲。
- backend `/health`、`/docs`、frontend 首页和 `/api/*` rewrite 的运行态结果。
- backend 容器用户、媒体目录权限和 SQLite volume 写权限。
- 无 Key 下 Library、Settings、Diary/基础页面的实际可用性。
- 无 Key 时 TMDB/AI 功能错误是否清楚且不泄露敏感数据。
- 最小 NFO 首次导入、重复扫描、无视频 NFO 和只读目录行为。
- 容器日志中是否含宿主机路径、Key 或其他敏感信息。
- 停止、重启、volume 持久化和数据恢复。
- 固定 `container_name` 在实际已有实例上的冲突表现（出于安全原因未尝试）。

## 12. 后续修复/验证任务建议

这些建议应在独立任务/分支实施；本分支不修复：

1. **安装文档与默认 Compose 对齐**：确定一个正式默认端口契约，同步 README、
   `README.docker.md`、根 Compose、release Compose 和 setup 输出。
2. **建立可复现安装基线**：使用版本 tag 或 digest；明确“拉取发布镜像”和“从当前源码构建”
   两条命令，确保本地构建 Compose 有 `build:`。
3. **移除固定容器名或使其可配置**：让 Compose project name 真正隔离所有资源，并补一项
   side-by-side smoke。
4. **拆分 liveness/readiness**：readiness 至少检查数据库、schema/migration、job runtime 和
   媒体目录状态；为 frontend 增加健康检查，并按 healthy 条件编排依赖。
5. **统一前端 backend URL 契约**：明确 build-time 与 runtime 变量，删除无效变量，测试默认
   Compose、反向代理和自定义后端地址。
6. **明确无 Key 产品路径**：README 说明哪些基础功能可用、哪些功能不可用、如何稍后配置
   Key；加入无 Key Docker smoke。
7. **完善媒体目录 onboarding**：setup 验证路径/权限，提供 Windows、Linux、NAS 示例，并
   清楚区分宿主机路径与容器 `/media`。
8. **在有 Docker 的干净环境补跑本报告**：使用唯一 project、临时目录和最小 NFO fixture，
   记录 pull/build、首次 backend 响应、healthy、frontend ready、导入完成和重复扫描耗时。
9. **增加安装 smoke 自动化**：验证 README URL、Compose config、无 Key 启动、最小 NFO、
   volume 持久化和日志脱敏。
10. **固定构建工具链**：评估为基础镜像和 `uv` 使用可审核版本/digest，并记录更新策略。

## 13. 修改与发布状态

| 项目 | 状态 |
| --- | --- |
| 修改文件 | 仅新增 `docs/install-baseline.md` |
| 被测对象修改 | 无 |
| Local/main 修改 | 无 |
| commit | 未创建 |
| push | 未执行 |
| PR | 未创建 |
| Codex Worktree 清理 | 未执行 |
