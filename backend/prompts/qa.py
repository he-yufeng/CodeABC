"""Prompt for answering a reader's question about a piece of code."""

from __future__ import annotations

_MAX_CODE_CHARS = 8000


def build_qa_prompt(
    question: str,
    code: str,
    *,
    file_path: str = "",
    language: str = "",
) -> str:
    """Build the LLM prompt for Q&A about a code selection.

    Args:
        question: the reader's question, in their own words.
        code: the selected code (or whole file) the question is about.
        file_path: optional path, to ground the answer.
        language: optional language name, for the code fence.
    """
    code = code.strip()
    if len(code) > _MAX_CODE_CHARS:
        code = code[:_MAX_CODE_CHARS] + "\n…（代码较长，已截断）"

    where = f"（来自文件 `{file_path}`）" if file_path else ""
    fence = language or ""
    code_block = f"```{fence}\n{code}\n```\n\n" if code else ""

    return f"""你是一个耐心的编程导师，正在帮一个不太懂编程的人读懂一段代码。

下面是用户选中的代码{where}：

{code_block}用户的问题是：
{question.strip()}

请用中文、大白话回答：
1. 直接回答问题，先给结论再展开，别绕圈子。
2. 尽量少用编程术语；必须用时，顺手用一句日常类比解释清楚。
3. 只依据给出的代码和通用编程常识回答；代码里看不出来的，就如实说"这段代码里看不出来"，不要编造。
4. 如果问题和这段代码无关，礼貌说明并尽量给出有用的方向。
5. 回答简洁，控制在几段以内，必要时可用短列表。

直接输出答案正文，不要重复问题、不要加多余的客套。"""
