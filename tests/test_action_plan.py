"""Tests for backend.services.action_plan — ranked remediation list."""

from __future__ import annotations

from backend.services.action_plan import build_action_plan, render_action_plan_markdown

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _security(findings: list[dict]) -> dict:
    crit = sum(1 for f in findings if f["category"] in ("hardcoded_secret", "dangerous_call"))
    return {"total": len(findings), "critical": crit, "findings": findings}


def _finding(file: str, category: str, reason: str = "reason") -> dict:
    return {"file": file, "line": 1, "category": category, "snippet": "x", "reason": reason}


def _coverage(untested: list[dict]) -> dict:
    return {"coverage_percent": 40, "untested_core": untested}


def _untested(path: str, fan_in: int) -> dict:
    return {"path": path, "language": "python", "fan_in": fan_in, "reason": f"fan-in {fan_in}"}


def _complexity(path: str, cx: int) -> dict:
    return {"path": path, "complexity": cx, "functions": 3, "reason": ""}


# ---------------------------------------------------------------------------
# Empty / defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_empty_returns_dict(self):
        r = build_action_plan()
        assert isinstance(r, dict)
        assert r["total"] == 0
        assert r["items"] == []

    def test_empty_has_clean_note(self):
        r = build_action_plan()
        assert any("基线良好" in n for n in r["notes"])

    def test_none_inputs_safe(self):
        r = build_action_plan(
            security=None,
            test_coverage=None,
            complexity_files=None,
            tech_debt_files=None,
            import_cycles=None,
        )
        assert r["total"] == 0


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_critical_finding_is_high_priority(self):
        r = build_action_plan(security=_security([_finding("a.py", "hardcoded_secret")]))
        assert r["items"][0]["priority"] == "high"
        assert r["items"][0]["category"] == "security"

    def test_non_critical_finding_is_medium(self):
        r = build_action_plan(security=_security([_finding("a.py", "debug_mode")]))
        assert r["items"][0]["priority"] == "medium"

    def test_critical_sorts_before_non_critical(self):
        findings = [_finding("a.py", "debug_mode"), _finding("b.py", "dangerous_call")]
        r = build_action_plan(security=_security(findings))
        # dangerous_call (critical) should be first
        assert r["items"][0]["target"] == "b.py"

    def test_security_capped_per_category(self):
        findings = [_finding(f"f{i}.py", "hardcoded_secret") for i in range(10)]
        r = build_action_plan(security=_security(findings))
        sec = [i for i in r["items"] if i["category"] == "security"]
        assert len(sec) <= 4

    def test_target_carries_file(self):
        r = build_action_plan(security=_security([_finding("svc/db.py", "hardcoded_secret")]))
        assert r["items"][0]["target"] == "svc/db.py"


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_high_fan_in_untested_is_high(self):
        r = build_action_plan(test_coverage=_coverage([_untested("core.py", 8)]))
        item = next(i for i in r["items"] if i["category"] == "test_coverage")
        assert item["priority"] == "high"

    def test_low_fan_in_untested_is_medium(self):
        r = build_action_plan(test_coverage=_coverage([_untested("leaf.py", 1)]))
        item = next(i for i in r["items"] if i["category"] == "test_coverage")
        assert item["priority"] == "medium"

    def test_empty_untested_no_items(self):
        r = build_action_plan(test_coverage=_coverage([]))
        assert r["total"] == 0


# ---------------------------------------------------------------------------
# Complexity
# ---------------------------------------------------------------------------


class TestComplexity:
    def test_only_high_complexity_flagged(self):
        r = build_action_plan(
            complexity_files=[_complexity("ok.py", 10), _complexity("bad.py", 35)]
        )
        cx = [i for i in r["items"] if i["category"] == "complexity"]
        assert len(cx) == 1
        assert cx[0]["target"] == "bad.py"

    def test_very_high_complexity_is_medium(self):
        r = build_action_plan(complexity_files=[_complexity("bad.py", 60)])
        cx = next(i for i in r["items"] if i["category"] == "complexity")
        assert cx["priority"] == "medium"

    def test_complexity_effort_is_large(self):
        r = build_action_plan(complexity_files=[_complexity("bad.py", 50)])
        cx = next(i for i in r["items"] if i["category"] == "complexity")
        assert cx["effort"] == "large"


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


class TestArchitecture:
    def test_cycle_produces_action(self):
        cycles = [{"files": ["a.py", "b.py"], "size": 2, "reason": ""}]
        r = build_action_plan(import_cycles=cycles)
        arch = next(i for i in r["items"] if i["category"] == "architecture")
        assert arch["priority"] == "medium"
        assert arch["target"] == "a.py"

    def test_cycle_detail_mentions_files(self):
        cycles = [{"files": ["a.py", "b.py", "c.py", "d.py"], "size": 4, "reason": ""}]
        r = build_action_plan(import_cycles=cycles)
        arch = next(i for i in r["items"] if i["category"] == "architecture")
        assert "a.py" in arch["detail"]
        assert "…" in arch["detail"]  # truncated past 3 files


# ---------------------------------------------------------------------------
# Tech debt
# ---------------------------------------------------------------------------


class TestTechDebt:
    def test_only_worst_debt_file_surfaced(self):
        debt = [{"path": "a.py", "count": 10}, {"path": "b.py", "count": 4}]
        r = build_action_plan(tech_debt_files=debt)
        td = [i for i in r["items"] if i["category"] == "tech_debt"]
        assert len(td) == 1
        assert td[0]["target"] == "a.py"

    def test_small_debt_not_surfaced(self):
        debt = [{"path": "a.py", "count": 1}]
        r = build_action_plan(tech_debt_files=debt)
        assert not [i for i in r["items"] if i["category"] == "tech_debt"]


# ---------------------------------------------------------------------------
# Ordering & caps
# ---------------------------------------------------------------------------


class TestOrdering:
    def test_high_before_medium_before_low(self):
        r = build_action_plan(
            security=_security([_finding("a.py", "hardcoded_secret")]),
            test_coverage=_coverage([_untested("leaf.py", 1)]),  # medium
            complexity_files=[_complexity("bad.py", 25)],  # low
        )
        ranks = [i["priority"] for i in r["items"]]
        order = {"high": 0, "medium": 1, "low": 2}
        assert ranks == sorted(ranks, key=lambda p: order[p])

    def test_total_capped(self):
        findings = [_finding(f"f{i}.py", "hardcoded_secret") for i in range(8)]
        untested = [_untested(f"u{i}.py", 8) for i in range(8)]
        r = build_action_plan(security=_security(findings), test_coverage=_coverage(untested))
        assert r["total"] <= 12

    def test_high_priority_gets_actionable_note(self):
        r = build_action_plan(security=_security([_finding("a.py", "hardcoded_secret")]))
        assert any("第一条" in n for n in r["notes"])


# ---------------------------------------------------------------------------
# render_action_plan_markdown
# ---------------------------------------------------------------------------


class TestRender:
    def test_none_returns_empty(self):
        assert render_action_plan_markdown("P", None) == ""

    def test_empty_items_returns_empty(self):
        assert render_action_plan_markdown("P", build_action_plan()) == ""

    def test_renders_project_name(self):
        r = build_action_plan(security=_security([_finding("a.py", "hardcoded_secret")]))
        md = render_action_plan_markdown("MyProj", r)
        assert "MyProj" in md

    def test_renders_table_and_detail(self):
        r = build_action_plan(security=_security([_finding("a.py", "hardcoded_secret")]))
        md = render_action_plan_markdown("MyProj", r)
        assert "优先级" in md
        assert "说明" in md

    def test_ends_with_newline(self):
        r = build_action_plan(test_coverage=_coverage([_untested("core.py", 8)]))
        md = render_action_plan_markdown("Repo", r)
        assert md.endswith("\n")


class TestDeepNestingActions:
    def test_deeply_nested_function_surfaces_flatten_action(self):
        r = build_action_plan(
            deep_nesting_files=[{"path": "srv.py", "function": "handler", "depth": 6}]
        )
        items = [i for i in r["items"] if i["category"] == "deep_nesting"]
        assert len(items) == 1
        assert items[0]["priority"] == "medium"  # depth >= 6
        assert "handler" in items[0]["title"]
        assert items[0]["target"] == "srv.py"

    def test_moderately_nested_is_low_priority(self):
        r = build_action_plan(deep_nesting_files=[{"path": "a.py", "function": "f", "depth": 4}])
        items = [i for i in r["items"] if i["category"] == "deep_nesting"]
        assert items and items[0]["priority"] == "low"

    def test_no_deep_nesting_no_action(self):
        r = build_action_plan(deep_nesting_files=[])
        assert not [i for i in r["items"] if i["category"] == "deep_nesting"]


class TestTypingActions:
    def test_under_annotated_file_surfaces_typing_action(self):
        r = build_action_plan(
            typing_files=[
                {"path": "m.py", "symbols": 10, "typed": 3, "coverage": 0.3, "missing": 7}
            ]
        )
        items = [i for i in r["items"] if i["category"] == "typing"]
        assert len(items) == 1
        assert items[0]["priority"] == "low"
        assert items[0]["target"] == "m.py"
        assert "7" in items[0]["detail"]

    def test_well_typed_file_not_flagged(self):
        # coverage >= 0.6 → not surfaced even with a missing hint or two.
        r = build_action_plan(
            typing_files=[
                {"path": "m.py", "symbols": 10, "typed": 9, "coverage": 0.9, "missing": 1}
            ]
        )
        assert not [i for i in r["items"] if i["category"] == "typing"]

    def test_only_a_couple_missing_not_flagged(self):
        # missing < 3 → below the noise floor, not surfaced.
        r = build_action_plan(
            typing_files=[{"path": "m.py", "symbols": 4, "typed": 2, "coverage": 0.5, "missing": 2}]
        )
        assert not [i for i in r["items"] if i["category"] == "typing"]


# ---------------------------------------------------------------------------
# Readability (long functions / too many parameters)
# ---------------------------------------------------------------------------
class TestReadabilityActions:
    def test_long_function_is_medium_when_very_long(self):
        r = build_action_plan(
            long_functions_files=[{"path": "a.py", "function": "big", "length": 150}]
        )
        item = next(i for i in r["items"] if i["category"] == "long_function")
        assert item["priority"] == "medium"  # >= 120 lines
        assert "big" in item["title"]

    def test_long_function_is_low_when_moderately_long(self):
        r = build_action_plan(
            long_functions_files=[{"path": "a.py", "function": "f", "length": 70}]
        )
        item = next(i for i in r["items"] if i["category"] == "long_function")
        assert item["priority"] == "low"  # < 120 lines

    def test_too_many_params_is_medium_when_very_wide(self):
        r = build_action_plan(
            too_many_params_files=[{"path": "a.py", "function": "wide", "params": 9}]
        )
        item = next(i for i in r["items"] if i["category"] == "too_many_params")
        assert item["priority"] == "medium"  # >= 8 params
        assert "wide" in item["title"]

    def test_too_many_params_is_low_at_threshold(self):
        r = build_action_plan(
            too_many_params_files=[{"path": "a.py", "function": "f", "params": 6}]
        )
        item = next(i for i in r["items"] if i["category"] == "too_many_params")
        assert item["priority"] == "low"  # < 8 params

    def test_empty_readability_inputs_add_no_items(self):
        r = build_action_plan(long_functions_files=[], too_many_params_files=[])
        assert not [i for i in r["items"] if i["category"] in ("long_function", "too_many_params")]
