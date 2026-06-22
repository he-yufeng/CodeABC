"""Security-pattern scanner: surface common dangerous patterns in code.

A non-programmer reviewing code — a founder auditing outsourced work, say —
can't easily spot subtle security issues, but certain patterns are clear red
flags: hardcoded passwords, unvalidated shell commands, dangerous deserialisation.

Four categories:

  hardcoded_secret  — passwords / tokens / API keys embedded directly in code
                      instead of env vars or a secrets store
  dangerous_call    — eval() / exec() / pickle.loads() / yaml.load() without
                      SafeLoader — calls where untrusted input can run arbitrary
                      code or deserialise untrusted data unsafely
  shell_injection   — os.system() / subprocess with shell=True — OS commands
                      assembled from dynamic input can execute arbitrary shell code
  debug_mode        — DEBUG=True / app.debug=True / app.run(debug=True) outside
                      test files — settings that leak stack traces in production

Each finding carries the file path, line number, the matching line snippet
(truncated to 120 chars), category, and a plain-language explanation for a
non-programmer.

Limitations:
  * Regex-based — cannot track data flow. A variable ultimately controlled by
    user input may not match these patterns; a pattern in a comment or test
    fixture may fire spuriously.
  * Absence of findings does not mean the code is secure.
  * Best treated as "flags for human review", not definitive security verdicts.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Category: hardcoded_secret
# Variables whose names suggest they hold a credential are assigned a
# non-trivial string literal rather than read from env vars or config.
# ---------------------------------------------------------------------------

# Step 1: match any identifier (possibly attribute like self.key) assigned a
# string literal that is at least 6 chars.  Group 1 = varname, group 2 = quote
# char, group 3 = string content.  Optional type annotation handled inline.
_ASSIGN_STR_RE = re.compile(
    r"([\w.]+)"  # variable / attribute name
    r"(?:\s*:\s*\S+)?"  # optional type annotation  (: str, : bytes, …)
    r"\s*=\s*"  # assignment
    r"(['\"])([^'\"]{6,})\2",  # string literal ≥ 6 chars
)

# Step 2: check if the variable name (lowercased, underscores/dots stripped)
# contains one of these secret-component words.
_SECRET_KEYWORDS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "passphrase",
        "token",
        "apitoken",
        "accesstoken",
        "refreshtoken",
        "secret",
        "clientsecret",
        "jwtsecret",
        "apikey",
        "apisecret",
        "secretkey",
        "authkey",
        "authsecret",
        "privatekey",
        "accesskey",
        "signingkey",
    }
)

# Obvious placeholder markers — these are NOT real secrets.
_PLACEHOLDER_RE = re.compile(
    r"(?i)(your[_\-]|<[a-z]|{[a-z]|example|placeholder|dummy|fake|test|changeme|replace)"
)

# All-same-character strings are clearly placeholders (e.g. "xxxxxxxxxxxx").
_UNIFORM_RE = re.compile(r"^(.)\1{5,}$")

_SECRET_REASON = (
    "硬编码的凭据：把密码/密钥/Token 直接写进代码里，一旦代码泄漏"
    "（GitHub 提交历史、日志、截图）这个凭据就对所有人可见。"
    "应该改成从环境变量读取，或者用 Vault / Secrets Manager 管理。"
)


def _is_real_secret(value: str) -> bool:
    """Return True if the string literal looks like a real credential, not a placeholder."""
    if not value or len(value) < 6:
        return False
    if _PLACEHOLDER_RE.search(value):
        return False
    if _UNIFORM_RE.match(value.strip()):
        return False
    return True


# ---------------------------------------------------------------------------
# Category: dangerous_call
# eval / exec / pickle.loads / yaml.load without SafeLoader.
# ---------------------------------------------------------------------------

_EVAL_RE = re.compile(r"\beval\s*\(")
_EXEC_RE = re.compile(r"\bexec\s*\(")
_PICKLE_RE = re.compile(r"\bpickle\.(loads?)\s*\(")
# yaml.load( but NOT yaml.safe_load( (safe_load doesn't match \byaml\.load\b)
_YAML_LOAD_RE = re.compile(r"\byaml\.load\s*\(")

_DANGEROUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        _EVAL_RE,
        "eval() 把字符串当代码执行——如果字符串来自用户输入或网络，"
        "攻击者可以借此在服务器上运行任意代码。",
    ),
    (
        _EXEC_RE,
        "exec() 与 eval() 一样危险——动态执行任意代码，输入来源可控时是严重的远程代码执行风险。",
    ),
    (
        _PICKLE_RE,
        "pickle.load(s)() 会执行对象里嵌入的 Python 代码——"
        "反序列化不可信来源的 pickle 数据等价于对攻击者开放一个 shell。",
    ),
    (
        _YAML_LOAD_RE,
        "yaml.load() 在 PyYAML 5.1 之前默认允许执行任意 Python 对象——"
        "反序列化不可信 YAML 可以在服务器上运行任意代码。"
        "改用 yaml.safe_load() 或显式传 Loader=yaml.SafeLoader。",
    ),
]

# ---------------------------------------------------------------------------
# Category: shell_injection
# os.system / os.popen / subprocess + shell=True.
# ---------------------------------------------------------------------------

_OS_SYSTEM_RE = re.compile(r"\bos\.(system|popen)\s*\(")
_SUBPROCESS_SHELL_RE = re.compile(r"\bshell\s*=\s*True\b")

_OS_SYSTEM_REASON = (
    "os.system() / os.popen() 把字符串作为 shell 命令执行——"
    "如果命令中包含来自用户输入或外部数据的部分，攻击者可以注入分号、管道等"
    "执行任意命令（命令注入）。"
)
_SUBPROCESS_SHELL_REASON = (
    "subprocess 使用 shell=True 时，参数经由 shell 解释——"
    "如果命令字符串含有未经清洗的用户输入，攻击者可注入任意 shell 命令。"
    "安全做法是 shell=False（默认）并把参数拆成列表传递。"
)

# ---------------------------------------------------------------------------
# Category: debug_mode
# DEBUG=True / app.debug=True / app.run(debug=True) outside test files.
# ---------------------------------------------------------------------------

_DEBUG_TRUE_RE = re.compile(r"\bDEBUG\s*=\s*True\b")
_APP_DEBUG_RE = re.compile(r"\bapp\.(debug)\s*=\s*True\b")
_APP_RUN_DEBUG_RE = re.compile(r"\bapp\.run\s*\([^)]*debug\s*=\s*True")

_DEBUG_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        _DEBUG_TRUE_RE,
        "DEBUG=True：调试模式开着——在生产环境中会把详细的错误栈（包括源代码、变量值）"
        "暴露给用户，是严重的信息泄露。上线前必须改为 DEBUG=False 或通过环境变量控制。",
    ),
    (
        _APP_DEBUG_RE,
        "app.debug=True：Flask/类似框架的调试模式——会在浏览器里显示交互式调试器，"
        "生产环境中这允许任何用户在服务器上执行任意 Python 代码。",
    ),
    (
        _APP_RUN_DEBUG_RE,
        "app.run(debug=True)：以调试模式启动服务——同上，只应出现在本地开发脚本，"
        "绝不应进入生产部署代码。",
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SNIPPET_MAX = 120


def _snip(line: str) -> str:
    """Return the line stripped of leading whitespace, capped at _SNIPPET_MAX chars."""
    stripped = line.strip()
    return stripped[:_SNIPPET_MAX] + ("…" if len(stripped) > _SNIPPET_MAX else "")


def _is_comment(line: str, lang: str) -> bool:
    """True if the entire line is a comment (not just partially)."""
    s = line.lstrip()
    if not s:
        return False
    if lang in ("python",):
        return s.startswith("#")
    # JS / TS / Java / Go etc.
    return s.startswith("//") or s.startswith("/*") or s.startswith("*")


def _is_test_file(path: str) -> bool:
    """True if the path looks like a test or fixture file."""
    p = path.replace("\\", "/").lower()
    parts = p.split("/")
    name = parts[-1]
    if any(d in parts[:-1] for d in ("test", "tests", "__tests__", "spec", "specs", "fixtures")):
        return True
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return (
        stem.startswith("test_")
        or stem.endswith("_test")
        or stem.endswith(".test")
        or stem.endswith(".spec")
    )


def _lang_for(path: str) -> str:
    """Coarse language label from file extension."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in ("py",):
        return "python"
    if ext in ("js", "ts", "jsx", "tsx", "mjs", "cjs"):
        return "javascript"
    return ext


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_security(file_contents: dict[str, str], *, limit: int = 30) -> dict:
    """Scan file contents for common security-risk patterns.

    Args:
        file_contents: mapping of path to file text.
        limit: cap on total findings returned (keep the report scannable).

    Returns::

        {
          "total": int,             # findings before capping
          "critical": int,          # hardcoded_secret + dangerous_call count
          "findings": [             # capped to *limit*, sorted critical-first
            {
              "file": str,
              "line": int,
              "category": str,      # one of the four category names above
              "snippet": str,       # truncated line text
              "reason": str,        # plain-language explanation
            }, …
          ],
          "notes": [str, …],        # human-readable summary bullets
        }
    """
    findings: list[dict] = []

    for path, content in file_contents.items():
        if not content:
            continue
        lang = _lang_for(path)
        is_test = _is_test_file(path)

        for lineno, line in enumerate(content.splitlines(), start=1):
            if _is_comment(line, lang):
                continue

            # ── hardcoded_secret ──────────────────────────────────────────
            for m in _ASSIGN_STR_RE.finditer(line):
                varname = m.group(1)
                value = m.group(3)
                # normalise to bare lowercase (strip _ and . separators) then
                # check whether any secret keyword appears as a substring
                norm = varname.lower().replace("_", "").replace(".", "")
                if any(k in norm for k in _SECRET_KEYWORDS) and _is_real_secret(value):
                    findings.append(
                        {
                            "file": path,
                            "line": lineno,
                            "category": "hardcoded_secret",
                            "snippet": _snip(line),
                            "reason": _SECRET_REASON,
                            "is_test": is_test,
                        }
                    )
                    break  # one finding per line is enough

            # ── dangerous_call ────────────────────────────────────────────
            for pattern, reason in _DANGEROUS_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "file": path,
                            "line": lineno,
                            "category": "dangerous_call",
                            "snippet": _snip(line),
                            "reason": reason,
                            "is_test": is_test,
                        }
                    )
                    break  # first matching pattern per line

            # ── shell_injection ───────────────────────────────────────────
            if _OS_SYSTEM_RE.search(line):
                findings.append(
                    {
                        "file": path,
                        "line": lineno,
                        "category": "shell_injection",
                        "snippet": _snip(line),
                        "reason": _OS_SYSTEM_REASON,
                        "is_test": is_test,
                    }
                )
            elif _SUBPROCESS_SHELL_RE.search(line):
                findings.append(
                    {
                        "file": path,
                        "line": lineno,
                        "category": "shell_injection",
                        "snippet": _snip(line),
                        "reason": _SUBPROCESS_SHELL_REASON,
                        "is_test": is_test,
                    }
                )

            # ── debug_mode (skip test files entirely — intentional there) ──
            if not is_test:
                for pattern, reason in _DEBUG_PATTERNS:
                    if pattern.search(line):
                        findings.append(
                            {
                                "file": path,
                                "line": lineno,
                                "category": "debug_mode",
                                "snippet": _snip(line),
                                "reason": reason,
                                "is_test": False,
                            }
                        )
                        break

    # Deduplicate: same file + line can match at most one finding per category.
    seen: set[tuple] = set()
    unique: list[dict] = []
    for f in findings:
        key = (f["file"], f["line"], f["category"])
        if key not in seen:
            seen.add(key)
            unique.append(f)

    total = len(unique)

    # Sort: non-test critical findings first, then others; within each group
    # by category weight then file+line.
    _WEIGHT = {"hardcoded_secret": 0, "dangerous_call": 1, "shell_injection": 2, "debug_mode": 3}
    unique.sort(
        key=lambda f: (
            int(f.get("is_test", False)),  # non-test before test
            _WEIGHT.get(f["category"], 9),
            f["file"],
            f["line"],
        )
    )

    critical_cats = {"hardcoded_secret", "dangerous_call"}
    critical = sum(1 for f in unique if f["category"] in critical_cats and not f.get("is_test"))

    # Strip the internal `is_test` flag before returning.
    capped = [{k: v for k, v in f.items() if k != "is_test"} for f in unique[:limit]]

    notes = _build_notes(total, critical, unique)

    return {
        "total": total,
        "critical": critical,
        "findings": capped,
        "notes": notes,
    }


def _build_notes(total: int, critical: int, findings: list[dict]) -> list[str]:
    if total == 0:
        return ["未发现常见安全风险模式，代码没有明显的高危信号。"]
    notes = []
    if critical:
        notes.append(
            f"发现 {critical} 处高危问题（硬编码凭据或危险调用），建议在上线或开源前逐一排查。"
        )
    cats: dict[str, int] = {}
    for f in findings:
        cats[f["category"]] = cats.get(f["category"], 0) + 1
    cat_zh = {
        "hardcoded_secret": "硬编码凭据",
        "dangerous_call": "危险调用",
        "shell_injection": "Shell 注入",
        "debug_mode": "调试模式残留",
    }
    for cat, count in sorted(cats.items(), key=lambda x: _WEIGHT.get(x[0], 9)):
        notes.append(f"{cat_zh.get(cat, cat)}：{count} 处")
    if total > 10:
        notes.append("安全问题较多——建议优先清理高危项，再结合安全审计工具做全面扫描。")
    notes.append("注意：这是静态模式匹配，无法追踪数据流。测试文件里的同类模式危险性通常较低。")
    return notes


def render_security_markdown(project_name: str, data: dict | None) -> str:
    """Render the security scan as a Markdown section, or ``""`` if clean."""
    if not data or not data.get("findings"):
        return ""
    total = data.get("total", 0)
    critical = data.get("critical", 0)
    lines = [
        f"# 安全风险（{project_name}）",
        "",
        f"> 发现 {total} 处安全模式，其中 {critical} 处高危（硬编码凭据/危险调用）。"
        " 静态检测，建议逐一核查上下文。",
        "",
    ]
    lines.extend(f"- {note}" for note in data.get("notes", []))

    _CAT_ZH = {
        "hardcoded_secret": "⚠ 硬编码凭据",
        "dangerous_call": "⚠ 危险调用",
        "shell_injection": "Shell 注入",
        "debug_mode": "调试模式残留",
    }

    lines.append("")
    lines.append("## 发现清单")
    lines.append("")
    for f in data.get("findings", []):
        cat = _CAT_ZH.get(f["category"], f["category"])
        lines.append(f"- `{f['file']}:{f['line']}` [{cat}] `{f['snippet']}`")
        lines.append(f"  > {f['reason']}")
    return "\n".join(lines).rstrip() + "\n"


# Expose the category weight for tests / external sorting.
_WEIGHT = {"hardcoded_secret": 0, "dangerous_call": 1, "shell_injection": 2, "debug_mode": 3}
