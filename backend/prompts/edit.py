"""Prompt + helper for natural-language code editing.

CodeABC never writes to the user's files; this produces a *suggested* edited
version of a snippet that the reader can review and copy. The prompt asks the
model to apply a plain-language instruction (e.g. "把茅台换成比亚迪") and
return only the modified code, which `extract_code_block` then unwraps.
"""

from __future__ import annotations

_MAX_CODE_CHARS = 8000


def build_edit_prompt(
    instruction: str,
    code: str,
    *,
    file_path: str = "",
    language: str = "",
) -> str:
    """Build the LLM prompt for applying a natural-language edit to *code*."""
    code = code.strip()
    if len(code) > _MAX_CODE_CHARS:
        code = code[:_MAX_CODE_CHARS] + "\n…（代码较长，已截断）"

    where = f"（来自文件 `{file_path}`）" if file_path else ""
    fence = language or ""

    return f"""你是一个细心的编程助手。下面是一段{language}代码{where}：

```{fence}
{code}
```

用户想这样修改它：
{instruction.strip()}

请按用户的要求修改代码，遵守：
1. 只做用户要求的改动，其余部分**原样保留**，不要顺手重构、改风格或加注释。
2. 保持原有缩进、命名习惯和语言不变。
3. 如果要求不清楚或在这段代码里无法完成，就原样返回代码不要乱改。

只输出修改后的**完整代码**，用一个 ```{fence} 代码块``` 包裹，前后不要写任何解释或多余文字。"""


def extract_code_block(text: str) -> str:
    """Unwrap a fenced code block from LLM output; fall back to stripped text.

    Tolerates an optional language tag after the opening fence and any stray
    prose the model adds outside the fence.
    """
    text = text.strip()
    start = text.find("```")
    if start == -1:
        return text
    # skip the opening fence line (which may carry a language tag)
    newline = text.find("\n", start)
    if newline == -1:
        return text
    end = text.find("```", newline)
    inner = text[newline + 1 : end] if end != -1 else text[newline + 1 :]
    return inner.strip("\n")
