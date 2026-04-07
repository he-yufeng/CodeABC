"""Prompt for generating project overview ("项目说明书")."""

from __future__ import annotations


def build_overview_prompt(files: list[dict]) -> str:
    """Build the LLM prompt for project overview generation.

    Args:
        files: list of {"path": str, "size": int, "language": str, "preview": str}
    """
    # build file context
    file_sections = []
    for f in files:
        preview = f.get("preview", "").strip()
        if not preview:
            file_sections.append(f"### {f['path']} ({f['language']}, {f['size']} bytes)\n(empty)")
            continue
        # truncate very long previews
        if len(preview) > 3000:
            preview = preview[:3000] + "\n... (truncated)"
        file_sections.append(
            f"### {f['path']} ({f['language']}, {f['size']} bytes)\n```\n{preview}\n```"
        )

    files_context = "\n\n".join(file_sections)

    return f"""你是一个耐心的编程导师，正在帮一个完全不懂代码的人理解一个项目。
请用中文、大白话来解释，不要使用任何编程专业术语。
如果必须提到技术概念，请用日常生活的类比来解释（比如把函数比作"一个做特定事情的小助手"）。

下面是这个项目的文件列表和部分内容：

{files_context}

请根据以上信息，生成一份"项目说明书"。严格输出以下 JSON 格式（不要输出其他内容）：

{{
  "summary": "一句话说明这个项目做什么（20字以内）",
  "description": "用2-3句大白话详细解释这个项目的用途，让完全不懂代码的人也能理解",
  "files": [
    {{"path": "文件路径", "role": "大白话描述作用", "importance": "high/medium/low"}}
  ],
  "how_to_run": [
    "步骤1：...",
    "步骤2：..."
  ],
  "quick_tips": [
    "如果你只想做XX，去YY文件改ZZ就行"
  ]
}}

注意：
- files 数组要包含所有重要文件，按重要性排序
- importance 为 high 的是核心文件（入口、主要逻辑），medium 是辅助文件，low 是配置/资源
- how_to_run 要写得足够具体，让不懂代码的人也能照着做
- quick_tips 给出1-3个最实用的提示"""
