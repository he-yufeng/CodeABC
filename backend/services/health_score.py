"""Project health score — aggregate signal from multiple analyses into a single 0-100 rating.

When a non-programmer receives a code review, a vendor codebase, or an inherited project,
they need a fast answer to the question: "is this code in good shape?" Before this module,
CodeABC produced several independent analyses (security, test coverage, activity, complexity,
tech debt, architecture) but left it to the viewer to mentally weigh them.

This module synthesises those signals into one score and grade.

Scoring dimensions and weights:
  Security         25 %   hardcoded secrets / dangerous calls cost heavily
  Test coverage    20 %   ratio of source files covered by tests
  Activity         20 %   recent commit cadence from the activity pulse
  Complexity       15 %   average cyclomatic complexity of source files
  Tech debt        10 %   density of TODO/FIXME/HACK markers
  Architecture     10 %   import-cycle count; orphan modules contribute to noise

Grade mapping:
  A   90–100   excellent
  B   75–89    good
  C   60–74    fair — consider targeted improvements
  D   40–59    needs work
  F     0–39   critical issues present

Pure function over already-computed analysis dicts — no repo access required.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ACTIVITY_LABEL_SCORE: dict[str, int] = {
    "active": 100,
    "slowing": 72,
    "quiet": 48,
    "stale": 22,
    "abandoned": 0,
    "unknown": 50,
    "": 50,
}

_GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (90, "A"),
    (75, "B"),
    (60, "C"),
    (40, "D"),
]


def _grade(score: int) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


def _security_score(security: dict | None) -> int:
    """100 = no issues; subtract for critical and non-critical findings."""
    if not security or not security.get("total"):
        return 100
    critical = security.get("critical", 0)
    total = security.get("total", 0)
    non_critical = total - critical
    s = 100 - critical * 25 - non_critical * 8
    return max(0, s)


def _coverage_score(test_coverage: dict | None) -> int:
    if not test_coverage:
        return 50  # unknown: neutral
    pct = test_coverage.get("coverage_percent", 0)
    # Reward coverage non-linearly: 0%→0, 50%→55, 80%→80, 100%→100
    if pct >= 80:
        return pct
    if pct >= 50:
        # scale 50-80 → 55-80
        return int(55 + (pct - 50) * (80 - 55) / (80 - 50))
    if pct > 0:
        # scale 1-49 → 5-54
        return max(5, int(pct * 54 / 49))
    return 0


def _activity_score(activity: dict | None) -> int:
    if not activity or not activity.get("available", True):
        # uploaded project without git — neutral
        return 50
    label = activity.get("label", "unknown")
    return _ACTIVITY_LABEL_SCORE.get(label, 50)


def _complexity_score(complexity_files: list[dict] | None, total_files: int) -> int:
    """Higher complexity → lower score.

    Complexity files are already the most complex ones in the project.
    We penalise for having highly complex files relative to project size.
    """
    if not complexity_files or total_files == 0:
        return 100
    # Complexity threshold: cyclomatic complexity > 20 is considered "high"
    HIGH_THRESHOLD = 20
    VERY_HIGH_THRESHOLD = 50
    high_count = sum(1 for f in complexity_files if f.get("complexity", 0) > HIGH_THRESHOLD)
    very_high_count = sum(
        1 for f in complexity_files if f.get("complexity", 0) > VERY_HIGH_THRESHOLD
    )
    # Fraction of project that is "high complexity"
    high_frac = high_count / max(total_files, 1)
    very_high_frac = very_high_count / max(total_files, 1)
    s = 100 - int(high_frac * 60) - int(very_high_frac * 20)
    return max(0, s)


def _tech_debt_score(tech_debt_files: list[dict] | None, total_files: int) -> int:
    """Score based on density of TODO/FIXME/HACK markers across the project."""
    if not tech_debt_files or total_files == 0:
        return 100
    total_markers = sum(f.get("count", 0) for f in tech_debt_files)
    markers_per_file = total_markers / max(total_files, 1)
    # 0 markers/file → 100; 1/file → ~80; 3/file → ~55; 10+/file → ~20
    if markers_per_file == 0:
        return 100
    if markers_per_file < 0.5:
        return 90
    if markers_per_file < 1:
        return 80
    if markers_per_file < 2:
        return 68
    if markers_per_file < 5:
        return int(68 - (markers_per_file - 2) * 9)
    return max(15, int(50 - markers_per_file * 3))


def _architecture_score(
    import_cycles: list[dict] | None,
    orphan_modules: list[dict] | None,
    total_files: int,
) -> int:
    """Score based on import cycles and orphan modules."""
    cycles = len(import_cycles) if import_cycles else 0
    orphans = len(orphan_modules) if orphan_modules else 0
    if cycles == 0 and orphans == 0:
        return 100
    orphan_frac = orphans / max(total_files, 1)
    s = 100 - min(cycles * 20, 60) - int(min(orphan_frac * 30, 30))
    return max(0, s)


# ---------------------------------------------------------------------------
# Strengths / weaknesses narrative
# ---------------------------------------------------------------------------


def _build_strengths_weaknesses(
    cat_scores: dict[str, int],
    security: dict | None,
    test_coverage: dict | None,
    complexity_files: list[dict] | None,
    tech_debt_files: list[dict] | None,
    import_cycles: list[dict] | None,
) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    weaknesses: list[str] = []

    # Security
    if cat_scores["security"] == 100:
        strengths.append("未发现硬编码密钥或高危调用，安全基线良好。")
    elif cat_scores["security"] < 60:
        crit = (security or {}).get("critical", 0)
        weaknesses.append(f"发现 {crit} 处高危安全问题（硬编码密钥或危险调用），应优先处理。")
    elif cat_scores["security"] < 80:
        weaknesses.append("存在轻度安全隐患，建议排查 security 报告中的 findings。")

    # Test coverage
    pct = (test_coverage or {}).get("coverage_percent", -1)
    if pct >= 75:
        strengths.append(f"测试覆盖率 {pct}%，源文件覆盖充分。")
    elif pct >= 0:
        weaknesses.append(f"测试覆盖率仅 {pct}%，核心文件建议补充单元测试。")
    else:
        weaknesses.append("缺少测试文件，无法评估测试覆盖率。")

    # Activity
    if cat_scores["activity"] >= 90:
        strengths.append("项目处于活跃维护期，近期提交频繁。")
    elif cat_scores["activity"] == 0:
        weaknesses.append("项目超过一年无新提交，疑似停摆，使用前请评估维护风险。")
    elif cat_scores["activity"] < 50:
        weaknesses.append("项目活跃度较低，近 3 个月内提交稀少。")

    # Complexity
    if cat_scores["complexity"] >= 90:
        strengths.append("代码复杂度在可控范围内，没有明显的「上帝函数」。")
    elif cat_scores["complexity"] < 60:
        high = [f for f in (complexity_files or []) if f.get("complexity", 0) > 20]
        weaknesses.append(f"{len(high)} 个文件复杂度偏高（圈复杂度 >20），阅读和维护成本大。")

    # Tech debt
    if cat_scores["tech_debt"] >= 90:
        strengths.append("技术债标记（TODO/FIXME/HACK）极少，代码整洁。")
    elif cat_scores["tech_debt"] < 55:
        total_m = sum(f.get("count", 0) for f in (tech_debt_files or []))
        weaknesses.append(f"技术债标记共 {total_m} 处，建议择期清理。")

    # Architecture
    if cat_scores["architecture"] >= 90:
        strengths.append("无循环依赖，模块边界清晰。")
    elif import_cycles:
        weaknesses.append(f"存在 {len(import_cycles)} 个循环依赖组，可能导致难以理解的耦合。")

    return strengths, weaknesses


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_WEIGHTS: dict[str, float] = {
    "security": 0.25,
    "test_coverage": 0.20,
    "activity": 0.20,
    "complexity": 0.15,
    "tech_debt": 0.10,
    "architecture": 0.10,
}


def compute_health_score(
    *,
    security: dict | None = None,
    test_coverage: dict | None = None,
    activity: dict | None = None,
    complexity_files: list[dict] | None = None,
    tech_debt_files: list[dict] | None = None,
    import_cycles: list[dict] | None = None,
    orphan_modules: list[dict] | None = None,
    total_files: int = 0,
) -> dict:
    """Compute an aggregate health score from existing analysis results.

    All arguments are optional and keyword-only; callers pass whichever
    analyses are available — missing dimensions default to a neutral 50.

    Returns::

        {
          "score": int,             # 0-100
          "grade": str,             # "A" | "B" | "C" | "D" | "F"
          "category_scores": {
            "security": int,
            "test_coverage": int,
            "activity": int,
            "complexity": int,
            "tech_debt": int,
            "architecture": int,
          },
          "weights": {str: float},  # applied weights for transparency
          "strengths": [str, ...],  # things going well
          "weaknesses": [str, ...], # things to address
          "notes": [str, ...],
        }
    """
    cat = {
        "security": _security_score(security),
        "test_coverage": _coverage_score(test_coverage),
        "activity": _activity_score(activity),
        "complexity": _complexity_score(complexity_files, total_files),
        "tech_debt": _tech_debt_score(tech_debt_files, total_files),
        "architecture": _architecture_score(import_cycles, orphan_modules, total_files),
    }

    weighted = sum(cat[k] * _WEIGHTS[k] for k in _WEIGHTS)
    score = max(0, min(100, round(weighted)))
    grade = _grade(score)

    strengths, weaknesses = _build_strengths_weaknesses(
        cat,
        security=security,
        test_coverage=test_coverage,
        complexity_files=complexity_files,
        tech_debt_files=tech_debt_files,
        import_cycles=import_cycles,
    )

    notes: list[str] = []
    if total_files == 0:
        notes.append("未扫描到代码文件，部分维度评分使用默认值。")
    if not import_cycles and not orphan_modules:
        notes.append("架构维度基于 import 图分析；上传项目（无 .git）同样支持。")

    return {
        "score": score,
        "grade": grade,
        "category_scores": cat,
        "weights": _WEIGHTS,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "notes": notes,
    }


def render_health_score_markdown(project_name: str, data: dict | None) -> str:
    """Render the health score as a Markdown section."""
    if not data:
        return ""
    score = data.get("score", 0)
    grade = data.get("grade", "?")
    cat = data.get("category_scores", {})

    _GRADE_EMOJI = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "🔴"}
    emoji = _GRADE_EMOJI.get(grade, "⚪")

    lines = [
        f"# 健康评分（{project_name}）",
        "",
        f"> **{score} / 100** — 等级 **{grade}** {emoji}",
        "",
        "## 各维度得分",
        "",
        "| 维度 | 得分 | 权重 |",
        "|------|------|------|",
    ]
    _DIM_LABELS = {
        "security": "安全性",
        "test_coverage": "测试覆盖",
        "activity": "活跃度",
        "complexity": "代码复杂度",
        "tech_debt": "技术债",
        "architecture": "架构健康",
    }
    weights = data.get("weights", _WEIGHTS)
    for key, label in _DIM_LABELS.items():
        s = cat.get(key, 50)
        w = int(weights.get(key, 0) * 100)
        lines.append(f"| {label} | {s} | {w}% |")

    strengths = data.get("strengths", [])
    if strengths:
        lines += ["", "## 做得好的地方", ""]
        for s in strengths:
            lines.append(f"- {s}")

    weaknesses = data.get("weaknesses", [])
    if weaknesses:
        lines += ["", "## 建议改进", ""]
        for w in weaknesses:
            lines.append(f"- {w}")

    notes = data.get("notes", [])
    if notes:
        lines += ["", "## 注意事项", ""]
        for n in notes:
            lines.append(f"- {n}")

    return "\n".join(lines).rstrip() + "\n"
