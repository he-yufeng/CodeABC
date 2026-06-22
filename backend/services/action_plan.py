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
    items += _architecture_actions(import_cycles)
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
