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
- **Reading map** A deterministic "start here, then read this" path appears before the AI call
- **How to run it** Step-by-step instructions, no jargon
- **Quick tips** "If you just want to change X, go to file Y"

### Hover Annotations

Click any file to view it with AI-generated annotations. Hover over any line to see a plain-language explanation of what it does. No programming jargon -- uses everyday analogies to explain concepts.

- Fine-grained: annotations cover every 1-3 lines, not just blocks
- Context-aware: explains _why_ a number is 0.05 or a timeout is 3600
- Cached: annotations are stored locally so repeat visits are instant

### Terminology Dictionary

Every file view lists the programming terms that actually appear in that file -- `async`, `decorator`, `closure`, `middleware`, `regex`, and dozens more. Hover a term to see a plain-language explanation that leans on everyday analogies. It is computed deterministically (no LLM, no API key), so it is instant and always available.

### Natural-Language Editing

Describe a change in plain words -- "把茅台换成比亚迪", "change the timeout from 3600 to 600" -- and CodeABC returns a suggested rewrite of the selected snippet, touching only what you asked for. It never writes to your files; the result is yours to review and copy.

### Q&A Mode

Select any snippet in a file (or just leave it unselected for the whole file) and ask a question in plain language -- "what does this do?", "why is this number here?". CodeABC answers in the same patient, jargon-light voice, grounded only in the code you pointed at. Answers are cached, so asking the same thing again is free.

### Bilingual UI (中文 / English)

The whole interface switches between Chinese and English with one toggle in the header. Your choice is remembered, and the first visit follows your browser language. (LLM-generated content like the manual and annotations follows the prompt language; the UI chrome is fully translated.)

### Cleaner Project Scans

CodeABC skips build outputs, package caches, minified bundles, generated frontend chunks, and paths ignored by the repository's `.gitignore` before sending files to the LLM. It also leaves out secret-shaped files such as real `.env` files, credential JSON files, API key notes, and private keys while still allowing safe examples like `.env.example`. That keeps the project manual focused on source code instead of `dist/`, `node_modules`, local scratch files, one-line JavaScript bundles, or private credentials.

### Start Reading Immediately

Before an LLM response is ready, CodeABC builds a deterministic reading map from README files, likely entry points, package manifests, core source directories, and tests. It gives newcomers a useful first route even when no API key is configured.

### Core Modules at a Glance

CodeABC builds a small import graph from the scanned files and ranks them by fan-in: how many other files import each one. The most-imported files are usually where the real logic lives (shared utilities, data models, core services), so they surface next to the reading map as "core modules", each tagged with the number of files that depend on it. It resolves Python imports (including relative and package imports) and JavaScript/TypeScript imports (relative paths with extension and index resolution), and ignores third-party and standard-library imports since they never point at a scanned file. Like the reading map, it runs without an LLM call, so it works with no API key configured.

### Is the Code Tested?

A blunt but useful question when you're sizing up code you didn't write — work you outsourced, say: does it actually have tests? CodeABC pairs each source file with the test files that exercise it, both by import and by the usual `test_scanner.py` / `scanner.test.ts` naming, then shows the share of files that are covered. More usefully, it ranks the *untested* files by how many other files depend on them: an untested file that half the project imports is exactly where a quiet regression spreads furthest, so it sits at the top of the "worth covering first" list with a plain-language note on why. A green progress bar gives the at-a-glance number; the list tells you where to look. Like the other maps it is deterministic and needs no API key.

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
export OPENAI_API_KEY=<OPENAI_API_KEY>
# or for other providers:
# export ANTHROPIC_API_KEY=<ANTHROPIC_API_KEY>
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
│   │   ├── importgraph.py   # Import-graph fan-in ranking (core-module detection)
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
- [x] Terminology dictionary (hover keywords for definitions)
- [x] Natural language editing ("change the stock from Maotai to BYD")
- [x] Q&A mode (select code and ask questions)
- [x] Multi-language UI (English interface)
- [x] Test-coverage map (which files have tests; untested core files ranked by risk)
- [ ] Desktop app (Tauri)

## Contributing

Issues and PRs welcome. This project is in early development.

## License

MIT
