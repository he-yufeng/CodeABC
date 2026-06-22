"""Package purposes: explain what a third-party library is for, in plain words.

:mod:`backend.services.dependencies` lists the packages a project installs, but a
bare name like ``fastapi``, ``pydantic`` or ``sqlalchemy`` means nothing to a
non-programmer. This is a curated dictionary (same plain-language voice as
:mod:`backend.services.glossary` and :mod:`backend.services.filenames`) mapping
the most common Python and JavaScript packages to a one-line "what it does, and
why a project would pull it in".

:func:`explain_package` normalises the name (lowercases, strips extras such as
``uvicorn[standard]``, and resolves a few well-known aliases) before looking it
up, and returns ``None`` for anything not in the dictionary. Deterministic — no
network, no LLM — so it is instant and unit-testable.
"""

from __future__ import annotations

import re

# Canonical lowercase package name -> plain-language purpose.
_PURPOSES: dict[str, str] = {
    # --- Python: web / API ---
    "fastapi": "搭 Web API 的框架，用很少的代码就能对外提供接口，自带数据校验和文档。",
    "flask": "一个轻量的 Web 框架，用来快速搭网站或接口，小项目常用。",
    "django": "一个全功能 Web 框架，自带数据库、后台管理、用户系统，适合做完整网站。",
    "starlette": "FastAPI 底层用的异步 Web 工具库，负责处理请求和路由。",
    "uvicorn": "把 Python Web 应用真正跑起来的服务器，FastAPI 项目几乎都用它启动。",
    "gunicorn": "生产环境里跑 Python Web 应用的服务器，能开多个进程扛并发。",
    "requests": "发 HTTP 请求的库（访问网页、调别人的接口），是 Python 里最常见的之一。",
    "httpx": "和 requests 类似的发 HTTP 请求的库，但支持异步、更现代。",
    "aiohttp": "异步地发 HTTP 请求或搭服务器，适合要同时处理很多网络请求的场景。",
    "websockets": "处理 WebSocket 长连接，用来做实时双向通信（如聊天、推送）。",
    # --- Python: data / validation ---
    "pydantic": "定义数据该长什么样并自动校验，传进来的数据不合规矩会直接报错。",
    "numpy": "数值计算的基础库，处理大批数字和矩阵又快又省，科学计算的地基。",
    "pandas": "处理表格数据（像代码版的 Excel），做数据清洗和分析的主力工具。",
    "scipy": "在 numpy 之上的科学计算库，提供统计、优化、信号处理等高级算法。",
    "matplotlib": "把数据画成图表（折线、柱状、散点等）的画图库。",
    "polars": "和 pandas 类似的表格数据处理库，主打速度快、省内存。",
    # --- Python: AI / ML ---
    "torch": "PyTorch，做深度学习/训练神经网络的主流框架。",
    "tensorflow": "Google 的深度学习框架，和 PyTorch 并列的两大主流之一。",
    "transformers": "Hugging Face 的库，几行代码就能加载和使用各种预训练大模型。",
    "openai": "调用 OpenAI（GPT 等）模型的官方库。",
    "anthropic": "调用 Anthropic（Claude）模型的官方库。",
    "langchain": "把大模型和工具、数据、流程串起来做 AI 应用的框架。",
    "scikit-learn": "经典机器学习库（分类、回归、聚类等），不涉及深度学习时常用。",
    "datasets": "Hugging Face 的库，方便地下载和处理机器学习数据集。",
    # --- Python: database / cache ---
    "sqlalchemy": "用 Python 对象操作数据库，不用手写一堆 SQL。",
    "psycopg2": "连接 PostgreSQL 数据库的驱动。",
    "pymysql": "连接 MySQL 数据库的驱动。",
    "redis": "连接 Redis（内存数据库/缓存）的库，常用来做缓存和队列。",
    "pymongo": "连接 MongoDB（文档数据库）的库。",
    "alembic": "管理数据库结构变更的工具，给 SQLAlchemy 配套做迁移。",
    # --- Python: utilities ---
    "pyyaml": "读写 YAML 格式的配置文件。",
    "python-dotenv": "把 .env 文件里的配置加载成环境变量。",
    "pillow": "处理图片（打开、缩放、裁剪、转格式）的库。",
    "opencv-python": "做图像和视频处理、计算机视觉的库（OpenCV）。",
    "beautifulsoup4": "从 HTML 网页里抽取数据（爬虫常用）。",
    "click": "做命令行工具的库，帮你定义命令、参数和帮助信息。",
    "rich": "在终端里打印彩色、表格、进度条等漂亮输出。",
    "tqdm": "给循环加一个进度条，一眼看出跑到哪了。",
    "celery": "做后台任务队列，把耗时活儿丢到后台异步处理。",
    "boto3": "操作 AWS 云服务（S3 存储、各种云资源）的官方库。",
    # --- Python: dev / test ---
    "pytest": "Python 最常用的测试框架，用来自动检查代码对不对。",
    "ruff": "又快又全的代码检查+格式化工具，挑出风格和潜在问题。",
    "mypy": "静态类型检查器，在不运行代码的情况下找出类型用错的地方。",
    "black": "自动把代码格式化成统一风格，省得手动调缩进和换行。",
    "flake8": "检查代码风格和明显错误的工具。",
    # --- JavaScript / TypeScript ---
    "react": "搭前端界面的主流框架，把页面拆成可复用的组件。",
    "react-dom": "把 React 组件真正渲染到网页上的配套库。",
    "vue": "和 React 并列的前端框架，搭交互式网页界面。",
    "express": "Node.js 上最常用的后端 Web 框架，搭接口和服务器。",
    "axios": "在浏览器或 Node 里发 HTTP 请求的库。",
    "lodash": "一堆现成的 JavaScript 工具函数（处理数组、对象等），省得自己写。",
    "typescript": "给 JavaScript 加类型的语言，写大型项目更稳、更好维护。",
    "vite": "现代前端构建/开发工具，启动快、热更新快。",
    "webpack": "把前端代码和资源打包成浏览器能跑的文件的构建工具。",
    "tailwindcss": "用一串小类名直接写样式的 CSS 框架，不用单独写 CSS 文件。",
    "next": "基于 React 的全栈框架，自带路由、服务端渲染等。",
    "eslint": "检查 JavaScript/TypeScript 代码风格和问题的工具。",
    "zod": "在 TypeScript 里定义并校验数据格式的库（类似 Python 的 pydantic）。",
    "zustand": "React 里管理共享状态的轻量库。",
}

# Aliases: the name as it may appear in a manifest -> the canonical key above.
_ALIASES: dict[str, str] = {
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "pil": "pillow",
    "bs4": "beautifulsoup4",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "pytorch": "torch",
    "react-router-dom": "react",
}

# Strip an extras suffix like "uvicorn[standard]" -> "uvicorn".
_EXTRAS_RE = re.compile(r"\[.*\]$")


def explain_package(name: str) -> str | None:
    """Return a plain-language purpose for *name*, or ``None`` if unknown."""
    if not name:
        return None
    key = _EXTRAS_RE.sub("", name.strip().lower())
    key = _ALIASES.get(key, key)
    return _PURPOSES.get(key)
