"""Test-coverage map: which code files have tests, and which don't.

A non-programmer sizing up a codebase — a founder reviewing outsourced work,
say — wants a blunt answer to "is this code actually tested?" and, more
usefully, "which important files have *no* test, so changing them is the
riskiest?". The static reading map and the risk list don't answer that; this
does.

Deterministic, no LLM. It pairs source files with test files two ways:

* by import — a test that imports a source file genuinely exercises it; this
  reuses the project import graph, no recomputation, and
* by name — the near-universal convention that ``test_scanner.py`` /
  ``scanner.test.ts`` / ``scanner.spec.ts`` cover ``scanner``.

Untested files are then ranked by import fan-in: a file nothing tests but many
files depend on is exactly where an unnoticed regression spreads furthest.

Pure functions over the scanner's file list — unit-testable with plain dicts,
no repo or git history needed.
"""

from __future__ import annotations

from .importgraph import _JS_LANGS, _PY_LANGS, _build_import_graph, _posix

# a file under one of these directories is a test regardless of its name
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}
# packaging / fixtures, not logic that warrants its own test
_NON_SOURCE_NAMES = {"__init__.py", "conftest.py", "setup.py"}


def _segments(path: str) -> list[str]:
    return [s for s in _posix(path).split("/") if s]


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else name


def _is_test_file(path: str, lang: str) -> bool:
    """True if the path looks like a test/spec file."""
    segs = _segments(path)
    name = segs[-1] if segs else ""
    stem = _stem(name)
    if any(d in _TEST_DIRS for d in segs[:-1]):
        return True
    if lang in _PY_LANGS:
        return stem == "conftest" or stem.startswith("test_") or stem.endswith("_test")
    if lang in _JS_LANGS:
        # scanner.test.ts / scanner.spec.ts -> stem ends with .test / .spec
        return stem.endswith(".test") or stem.endswith(".spec")
    return False


def _tested_stem(path: str, lang: str) -> str | None:
    """The source stem a test file targets by naming convention, or None."""
    stem = _stem(_segments(path)[-1])
    if lang in _PY_LANGS:
        if stem.startswith("test_"):
            return stem[len("test_") :] or None
        if stem.endswith("_test"):
            return stem[: -len("_test")] or None
        return None
    if lang in _JS_LANGS:
        for suffix in (".test", ".spec"):
            if stem.endswith(suffix):
                return stem[: -len(suffix)] or None
    return None


def _untested_reason(fan_in: int) -> str:
    if fan_in >= 5:
        return f"没有测试，却有 {fan_in} 个文件依赖它——这里出问题会牵连一大片，补测试的优先级最高。"
    if fan_in >= 1:
        return f"没有测试，有 {fan_in} 个文件依赖它：改动缺少自动验证，留意回归。"
    return "没有测试：相对孤立的文件，改动靠人工确认即可，风险较低。"


def _coverage_notes(total: int, pct: int, test_file_count: int, core_count: int) -> list[str]:
    if total == 0:
        return ["没有发现源代码文件。"]
    if test_file_count == 0:
        return ["没有发现任何测试文件——这个项目没有自动化测试，每次改动都得靠人工验证。"]
    notes = []
    if pct >= 70:
        notes.append(f"{pct}% 的代码文件有对应测试，改动相对有保障。")
    elif pct >= 30:
        notes.append(f"只有 {pct}% 的代码文件有测试，不少改动缺少自动验证、更容易留隐患。")
    else:
        notes.append(f"只有 {pct}% 的代码文件有测试，测试覆盖很薄，改动风险偏高。")
    if core_count:
        notes.append(
            f"其中 {core_count} 个被其它文件依赖的核心文件没有测试，改它们风险最高，建议优先补。"
        )
    return notes


def assess_test_coverage(files: list[dict], *, limit: int = 12) -> dict:
    """Map source files to whether they have a test, and rank the untested core.

    Args:
        files: the scanner's file list — dicts with ``path``, ``language`` and
            ``preview`` (used to resolve imports).
        limit: how many untested files to surface in ``untested_core``.

    Returns a dict shaped for ``TestCoverageSummary``: file counts, a 0-100
    ``coverage_percent`` (tested source files / total source files), the
    untested files ranked by import fan-in, and plain-language ``notes``.
    """
    _, imports, fan_in = _build_import_graph(files)

    test_files: set[str] = set()
    source_files: set[str] = set()
    lang_of: dict[str, str] = {}
    for f in files:
        path = _posix(f["path"])
        lang = f.get("language", "unknown")
        if lang not in _PY_LANGS and lang not in _JS_LANGS:
            continue
        lang_of[path] = lang
        if _is_test_file(path, lang):
            test_files.add(path)
        elif _segments(path)[-1] not in _NON_SOURCE_NAMES:
            source_files.add(path)

    covered: set[str] = set()
    # 1) import-based: a test that imports a source file exercises it
    for t in test_files:
        for dep in imports.get(t, ()):
            if dep in source_files:
                covered.add(dep)
    # 2) name-based: test_scanner.py <-> scanner.py, scanner.test.ts <-> scanner.ts
    tested_stems = {s for t in test_files if (s := _tested_stem(t, lang_of[t])) is not None}
    tested_stems = {s.lower() for s in tested_stems}
    if tested_stems:
        for s in source_files:
            if _stem(_segments(s)[-1]).lower() in tested_stems:
                covered.add(s)

    untested = sorted(
        source_files - covered,
        key=lambda p: (-len(fan_in.get(p, ())), p),
    )

    total = len(source_files)
    tested = len(covered)
    pct = round(tested / total * 100) if total else 0

    untested_core = [
        {
            "path": p,
            "language": lang_of.get(p, "unknown"),
            "fan_in": len(fan_in.get(p, ())),
            "reason": _untested_reason(len(fan_in.get(p, ()))),
        }
        for p in untested[:limit]
    ]
    core_count = sum(1 for u in untested_core if u["fan_in"] >= 1)

    return {
        "total_source_files": total,
        "tested_files": tested,
        "untested_files": total - tested,
        "test_files": len(test_files),
        "coverage_percent": pct,
        "untested_core": untested_core,
        "notes": _coverage_notes(total, pct, len(test_files), core_count),
    }


def render_coverage_markdown(name: str, coverage: dict | None) -> str:
    """Render the test-coverage summary as a Markdown section, or ``""``."""
    if not coverage or not coverage.get("total_source_files"):
        return ""
    pct = coverage.get("coverage_percent", 0)
    lines = [
        f"# 测试覆盖（{name}）",
        "",
        f"> {coverage.get('tested_files', 0)}/{coverage.get('total_source_files', 0)} "
        f"个代码文件有测试（{pct}%），共发现 {coverage.get('test_files', 0)} 个测试文件。",
        "",
    ]
    lines.extend(f"- {note}" for note in coverage.get("notes", []))
    untested = coverage.get("untested_core", [])
    if untested:
        lines.extend(["", "## 没有测试、最该补的文件", ""])
        lines.extend(f"- `{u['path']}` — {u['reason']}" for u in untested)
    return "\n".join(lines).rstrip() + "\n"
