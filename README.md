# CodeABC (码上懂)

[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/he-yufeng/CodeABC/actions/workflows/ci.yml/badge.svg)](https://github.com/he-yufeng/CodeABC/actions)
[![中文](https://img.shields.io/badge/lang-中文-red)](README_CN.md)

**Read code without learning to code.** An AI-powered code reader built for non-programmers.

Cursor and VS Code are Swiss army knives for developers. CodeABC is a magnifying glass for everyone else -- it lets you read code like reading an article, and annotate code like annotating a document.

## The Problem

More and more non-programmers need to deal with code: grad students running Python data analysis scripts, product managers reviewing what developers built, founders evaluating outsourced code quality. But every existing tool assumes you already know how to code.

**AI can already explain code perfectly.** What's missing is a product that wraps this capability in a UX designed for people who don't code.

## Features

### Project Overview

Drop in a project folder or paste a GitHub link. CodeABC scans the files and generates a plain-language "project manual":

- **What is this?** One-sentence summary anyone can understand
- **File guide** Every file explained in plain language, sorted by importance
- **How to run it** Step-by-step instructions, no jargon
- **Quick tips** "If you just want to change X, go to file Y"

### Hover Annotations

Click any file to view it with AI-generated annotations. Hover over any line to see a plain-language explanation of what it does. No programming jargon -- uses everyday analogies to explain concepts.

- Fine-grained: annotations cover every 1-3 lines, not just blocks
- Context-aware: explains _why_ a number is 0.05 or a timeout is 3600
- Cached: annotations are stored locally so repeat visits are instant

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | React 19 + Vite + TailwindCSS 4 | Fast dev, no SSR needed for this app |
| Code highlighting | Shiki | VS Code-quality syntax highlighting, zero runtime JS |
| Tooltips | @floating-ui/react | Lightweight positioning for hover annotations |
| State | Zustand | Minimal, performant state management |
| Backend | FastAPI + uvicorn | Async Python, great for streaming LLM responses |
| LLM | litellm | Multi-provider support (OpenAI, Claude, DeepSeek, Kimi, etc.) |
| Cache | SQLite | Simple, no Redis needed for MVP |

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- An LLM API key (OpenAI, Claude, DeepSeek, or any litellm-compatible provider)

### Backend

```bash
cd CodeABC
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# set your API key
export OPENAI_API_KEY=sk-xxx
# or for other providers:
# export ANTHROPIC_API_KEY=sk-ant-xxx
# export DEEPSEEK_API_KEY=xxx

# optional: change the default model
# export CODEABC_MODEL=deepseek/deepseek-chat

uvicorn backend.app:app --reload
```

### Frontend

```bash
cd CodeABC/frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

### Using It

1. **Local folder**: Drag a project folder into the upload zone, or click to select
2. **GitHub repo**: Paste a GitHub URL like `https://github.com/user/repo` and click "Analyze"
3. Browse the generated project overview
4. Click any file to see it with hover annotations

### API Key

CodeABC supports two modes:

- **Free mode** (default): Limited to 20 requests per day
- **BYOK mode**: Click the gear icon in the top-right corner to enter your own API key for unlimited use. The key is stored only in your browser's localStorage.

## Project Structure

```
CodeABC/
├── backend/                 # Python FastAPI server
│   ├── app.py               # Entry point, CORS, lifespan
│   ├── models.py            # Pydantic data models
│   ├── routers/
│   │   ├── project.py       # Upload / GitHub clone / file endpoints
│   │   └── analyze.py       # Overview + annotation generation
│   ├── services/
│   │   ├── scanner.py       # Project file scanner with smart filtering
│   │   ├── github_clone.py  # Shallow clone with size limits
│   │   ├── llm.py           # litellm wrapper (stream + non-stream)
│   │   └── cache.py         # SQLite cache layer
│   └── prompts/
│       ├── overview.py      # Project overview prompt
│       └── annotate.py      # Line-by-line annotation prompt
├── frontend/                # React + Vite + TailwindCSS
│   └── src/
│       ├── pages/           # Home, Overview, FileView
│       ├── components/      # UploadZone, CodeViewer, AnnotationTooltip, ApiKeyModal
│       ├── stores/          # Zustand state management
│       └── lib/             # API client
├── pyproject.toml
└── README.md
```

## Roadmap

- [x] Project overview generation
- [x] Hover annotations (Python priority)
- [ ] Terminology dictionary (hover keywords for definitions)
- [ ] Natural language editing ("change the stock from Maotai to BYD")
- [ ] Q&A mode (select code and ask questions)
- [ ] Multi-language UI (English interface)
- [ ] Desktop app (Tauri)

## Contributing

Issues and PRs welcome. This project is in early development.

## License

MIT
