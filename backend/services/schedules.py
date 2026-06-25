"""Scheduled & automated tasks map — what this project runs on its own.

Entry points answer "how do I *start* this myself" and CLI commands answer
"what verbs can I *type*". This answers a question a non-programmer rarely thinks
to ask but very much wants the answer to: **does this project do anything by
itself — on a timer, on a schedule, automatically?** A repo that quietly emails a
report every morning, retries a queue every 30 seconds, or runs a CI job nightly
behaves very differently from one that only ever acts when you press a button,
and that difference is invisible unless you know the handful of libraries people
use to wire it up.

This collects those automated triggers straight from the source CodeABC already
loaded — no LLM, nothing to install — by recognising the common scheduling
mechanisms across the stacks CodeABC sees most:

  GitHub Actions   ``on: schedule: - cron: "*/5 * * * *"`` (.github/workflows)
  APScheduler      ``@scheduler.scheduled_job("cron", hour=0)`` / ``add_job(...)``
  Celery beat      ``@periodic_task(...)`` / ``crontab(...)`` / ``beat_schedule``
  schedule (lib)   ``schedule.every(10).minutes.do(job)``
  FastAPI          ``@repeat_every(seconds=3600)``
  node-cron        ``cron.schedule("0 * * * *", task)``
  NestJS           ``@Cron(...)`` / ``@Interval(...)`` / ``@Timeout(...)``
  Browser/Node     ``setInterval(fn, 5000)``

For each hit it reports *what* runs, by *which* mechanism, *how often* (the raw
schedule as written) and — the文科生-friendly touch — a plain-language gloss of
common cron expressions (``*/5 * * * *`` → ``每 5 分钟``).

:func:`find_scheduled_tasks` is pure over the file contents, so it is
unit-testable with plain strings and needs no repository.

Limitations (kept honest on purpose):

  * Pattern-based, not a full parse. A schedule whose decorator arguments span
    several lines, or one built dynamically at runtime, may be missed.
  * ``setInterval`` is reported as a recurring timer; a bare ``setTimeout``
    (usually a one-shot delay) is intentionally not, to avoid flooding the map.
  * The plain-language gloss only covers the common cron shapes; anything
    unusual is shown verbatim without a translation rather than guessed at.
"""

from __future__ import annotations

import re

_PY_SUFFIX = ".py"
_JS_SUFFIXES = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")
_YAML_SUFFIXES = (".yml", ".yaml")

# A trailing function/method captured after one or more stacked decorators.
_DEF_TAIL = r"[^\n]*\n(?:[ \t]*@[^\n]*\n)*[ \t]*(?:async[ \t]+)?def[ \t]+(\w+)"

# --- GitHub Actions / any YAML cron: key -----------------------------------
# Matches `- cron: "*/5 * * * *"` and unquoted forms; the backref keeps the
# quotes balanced so a trailing `# comment` is not swallowed into the value.
_YAML_CRON = re.compile(
    r"""^[ \t]*-?[ \t]*cron:[ \t]*(['"]?)([^\n#]*?)\1[ \t]*(?:#.*)?$""",
    re.MULTILINE,
)

# --- Python --------------------------------------------------------------
_APS_DECORATOR = re.compile(r"@[\w.]*?scheduled_job\(([^)]*)\)" + _DEF_TAIL)
_PERIODIC_TASK = re.compile(r"@(?:[\w.]+\.)?periodic_task\(([^)]*)\)" + _DEF_TAIL)
_REPEAT_EVERY = re.compile(r"@(?:[\w.]+\.)?repeat_every\(([^)]*)\)" + _DEF_TAIL)
_ADD_JOB = re.compile(r"\.add_job\(\s*([\w.]+)?")
_SCHEDULE_LIB = re.compile(
    r"\bschedule\.every\(([^)]*)\)((?:\.\w+(?:\([^)]*\))?)+?)\.do\(\s*([\w.]+)?"
)
_CRONTAB = re.compile(r"\bcrontab\(([^)]*)\)")
_BEAT_SCHEDULE = re.compile(r"\bbeat_schedule\b\s*=\s*\{")

# --- JS / TS -------------------------------------------------------------
_NODE_CRON = re.compile(r"""\bcron\.schedule\(\s*(['"`])([^'"`]+)\1""")
_NEST = re.compile(
    r"@(Cron|Interval|Timeout)\(([^)]*)\)"
    r"[^\n]*\n(?:[ \t]*@[^\n]*\n)*[ \t]*"
    r"(?:public |private |protected |async |readonly )*(\w+)\s*\("
)
_SET_INTERVAL = re.compile(r"\bsetInterval\b\s*\(([^,]*),\s*(\d[\d_]*)?")

_MECH_LABEL = {
    "github-actions": "GitHub Actions 定时",
    "apscheduler": "APScheduler",
    "celery": "Celery 定时",
    "schedule": "schedule 库",
    "repeat-every": "FastAPI 周期任务",
    "node-cron": "node-cron",
    "nestjs": "NestJS 定时",
    "interval": "setInterval 定时器",
}

_SCHEDULE_UNIT = {
    "second": "秒",
    "seconds": "秒",
    "minute": "分钟",
    "minutes": "分钟",
    "hour": "小时",
    "hours": "小时",
    "day": "天",
    "days": "天",
    "week": "周",
    "weeks": "周",
}


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def _stem(path: str) -> str:
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] or base


def _cron_to_human(expr: str) -> str:
    """Plain-language gloss of the common 5-field cron shapes, else ``""``."""
    parts = expr.split()
    if len(parts) != 5:
        return ""
    minute, hour, dom, month, dow = parts
    star_rest = dom == month == dow == "*"

    if parts == ["*", "*", "*", "*", "*"]:
        return "每分钟"
    m = re.fullmatch(r"\*/(\d+)", minute)
    if m and hour == "*" and star_rest:
        return f"每 {int(m.group(1))} 分钟"
    if hour == "*" and star_rest and minute.isdigit():
        return "每小时整点" if minute == "0" else f"每小时第 {int(minute)} 分"
    mh = re.fullmatch(r"\*/(\d+)", hour)
    if mh and star_rest and minute.isdigit():
        head = f"每 {int(mh.group(1))} 小时"
        return head if minute == "0" else head + f"第 {int(minute)} 分"
    if minute.isdigit() and hour.isdigit() and star_rest:
        return f"每天 {int(hour):02d}:{int(minute):02d}"
    if minute.isdigit() and hour.isdigit() and dom == "*" and month == "*" and dow.isdigit():
        names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
        return f"每{names[int(dow) % 7]} {int(hour):02d}:{int(minute):02d}"
    if minute.isdigit() and hour.isdigit() and dom.isdigit() and month == "*" and dow == "*":
        return f"每月 {int(dom)} 日 {int(hour):02d}:{int(minute):02d}"
    return ""


def _amount_to_human(amount: int, unit_zh: str) -> str:
    return f"每 {amount} {unit_zh}" if amount != 1 else f"每{unit_zh}"


def _seconds_to_human(raw: str) -> str:
    try:
        n = int(raw)
    except ValueError:
        return ""
    if n % 86400 == 0:
        return _amount_to_human(n // 86400, "天")
    if n % 3600 == 0:
        return _amount_to_human(n // 3600, "小时")
    if n % 60 == 0:
        return _amount_to_human(n // 60, "分钟")
    return _amount_to_human(n, "秒")


def _ms_to_human(raw: str) -> str:
    digits = raw.replace("_", "")
    if not digits.isdigit():
        return ""
    n = int(digits)
    if n % 3_600_000 == 0:
        return _amount_to_human(n // 3_600_000, "小时")
    if n % 60_000 == 0:
        return _amount_to_human(n // 60_000, "分钟")
    if n % 1000 == 0:
        return _amount_to_human(n // 1000, "秒")
    return _amount_to_human(n, "毫秒")


_APS_TIMING_KW = frozenset(
    {
        "seconds",
        "minutes",
        "hours",
        "days",
        "weeks",
        "second",
        "minute",
        "hour",
        "day",
        "day_of_week",
        "month",
        "week",
    }
)


def _aps_trigger(text: str) -> str:
    """Summarise an APScheduler trigger spec (positional kind + timing kwargs).

    Timing kwargs are emitted in source order so the gloss reads the way the
    author wrote it (``cron, hour=0, minute=30``), not in a fixed reshuffle.
    """
    parts: list[str] = []
    kind = re.search(r"""['"](cron|interval|date)['"]""", text)
    if kind:
        parts.append(kind.group(1))
    for km in re.finditer(r"\b(\w+)\s*=\s*([^\s,)]+)", text):
        if km.group(1) in _APS_TIMING_KW:
            parts.append(f"{km.group(1)}={km.group(2)}")
    return ", ".join(parts)


def _find_in_yaml(path: str, content: str) -> list[dict]:
    found: list[dict] = []
    name = _stem(path)
    for m in _YAML_CRON.finditer(content):
        expr = m.group(2).strip()
        if not expr:
            continue
        found.append(
            {
                "name": name,
                "mechanism": "github-actions",
                "schedule": expr,
                "schedule_human": _cron_to_human(expr),
                "line": _line_of(content, m.start()),
            }
        )
    return found


def _find_in_python(content: str) -> list[dict]:
    found: list[dict] = []

    for m in _APS_DECORATOR.finditer(content):
        found.append(
            _task(m.group(2), "apscheduler", _aps_trigger(m.group(1)), "", content, m.start())
        )
    for m in _PERIODIC_TASK.finditer(content):
        found.append(_task(m.group(2), "celery", _aps_trigger(m.group(1)), "", content, m.start()))
    for m in _REPEAT_EVERY.finditer(content):
        secs = re.search(r"seconds\s*=\s*([\d_]+)", m.group(1))
        raw = m.group(1).strip()
        human = _seconds_to_human(secs.group(1).replace("_", "")) if secs else ""
        found.append(_task(m.group(2), "repeat-every", raw, human, content, m.start()))
    for m in _ADD_JOB.finditer(content):
        window = content[m.start() : m.start() + 220]
        name = m.group(1) or "add_job 任务"
        found.append(_task(name, "apscheduler", _aps_trigger(window), "", content, m.start()))
    for m in _SCHEDULE_LIB.finditer(content):
        amount, chain, target = m.group(1).strip(), m.group(2), m.group(3)
        sched = f"every({amount}){chain}"
        unit = chain.lstrip(".").split(".")[0]
        human = ""
        if amount.isdigit() and unit in _SCHEDULE_UNIT:
            human = _amount_to_human(int(amount), _SCHEDULE_UNIT[unit])
        found.append(_task(target or "schedule 任务", "schedule", sched, human, content, m.start()))
    for m in _CRONTAB.finditer(content):
        args = m.group(1).strip()
        found.append(_task("Celery 周期任务", "celery", f"crontab({args})", "", content, m.start()))
    for m in _BEAT_SCHEDULE.finditer(content):
        found.append(_task("周期任务表 (beat_schedule)", "celery", "", "", content, m.start()))

    return found


def _find_in_js(content: str) -> list[dict]:
    found: list[dict] = []
    for m in _NODE_CRON.finditer(content):
        expr = m.group(2).strip()
        found.append(
            _task("node-cron 任务", "node-cron", expr, _cron_to_human(expr), content, m.start())
        )
    for m in _NEST.finditer(content):
        decorator, args, method = m.group(1), m.group(2).strip(), m.group(3)
        sched, human = _nest_schedule(decorator, args)
        found.append(_task(method, "nestjs", sched, human, content, m.start()))
    for m in _SET_INTERVAL.finditer(content):
        ms = m.group(2)
        human = _ms_to_human(ms) if ms else ""
        sched = f"{ms} ms" if ms else ""
        found.append(_task("周期定时器", "interval", sched, human, content, m.start()))
    return found


def _nest_schedule(decorator: str, args: str) -> tuple[str, str]:
    quoted = re.search(r"""['"]([^'"]+)['"]""", args)
    if quoted and len(quoted.group(1).split()) == 5:
        expr = quoted.group(1)
        return expr, _cron_to_human(expr)
    if decorator in ("Interval", "Timeout"):
        num = re.search(r"\b(\d[\d_]*)\b", args)
        if num:
            return f"{decorator}({args})", _ms_to_human(num.group(1))
    return args or decorator, ""


def _task(name: str, mechanism: str, schedule: str, human: str, content: str, pos: int) -> dict:
    return {
        "name": name,
        "mechanism": mechanism,
        "schedule": schedule,
        "schedule_human": human,
        "line": _line_of(content, pos),
    }


def find_scheduled_tasks(file_contents: dict[str, str], *, limit: int = 50) -> dict:
    """Collect the automated / scheduled triggers a project wires up.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many tasks to return in the sorted list.

    Returns ``{"total", "mechanisms", "tasks"}`` where each task is
    ``{"name", "mechanism", "schedule", "schedule_human", "path", "line"}``.
    """
    seen: set[tuple] = set()
    tasks: list[dict] = []

    for path, content in file_contents.items():
        if not content:
            continue
        if path.endswith(_YAML_SUFFIXES):
            entries = _find_in_yaml(path, content)
        elif path.endswith(_PY_SUFFIX):
            entries = _find_in_python(content)
        elif path.endswith(_JS_SUFFIXES):
            entries = _find_in_js(content)
        else:
            continue

        for entry in entries:
            key = (path, entry["line"], entry["name"], entry["mechanism"])
            if key in seen:
                continue
            seen.add(key)
            tasks.append({**entry, "path": path})

    tasks.sort(key=lambda t: (t["path"], t["line"]))
    mechanisms = sorted({t["mechanism"] for t in tasks})
    return {"total": len(tasks), "mechanisms": mechanisms, "tasks": tasks[:limit]}


def render_schedules_markdown(project_name: str, data: dict | None) -> str:
    """Render the scheduled-tasks map as Markdown, or ``""`` if none were found."""
    tasks = (data or {}).get("tasks") or []
    if not tasks:
        return ""

    lines = [
        f"# {project_name} — 会自己定时跑的任务（自动化 / 定时）",
        "",
        "> 入口是“我怎么手动启动”，这里是“项目会不会自己定时做点什么”——"
        "比如每天发一封报告、每 30 秒重试一次队列、每晚跑一次 CI。"
        "这类任务不用你按按钮就会发生，看清它跑什么、多久跑一次，再决定要不要改。",
        "",
    ]
    current_path = None
    for task in tasks:
        if task["path"] != current_path:
            current_path = task["path"]
            lines.append(f"## `{current_path}`")
        label = _MECH_LABEL.get(task["mechanism"], task["mechanism"])
        bits = [f"- `{task['name']}` — {label}"]
        if task["schedule"]:
            bits.append(f"：`{task['schedule']}`")
        if task["schedule_human"]:
            bits.append(f"（{task['schedule_human']}）")
        bits.append(f"  第 {task['line']} 行")
        lines.append("".join(bits))
    return "\n".join(lines).rstrip() + "\n"
