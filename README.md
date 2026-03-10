# 🎬 5X49

[English](README.md) | [简体中文](README.zh-CN.md)
> A modern, AI-powered film library manager with deep genealogy analysis and a premium A24-inspired aesthetic.

![Library Grid](docs/images/library_grid.png)

## ✨ Introduction

**5X49** is not just a media server; it's a cinematic exploration tool. Managing your local film collection has never been this beautiful. It scans your metadata, presents your films in a stunning dark-mode interface, and uses advanced AI to analyze the "genealogy" of films—connecting them by themes, directors, visual styles, and historical context.

## 🚀 Key Features

### 📚 Immersive Library
Automatically scans your local NFO-based collection (compatible with TinyMediaManager) and presents it in a responsive, visually rich grid.
![Menu Navigation](docs/images/menu_open.png)

### 🧠 AI-Powered Analysis
Deep dives into each film using Large Language Models (LLMs) to generate "genealogy reports," formatted in beautiful markdown. Explore connections you never knew existed.
![Detail Page](docs/images/detail_page.png)
![Detail Page 2](docs/images/detail_page2.png)
![Film Genealogy](docs/images/film_genealogy.png)

### 🤖 Intelligent Librarian Agent (LangGraph/ReAct)
Featuring an autonomous background agent powered by **LangGraph** and **LangChain**. The agent monitors an incoming `inbox` folder, handles chaotic filenames using *Function Calling*, searches for metadata, and autonomously renames and files media into the library. 
Watch the agent's Step-by-Step reasoning via Server-Sent Events (SSE) in the real-time Librarian Console.

### 🔌 Extensible API & Agent Skills
Fully documented RESTful API (see [API Documentation](docs/api.md)) allowing easy integration with other services. Includes a ready-to-use **OpenClaw Skill** (`skills/5x49-backend`) so external AI agents can natively manage your library and trigger analysis.

### 📂 Easy Management
- **File Browser**: Select your media directory visually—no manual path typing required.
- **Manual Scan**: Trigger library updates on demand without restarting the server.
![Settings & Scan](docs/images/settings_scan.png)

### 🐳 Docker Ready
Built for containerization from day one. Deploy easily with Docker Compose on any system, now with full **Multi-Architecture support (AMD64 & ARM64)** out of the box. The frontend automatically proxies API traffic to avoid IP configuration hassles on local NAS setups.

## 🛠️ Tech Stack

- **Frontend**: Next.js 14, Tailwind CSS, Framer Motion
- **Backend**: FastAPI, SQLModel (SQLite), Pydantic
- **AI Integration**: OpenAI/OpenRouter API
- **Infrastructure**: Docker, Docker Compose

## 🏁 Getting Started (Docker)

The recommended way to run Film Genealogy is via Docker.

### 1. Requirements
- Docker & Docker Compose installed
- An API Key for OpenRouter (or OpenAI/Anthropic)

### 2. Quick Deploy
Save the following as `docker-compose.yml`:

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

### 3. Setup Configuration (Optional but Recommended)
For the easiest deployment experience, you can download and run our interactive setup script. This will automatically generate a `.env` file with your preferences:
```bash
bash <(curl -sL https://raw.githubusercontent.com/chiosyang/5x49/main/setup.sh)
```

### 4. Run it
Run the containers:
```bash
docker-compose up -d
```

Access the app at [http://localhost:3000](http://localhost:3000).

## 💻 Local Development

If you want to contribute or modify the code:

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## ⚙️ Configuration

| Variable | Description | Default |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | API Key for LLM analysis | **Required** |
| `MEDIA_DIR` | Path to your movie collection (NFOs) | `/media` (Docker) |
| `API_BASE_URL` | LLM API Endpoint | `https://openrouter.ai/api/v1` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `http://localhost:3000` |

---

*Crafted with 🖤 for film lovers.*
