"""External services: which live third-party services this code talks to.

``dependencies`` lists the packages a project *declares*; ``envscan`` lists the
environment variables it *reads*. This answers the question a non-programmer
actually asks before they can run an inherited project: "what outside services
does this thing need, and which of them will cost me money or an account?"

A 200-line file that imports ``openai`` and ``boto3`` means you can't run it
without an OpenAI API key and an AWS account, no matter how clean the code is.
That fact doesn't show up in a dependency list in any obvious way.

:func:`detect_external_services` scans the already-read file contents for the
import statements (and a few tell-tale hostnames) of well-known services, maps
them to a plain-language note, and groups them by category. Pure functions over
the file-content map, so it is unit-testable with plain strings. Detection is a
curated dictionary, not an exhaustive registry: it aims to catch the services
that matter for "can I run this", and to stay quiet rather than guess.
"""

from __future__ import annotations

import re

# module/import token -> (display name, category, plain-language note)
# Keyed by the root import token (python) or package name (js/go path tail).
_SERVICE_BY_MODULE: dict[str, tuple[str, str, str]] = {
    # --- AI / LLM ---
    "openai": ("OpenAI", "AI / 大模型", "调用 OpenAI 接口，需要 OpenAI API key（按用量计费）。"),
    "anthropic": (
        "Anthropic",
        "AI / 大模型",
        "调用 Anthropic Claude 接口，需要 API key（按用量计费）。",
    ),
    "cohere": ("Cohere", "AI / 大模型", "调用 Cohere 接口，需要 API key。"),
    "google.generativeai": ("Google Gemini", "AI / 大模型", "调用 Google Gemini，需要 API key。"),
    "replicate": (
        "Replicate",
        "AI / 大模型",
        "在 Replicate 上跑模型，需要 API token（按用量计费）。",
    ),
    "huggingface_hub": ("Hugging Face", "AI / 大模型", "访问 Hugging Face，私有模型需要 token。"),
    "transformers": ("Hugging Face", "AI / 大模型", "用 Hugging Face 模型，可能联网下载权重。"),
    # --- Cloud ---
    "boto3": ("AWS", "云服务", "调用 AWS（S3/等），需要 AWS 账号与密钥（按用量计费）。"),
    "botocore": ("AWS", "云服务", "调用 AWS，需要 AWS 账号与密钥。"),
    "google.cloud": ("Google Cloud", "云服务", "调用 Google Cloud，需要 GCP 账号与凭据。"),
    "azure": ("Azure", "云服务", "调用 Microsoft Azure，需要 Azure 账号与凭据。"),
    # --- Databases / cache ---
    "psycopg2": ("PostgreSQL", "数据库", "连接 PostgreSQL 数据库，需要一个可用的数据库实例。"),
    "psycopg": ("PostgreSQL", "数据库", "连接 PostgreSQL 数据库，需要一个可用的数据库实例。"),
    "asyncpg": ("PostgreSQL", "数据库", "连接 PostgreSQL 数据库，需要一个可用的数据库实例。"),
    "pymysql": ("MySQL", "数据库", "连接 MySQL 数据库，需要一个可用的数据库实例。"),
    "mysqlclient": ("MySQL", "数据库", "连接 MySQL 数据库，需要一个可用的数据库实例。"),
    "pymongo": ("MongoDB", "数据库", "连接 MongoDB，需要一个可用的 MongoDB 实例。"),
    "redis": ("Redis", "数据库 / 缓存", "连接 Redis，需要一个可用的 Redis 实例。"),
    "elasticsearch": ("Elasticsearch", "数据库 / 搜索", "连接 Elasticsearch，需要一个可用的集群。"),
    "pinecone": ("Pinecone", "数据库 / 向量库", "调用 Pinecone 向量库，需要 API key。"),
    # --- Payments ---
    "stripe": ("Stripe", "支付", "调用 Stripe 收款，需要 Stripe 账号与密钥。"),
    # --- Messaging / comms ---
    "twilio": ("Twilio", "通讯", "发短信/打电话走 Twilio，需要账号（按用量计费）。"),
    "sendgrid": ("SendGrid", "邮件", "发邮件走 SendGrid，需要 API key。"),
    "slack_sdk": ("Slack", "通讯", "对接 Slack，需要 Slack token。"),
    "kafka": ("Kafka", "消息队列", "用 Kafka 收发消息，需要一个 Kafka 集群。"),
    "pika": (
        "RabbitMQ",
        "消息队列",
        "用 RabbitMQ 在不同程序间传消息，需要先搭一台 RabbitMQ 服务。",
    ),
    "celery": (
        "Celery",
        "任务队列",
        "用 Celery 跑后台任务，还需要一台帮它排队的中转服务（通常是 Redis）。",
    ),
    # --- Auth / monitoring / dev ---
    "firebase_admin": (
        "Firebase",
        "后端服务",
        "对接 Google 的 Firebase，需要一个 Firebase 项目和它的密钥文件。",
    ),
    "sentry_sdk": (
        "Sentry",
        "监控",
        "把程序报错自动上报到 Sentry 看板，需要先注册 Sentry 拿一个上报地址。",
    ),
    "github": ("GitHub API", "开发者平台", "调用 GitHub API，私有操作需要 token。"),
}

# A few high-signal hostnames for when the SDK isn't imported but the API is hit.
_SERVICE_BY_HOST: dict[str, tuple[str, str, str]] = {
    "api.openai.com": ("OpenAI", "AI / 大模型", "直接请求 OpenAI 接口，需要 OpenAI API key。"),
    "api.anthropic.com": ("Anthropic", "AI / 大模型", "直接请求 Anthropic 接口，需要 API key。"),
    "api.stripe.com": ("Stripe", "支付", "直接请求 Stripe 接口，需要密钥。"),
    "amazonaws.com": ("AWS", "云服务", "请求 AWS 服务，需要 AWS 账号与密钥。"),
    "hooks.slack.com": ("Slack", "通讯", "把消息自动发到 Slack 群里。"),
    "api.telegram.org": (
        "Telegram",
        "通讯",
        "用 Telegram 机器人发消息，需要先找 Telegram 申请一个机器人密钥。",
    ),
}

_CODE_EXTS = {"py", "pyi", "js", "jsx", "ts", "tsx", "mjs", "cjs", "go", "java", "rb"}
_TEST_SEGMENTS = {"test", "tests", "__tests__", "spec", "specs"}

# python `import a.b` / `from a.b import` ; js `from 'x'` / require('x')
_PY_IMPORT = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)")
_JS_IMPORT = re.compile(r"""(?:from|require\(|import)\s*['"]([^'"]+)['"]""")
_GO_IMPORT = re.compile(r"""^\s*(?:_\s+)?["']([^"']+)["']""")
_HOST = re.compile(r"https?://([a-zA-Z0-9.\-]+)")


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _is_test(path: str) -> bool:
    segs = [s for s in path.replace("\\", "/").split("/") if s]
    if any(s in _TEST_SEGMENTS for s in segs):
        return True
    name = segs[-1] if segs else ""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem.startswith("test_") or stem.endswith("_test") or ".test" in name or ".spec" in name


def _module_root(token: str) -> str:
    """Normalize an import token to a lookup key.

    `openai.types.chat` -> tries `openai.types.chat`, `openai.types`, `openai`.
    For JS, `@slack/web-api` -> `slack`; `aws-sdk` -> `aws-sdk`.
    """
    token = token.strip()
    # JS scoped/path packages: take a meaningful segment
    if token.startswith("@"):
        token = token[1:]
    token = token.split("/")[0] if "/" in token and "." not in token else token
    return token


def _lookup(token: str) -> tuple[str, str, str] | None:
    # try progressively shorter dotted prefixes (python style)
    parts = token.split(".")
    for i in range(len(parts), 0, -1):
        key = ".".join(parts[:i])
        if key in _SERVICE_BY_MODULE:
            return _SERVICE_BY_MODULE[key]
    return None


def _scan_file(content: str, ext: str) -> list[tuple[str, tuple[str, str, str]]]:
    """Return (evidence, service-tuple) hits for one file."""
    hits: list[tuple[str, tuple[str, str, str]]] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        tokens: list[str] = []
        if ext in {"py", "pyi"}:
            m = _PY_IMPORT.match(line)
            if m:
                tokens.append(_module_root(m.group(1)))
        elif ext in {"js", "jsx", "ts", "tsx", "mjs", "cjs"}:
            m = _JS_IMPORT.search(line)
            if m and not m.group(1).startswith("."):
                tokens.append(_module_root(m.group(1)))
        elif ext == "go":
            m = _GO_IMPORT.match(line)
            if m:
                # github.com/aws/aws-sdk-go -> check each path segment
                tokens.extend(seg for seg in m.group(1).split("/") if seg)
        for tok in tokens:
            svc = _lookup(tok)
            if svc:
                hits.append((line[:80], svc))
        # hostname signal (any line)
        if "http" in line:
            for host in _HOST.findall(line):
                for known, svc in _SERVICE_BY_HOST.items():
                    if host.endswith(known):
                        hits.append((line[:80], svc))
    return hits


def detect_external_services(file_contents: dict[str, str], *, limit: int = 20) -> dict:
    """Detect the external services a codebase talks to.

    Returns::

        {
          "total": int,                 # distinct services
          "services": [                 # one entry per distinct service
            {"name", "category", "note", "file_count", "example"}, ...
          ],
          "categories": {cat: count},
          "notes": [str, ...],
        }
    """
    # name -> {category, note, files:set, example}
    found: dict[str, dict] = {}
    for path, content in file_contents.items():
        if not content or _is_test(path):
            continue
        ext = _ext(path)
        if ext not in _CODE_EXTS:
            continue
        for evidence, (name, category, note) in _scan_file(content, ext):
            entry = found.setdefault(
                name, {"category": category, "note": note, "files": set(), "example": evidence}
            )
            entry["files"].add(path)

    services = [
        {
            "name": name,
            "category": info["category"],
            "note": info["note"],
            "file_count": len(info["files"]),
            "example": info["example"],
        }
        for name, info in found.items()
    ]
    # most-used first, then name for stability
    services.sort(key=lambda s: (-s["file_count"], s["name"]))

    categories: dict[str, int] = {}
    for s in services:
        categories[s["category"]] = categories.get(s["category"], 0) + 1

    notes: list[str] = []
    if not services:
        notes.append("没有发现明显的外部服务依赖，项目大概率能离线/本地跑起来。")

    return {
        "total": len(services),
        "services": services[:limit],
        "categories": categories,
        "notes": notes,
    }


def render_integrations_markdown(project_name: str, data: dict | None) -> str:
    """Render the external-services map as a Markdown section, or ``""``."""
    d = data or {}
    total = d.get("total", 0)
    if not total:
        return ""

    lines = [
        f"# {project_name} — 外部服务依赖",
        "",
        f"> 这个项目用到了 {total} 个外部服务。想在自己电脑上把它跑起来，你大概率得先去注册"
        "下面这些服务、拿到它们给的密钥或账号（「密钥 / API key」就是一串用来证明身份的字符；"
        "有些服务会按使用量收费）。",
        "",
        "## 需要准备的外部服务",
        "",
    ]
    for s in d.get("services") or []:
        where = f"（{s['file_count']} 个文件用到）" if s["file_count"] > 1 else ""
        lines.append(f"- **{s['name']}**（{s['category']}）{where} — {s['note']}")

    return "\n".join(lines).rstrip() + "\n"
