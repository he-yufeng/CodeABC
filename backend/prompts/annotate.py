"""Prompt for generating line-by-line code annotations."""

from __future__ import annotations


def build_annotation_prompt(code: str, language: str = "python") -> str:
    """Build the LLM prompt for code annotation.

    Args:
        code: full source code of the file
        language: programming language name
    """
    # for very long files, only annotate the first 200 lines
    lines = code.splitlines()
    if len(lines) > 200:
        code = "\n".join(lines[:200])
        truncated_note = f"\n\n（注意：文件共 {len(lines)} 行，这里只展示前 200 行）"
    else:
        truncated_note = ""

    return f"""你是一个耐心的编程导师。下面是一个 {language} 源文件的内容。
请为这段代码生成逐行/逐块的中文批注，帮助完全不懂编程的人理解每一部分在做什么。

要求：
1. 批注粒度要细：每 1-3 行逻辑代码为一个批注单元，不要把很多行合并成一个笼统的解释
2. 用大白话解释，不要使用编程术语（比如不要说"变量""函数"，而是说"名字""小助手"）
3. 如果代码中有数字常量（比如 0.05、100、3600），解释这个数字代表什么意思
4. 适当用日常生活的类比让解释更生动
5. 空行、纯注释行可以跳过不批注
6. 对于 import 语句，简单说明引入了什么工具、这个工具用来做什么

代码内容（{language}）：
```{language}
{code}
```{truncated_note}

严格输出 JSON 数组格式（不要输出其他任何内容）：
[
  {{"line_start": 1, "line_end": 1, "annotation": "这行的中文解释"}},
  {{"line_start": 3, "line_end": 5, "annotation": "这几行的中文解释"}},
  ...
]

注意 line_start 和 line_end 是从 1 开始的行号。确保覆盖文件中所有有意义的代码行。"""
