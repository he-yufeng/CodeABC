"""Compare two uploaded source snapshots without executing either one."""

from __future__ import annotations

import difflib
import hashlib
from collections import defaultdict, deque
from itertools import islice
from pathlib import PurePosixPath

from backend.services import scanner, security

_MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
_MAX_DIFF_LINES = 80
_MAX_DIFF_CHARS = 8000
_MAX_SOURCE_LINES_FOR_DIFF = 2000
_MAX_FINDINGS = 5000
_MAX_DISPLAY_FINDINGS = 200


def _snapshot(files: list[dict]) -> tuple[dict[str, str], set[str]]:
    contents: dict[str, str] = {}
    total_bytes = 0
    for item in files:
        path = str(PurePosixPath(item["path"].replace("\\", "/")))
        if path in contents:
            raise ValueError(f"Duplicate file path: {path}")
        content = item["content"]
        total_bytes += len(content.encode("utf-8"))
        if total_bytes > _MAX_SNAPSHOT_BYTES:
            raise ValueError("Each snapshot must contain at most 5 MiB of text")
        contents[path] = content
    scanned = scanner.scan_uploaded_files(
        [{"path": p, "content": c} for p, c in contents.items() if "\0" not in c]
    )
    allowed = {item["path"] for item in scanned}
    return {p: c for p, c in contents.items() if p in allowed}, contents.keys() - allowed


def _preview(path: str, before: str, after: str) -> tuple[str, bool]:
    old_lines, new_lines = before.splitlines(), after.splitlines()
    if max(len(old_lines), len(new_lines)) > _MAX_SOURCE_LINES_FOR_DIFF:
        return "", True
    lines = list(
        islice(
            difflib.unified_diff(
                old_lines, new_lines, fromfile=f"before/{path}", tofile=f"after/{path}", lineterm=""
            ),
            _MAX_DIFF_LINES + 1,
        )
    )
    text = "\n".join(lines[:_MAX_DIFF_LINES])
    return text[:_MAX_DIFF_CHARS], len(lines) > _MAX_DIFF_LINES or len(text) > _MAX_DIFF_CHARS


def _security_changes(before: dict[str, str], after: dict[str, str]) -> dict:
    old = security.scan_security(before, limit=_MAX_FINDINGS)
    new = security.scan_security(after, limit=_MAX_FINDINGS)
    complete = old["total"] <= _MAX_FINDINGS and new["total"] <= _MAX_FINDINGS
    result = {
        "complete": complete,
        "before_total": old["total"],
        "after_total": new["total"],
        "introduced": None,
        "no_longer_detected": None,
        "persistent": None,
        "changes": [],
        "display_truncated": False,
    }
    if not complete:
        return result

    # A line insertion must not turn the same warning into a resolved/new pair.
    previous: dict[tuple, deque] = defaultdict(deque)
    for finding in old["findings"]:
        key = (finding["file"], finding["category"], finding["snippet"])
        previous[key].append(finding)
    changes = []
    for finding in new["findings"]:
        key = (finding["file"], finding["category"], finding["snippet"])
        match = previous[key].popleft() if previous[key] else None
        changes.append(
            {
                "status": "persistent" if match else "introduced",
                "before": match,
                "after": finding,
            }
        )
    for remaining in previous.values():
        for finding in remaining:
            changes.append({"status": "no_longer_detected", "before": finding, "after": None})
    order = {"introduced": 0, "no_longer_detected": 1, "persistent": 2}
    changes.sort(
        key=lambda change: (
            order[change["status"]],
            (change["after"] or change["before"])["file"],
            (change["after"] or change["before"])["line"],
        )
    )
    for status in order:
        result[status] = sum(change["status"] == status for change in changes)
    result["changes"] = changes[:_MAX_DISPLAY_FINDINGS]
    result["display_truncated"] = len(changes) > _MAX_DISPLAY_FINDINGS
    return result


def compare_projects(
    before_files: list[dict],
    after_files: list[dict],
    *,
    before_name: str = "before",
    after_name: str = "after",
) -> dict:
    before, before_excluded = _snapshot(before_files)
    after, after_excluded = _snapshot(after_files)
    excluded = before_excluded | after_excluded
    # An unreadable/filtered new version is unknown, not a deleted source file.
    before = {p: c for p, c in before.items() if p not in excluded}
    after = {p: c for p, c in after.items() if p not in excluded}
    summary = {
        "added": 0,
        "deleted": 0,
        "modified": 0,
        "unchanged": 0,
        "not_compared": len(excluded),
    }
    changes = []
    for path in sorted(before.keys() | after.keys()):
        old, new = before.get(path), after.get(path)
        if old == new:
            summary["unchanged"] += 1
            continue
        status = "added" if old is None else "deleted" if new is None else "modified"
        summary[status] += 1
        preview, truncated = _preview(path, old or "", new or "")
        changes.append(
            {
                "path": path,
                "status": status,
                "before_bytes": len(old.encode("utf-8")) if old is not None else 0,
                "after_bytes": len(new.encode("utf-8")) if new is not None else 0,
                "before_hash": hashlib.sha256(old.encode("utf-8")).hexdigest()
                if old is not None
                else None,
                "after_hash": hashlib.sha256(new.encode("utf-8")).hexdigest()
                if new is not None
                else None,
                "diff": preview,
                "diff_truncated": truncated,
            }
        )
    return {
        "schema_version": 1,
        "before_name": before_name,
        "after_name": after_name,
        "before_files": len(before),
        "after_files": len(after),
        "summary": summary,
        "files": changes,
        "excluded_paths": sorted(excluded),
        "security": _security_changes(before, after),
        "notes": [
            "Only the supplied readable text is compared; filtered files are unknown, not deleted.",
            "Files are matched by relative path. A rename appears as a deletion and an addition.",
            "Risk warnings are static pattern matches, not confirmed vulnerabilities or fixes.",
            "No source code is executed and no language model is called.",
        ],
    }
