"""Filename meanings: explain what a file *is* from its name alone.

A non-programmer dropped into a repository trips over filenames as much as over
code. ``conftest.py``, ``serializers.py``, ``__init__.py``, ``Dockerfile`` — each
is a wall of jargon before a single line is read. Developers recognise these by
convention; everyone else has to guess.

This is a curated dictionary of those conventions (same plain-language voice as
:mod:`backend.services.glossary`). :func:`explain_path` takes a file path and
returns a short "what this file usually is" note, matching from most specific to
least: an exact well-known filename, then a directory convention, then a
stem/suffix pattern, and finally a bare extension. It depends only on the path —
no file contents, no LLM — so it is instant, free, and unit-testable.
"""

from __future__ import annotations

import re

# --- Exact filenames (highest priority) ----------------------------------
# Keyed by lowercase basename. Each value is (kind, explanation).
_EXACT: dict[str, tuple[str, str]] = {
    "__init__.py": (
        "包标记",
        "告诉 Python「这个文件夹是一个包」，可以被别处 import。常常是空的，空着也完全正常。",
    ),
    "__main__.py": (
        "运行入口",
        "用 `python -m 包名` 跑这个包时，实际执行的就是这里，相当于这个包的「开始按钮」。",
    ),
    "conftest.py": (
        "测试配置",
        "pytest 的共享测试配置：里面的夹具（fixture）会在跑测试时自动加载，不用手动 import。它不是项目功能代码。",
    ),
    "setup.py": (
        "打包脚本",
        "老式的「怎么把这个项目打包安装」说明，定义项目名、版本、依赖。多数已被 pyproject.toml 取代。",
    ),
    "setup.cfg": (
        "打包/工具配置",
        "项目的打包信息和一些工具（如 flake8）的配置，纯文本键值对，不是运行代码。",
    ),
    "pyproject.toml": (
        "项目说明书",
        "现代 Python 项目的「身份证+配置中心」：项目名、版本、依赖、打包方式、各种工具设置都写在这。",
    ),
    "requirements.txt": (
        "依赖清单",
        "这个项目运行所需要的第三方库列表，`pip install -r` 会照着它一次装齐。",
    ),
    "package.json": (
        "项目说明书",
        "JavaScript/Node 项目的「身份证+配置中心」：项目名、版本、依赖库、可运行的脚本命令都在这里。",
    ),
    "package-lock.json": (
        "依赖锁定",
        "把每个依赖的精确版本钉死，保证别人装出来和你一模一样。机器生成的，一般不用手改。",
    ),
    "yarn.lock": (
        "依赖锁定",
        "和 package-lock.json 作用一样，是 yarn 这个工具生成的依赖版本锁定文件，一般不用手改。",
    ),
    "tsconfig.json": (
        "TS 配置",
        "TypeScript 的编译配置：告诉编译器用哪个语法版本、哪些目录算源码、严格到什么程度。",
    ),
    "dockerfile": (
        "打包成镜像",
        "一份「怎么把这个项目装进一个标准化集装箱（容器）」的步骤说明，照着它能在任何机器上一键跑起来。",
    ),
    "docker-compose.yml": (
        "多容器编排",
        "一次性启动并连接好多个容器（比如「后端+数据库+缓存」）的配置，省得一个个手动启动。",
    ),
    "makefile": (
        "命令快捷表",
        "把一串常用命令起个短名字（如 `make test`），敲一下就跑一整套，省得记长命令。",
    ),
    ".gitignore": (
        "忽略清单",
        "告诉 Git「这些文件不要纳入版本管理」（如临时文件、密钥、依赖目录），避免误传上去。",
    ),
    ".env": (
        "环境变量/密钥",
        "存放配置和敏感信息（数据库地址、API 密钥等）的本地文件。通常不该提交到仓库里。",
    ),
    ".env.example": (
        "配置模板",
        "`.env` 的样板：列出需要填哪些配置项但留空，方便别人照着复制一份自己的。",
    ),
    "readme.md": (
        "项目简介",
        "项目的「门面」：这是什么、能干嘛、怎么安装运行。打开一个陌生项目，先读它。",
    ),
    "license": (
        "授权协议",
        "规定别人可以怎么使用、修改、分发这份代码的法律条款。",
    ),
    "changelog.md": (
        "更新日志",
        "按版本记录「每次更新改了什么」的流水账，想知道某个功能哪个版本加的就看它。",
    ),
}

# --- Directory conventions: a path segment that gives the file its role ---
# Keyed by lowercase directory name appearing anywhere in the path.
_DIR_HINTS: dict[str, tuple[str, str]] = {
    "migrations": (
        "数据库变更",
        "数据库结构的「变更记录」：每个文件是一次「给表加一列 / 改个字段」的步骤，按顺序累积。一般是工具生成的，不用手读。",
    ),
    "tests": (
        "测试代码",
        "用来自动检查功能对不对的代码，不影响项目正常运行；它是项目的「质检员」。",
    ),
    "test": (
        "测试代码",
        "用来自动检查功能对不对的代码，不影响项目正常运行；它是项目的「质检员」。",
    ),
    "__tests__": (
        "测试代码",
        "用来自动检查功能对不对的代码（JS 项目常用这个文件夹名），不影响项目正常运行。",
    ),
    "node_modules": (
        "第三方库",
        "自动下载的所有依赖库存放处，体积大、机器生成，几乎从不需要手动看或改。",
    ),
}


# --- Stem / suffix conventions (matched on the basename) ------------------
# Order matters: first match wins. Each entry is (predicate, kind, explanation).
def _stem_rules() -> list[tuple[re.Pattern[str], str, str]]:
    return [
        (
            re.compile(r"^test_.*\.py$|.*_test\.py$"),
            "测试代码",
            "一个测试文件：自动检查对应功能是否正确，不是项目本身运行的代码。",
        ),
        (
            re.compile(r".*\.(test|spec)\.(t|j)sx?$"),
            "测试代码",
            "一个测试文件：自动检查对应功能是否正确，不是项目本身运行的代码。",
        ),
        (
            re.compile(r"^models?\.py$|^models?\.(t|j)sx?$"),
            "数据结构",
            "定义「数据长什么样」的地方：常对应数据库里的表或核心业务对象的字段。",
        ),
        (
            re.compile(r"^views?\.py$"),
            "页面/接口逻辑",
            "处理「收到一个请求后做什么、返回什么」的逻辑，是前端和数据之间的中间层。",
        ),
        (
            re.compile(r"^(urls?|routes?|router)\.(py|ts|js)$"),
            "地址路由表",
            "网址（路由）对照表：规定「访问哪个地址，就交给哪段代码处理」。",
        ),
        (
            re.compile(r"^serializers?\.py$"),
            "数据转换",
            "负责把程序内部的对象和对外的传输格式（如 JSON）来回转换，进出口的「翻译官」。",
        ),
        (
            re.compile(r"^schemas?\.(py|ts|js)$"),
            "数据格式定义",
            "定义数据应有的字段和类型，用来校验「传进来的数据合不合规矩」。",
        ),
        (
            re.compile(r"^(settings?|config|configuration)\.(py|ts|js)$"),
            "配置",
            "项目的各种设置项集中地（数据库地址、开关、密钥等），改行为多半从这里改。",
        ),
        (
            re.compile(r"^constants?\.(py|ts|js)$"),
            "常量",
            "把固定不变的值（如默认数字、固定字符串）集中起来取好名字，避免到处硬写。",
        ),
        (
            re.compile(r"^(utils?|helpers?)\.(py|ts|js)$"),
            "工具函数",
            "一堆零散的小工具函数集合，被项目各处反复借用，没有单一主线。",
        ),
        (
            re.compile(r"^index\.(t|j)sx?$"),
            "目录入口",
            "这个文件夹的「总入口/总开关」：别处 import 这个文件夹时，默认进来的就是它。",
        ),
        (
            re.compile(r".*\.d\.ts$"),
            "类型声明",
            "只描述「类型长什么样」、不含实际逻辑的 TypeScript 声明文件，给编辑器和编译器看的。",
        ),
    ]


_STEM_RULES = _stem_rules()

# --- Bare extension fallback ----------------------------------------------
_EXT: dict[str, tuple[str, str]] = {
    ".py": ("Python 源码", "一段 Python 程序代码。"),
    ".ts": ("TypeScript 源码", "一段 TypeScript 程序代码（带类型的 JavaScript）。"),
    ".tsx": ("React 组件", "一个用 TypeScript 写的 React 界面组件，对应页面上的一块 UI。"),
    ".js": ("JavaScript 源码", "一段 JavaScript 程序代码。"),
    ".jsx": ("React 组件", "一个用 JavaScript 写的 React 界面组件，对应页面上的一块 UI。"),
    ".md": ("说明文档", "用 Markdown 写的文字说明文档，不是运行代码。"),
    ".json": ("数据/配置", "用 JSON 格式存的数据或配置，纯文本的键值结构。"),
    ".yml": ("配置", "用 YAML 格式写的配置文件，常见于 CI、部署、各类工具设置。"),
    ".yaml": ("配置", "用 YAML 格式写的配置文件，常见于 CI、部署、各类工具设置。"),
    ".toml": ("配置", "用 TOML 格式写的配置文件，常见于 Python 项目设置。"),
    ".sh": ("脚本", "一段在终端里跑的 Shell 脚本，通常用来安装、构建或部署。"),
    ".sql": ("数据库语句", "操作数据库的 SQL 语句（查询、建表、改数据等）。"),
    ".css": ("样式", "控制页面长相（颜色、间距、字体等）的样式文件。"),
    ".html": ("网页结构", "网页的骨架结构文件，决定页面上有哪些元素。"),
    ".txt": ("纯文本", "一个纯文本文件。"),
}


def explain_path(path: str) -> dict | None:
    """Explain what a file *is* from its name, or ``None`` if nothing fits.

    Returns ``{"name", "kind", "explanation"}`` where ``name`` is the basename,
    ``kind`` is a short category label, and ``explanation`` is a plain-language
    sentence. Matching runs most-specific first: exact filename, then directory
    convention, then stem/suffix pattern, then bare extension.
    """
    if not path:
        return None

    posix = path.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1]
    lower = name.lower()

    # 1. Exact well-known filename.
    if lower in _EXACT:
        kind, explanation = _EXACT[lower]
        return {"name": name, "kind": kind, "explanation": explanation}

    # 2. Stem/suffix pattern (before directory, so test_x.py reads as a test
    #    file rather than just "something in a tests/ folder").
    for pattern, kind, explanation in _STEM_RULES:
        if pattern.match(lower):
            return {"name": name, "kind": kind, "explanation": explanation}

    # 3. Directory convention anywhere in the path.
    segments = {seg.lower() for seg in posix.split("/")[:-1]}
    for seg in segments:
        if seg in _DIR_HINTS:
            kind, explanation = _DIR_HINTS[seg]
            return {"name": name, "kind": kind, "explanation": explanation}

    # 4. Bare extension fallback.
    dot = lower.rfind(".")
    if dot > 0:
        ext = lower[dot:]
        if ext in _EXT:
            kind, explanation = _EXT[ext]
            return {"name": name, "kind": kind, "explanation": explanation}

    return None
