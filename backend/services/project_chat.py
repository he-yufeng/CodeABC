"""Deterministic evidence selection for whole-project conversations."""

from __future__ import annotations

import json
import re

from backend.prompts.qa import build_project_chat_prompt
from backend.services import scanner

MAX_SOURCE_FILES = 6
MAX_CONTEXT_CHARS = 20000
_MAX_MAP_CHARS = 4000
_MAX_EXCERPT_CHARS = 3500
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]{2,}")
_STOP_WORDS = {
    "about",
    "code",
    "does",
    "file",
    "function",
    "how",
    "project",
    "src",
    "the",
    "this",
    "what",
    "where",
    "with",
    "work",
}
_TOPICS = (
    (
        ("启动", "运行", "安装", "launch", "start", "run", "install"),
        ("entry_points", "run_requirements"),
    ),
    (("测试", "test", "ci", "覆盖"), ("ci_checks",)),
    (
        ("配置", "环境变量", "config", "env", "setting"),
        ("env_vars", "config_files", "tunable_settings"),
    ),
    (("发布", "版本", "release", "version"), ("release",)),
    (("定时", "调度", "cron", "schedule"), ("scheduled_tasks",)),
    (("依赖", "dependency", "dependencies", "integration"), ("dependencies", "integrations")),
    (("安全", "security", "漏洞"), ("security",)),
    (("api", "接口", "路由", "endpoint"), ("api_map",)),
    (("数据模型", "字段", "model", "schema"), ("data_models",)),
    (("文档", "贡献", "docs", "contributing"), ("doc_coverage", "contribution")),
)


def _plain(value):
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump())
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _map_items(project: dict, key: str) -> list:
    value = _plain(project.get(key))
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for nested in (
            "entry_points",
            "requirements",
            "commands",
            "tasks",
            "checks",
            "findings",
            "services",
            "automation",
            "routes",
            "files",
            "items",
            "vars",
            "settings",
            "models",
        ):
            if isinstance(value.get(nested), list):
                return value[nested]
        return [value] if value else []
    return []


def _topic_keys(question: str) -> list[str]:
    lowered = question.casefold()
    keys = []
    for needles, map_keys in _TOPICS:
        if any(needle in lowered for needle in needles):
            keys.extend(map_keys)
    return list(dict.fromkeys(keys))


def _terms(question: str) -> list[str]:
    return [
        token
        for token in dict.fromkeys(_WORD_RE.findall(question.casefold()))
        if token not in _STOP_WORDS
    ]


def _direct_paths(project: dict, question: str) -> set[str]:
    lowered = question.casefold()
    direct = set()
    for path in project.get("file_contents", {}):
        folded = path.casefold()
        if folded in lowered or folded.rsplit("/", 1)[-1] in lowered:
            direct.add(path)
    return direct


def _map_summary(project: dict, topic_keys: list[str]) -> tuple[str, list[str], list[str], bool]:
    sections = []
    maps_used = []
    topic_paths = []
    truncated = False
    used_chars = 0
    for key in topic_keys:
        items = _map_items(project, key)
        if not items:
            continue
        rendered = json.dumps(items[:4], ensure_ascii=False)
        if len(items) > 4:
            truncated = True
        section = f"图谱 {key}：\n{rendered}"
        if len(section) > 1200:
            section = section[:1200] + "\n…（图谱已截断）"
            truncated = True
        additional_chars = len(section) + (2 if sections else 0)
        if used_chars + additional_chars > _MAX_MAP_CHARS:
            truncated = True
            break
        sections.append(section)
        maps_used.append(key)
        topic_paths.extend(
            item["path"]
            for item in items
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        )
        used_chars += additional_chars
    text = "\n\n".join(sections)
    if truncated:
        text += "\n…（图谱内容有截断或部分图谱未纳入）"
    return text, maps_used, topic_paths, truncated


def _candidate_scores(
    project: dict, question: str, topic_paths: list[str]
) -> dict[str, tuple[int, str]]:
    terms = _terms(question)
    direct = _direct_paths(project, question)
    candidates: dict[str, tuple[int, str]] = {}
    for path, content in project.get("file_contents", {}).items():
        if direct and path not in direct:
            continue
        folded_path = path.casefold()
        folded_content = content.casefold()
        score = 0
        reason = "question terms"
        if path in direct:
            score += 100
            reason = "named in the question"
        if path in topic_paths:
            score += 30
            reason = "selected project map"
        path_hits = sum(term in folded_path for term in terms)
        content_hits = sum(term in folded_content for term in terms)
        score += path_hits * 12 + content_hits * 6
        if score:
            candidates[path] = (score, reason)
    if candidates:
        return candidates

    # A vague project-level question still gets a small, honest reading route
    # rather than every file or an unsupported claim that the model read it all.
    for step in scanner.build_reading_map(project.get("files", []))[:3]:
        path = step["path"]
        if path in project.get("file_contents", {}):
            candidates[path] = (1, "deterministic reading route")
    return candidates


def _excerpt(content: str, terms: list[str]) -> tuple[str, int, int, bool]:
    lines = content.splitlines()
    if not lines:
        return "", 1, 1, False
    lowered_terms = sorted(terms, key=len, reverse=True)
    match_index = 0
    if lowered_terms:
        for index, line in enumerate(lines):
            folded = line.casefold()
            if any(term in folded for term in lowered_terms):
                match_index = index
                break
    start = max(0, match_index - 15)
    end = min(len(lines), match_index + 36)
    excerpt = "\n".join(lines[start:end])
    truncated = start > 0 or end < len(lines)
    if len(excerpt) > _MAX_EXCERPT_CHARS:
        excerpt = excerpt[:_MAX_EXCERPT_CHARS]
        truncated = True
    return excerpt, start + 1, end, truncated


def build_project_chat_context(
    project: dict,
    question: str,
    *,
    history: list[dict] | tuple[dict, ...] = (),
) -> dict:
    """Select a bounded evidence pack and build the corresponding prompt."""
    question = question.strip()
    topic_keys = _topic_keys(question)
    map_text, maps_used, topic_paths, truncated = _map_summary(project, topic_keys)
    candidates = _candidate_scores(project, question, topic_paths)
    ranked = sorted(candidates.items(), key=lambda item: (-item[1][0], item[0]))
    if len(ranked) > MAX_SOURCE_FILES:
        truncated = True

    context_parts = [
        f"项目名称：{project.get('name', '未命名项目')}\n文件总数：{len(project.get('files', []))}"
    ]
    if map_text:
        context_parts.append(map_text)

    sources = []
    for path, (_, reason) in ranked[:MAX_SOURCE_FILES]:
        content = project.get("file_contents", {}).get(path)
        if content is None:
            continue
        excerpt, line_start, line_end, source_truncated = _excerpt(content, _terms(question))
        header = f"文件 {path}（第 {line_start}-{line_end} 行）：\n"
        remaining = MAX_CONTEXT_CHARS - len("\n\n".join(context_parts)) - 2 - len(header)
        if remaining <= 100:
            truncated = True
            break
        if len(excerpt) > remaining:
            excerpt = excerpt[:remaining]
            source_truncated = True
        line_end = line_start + excerpt.count("\n")
        sources.append(
            {
                "path": path,
                "reason": reason,
                "line_start": line_start,
                "line_end": line_end,
                "truncated": source_truncated,
            }
        )
        truncated = truncated or source_truncated
        context_parts.append(header + excerpt)

    if not sources:
        context_parts.append("当前项目没有可用源码或没有匹配到可展示片段；不要据此猜测具体实现。")
    context_text = "\n\n".join(context_parts)
    return {
        "prompt": build_project_chat_prompt(question, context_text, history=history),
        "sources": sources,
        "maps_used": maps_used,
        "truncated": truncated,
        "context_chars": len(context_text),
    }
