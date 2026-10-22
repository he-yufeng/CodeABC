"""Runtime requirements: what kind of machine and services a project needs to run.

The dependency list answers "which libraries get installed"; this map answers the
more basic question a non-programmer asks first: *will this thing run on my
machine at all?* Do I need a specific Python or Node version, a database server
running in the background, an NVIDIA graphics card, a particular operating
system — or is there a Docker escape hatch that skips all of it?

Everything here is read off files CodeABC already loaded — version pins in
manifests, service client libraries in the dependency lists and imports,
GPU-shaped dependencies and CUDA sources, OS-specific imports, and the presence
of container files. Deterministic, no LLM, no network.

:func:`scan_run_requirements` is pure over the file-contents mapping, so it is
unit-testable with plain strings and needs no repository.

Honesty limits, kept on purpose:

- A service found only in a manifest (not imported by scanned source) is marked
  "可能在某些功能里用到" rather than required — plenty of projects declare
  clients they barely use.
- The GPU note means "parts of this project expect an NVIDIA GPU". CPU-only
  fallbacks are common; when no GPU signal exists we say nothing rather than
  promising it runs everywhere.
- OS signals come from a small, honest set of imports/packages; absence of a
  signal is not a portability guarantee.
"""

from __future__ import annotations

import re

# --- version floors -----------------------------------------------------------

_REQUIRES_PYTHON_RE = re.compile(r"""requires-python\s*=\s*['"]([^'"]+)['"]""")
_PYPROJECT_FLAVOR_RE = re.compile(r"^\s*\[project\]", re.M)
_SETUP_CFG_REQUIRES_RE = re.compile(r"""python_requires\s*=\s*([><=!~0-9., ]+)""")
_PIPFILE_REQUIRES_RE = re.compile(r"""python(?:_full)?_version\s*=\s*['"]([0-9.]+)['"]""")
_RUNTIME_TXT_RE = re.compile(r"^python-([0-9.]+)\s*$", re.M)
_ENGINES_NODE_RE = re.compile(r"""['"]node['"]\s*:\s*['"]([^'"]+)['"]""")

# --- service clients ----------------------------------------------------------

# canonical service -> (manifest package names, importable module names)
_SERVICES: dict[str, tuple[set[str], set[str]]] = {
    "PostgreSQL": (
        {"psycopg", "psycopg2", "psycopg2-binary", "pg8000", "asyncpg"},
        {"psycopg", "psycopg2", "pg8000", "asyncpg"},
    ),
    "MySQL": (
        {"pymysql", "mysqlclient", "mysql-connector-python", "aiomysql"},
        {"pymysql", "MySQLdb", "mysql", "aiomysql"},
    ),
    "Redis": (
        {"redis", "aioredis", "ioredis"},
        {"redis", "aioredis"},
    ),
    "MongoDB": (
        {"pymongo", "motor", "mongodb", "mongoose"},
        {"pymongo", "motor"},
    ),
    "Elasticsearch": (
        {"elasticsearch", "elasticsearch8", "@elastic/elasticsearch"},
        {"elasticsearch"},
    ),
    "Kafka": (
        {"kafka-python", "confluent-kafka", "aiokafka", "kafkajs"},
        {"kafka", "aiokafka", "confluent_kafka"},
    ),
    "RabbitMQ": (
        {"pika", "aio-pika", "amqplib"},
        {"pika", "aio_pika", "amqp"},
    ),
}

_SERVICE_NOTES = {
    "PostgreSQL": (
        "一种常用的数据库服务器。光装 Python 包不够，"
        "还得有一台正在运行的 PostgreSQL（可以装在本机，也可以用云上的）。"
    ),
    "MySQL": "一种常用的数据库服务器。需要先有一台正在运行的 MySQL（本机安装或云服务都可以）。",
    "Redis": "一个跑在后台的内存数据库，常用来做缓存或队列。需要先启动 Redis 服务。",
    "MongoDB": "一种文档型数据库服务器。需要先有一台正在运行的 MongoDB。",
    "Elasticsearch": "一个搜索引擎服务器，常用于全文检索。需要先部署并启动它。",
    "Kafka": "一个消息队列服务器，常见于大型数据管道。需要先部署 Kafka 集群。",
    "RabbitMQ": "一个消息队列服务器。需要先启动 RabbitMQ 服务。",
}

# --- GPU / OS signals ----------------------------------------------------------

_GPU_PACKAGES = {
    "torch",
    "tensorflow",
    "jax",
    "jaxlib",
    "cuda-python",
    "cupy",
    "vllm",
    "flash-attn",
}
_CUDA_DEVICE_RE = re.compile(r"""['"]cuda(?::\d+)?['"]""")

_OS_SIGNALS: dict[str, tuple[set[str], set[str], str]] = {
    "windows_only": (
        {"pywin32", "pywintypes", "winreg"},
        {"winreg", "msvcrt", "pywintypes"},
        "Windows 专属：代码里用到了只有 Windows 才有的组件，其他系统跑不了这部分。",
    ),
    "mac_only": (
        {"pyobjc", "pyobjc-core"},
        {"pyobjc"},
        "macOS 专属：代码里用到了苹果系统特有的组件。",
    ),
    "posix_only": (
        set(),
        {"fcntl", "termios", "pwd", "grp", "resource"},
        "类 Unix 系统（Linux/macOS）专属：用到了 Windows 没有的系统接口。",
    ),
}

_CONTAINER_FILES = {
    "dockerfile",
    "containerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

# manifest files we read version pins / package names from
_MANIFEST_NAMES = re.compile(
    r"(^|/)(pyproject\.toml|setup\.cfg|setup\.py|Pipfile|runtime\.txt|package\.json|requirements.*\.txt)$",
    re.I,
)

_IMPORT_RES = [
    re.compile(r"""(?m)^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)"""),  # python
    re.compile(r"""require\(\s*['"]([A-Za-z0-9@][^'"]*)['"]\s*\)"""),  # js require
    re.compile(r"""(?m)^\s*import\s+.*?from\s+['"]([^'"]+)['"]"""),  # js import
]
_PY_EXTS = (".py",)
_JS_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _manifest_packages(content: str, name: str) -> set[str]:
    """Pull rough package names out of a manifest's text.

    Deliberately tolerant: split requirements-style lines on version specifiers,
    and collect quoted names in TOML/JSON dependency arrays.
    """
    lower = name.lower()
    found: set[str] = set()
    if lower.endswith(".txt"):
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            pkg = re.split(r"[<>=!~\[ ;]", line, maxsplit=1)[0].strip()
            if pkg:
                found.add(pkg.lower())
    else:
        for quoted in re.findall(r"""['"]([A-Za-z0-9][A-Za-z0-9._/-]*)['"]""", content):
            found.add(quoted.split("/")[-1].lower())
    return found


def _imported_modules(file_contents: dict[str, str]) -> set[str]:
    """Top-level module/package names imported anywhere in the scanned source."""
    mods: set[str] = set()
    for path, content in file_contents.items():
        lower = path.lower()
        is_py = lower.endswith(_PY_EXTS)
        is_js = lower.endswith(_JS_EXTS)
        if not (is_py or is_js):
            continue
        if is_py:
            for m in _IMPORT_RES[0].finditer(content):
                mods.add(m.group(1))
        else:
            for rx in _IMPORT_RES[1:]:
                for m in rx.finditer(content):
                    name = m.group(1)
                    if not name.startswith("."):
                        mods.add(name.split("/")[0].lstrip("@"))
    return mods


def scan_run_requirements(file_contents: dict[str, str]) -> dict:
    """Collect what kind of machine and services the project needs to run.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).

    Returns ``{"requirements": [...]}`` where each requirement is
    ``{"category", "name", "detail", "note", "required"}`` and ``category`` is
    one of ``python``, ``node``, ``service``, ``gpu``, ``os`` or ``container``.
    ``detail`` is the raw evidence (file + constraint); ``note`` is a
    plain-language explanation; ``required`` is False for signals that only
    appear in a manifest or dev-only context.
    """
    reqs: list[dict] = []

    # --- version floors ---
    python_floor: tuple[str, str] | None = None  # (constraint, source file)
    node_floor: tuple[str, str] | None = None

    _DOTFILES = (".nvmrc", ".node-version", ".python-version")
    for path, content in file_contents.items():
        base = _basename(path)
        lower = base.lower()
        if not _MANIFEST_NAMES.search(path) and lower not in _DOTFILES:
            continue

        if lower == "pyproject.toml" and _PYPROJECT_FLAVOR_RE.search(content):
            m = _REQUIRES_PYTHON_RE.search(content)
            if m and python_floor is None:
                python_floor = (m.group(1).strip(), path)
        elif lower in ("setup.cfg", "setup.py"):
            m = _SETUP_CFG_REQUIRES_RE.search(content)
            if m and python_floor is None:
                python_floor = (m.group(1).strip(), path)
        elif lower == "pipfile":
            m = _PIPFILE_REQUIRES_RE.search(content)
            if m and python_floor is None:
                python_floor = (f">={m.group(1)}", path)
        elif lower == "runtime.txt":
            m = _RUNTIME_TXT_RE.search(content)
            if m and python_floor is None:
                python_floor = (f"=={m.group(1)}", path)
        elif lower == ".python-version":
            ver = content.strip().splitlines()[0].strip() if content.strip() else ""
            if ver and python_floor is None:
                python_floor = (f"=={ver}", path)
        elif lower == "package.json":
            m = _ENGINES_NODE_RE.search(content)
            if m and node_floor is None:
                node_floor = (m.group(1).strip(), path)
        elif lower in (".nvmrc", ".node-version"):
            ver = content.strip().lstrip("v")
            if ver and node_floor is None:
                node_floor = (f"=={ver}", path)

    if python_floor:
        constraint, source = python_floor
        reqs.append(
            {
                "category": "python",
                "name": f"Python {constraint}",
                "detail": f"{source} 里声明了 Python 版本要求",
                "note": (
                    "电脑上装的 Python 版本要满足这个要求。"
                    "命令行里输入 python3 --version 就能看自己装的是几。"
                ),
                "required": True,
            }
        )
    if node_floor:
        constraint, source = node_floor
        reqs.append(
            {
                "category": "node",
                "name": f"Node.js {constraint}",
                "detail": f"{source} 里声明了 Node.js 版本要求",
                "note": (
                    "电脑上装的 Node.js 版本要满足这个要求。"
                    "命令行里输入 node --version 就能看自己装的是几。"
                ),
                "required": True,
            }
        )

    # --- services ---
    manifest_pkgs: set[str] = set()
    manifest_only_pkgs: set[str] = set()
    for path, content in file_contents.items():
        base = _basename(path)
        if _MANIFEST_NAMES.search(path):
            pkgs = _manifest_packages(content, base)
            manifest_pkgs |= pkgs
            if "dev" not in base.lower():
                manifest_only_pkgs |= pkgs
    imports = _imported_modules(file_contents)

    for service, (pkg_names, mod_names) in _SERVICES.items():
        in_manifest = bool(pkg_names & manifest_pkgs)
        # JS imports use the npm package name directly, so check both sets.
        in_imports = bool((mod_names | pkg_names) & imports)
        if not (in_manifest or in_imports):
            continue
        reqs.append(
            {
                "category": "service",
                "name": service,
                "detail": "代码里直接引入了它的客户端"
                if in_imports
                else "依赖清单里列了它的客户端",
                "note": _SERVICE_NOTES[service],
                "required": in_imports,
            }
        )

    # --- GPU ---
    gpu_pkg = sorted(_GPU_PACKAGES & manifest_pkgs)
    has_cu = any(p.lower().endswith((".cu", ".cuh")) for p in file_contents)
    has_cuda_device = False
    if not gpu_pkg:
        for path, content in file_contents.items():
            if path.lower().endswith(_PY_EXTS) and _CUDA_DEVICE_RE.search(content):
                has_cuda_device = True
                break
    if gpu_pkg or has_cu or has_cuda_device:
        evidence = (
            f"依赖里有 {', '.join(gpu_pkg[:3])}"
            if gpu_pkg
            else ("有 .cu CUDA 源文件" if has_cu else "代码里指定了 cuda 设备")
        )
        reqs.append(
            {
                "category": "gpu",
                "name": "NVIDIA 显卡（GPU）",
                "detail": evidence,
                "note": (
                    "项目的部分功能需要英伟达显卡才能跑（普通办公电脑的集成显卡不算）。"
                    "有些项目也提供纯 CPU 的降级用法，但会慢很多。"
                ),
                "required": True,
            }
        )

    # --- OS constraints ---
    for _key, (pkgs, mods, note) in _OS_SIGNALS.items():
        if (pkgs & manifest_pkgs) or (mods & imports):
            label = {
                "windows_only": "仅 Windows",
                "mac_only": "仅 macOS",
                "posix_only": "仅 Linux / macOS",
            }[_key]
            reqs.append(
                {
                    "category": "os",
                    "name": label,
                    "detail": "代码或依赖里出现了系统专属组件",
                    "note": note,
                    "required": True,
                }
            )

    # --- container escape hatch ---
    container = next(
        (p for p in file_contents if _basename(p).lower() in _CONTAINER_FILES),
        None,
    )
    if container:
        reqs.append(
            {
                "category": "container",
                "name": "可以用 Docker",
                "detail": f"仓库里有 {container}",
                "note": (
                    "如果装了 Docker，可以不管上面的版本和服务要求，直接用容器一键起。"
                    "这通常是最省事的办法。"
                ),
                "required": False,
            }
        )

    order = {"python": 0, "node": 1, "service": 2, "gpu": 3, "os": 4, "container": 5}
    reqs.sort(key=lambda r: order[r["category"]])
    return {"requirements": reqs}
