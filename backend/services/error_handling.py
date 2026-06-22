"""Silent failures: where the code catches an error and then does nothing.

Tests answer "is this code verified?"; docs answer "is this code explained?".
This answers a third question that scares anyone inheriting a codebase: "where
does this code *hide its own problems*?" A caught error that is thrown away --
a bare ``except:``, an ``except ...: pass``, an empty ``catch {}`` -- means a
real failure can happen in production and leave no exception, no log, no trace.
Those are the spots where a bug can live for months without anyone noticing,
and they don't show up in a test-coverage or complexity report.

:func:`find_swallowed_errors` walks the already-read file contents and flags
three high-confidence, syntactic patterns (no full parser, just an honest
line/indentation heuristic):

* Python bare ``except:`` -- catches everything, including ``KeyboardInterrupt``
  and ``SystemExit``, and can't tell one error from another.
* Python ``except ...:`` whose whole body is just ``pass`` or ``...``.
* JS/TS empty ``catch (e) {}`` / ``catch {}``.

It deliberately does NOT flag a ``catch`` whose body is a comment (that is a
*documented* decision to ignore) or an ``except`` that actually does something,
to keep the signal high and the noise low.
"""

from __future__ import annotations

import re

_PY = {"py", "pyi"}
_JSTS = {"js", "jsx", "ts", "tsx", "mjs", "cjs", "mts", "cts"}

_TEST_SEGMENTS = {"test", "tests", "__tests__", "spec", "specs"}

# A Python ``except`` clause: capture the exception type (empty for a bare
# ``except:``) and anything written inline after the colon.
_EXCEPT_RE = re.compile(r"except\b\s*([^:]*):(.*)$")
# An empty JS/TS catch on one line: ``catch {}`` / ``catch (e) {}``.
_INLINE_EMPTY_CATCH_RE = re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}")
# A catch that opens a block at end of line: ``catch (e) {``.
_OPEN_CATCH_RE = re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*$")

_NOOP_BODIES = {"pass", "...", "pass  # noqa", "pass # noqa"}


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _is_test(path: str) -> bool:
    norm = path.replace("\\", "/")
    segments = [s for s in norm.split("/") if s]
    if any(s in _TEST_SEGMENTS for s in segments):
        return True
    name = segments[-1] if segments else ""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem.startswith("test_") or stem.endswith("_test") or ".test" in name or ".spec" in name


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _except_body_is_noop(lines: list[str], idx: int) -> bool:
    """True when the block opened by the ``except`` at ``idx`` is only pass/...."""
    base_indent = _indent(lines[idx])
    body: list[str] = []
    for j in range(idx + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            continue
        if _indent(line) <= base_indent:
            break  # dedented: the except block is over
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # a comment is a documented choice; don't count it as the body
        body.append(stripped)
    return len(body) == 1 and body[0] in _NOOP_BODIES


def _scan_python(path: str, content: str) -> list[dict]:
    out: list[dict] = []
    lines = content.splitlines()
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        m = _EXCEPT_RE.match(stripped)
        if not m:
            continue
        exc_type = m.group(1).strip()
        inline_body = m.group(2).strip()
        line_no = i + 1

        if exc_type == "":
            out.append(
                {
                    "path": path,
                    "line": line_no,
                    "category": "bare_except",
                    "snippet": stripped[:120],
                    "reason": "`except:` 捕获所有异常（连 Ctrl+C、系统退出都接住），又不区分错误"
                    "类型，真出问题时会被无差别吞掉、很难定位。",
                }
            )
            continue

        # `except X: pass` written on one line, or a block whose body is only pass/...
        swallowed = inline_body in _NOOP_BODIES or (
            (inline_body == "" or inline_body.startswith("#")) and _except_body_is_noop(lines, i)
        )
        if swallowed:
            out.append(
                {
                    "path": path,
                    "line": line_no,
                    "category": "swallowed",
                    "snippet": stripped[:120],
                    "reason": "捕获到错误后只写了 `pass`，等于把问题悄悄丢掉：程序不报错、日志"
                    "不留痕，bug 发生了也没人会知道。",
                }
            )
    return out


def _scan_jsts(path: str, content: str) -> list[dict]:
    out: list[dict] = []
    lines = content.splitlines()
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if _INLINE_EMPTY_CATCH_RE.search(stripped):
            hit = True
        elif _OPEN_CATCH_RE.search(stripped):
            # multi-line: the catch opens a block; flag only if the next
            # non-blank line closes it immediately (a truly empty body).
            hit = False
            for j in range(i + 1, len(lines)):
                nxt = lines[j].strip()
                if not nxt:
                    continue
                hit = nxt.startswith("}")
                break
        else:
            continue
        if hit:
            out.append(
                {
                    "path": path,
                    "line": i + 1,
                    "category": "empty_catch",
                    "snippet": stripped[:120],
                    "reason": "`catch` 块是空的，错误被接住后什么都不做，出问题时不会报错也"
                    "不留痕迹。",
                }
            )
    return out


# Worst-first: a bare except hides the most, an empty catch the least.
_SEVERITY = {"bare_except": 0, "swallowed": 1, "empty_catch": 2}


def find_swallowed_errors(file_contents: dict[str, str], *, limit: int = 15) -> dict:
    """Find places that catch an error and silently drop it.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many findings to return in the ranked list.

    Returns::

        {
          "total": int,                 # all findings across the project
          "files_affected": int,        # distinct files with at least one
          "findings": [                 # ranked worst-first, capped at limit
            {"path", "line", "category", "snippet", "reason"}, ...
          ],
          "notes": [str, ...],
        }
    """
    findings: list[dict] = []
    for path, content in file_contents.items():
        if not content or _is_test(path):
            continue
        ext = _ext(path)
        if ext in _PY:
            findings.extend(_scan_python(path, content))
        elif ext in _JSTS:
            findings.extend(_scan_jsts(path, content))

    findings.sort(key=lambda f: (_SEVERITY.get(f["category"], 9), f["path"], f["line"]))
    files_affected = len({f["path"] for f in findings})

    notes: list[str] = []
    if not findings:
        notes.append("没有发现被静默吞掉的错误，错误处理这块比较稳。")
    elif len(findings) > limit:
        notes.append(f"共发现 {len(findings)} 处，下面按严重程度只列前 {limit} 处。")

    return {
        "total": len(findings),
        "files_affected": files_affected,
        "findings": findings[:limit],
        "notes": notes,
    }


_CATEGORY_LABEL = {
    "bare_except": "裸 except（吞掉一切）",
    "swallowed": "捕获后只 pass",
    "empty_catch": "空 catch 块",
}


def render_error_handling_markdown(project_name: str, data: dict | None) -> str:
    """Render the silent-failures map as a Markdown section, or ``""``."""
    d = data or {}
    total = d.get("total", 0)
    if not total:
        return ""

    lines = [
        f"# {project_name} — 静默失败的地方",
        "",
        f"> 发现 {total} 处「错误被接住后悄悄丢掉」的代码，分布在 {d.get('files_affected', 0)} "
        "个文件里。这些地方一旦出问题，既不会报错也不会留日志，是 bug 最容易长期藏身的角落。",
        "",
        "## 最该补错误处理的地方",
        "",
    ]
    for f in d.get("findings") or []:
        label = _CATEGORY_LABEL.get(f["category"], f["category"])
        lines.append(f"- `{f['path']}:{f['line']}`（{label}）— {f['reason']}")

    notes = d.get("notes") or []
    if notes:
        lines += ["", "## 注意事项", ""]
        for n in notes:
            lines.append(f"- {n}")

    return "\n".join(lines).rstrip() + "\n"
