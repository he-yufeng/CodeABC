"""Risk hotspots: fuse static centrality with change frequency.

The import graph says which files are *central* (lots of things depend on
them); the git-history churn says which files *change a lot*. Neither alone
tells you where defects concentrate — but a file that is BOTH heavily
depended on AND frequently changed is exactly where a regression hurts most
and where review/tests pay off first. This module joins the two existing
analyses (no recomputation) and ranks that intersection.

Pure functions over the outputs of ``importgraph.rank_hotspots`` and
``churn.analyze_churn`` — unit-testable with plain dicts, no repo needed.
"""

from __future__ import annotations


def _risk_reason(fan_in: int, commits: int) -> str:
    if fan_in >= 5 and commits >= 10:
        return (
            f"{fan_in} 个文件依赖它、又改了 {commits} 次——既是核心又高频变动,"
            "是 bug 最容易出的地方,审查和回归测试优先级最高。"
        )
    return f"{fan_in} 个文件依赖它、改了 {commits} 次:核心且在动,改它要格外小心、最好先补测试。"


def rank_risk(
    import_hotspots: list[dict],
    churn_hotspots: list[dict],
    *,
    limit: int = 8,
) -> list[dict]:
    """Rank files that are both depended-on (central) and frequently changed.

    Args:
        import_hotspots: ``importgraph.rank_hotspots`` output — dicts with
            ``path`` and ``fan_in``.
        churn_hotspots: ``churn.analyze_churn`` ``hotspots`` — dicts with
            ``path`` and ``commits``.
        limit: how many to return.

    Returns ``{"path", "fan_in", "commits", "score", "reason"}`` for files
    present in BOTH inputs, sorted by a 0-100 risk score (high fan-in AND high
    churn score highest). Files in only one input are not risk hotspots.
    """
    fan_in = {h["path"]: h.get("fan_in", 0) for h in import_hotspots}
    commits = {h["path"]: h.get("commits", 0) for h in churn_hotspots}

    shared = [p for p in commits if p in fan_in]
    if not shared:
        return []

    max_fan = max((fan_in[p] for p in shared), default=0) or 1
    max_commits = max((commits[p] for p in shared), default=0) or 1

    ranked = []
    for path in shared:
        f, c = fan_in[path], commits[path]
        # normalised product: rewards being high on BOTH axes, not just one
        score = round((f / max_fan) * (c / max_commits) * 100)
        ranked.append(
            {
                "path": path,
                "fan_in": f,
                "commits": c,
                "score": score,
                "reason": _risk_reason(f, c),
            }
        )
    ranked.sort(key=lambda r: (-r["score"], -r["commits"], r["path"]))
    return ranked[:limit]
