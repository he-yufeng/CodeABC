"""Tests for the natural-language edit prompt and code-fence extractor."""

from __future__ import annotations

from backend.prompts.edit import build_edit_prompt, extract_code_block


def test_prompt_includes_instruction_and_code():
    prompt = build_edit_prompt("把茅台换成比亚迪", "stock = '茅台'", language="python")
    assert "把茅台换成比亚迪" in prompt
    assert "stock = '茅台'" in prompt
    assert "只输出修改后的" in prompt  # asks for code-only output
    assert "```python" in prompt


def test_prompt_preserves_other_code_instruction():
    prompt = build_edit_prompt("x", "y = 1")
    assert "原样保留" in prompt  # only-the-requested-change guard


def test_extract_unwraps_fenced_block():
    raw = "好的，这是修改后的代码：\n```python\nstock = 'BYD'\n```\n希望有帮助"
    assert extract_code_block(raw) == "stock = 'BYD'"


def test_extract_handles_no_language_tag():
    raw = "```\na = 1\nb = 2\n```"
    assert extract_code_block(raw) == "a = 1\nb = 2"


def test_extract_without_fence_returns_stripped_text():
    assert extract_code_block("  just code, no fence  ") == "just code, no fence"


def test_extract_handles_unterminated_fence():
    raw = "```python\nx = 1\ny = 2"
    assert extract_code_block(raw) == "x = 1\ny = 2"
