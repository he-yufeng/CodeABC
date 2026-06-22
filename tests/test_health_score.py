"""Tests for backend.services.health_score — aggregate project health score."""

from __future__ import annotations

from backend.services.health_score import compute_health_score, render_health_score_markdown

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _security(critical: int = 0, total: int = 0) -> dict:
    return {"critical": critical, "total": total, "findings": []}


def _coverage(pct: int) -> dict:
    return {"coverage_percent": pct, "total_source_files": 10, "tested_files": pct // 10}


def _activity(label: str) -> dict:
    return {"available": True, "label": label, "total_commits": 50}


def _complexity(complexities: list[int]) -> list[dict]:
    return [
        {"path": f"f{i}.py", "complexity": c, "functions": 5} for i, c in enumerate(complexities)
    ]


def _tech_debt(counts: list[int]) -> list[dict]:
    return [{"path": f"f{i}.py", "count": c} for i, c in enumerate(counts)]


def _cycles(n: int) -> list[dict]:
    return [{"files": [f"a{i}.py", f"b{i}.py"], "size": 2, "reason": ""} for i in range(n)]


# ---------------------------------------------------------------------------
# Smoke test: defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_empty_input_returns_dict(self):
        r = compute_health_score()
        assert isinstance(r, dict)

    def test_empty_input_has_score(self):
        r = compute_health_score()
        assert 0 <= r["score"] <= 100

    def test_empty_input_has_grade(self):
        r = compute_health_score()
        assert r["grade"] in ("A", "B", "C", "D", "F")

    def test_empty_input_has_category_scores(self):
        r = compute_health_score()
        expected_keys = (
            "security",
            "test_coverage",
            "activity",
            "complexity",
            "tech_debt",
            "architecture",
        )
        for key in expected_keys:
            assert key in r["category_scores"]

    def test_empty_input_has_weights(self):
        r = compute_health_score()
        assert abs(sum(r["weights"].values()) - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Security dimension
# ---------------------------------------------------------------------------


class TestSecurityScore:
    def test_no_findings_perfect(self):
        r = compute_health_score(security=_security(0, 0))
        assert r["category_scores"]["security"] == 100

    def test_one_critical_penalises(self):
        r = compute_health_score(security=_security(1, 1))
        assert r["category_scores"]["security"] == 75

    def test_four_critical_floors_at_zero(self):
        r = compute_health_score(security=_security(4, 4))
        assert r["category_scores"]["security"] == 0

    def test_non_critical_lighter_penalty(self):
        r_noncrit = compute_health_score(security=_security(0, 3))
        r_crit = compute_health_score(security=_security(3, 3))
        assert r_noncrit["category_scores"]["security"] > r_crit["category_scores"]["security"]

    def test_none_security_defaults_100(self):
        r = compute_health_score(security=None)
        assert r["category_scores"]["security"] == 100


# ---------------------------------------------------------------------------
# Test coverage dimension
# ---------------------------------------------------------------------------


class TestCoverageScore:
    def test_zero_coverage_scores_zero(self):
        r = compute_health_score(test_coverage=_coverage(0))
        assert r["category_scores"]["test_coverage"] == 0

    def test_full_coverage_scores_100(self):
        r = compute_health_score(test_coverage=_coverage(100))
        assert r["category_scores"]["test_coverage"] == 100

    def test_high_coverage_good_score(self):
        r = compute_health_score(test_coverage=_coverage(80))
        assert r["category_scores"]["test_coverage"] >= 80

    def test_none_coverage_neutral(self):
        r = compute_health_score(test_coverage=None)
        assert r["category_scores"]["test_coverage"] == 50

    def test_coverage_monotone(self):
        scores = [
            compute_health_score(test_coverage=_coverage(p))["category_scores"]["test_coverage"]
            for p in (0, 30, 60, 80, 100)
        ]
        assert scores == sorted(scores)


# ---------------------------------------------------------------------------
# Activity dimension
# ---------------------------------------------------------------------------


class TestActivityScore:
    def test_active_label_100(self):
        r = compute_health_score(activity=_activity("active"))
        assert r["category_scores"]["activity"] == 100

    def test_abandoned_label_0(self):
        r = compute_health_score(activity=_activity("abandoned"))
        assert r["category_scores"]["activity"] == 0

    def test_labels_ordered(self):
        labels = ["active", "slowing", "quiet", "stale", "abandoned"]
        scores = [
            compute_health_score(activity=_activity(lbl))["category_scores"]["activity"]
            for lbl in labels
        ]
        assert scores == sorted(scores, reverse=True)

    def test_unavailable_neutral(self):
        r = compute_health_score(activity={"available": False})
        assert r["category_scores"]["activity"] == 50

    def test_none_neutral(self):
        r = compute_health_score(activity=None)
        assert r["category_scores"]["activity"] == 50


# ---------------------------------------------------------------------------
# Complexity dimension
# ---------------------------------------------------------------------------


class TestComplexityScore:
    def test_no_complexity_files_perfect(self):
        r = compute_health_score(complexity_files=[], total_files=10)
        assert r["category_scores"]["complexity"] == 100

    def test_none_complexity_perfect(self):
        r = compute_health_score(complexity_files=None, total_files=10)
        assert r["category_scores"]["complexity"] == 100

    def test_many_high_complexity_penalises(self):
        r_clean = compute_health_score(complexity_files=_complexity([5, 5, 5]), total_files=10)
        r_complex = compute_health_score(complexity_files=_complexity([30, 40, 60]), total_files=10)
        assert r_complex["category_scores"]["complexity"] < r_clean["category_scores"]["complexity"]

    def test_complexity_floor_zero(self):
        r = compute_health_score(complexity_files=_complexity([100] * 10), total_files=10)
        assert r["category_scores"]["complexity"] >= 0


# ---------------------------------------------------------------------------
# Tech debt dimension
# ---------------------------------------------------------------------------


class TestTechDebtScore:
    def test_no_debt_perfect(self):
        r = compute_health_score(tech_debt_files=[], total_files=10)
        assert r["category_scores"]["tech_debt"] == 100

    def test_heavy_debt_penalises(self):
        r_clean = compute_health_score(tech_debt_files=_tech_debt([0, 0, 0]), total_files=10)
        r_dirty = compute_health_score(tech_debt_files=_tech_debt([10, 8, 12]), total_files=10)
        assert r_dirty["category_scores"]["tech_debt"] < r_clean["category_scores"]["tech_debt"]

    def test_none_debt_perfect(self):
        r = compute_health_score(tech_debt_files=None, total_files=10)
        assert r["category_scores"]["tech_debt"] == 100


# ---------------------------------------------------------------------------
# Architecture dimension
# ---------------------------------------------------------------------------


class TestArchitectureScore:
    def test_no_cycles_perfect(self):
        r = compute_health_score(import_cycles=[], orphan_modules=[], total_files=10)
        assert r["category_scores"]["architecture"] == 100

    def test_cycles_penalise(self):
        r_clean = compute_health_score(import_cycles=[], total_files=10)
        r_cyclic = compute_health_score(import_cycles=_cycles(3), total_files=10)
        arch = r_cyclic["category_scores"]["architecture"]
        arch_clean = r_clean["category_scores"]["architecture"]
        assert arch < arch_clean

    def test_architecture_floor_zero(self):
        orphans = [{"path": f"x{i}.py"} for i in range(20)]
        r = compute_health_score(import_cycles=_cycles(10), orphan_modules=orphans, total_files=5)
        assert r["category_scores"]["architecture"] >= 0


# ---------------------------------------------------------------------------
# Overall score and grade
# ---------------------------------------------------------------------------


class TestOverallScore:
    def test_perfect_project_grade_a(self):
        r = compute_health_score(
            security=_security(0, 0),
            test_coverage=_coverage(100),
            activity=_activity("active"),
            complexity_files=_complexity([3, 4, 5]),
            tech_debt_files=_tech_debt([0, 0]),
            import_cycles=[],
            orphan_modules=[],
            total_files=10,
        )
        assert r["grade"] == "A"
        assert r["score"] >= 90

    def test_bad_project_grade_d_or_f(self):
        r = compute_health_score(
            security=_security(4, 5),
            test_coverage=_coverage(0),
            activity=_activity("abandoned"),
            complexity_files=_complexity([80, 90, 100]),
            tech_debt_files=_tech_debt([20, 15, 18]),
            import_cycles=_cycles(5),
            total_files=10,
        )
        assert r["grade"] in ("D", "F")
        assert r["score"] <= 50

    def test_score_clamped_0_100(self):
        r = compute_health_score()
        assert 0 <= r["score"] <= 100


# ---------------------------------------------------------------------------
# Strengths and weaknesses narrative
# ---------------------------------------------------------------------------


class TestStrengthsWeaknesses:
    def test_no_security_issues_in_strengths(self):
        r = compute_health_score(security=_security(0, 0))
        assert any("安全" in s for s in r["strengths"])

    def test_critical_security_in_weaknesses(self):
        r = compute_health_score(security=_security(2, 2))
        assert any("安全" in w or "高危" in w for w in r["weaknesses"])

    def test_good_coverage_in_strengths(self):
        r = compute_health_score(test_coverage=_coverage(85))
        assert any("覆盖" in s for s in r["strengths"])

    def test_low_coverage_in_weaknesses(self):
        r = compute_health_score(test_coverage=_coverage(20))
        assert any("覆盖" in w or "测试" in w for w in r["weaknesses"])

    def test_active_in_strengths(self):
        r = compute_health_score(activity=_activity("active"))
        assert any("活跃" in s for s in r["strengths"])

    def test_abandoned_in_weaknesses(self):
        r = compute_health_score(activity=_activity("abandoned"))
        assert any("停摆" in w or "无新提交" in w for w in r["weaknesses"])

    def test_no_cycles_in_strengths(self):
        r = compute_health_score(import_cycles=[], total_files=5)
        assert any("循环" in s or "模块" in s for s in r["strengths"])


# ---------------------------------------------------------------------------
# render_health_score_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_none_returns_empty(self):
        assert render_health_score_markdown("MyProject", None) == ""

    def test_renders_score(self):
        r = compute_health_score(security=_security(0, 0), test_coverage=_coverage(80))
        md = render_health_score_markdown("MyProject", r)
        assert str(r["score"]) in md

    def test_renders_grade(self):
        r = compute_health_score(
            security=_security(0, 0),
            test_coverage=_coverage(100),
            activity=_activity("active"),
        )
        md = render_health_score_markdown("MyProject", r)
        assert r["grade"] in md

    def test_renders_project_name(self):
        r = compute_health_score()
        md = render_health_score_markdown("MyProject", r)
        assert "MyProject" in md

    def test_renders_category_table(self):
        r = compute_health_score()
        md = render_health_score_markdown("MyProject", r)
        assert "安全性" in md
        assert "测试覆盖" in md
        assert "活跃度" in md

    def test_ends_with_newline(self):
        r = compute_health_score()
        md = render_health_score_markdown("Repo", r)
        assert md.endswith("\n")
