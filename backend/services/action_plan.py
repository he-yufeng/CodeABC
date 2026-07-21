"""Priority action plan — turn the analyses into an ordered "what do I fix first?" list.

The health score tells a non-programmer *how* a codebase is doing and *which
dimensions* drag it down. The obvious next question is "OK, so what do I actually
do?" — and a category score doesn't answer that. This module does.

It reads the same analysis results (security findings, untested core files,
complexity, import cycles, tech debt) and emits a single ranked list of concrete
actions, each pinned to a real file where possible and written in plain language:
what's wrong, why it matters, and roughly how big the fix is.

Ranking favours impact-over-effort: a hardcoded secret outranks a long function,
and an untested file that ten others depend on outranks one nothing imports.

Pure function over already-computed analysis dicts — no repo access required.
"""

from __future__ import annotations

# Severity weights drive the ordering: higher sorts first.
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

# Caps so the plan stays a short, actionable list rather than a dump.
_MAX_ITEMS = 12
_MAX_PER_CATEGORY = 4


def _security_actions(security: dict | None) -> list[dict]:
    if not security or not security.get("findings"):
        return []
    actions: list[dict] = []
    # Critical findings (secrets / dangerous calls) first, then the rest.
    findings = sorted(
        security["findings"],
        key=lambda f: 0 if f.get("category") in ("hardcoded_secret", "dangerous_call") else 1,
    )
    for f in findings[:_MAX_PER_CATEGORY]:
        critical = f.get("category") in ("hardcoded_secret", "dangerous_call")
        actions.append(
            {
                "priority": "high" if critical else "medium",
                "category": "security",
                "title": f"处理安全隐患：{f.get('file', '?')}:{f.get('line', '?')}",
                "target": f.get("file", ""),
                "detail": f.get("reason", "存在潜在安全问题，建议人工核查。"),
                "effort": "small",
            }
        )
    return actions


def _coverage_actions(test_coverage: dict | None) -> list[dict]:
    if not test_coverage:
        return []
    actions: list[dict] = []
    # Untested core files are already ranked by fan-in upstream.
    for f in (test_coverage.get("untested_core") or [])[:_MAX_PER_CATEGORY]:
        fan_in = f.get("fan_in", 0)
        actions.append(
            {
                "priority": "high" if fan_in >= 5 else "medium",
                "category": "test_coverage",
                "title": f"给核心文件补测试：{f.get('path', '?')}",
                "target": f.get("path", ""),
                "detail": f.get(
                    "reason",
                    f"这个文件没有测试，却有 {fan_in} 个文件依赖它，改动缺少自动验证。",
                ),
                "effort": "medium",
            }
        )
    return actions


def _complexity_actions(complexity_files: list[dict] | None) -> list[dict]:
    if not complexity_files:
        return []
    actions: list[dict] = []
    # Only flag genuinely gnarly files (cyclomatic complexity > 20).
    gnarly = sorted(
        (f for f in complexity_files if f.get("complexity", 0) > 20),
        key=lambda f: f.get("complexity", 0),
        reverse=True,
    )
    for f in gnarly[:_MAX_PER_CATEGORY]:
        cx = f.get("complexity", 0)
        actions.append(
            {
                "priority": "medium" if cx > 40 else "low",
                "category": "complexity",
                "title": f"拆分复杂逻辑：{f.get('path', '?')}",
                "target": f.get("path", ""),
                "detail": (
                    f"圈复杂度约 {cx}，分支太多、读起来和改起来都费劲，建议拆成更小的函数。"
                ),
                "effort": "large",
            }
        )
    return actions


def _deep_nesting_actions(deep_nesting_files: list[dict] | None) -> list[dict]:
    if not deep_nesting_files:
        return []
    actions: list[dict] = []
    # Deepest first; the analyzer already filtered to the flagged threshold.
    deepest = sorted(deep_nesting_files, key=lambda f: f.get("depth", 0), reverse=True)
    for f in deepest[:_MAX_PER_CATEGORY]:
        depth = f.get("depth", 0)
        func = f.get("function", "?")
        actions.append(
            {
                "priority": "medium" if depth >= 6 else "low",
                "category": "deep_nesting",
                "title": f"拍平深层嵌套：{f.get('path', '?')} 的 {func}",
                "target": f.get("path", ""),
                "detail": (
                    f"函数 {func} 的控制流嵌套了 {depth} 层，读的时候要同时记住每一层的条件，"
                    "很容易看晕。建议用提前 return / 卫语句 / 把里层抽成一个小函数来拍平。"
                ),
                "effort": "medium",
            }
        )
    return actions


def _long_functions_actions(long_functions_files: list[dict] | None) -> list[dict]:
    if not long_functions_files:
        return []
    actions: list[dict] = []
    # Longest first; the analyzer already filtered to the flagged threshold.
    longest = sorted(long_functions_files, key=lambda f: f.get("length", 0), reverse=True)
    for f in longest[:_MAX_PER_CATEGORY]:
        length = f.get("length", 0)
        func = f.get("function", "?")
        actions.append(
            {
                "priority": "medium" if length >= 120 else "low",
                "category": "long_function",
                "title": f"拆分过长的函数：{f.get('path', '?')} 的 {func}",
                "target": f.get("path", ""),
                "detail": (
                    f"函数 {func} 有 {length} 行，一口气读完很吃力、中间没有自然的停顿点。"
                    "建议按职责拆成几个各做一件事、名字取好的小函数。"
                ),
                "effort": "medium",
            }
        )
    return actions


def _duplicate_code_actions(duplicate_code_clusters: list[list[dict]] | None) -> list[dict]:
    if not duplicate_code_clusters:
        return []
    actions: list[dict] = []
    # Largest clusters first; the analyzer already filtered to real duplicates.
    biggest = sorted(duplicate_code_clusters, key=len, reverse=True)
    for cluster in biggest[:_MAX_PER_CATEGORY]:
        spots = "、".join(f"{o.get('path', '?')}:{o.get('line', '?')}" for o in cluster)
        actions.append(
            {
                "priority": "medium" if len(cluster) >= 3 else "low",
                "category": "duplicate_code",
                "title": f"抽取重复代码：{cluster[0].get('path', '?')} 等 {len(cluster)} 处",
                "target": cluster[0].get("path", ""),
                "detail": (
                    f"同一段代码出现在 {len(cluster)} 个地方（{spots}）。"
                    "改一处时其余几处不会跟着变，建议抽成公共函数，以后只改一处。"
                ),
                "effort": "medium",
            }
        )
    return actions


def _too_many_params_actions(too_many_params_files: list[dict] | None) -> list[dict]:
    if not too_many_params_files:
        return []
    actions: list[dict] = []
    # Widest first; the analyzer already filtered to the flagged threshold.
    widest = sorted(too_many_params_files, key=lambda f: f.get("params", 0), reverse=True)
    for f in widest[:_MAX_PER_CATEGORY]:
        params = f.get("params", 0)
        func = f.get("function", "?")
        actions.append(
            {
                "priority": "medium" if params >= 8 else "low",
                "category": "too_many_params",
                "title": f"减少参数个数：{f.get('path', '?')} 的 {func}",
                "target": f.get("path", ""),
                "detail": (
                    f"函数 {func} 有 {params} 个参数，调用时要记住每个位置传什么、很容易传错。"
                    "建议把关系紧密的参数打包成一个对象（或 dataclass），或拆成更小的函数。"
                ),
                "effort": "medium",
            }
        )
    return actions


def _typing_actions(typing_files: list[dict] | None) -> list[dict]:
    if not typing_files:
        return []
    actions: list[dict] = []
    # Files with the most unannotated public symbols and low coverage first;
    # only surface genuinely under-annotated files (not a stray missing hint).
    weak = sorted(
        (f for f in typing_files if f.get("missing", 0) >= 3 and f.get("coverage", 1) < 0.6),
        key=lambda f: (-f.get("missing", 0), f.get("coverage", 1)),
    )
    for f in weak[:_MAX_PER_CATEGORY]:
        missing = f.get("missing", 0)
        pct = round(f.get("coverage", 0) * 100)
        actions.append(
            {
                "priority": "low",
                "category": "typing",
                "title": f"补类型注解：{f.get('path', '?')}",
                "target": f.get("path", ""),
                "detail": (
                    f"这个文件里有 {missing} 个对外函数没写类型注解（类型覆盖率约 {pct}%），"
                    "补上参数和返回值的类型能让编辑器提示更准、也更容易发现用错类型的调用。"
                ),
                "effort": "small",
            }
        )
    return actions


def _architecture_actions(import_cycles: list[dict] | None) -> list[dict]:
    if not import_cycles:
        return []
    actions: list[dict] = []
    for c in import_cycles[:_MAX_PER_CATEGORY]:
        files = c.get("files", [])
        preview = "、".join(files[:3]) + ("…" if len(files) > 3 else "")
        actions.append(
            {
                "priority": "medium",
                "category": "architecture",
                "title": f"打破循环依赖（{len(files)} 个文件）",
                "target": files[0] if files else "",
                "detail": (
                    f"这些文件互相 import 形成环：{preview}。循环依赖会让模块难以单独理解和测试。"
                ),
                "effort": "medium",
            }
        )
    return actions


def _tech_debt_actions(tech_debt_files: list[dict] | None) -> list[dict]:
    if not tech_debt_files:
        return []
    # Only surface the single worst offender — tech debt is low priority next to
    # security and missing tests, and we don't want to crowd the list.
    worst = max(tech_debt_files, key=lambda f: f.get("count", 0), default=None)
    if not worst or worst.get("count", 0) < 3:
        return []
    return [
        {
            "priority": "low",
            "category": "tech_debt",
            "title": f"清理技术债标记：{worst.get('path', '?')}",
            "target": worst.get("path", ""),
            "detail": (
                f"这个文件有 {worst.get('count', 0)} 处 TODO/FIXME/HACK 标记，"
                "择期清理能降低后续维护成本。"
            ),
            "effort": "small",
        }
    ]


def build_action_plan(
    *,
    security: dict | None = None,
    test_coverage: dict | None = None,
    complexity_files: list[dict] | None = None,
    tech_debt_files: list[dict] | None = None,
    import_cycles: list[dict] | None = None,
    deep_nesting_files: list[dict] | None = None,
    long_functions_files: list[dict] | None = None,
    too_many_params_files: list[dict] | None = None,
    duplicate_code_clusters: list[list[dict]] | None = None,
    typing_files: list[dict] | None = None,
) -> dict:
    """Build a ranked, plain-language remediation list from existing analyses.

    All arguments are optional and keyword-only; callers pass whichever analyses
    are available. Returns::

        {
          "total": int,
          "items": [
            {
              "priority": "high" | "medium" | "low",
              "category": str,
              "title": str,
              "target": str,    # file path, or "" when not file-specific
              "detail": str,    # plain-language explanation
              "effort": "small" | "medium" | "large",
            },
            ...
          ],
          "notes": [str, ...],
        }
    """
    items: list[dict] = []
    items += _security_actions(security)
    items += _coverage_actions(test_coverage)
    items += _complexity_actions(complexity_files)
    items += _deep_nesting_actions(deep_nesting_files)
    items += _long_functions_actions(long_functions_files)
    items += _too_many_params_actions(too_many_params_files)
    items += _duplicate_code_actions(duplicate_code_clusters)
    items += _architecture_actions(import_cycles)
    items += _typing_actions(typing_files)
    items += _tech_debt_actions(tech_debt_files)

    # Stable sort by priority so within a priority the source order (security,
    # coverage, complexity, …) is preserved.
    items.sort(key=lambda a: _PRIORITY_RANK.get(a["priority"], 9))
    items = items[:_MAX_ITEMS]

    notes: list[str] = []
    if not items:
        notes.append("没有发现需要优先处理的问题，代码基线良好。")
    elif items[0]["priority"] == "high":
        notes.append("列表已按优先级排序，建议从第一条开始处理。")

    return {"total": len(items), "items": items, "notes": notes}


_PRIORITY_LABEL = {"high": "🔴 高", "medium": "🟡 中", "low": "⚪ 低"}
_EFFORT_LABEL = {"small": "小", "medium": "中", "large": "大"}


def render_action_plan_markdown(project_name: str, data: dict | None) -> str:
    """Render the action plan as a Markdown section."""
    if not data or not data.get("items"):
        return ""
    lines = [
        f"# 优先行动清单（{project_name}）",
        "",
        "> 按「先做哪个最值」排序：安全和缺测试的核心文件排在前面。",
        "",
        "| # | 优先级 | 事项 | 工作量 |",
        "|---|--------|------|--------|",
    ]
    for i, item in enumerate(data["items"], start=1):
        prio = _PRIORITY_LABEL.get(item["priority"], item["priority"])
        effort = _EFFORT_LABEL.get(item["effort"], item["effort"])
        lines.append(f"| {i} | {prio} | {item['title']} | {effort} |")

    lines += ["", "## 说明", ""]
    for item in data["items"]:
        lines.append(f"- **{item['title']}** — {item['detail']}")

    notes = data.get("notes", [])
    if notes:
        lines += ["", "## 注意事项", ""]
        for n in notes:
            lines.append(f"- {n}")

    return "\n".join(lines).rstrip() + "\n"
