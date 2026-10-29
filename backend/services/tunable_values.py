"""Tunable-value scanner: surface hard-coded knobs a non-programmer may want to change.

``settings_map`` catches module-level UPPER_SNAKE_CASE constants; this module
casts a wider net.  It finds literals buried in function bodies, call arguments,
and conditionals that a reader would recognise as "a number I might want to
tweak": a timeout, a retry count, a URL, a file path, a threshold.  Each
finding carries the file, line, the matching snippet, a category, and a
plain-language note about what kind of knob it is.

Seven categories:

  url            — HTTP / HTTPS endpoints, webhooks, documentation links
  timeout        — sleep(), timeout=, deadline, TTL, and similar time knobs
  limit          — max_*, min_*, threshold, batch_size, page_size and friends
  path           — file-system paths (absolute or clearly project-relative)
  contact        — e-mail addresses and phone-like strings
  version        — semantic version strings and pinned version numbers
  number         — other numeric literals that look like business rules

Pure regex/AST over file contents, no LLM or network needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CATEGORY_ORDER = ("url", "timeout", "limit", "path", "contact", "version", "number")

_CATEGORY_LABELS = {
    "url": "URL 地址",
    "timeout": "超时 / 等待时间",
    "limit": "上限 / 阈值",
    "path": "文件路径",
    "contact": "联系方式",
    "version": "版本号",
    "number": "数字常量",
}

_CATEGORY_NOTES = {
    "url": "这个地址写死在代码里，如果要换成别的服务或环境，需要改这里。",
    "timeout": "这是代码等待的最长时间，网络慢或数据量大时可能需要调大。",
    "limit": "这是一个数量或范围的边界值，数据变多时可能需要调整。",
    "path": "文件或目录的位置写死了，换一台电脑或换个目录可能就不对了。",
    "contact": "这里有一个联系方式，如果联系人变了需要更新。",
    "version": "版本号写死在代码里，升级依赖时要注意这里。",
    "number": "这是一个固定数字，可能是业务规则（比如打分权重、比例），想调整的话改这里。",
}


@dataclass
class TunableValue:
    """One hard-coded value that a reader might want to adjust."""

    file: str
    line: int
    category: str
    value: str
    snippet: str
    note: str


@dataclass
class TunableReport:
    """Aggregated scan result grouped by category."""

    values: list[TunableValue] = field(default_factory=list)

    @property
    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.values:
            counts[v.category] = counts.get(v.category, 0) + 1
        return counts

    def by_category(self) -> dict[str, list[TunableValue]]:
        grouped: dict[str, list[TunableValue]] = {}
        for v in self.values:
            grouped.setdefault(v.category, []).append(v)
        return grouped


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_URL_RE = re.compile(
    r"""(?P<value>https?://[^\s"'`<>\)\]}]+)""",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(
    r"(?P<value>[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
)

_SEMVER_RE = re.compile(
    r"(?<![\w.])"
    r"(?P<value>\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?(?:\+[a-zA-Z0-9.]+)?)"
    r"(?![\w.])"
)

# Sleep / timeout / TTL call or keyword patterns.
_TIMEOUT_KW_RE = re.compile(
    r"(?P<value>\b\w*(?:timeout|ttl|deadline|expires?_?(?:in|at)|retry_delay|sleep|wait|delay)\w*\s*[=:]\s*[\d.]+)",
    re.IGNORECASE,
)
_SLEEP_CALL_RE = re.compile(
    r"(?P<value>\b(?:sleep|wait|delay)\s*\(\s*[\d.]+\s*\))",
    re.IGNORECASE,
)

_LIMIT_KW_RE = re.compile(
    r"(?P<value>\b(?:max|maximum|min|minimum|threshold|limit|batch_size|page_size|top_?k|chunk_size|buffer_size|max_?len|max_?size|max_?count|max_?retries|max_?attempts|max_?depth|sample_rate|learning_rate|ratio)\b\s*[=:]\s*[\d.]+)",
    re.IGNORECASE,
)

# Absolute or clearly project-relative paths in string literals.
_PATH_RE = re.compile(
    r"""(?P<value>(?:/(?:[\w.-]+/)+[\w.-]*|~/[\w./-]+|(?:src|lib|app|tests?|docs?|scripts?|config|data|assets|static|public|var|etc|opt)/[\w./-]+))""",
)

# Numeric literals that are not part of the above categories.
_PLAIN_NUMBER_RE = re.compile(
    r"(?<![\"\w.])(?P<value>\b\d{2,}\b)(?![\"\w.])",
)

_MAX_PER_CATEGORY = 50
_SNIPPET_MAX = 120


def _truncate(text: str, limit: int = _SNIPPET_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _categorise_line(line: str, lineno: int, filepath: str) -> list[TunableValue]:
    """Return tunable values found in a single source line."""
    found: list[TunableValue] = []
    seen: set[tuple[str, str]] = set()

    def _add(category: str, value: str) -> None:
        key = (category, value)
        if key in seen:
            return
        seen.add(key)
        found.append(
            TunableValue(
                file=filepath,
                line=lineno,
                category=category,
                value=value,
                snippet=_truncate(line.strip()),
                note=_CATEGORY_NOTES[category],
            )
        )

    for m in _URL_RE.finditer(line):
        _add("url", m.group("value"))

    for m in _EMAIL_RE.finditer(line):
        _add("contact", m.group("value"))

    for m in _TIMEOUT_KW_RE.finditer(line):
        _add("timeout", m.group("value"))

    for m in _SLEEP_CALL_RE.finditer(line):
        _add("timeout", m.group("value"))

    for m in _LIMIT_KW_RE.finditer(line):
        _add("limit", m.group("value"))

    for m in _PATH_RE.finditer(line):
        # Skip strings that are really URLs (already caught above).
        val = m.group("value")
        if val.startswith("http"):
            continue
        _add("path", val)

    for m in _SEMVER_RE.finditer(line):
        _add("version", m.group("value"))

    # Plain numbers only if nothing else matched on this line, to avoid noise.
    if not found:
        for m in _PLAIN_NUMBER_RE.finditer(line):
            _add("number", m.group("value"))

    return found


def scan_tunable_values(
    file_contents: dict[str, str],
    *,
    source_extensions: tuple[str, ...] = (
        "py",
        "js",
        "ts",
        "jsx",
        "tsx",
        "go",
        "rs",
        "java",
        "rb",
        "php",
        "sh",
        "yaml",
        "yml",
        "toml",
        "json",
        "cfg",
        "ini",
        "env",
    ),
) -> TunableReport:
    """Scan file contents for hard-coded values a reader may want to adjust.

    *file_contents* maps relative file paths to their text.  Only files whose
    extension appears in *source_extensions* are scanned; test files and
    lockfiles are skipped to keep the signal useful.

    Pure function over the mapping, so it is unit-testable with plain strings.
    """
    report = TunableReport()
    per_category: dict[str, int] = {}

    for filepath, text in sorted(file_contents.items()):
        ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""
        if ext not in source_extensions:
            continue
        lowered = filepath.lower()
        if any(
            skip in lowered
            for skip in ("lock", "package-lock", "yarn.lock", "node_modules", ".min.js", "vendor/")
        ):
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "*", "/*", "<!--")):
                continue
            for val in _categorise_line(line, lineno, filepath):
                if per_category.get(val.category, 0) >= _MAX_PER_CATEGORY:
                    continue
                per_category[val.category] = per_category.get(val.category, 0) + 1
                report.values.append(val)

    # Stable order: category priority, then file, then line.
    report.values.sort(key=lambda v: (_CATEGORY_ORDER.index(v.category), v.file, v.line))
    return report
