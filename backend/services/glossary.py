"""Terminology dictionary: plain-language definitions for jargon in code.

A reader new to a codebase trips over vocabulary as much as logic. This is a
curated dictionary of common programming terms with everyday, jargon-free
explanations (the same voice as the line annotations), plus a scanner that
reports which of those terms actually appear in a given file so the UI can
offer "hover a keyword, see what it means".

Deterministic — no LLM call — so it's instant, free, and unit-testable.
"""

from __future__ import annotations

import re

# term (lowercase canonical) -> plain-language explanation.
# Definitions deliberately avoid jargon and lean on everyday analogies.
GLOSSARY: dict[str, str] = {
    "api": "一套约定好的「对外接口」，别的程序按这套约定就能调用你的功能，像餐厅菜单：照着点就行，不用进厨房。",
    "async": "异步：发起一件耗时的事后不干等着，先去做别的，等它好了再回来处理，像点了外卖继续干活而不是站在门口等。",
    "await": "等一件异步的事真正完成再往下走，相当于「这一步必须拿到结果才能继续」。",
    "cache": "缓存：把算过/取过的结果先存起来，下次直接拿，省得重复跑，像把常用调料放灶台边而不是每次去仓库。",
    "callback": "回调：把一个函数交给别人，让对方在某件事发生时替你调用它，像留个电话「好了打给我」。",
    "closure": "闭包：一个函数把它出生时周围的变量一起「打包带走」，之后还能用到那些变量，像便当带上了家里的菜。",
    "concurrency": "并发：让多件事在时间上交错推进，看起来同时在做，像一个人左右手轮流照看几口锅。",
    "coroutine": "协程：能中途暂停、之后从原地接着跑的函数，配合异步用来高效处理大量等待。",
    "decorator": "装饰器：在不改原函数的前提下给它套一层额外行为，像给手机套个壳，功能多了但手机没变。",
    "dependency": "依赖：这段代码要正常工作所必须用到的别的库或模块，缺了就跑不起来。",
    "deserialize": "反序列化：把存成文本/字节的数据还原成程序里能用的对象，是序列化的逆操作。",
    "endpoint": "端点：服务对外暴露的一个具体网址入口，访问它就能触发某个功能。",
    "enum": "枚举：把一组固定的可选值起好名字管起来，比如「红/黄/绿」，避免到处写魔法数字。",
    "generator": "生成器：需要时才一个一个「现产」数据而不是一次全做好，省内存，像点一份做一份。",
    "hash": "哈希：把任意数据压成一个固定长度的「指纹」，常用来快速比对或定位。",
    "idempotent": "幂等：同样的操作做一次和做多次效果一样，像电梯按钮多按几下也只来一趟。",
    "inheritance": "继承：新类直接沿用并扩展已有类的能力，像孩子继承父母的部分特征再加自己的。",
    "iterator": "迭代器：负责「逐个往下取」集合里元素的东西，for 循环背后就靠它。",
    "lambda": "匿名函数：临时用、不取名字的小函数，写在用它的地方，用完即弃。",
    "lazy": "惰性：能拖到真正需要时再算/再加载，不提前浪费力气。",
    "lock": "锁：同一时刻只让一个人动共享数据，防止大家一起改乱套，像洗手间的门闩。",
    "memoize": "记忆化：把函数对某组输入算出的结果缓存下来，下次同样输入直接返回。",
    "middleware": "中间件：夹在请求和真正处理之间的一层，统一做鉴权、日志等杂活，像进场前的安检。",
    "mutex": "互斥锁：保证同一份资源同一时间只被一个线程使用的开关。",
    "orm": "对象关系映射：让你用操作对象的方式读写数据库，不必手写 SQL，像翻译官帮你和数据库对话。",
    "polymorphism": "多态：同一个调用，不同对象给出各自的实现，像「叫一声」猫和狗反应不同。",
    "promise": "承诺对象：代表一件「将来才会有结果」的事，先拿到凭据，结果到了再兑现。",
    "recursion": "递归：函数自己调用自己来把大问题拆成同样的小问题，像两面镜子互照。",
    "refactor": "重构：在不改变外部行为的前提下整理代码结构，让它更清晰好维护。",
    "regex": "正则表达式：用一串符号描述「什么样的文本算匹配」，用来查找或校验字符串，像高级版的查找替换。",
    "serialize": "序列化：把程序里的对象转成可保存或可传输的文本/字节，方便存盘或发送。",
    "singleton": "单例：整个程序里某个东西只允许存在一个实例，大家共用它。",
    "stub": "桩：测试时用来顶替真实依赖的简化假货，让测试不碰外部系统。",
    "thread": "线程：程序里一条独立执行的「流水线」，多条线程可以并行干活。",
    "throttle": "节流：限制某操作的触发频率，太频繁就先压一压，避免把系统压垮。",
    "token": "令牌：一小段代表身份或权限的凭证，带着它就能证明「我是谁、能干啥」。",
    "tuple": "元组：一串按顺序排好、且不可修改的值，像一张定好的座位表。",
    "yield": "把当前结果先「吐」出去并暂停，等下次再要时从这里继续，是生成器的核心动作。",
    "race condition": "竞态：多个执行流同时改一份数据、谁先谁后没定准，导致结果飘忽的 bug。",
    "dependency injection": "依赖注入：一个组件需要的零件由外部传进来，而不是自己 new，方便替换和测试。",
    "garbage collection": "垃圾回收：运行时自动把不再用到的内存清掉，省得你手动释放。",
}

# Pre-build one matcher per term so we can map matches back to the canonical
# key. Phrases allow flexible whitespace; all matching is whole-word and
# case-insensitive so "in" never lights up inside "string".
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        term,
        re.compile(
            r"\b" + r"\s+".join(re.escape(part) for part in term.split()) + r"\b",
            re.IGNORECASE,
        ),
    )
    for term in GLOSSARY
]


def lookup(term: str) -> str | None:
    """Return the definition for *term* (case-insensitive), or ``None``."""
    return GLOSSARY.get(term.strip().lower())


def scan_terms(text: str) -> list[dict]:
    """Return the glossary terms that appear in *text*, with definitions.

    Each entry is ``{"term", "definition"}``. Results are de-duplicated and
    sorted alphabetically so the panel order is stable.
    """
    if not text:
        return []
    found = [
        {"term": term, "definition": GLOSSARY[term]}
        for term, pattern in _PATTERNS
        if pattern.search(text)
    ]
    found.sort(key=lambda e: e["term"])
    return found
