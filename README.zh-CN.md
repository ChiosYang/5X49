# 🎬 5X49

[English](README.md) | [简体中文](README.zh-CN.md)

> 一个现代化的、由 AI 驱动的电影库管理工具，具备深度的“电影家谱”分析功能，并采用类似 A24 的高级极简美学设计。

![Library Grid](docs/images/library_grid.png)

## ✨ 简介

**5X49** 不仅仅是一个媒体服务器；它是一个电影探索工具。管理你的本地电影收藏从未如此赏心悦目。它会扫描你的元数据，在一个令人惊叹的暗色模式界面中呈现你的电影，并利用先进的 AI 分析电影的“家谱”——通过主题、导演、视觉风格和历史背景将它们联系起来。

界面采用**高级的极简主义美学**设计，灵感来自 A24，完全专注于电影艺术本身。

## 🚀 核心功能

### 📚 沉浸式媒体库
自动扫描基于 NFO 的本地收藏（兼容 TinyMediaManager），并在一个响应式且视觉丰富的网格中呈现。
![Menu Navigation](docs/images/menu_open.png)

### 🧠 AI 驱动分析
利用大型语言模型（LLMs）对每部电影进行深度挖掘，生成“家谱报告”，并以精美的 Markdown 格式呈现。探索你从未发觉的电影关联。
![Detail Page](docs/images/detail_page.png)
![Detail Page 2](docs/images/detail_page2.png)
![Film Genealogy](docs/images/film_genealogy.png)

### 🤖 智能图书管理员 Agent (LangGraph/ReAct)
包含一个由 **LangGraph** 和 **LangChain** 驱动的后台自主智能体。该 Agent 监控传入的 `inbox` 文件夹，通过*函数调用 (Function Calling)* 处理混乱的文件名，搜索元数据，并自主重命名和将媒体归档到库中。
在实时的 Librarian Console 中，通过服务器发送事件 (SSE) 观察 Agent 的逐步推理过程。

### 📂 轻松管理
- **文件浏览器**：可视化选择媒体目录——无需手动输入路径。
- **手动扫描**：无需重启服务器即可按需触发媒体库更新。
![Settings & Scan](docs/images/settings_scan.png)

### 🐳 支持 Docker
从一开始就为容器化构建。可以在任何系统上使用 Docker Compose 轻松部署，现已全面支持 **多架构（AMD64 & ARM64）**。前端自动代理 API 流量，彻底避开了本地 NAS 部署中的 IP 配置困扰。

## 🛠️ 技术栈

- **前端**: Next.js 14, Tailwind CSS, Framer Motion
- **后端**: FastAPI, SQLModel (SQLite), Pydantic
- **AI 集成**: OpenAI/OpenRouter API
- **基础设施**: Docker, Docker Compose

## 🏁 快速开始 (Docker)

推荐通过 Docker 运行 5X49。

### 1. 环境要求
- 已安装 Docker & Docker Compose
- 一个 OpenRouter（或 OpenAI/Anthropic）的 API Key

### 2. 快速部署
将以下内容保存为 `docker-compose.yml` (如果你是完全新手，推荐跳过手动编写环境变量，看第3步):

```yaml
services:
  backend:
    image: alicolia/5x49-backend:latest
    ports:
      - "8000:8000"
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
      - MEDIA_DIR=${MEDIA_DIR:-/media}
    volumes:
      - ./data:/app/data
      - ${MEDIA_DIR:-./media}:/media  # Map your local movie folder here

  frontend:
    image: alicolia/5x49-frontend:latest
    ports:
      - "3000:3000"
    depends_on:
      - backend
```

### 3. 初始化配置 (推荐)
为了降低部署门槛，你可以下载并运行我们提供的一键化引导脚本。此脚本会交互式地询问你的配置，并自动在当前目录生成 `.env` 文件：
```bash
bash <(curl -sL https://raw.githubusercontent.com/chiosyang/5x49/main/setup.sh)
```

### 4. 运行服务
运行容器:
```bash
docker-compose up -d
```

然后在浏览器访问 [http://localhost:3000](http://localhost:3000)。

## 💻 本地开发

如果你想贡献代码或进行修改：

### 后端
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

## ⚙️ 配置项

| 变量 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | 用于 LLM 分析的 API Key | **必填** |
| `MEDIA_DIR` | 你的电影收藏路径 (NFOs) | `/media` (Docker) |
| `API_BASE_URL` | LLM API 端点 | `https://openrouter.ai/api/v1` |
| `ALLOWED_ORIGINS` | 允许的 CORS 来源 | `http://localhost:3000` |

---

*Crafted with 🖤 for film lovers. (为电影爱好者精心打造 🖤)*
