# OfferFlow

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688.svg)](https://fastapi.tiangolo.com/)

**核心亮点：AI 解析求职邮箱。**  
绑定你的邮箱（IMAP）并配置 AI 模型后，OfferFlow 会自动读取笔试 / 面试 / Offer 等邮件，抽取公司、岗位、时间与状态，并回填到投递表——不用再手动抄邮件内容。

在此之外，它还是一套本地优先的实习 / 校招投递管理工具：表格跟踪进度、面试倒计时与日历视图，数据存在本机 SQLite，无需注册登录。

![校招投递页面截图](https://cdn.jsdelivr.net/gh/Xiangyahaian/offerflow@8e1b231ad20fd4c6a6fae880a1488cac86b61736/docs/screenshots/campus.png)

## Features

- **AI 邮箱解析**：IMAP 拉取求职邮件 → AI 提取关键信息 → 自动创建 / 更新投递记录
- **实习 / 校招投递**：状态流转、优先级、面试轮次、倒计时、拖拽排序与批量操作
- **工作台**：投递总量、待处理事项与 Offer 概览
- **日历视图**：集中查看笔试 / 面试安排
- **本地存储**：默认 SQLite，数据完全在你自己的机器上
- **一键启动**：支持本地 Python 与 Docker Compose

## Tech Stack

| Layer | Stack |
|-------|--------|
| Backend | FastAPI · SQLAlchemy · SQLite |
| Frontend | Jinja2 · 原生 JS / CSS |
| Runtime | Python 3.10+ · Uvicorn |

## Quick Start

### Requirements

- Python 3.10+
- 或 Docker / Docker Compose

### Run locally

```bash
git clone https://github.com/Xiangyahaian/offerflow.git
cd offerflow

python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp env.example .env   # Windows: copy env.example .env

# optional: load sample applications
python scripts/seed_demo.py

python run.py
```

Open [http://localhost:8001](http://localhost:8001)

### Run with Docker

```bash
docker compose up -d --build
```

App: [http://localhost:8001](http://localhost:8001)  
Database file: `./data/offerflow.db`

## Configuration

Copy `env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8001` | Server port |
| `DATABASE_URL` | `sqlite:///./offerflow.db` | SQLite path |
| `ENV` | `development` | Use `production` to disable reload and `/docs` |
| `SECRET_KEY` | (example) | Used to encrypt IMAP / AI API keys |

**启用 AI 邮箱解析（核心功能）：** 在侧边栏打开邮箱 / AI 助手页面，填写 IMAP 账号与 AI 模型 API Key；之后即可自动拉取并解析求职邮件。`SECRET_KEY` 用于加密这些凭据。

## Project Structure

```text
offerflow/
├── run.py                 # entrypoint
├── requirements.txt
├── env.example
├── Dockerfile
├── docker-compose.yml
├── backend/               # FastAPI app, models, routers
├── frontend/              # templates + static assets
├── scripts/seed_demo.py   # sample data
└── docs/screenshots/      # README screenshots
```

## API

With `ENV=development`, interactive docs are available at `/docs`.

| Endpoint | Description |
|----------|-------------|
| `/api/campus` | Campus applications |
| `/api/internships` | Internship applications |
| `/api/dashboard/stats` | Dashboard stats |
| `/api/mail` | Mailbox / IMAP |
| `/api/ai-assistant` | Mail AI parsing |

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create your branch (`git checkout -b feature/awesome`)
3. Commit your changes
4. Open a Pull Request

## License

Released under the [MIT License](LICENSE).
