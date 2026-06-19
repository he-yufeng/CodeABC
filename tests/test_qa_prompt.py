"""Tests for the Q&A prompt builder (pure string construction)."""

from __future__ import annotations

from backend.prompts.qa import build_qa_prompt


def test_includes_question_and_code():
    prompt = build_qa_prompt("这个函数干嘛的？", "def add(a, b):\n    return a + b")
    assert "这个函数干嘛的？" in prompt
    assert "def add(a, b):" in prompt
    assert "编程导师" in prompt  # keeps the tutor voice


def test_grounds_with_file_path_and_language():
    prompt = build_qa_prompt("?", "x = 1", file_path="src/app.py", language="python")
    assert "src/app.py" in prompt
    assert "```python" in prompt


def test_no_code_block_when_code_empty():
    prompt = build_qa_prompt("整个项目是做什么的？", "")
    assert "```" not in prompt
    assert "整个项目是做什么的？" in prompt


def test_long_code_is_truncated():
    big = "\n".join(f"line {i}" for i in range(5000))
    prompt = build_qa_prompt("解释一下", big)
    assert "已截断" in prompt
    assert len(prompt) < len(big) + 2000  # not the whole blob


def test_question_and_code_are_stripped():
    prompt = build_qa_prompt("  有空格的问题  ", "  code  ")
    assert "有空格的问题" in prompt
    # the answer-format guidance is always appended
    assert "直接输出答案正文" in prompt
