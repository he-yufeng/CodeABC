"""Language-specific guidance for beginner-friendly code annotations."""

from __future__ import annotations

_GUIDANCE = {
    "javascript": (
        "- 对于 import、export 和 require，说清引入或暴露的是什么工具；"
        "区分默认导入、命名导入和只执行副作用的导入。\n"
        "- 解释 const、let、var 时，重点说名字能否重新赋值以及生效范围，"
        "不要把它们当成类型标注。\n"
        "- 解释 Promise、async/await、.then() 和 .catch() 时，"
        "说清等待的是哪件事、结果交给谁；不要把异步说成自动多线程。\n"
        "- 解释 try/catch/finally 和 Promise 拒绝时，"
        "指出正常路径、失败路径和清理工作；不要假定异步错误会被同步 catch 自动接住。"
    ),
    "typescript": (
        "- 对于 import、export 和 import type，"
        "说清引入的是运行时会用到的工具，还是只帮助检查代码的类型。\n"
        "- 解释 interface、type、泛型、联合类型和类型标注时，"
        "用大白话说它们限制了什么；说明这些检查信息通常会在运行前被擦除。\n"
        "- 解释 Promise<T>、async/await 和类型化返回值时，"
        "同时说清等待哪件事以及最后得到什么形状的结果。\n"
        "- 解释 try/catch/finally、unknown 和 as 时，"
        "区分真实错误处理与静态检查；类型断言本身不会验证运行时数据。"
    ),
    "go": (
        "- 对于 import，说清引入了哪个包以及包里哪个工具会被使用；"
        "遇到分组导入或空白标识符导入时解释它们的特别作用。\n"
        "- 解释 var、:=、const、struct、slice 和 map 时，"
        "说清数据是什么形状、名字如何绑定，以及值能否继续修改。\n"
        "- 解释 goroutine、channel 和 sync.WaitGroup 时，"
        "说清谁和谁同时做事、如何传话和等待；Go 没有 async/await，也不要把并发保证说成并行。\n"
        "- 解释多返回值、if err != nil 和 defer 时，"
        "指出结果与错误如何分开交接以及清理何时发生；panic/recover 不能当成普通 err 处理。"
    ),
}

_ALIASES = {
    "js": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "golang": "go",
}


def get_annotation_language_guidance(language: str) -> str:
    """Return prompt guidance for a scanner language, or an empty string."""
    normalized = language.strip().lower()
    profile = _ALIASES.get(normalized, normalized)
    return _GUIDANCE.get(profile, "")
