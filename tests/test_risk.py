"""Tests for risk-hotspot fusion (static centrality x change frequency)."""

from __future__ import annotations

from backend.services import risk


def _imp(*pairs):
    return [{"path": p, "fan_in": f} for p, f in pairs]


def _churn(*pairs):
    return [{"path": p, "commits": c} for p, c in pairs]


def test_only_intersection_is_risky():
    # core.py is both central and churny; util.py only central; new.py only churny
    imp = _imp(("core.py", 8), ("util.py", 5))
    chn = _churn(("core.py", 12), ("new.py", 9))
    result = risk.rank_risk(imp, chn)
    assert [r["path"] for r in result] == ["core.py"]
    assert result[0]["fan_in"] == 8
    assert result[0]["commits"] == 12


def test_ranked_by_both_axes():
    # a.py: high on both -> top. b.py: high fan-in, low churn. c.py: opposite.
    imp = _imp(("a.py", 10), ("b.py", 10), ("c.py", 1))
    chn = _churn(("a.py", 10), ("b.py", 1), ("c.py", 10))
    result = risk.rank_risk(imp, chn)
    assert result[0]["path"] == "a.py"
    assert result[0]["score"] == 100  # max on both axes
    # b.py and c.py both score low (10/100) since each is weak on one axis
    scores = {r["path"]: r["score"] for r in result}
    assert scores["a.py"] > scores["b.py"]
    assert scores["a.py"] > scores["c.py"]


def test_empty_inputs():
    assert risk.rank_risk([], []) == []
    assert risk.rank_risk(_imp(("x.py", 3)), []) == []
    assert risk.rank_risk([], _churn(("x.py", 3))) == []


def test_no_overlap_returns_empty():
    assert risk.rank_risk(_imp(("a.py", 5)), _churn(("b.py", 5))) == []


def test_limit_and_reason():
    imp = _imp(*[(f"f{i}.py", i + 1) for i in range(12)])
    chn = _churn(*[(f"f{i}.py", i + 1) for i in range(12)])
    result = risk.rank_risk(imp, chn, limit=5)
    assert len(result) == 5
    assert all(r["reason"] for r in result)
    # highest fan_in+commits file ranks first
    assert result[0]["path"] == "f11.py"
