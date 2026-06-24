"""CLI command surface — what you can actually type to drive the tool.

The entry-points map answers "which file or console command starts the program"
— that you run ``mytool`` or ``python manage.py``. It stops at the front door.
This map walks through it: once you have a CLI, what *sub-commands* does it
accept, and what does each one do? For someone evaluating a tool without reading
the code, that is the real question — ``mytool build``, ``mytool deploy``, the
list of verbs and the one-line help next to each.

It reads the command surface straight from the source CodeABC already loaded —
no LLM, and nothing to install or run — by recognising the three CLI frameworks
that cover the overwhelming majority of Python tools:

  argparse   ``sub = parser.add_subparsers(); sub.add_parser("build", help=...)``
  click      ``@cli.command("build")`` / ``@click.command`` + ``@click.option``
  typer      ``@app.command()`` on a ``typer.Typer()`` app

Each command carries its name, the framework it came from, a short help line (the
``help=`` argument, or the function's docstring first line), the option/argument
flags it declares, and the file and line where it is defined.

:func:`find_cli_commands` is pure over the file contents, so it is unit-testable
with plain strings and needs no repository.

Limitations (kept honest on purpose):

  * Only the three frameworks above, and only statically-declared commands.
    Names or help built at runtime, plugin-loaded sub-commands, and groups
    registered dynamically are out of scope.
  * A file that does not parse as Python is skipped, not guessed at.
  * Group nesting is recorded by each command's own name, not rebuilt into a
    full ``parent child`` path.
  * argparse option flags need dataflow to tie back to their sub-parser, so
    argparse commands list their name and help but not their flags.
"""

from __future__ import annotations

import ast

# Decorator attribute names that register a CLI command or group.
_COMMAND_ATTRS = ("command", "group")
# Decorator attribute names that declare a flag/argument on a click/typer command.
_OPTION_ATTRS = ("option", "argument")


def _base_name(node: ast.expr) -> str | None:
    """Return the left-most name of ``a`` in ``@a.command`` / ``@a.b.command``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _base_name(node.value)
    return None


def _first_string_arg(call: ast.Call) -> str | None:
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _string_kwarg(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if (
            kw.arg == name
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    return None


def _docstring_summary(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    doc = ast.get_docstring(func)
    if not doc:
        return ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _command_decorator(dec: ast.expr) -> ast.Attribute | None:
    """Return the decorator's target if it is a ``.command`` / ``.group`` one."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Attribute) and target.attr in _COMMAND_ATTRS:
        return target
    return None


def _option_flag(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
        if dec.func.attr in _OPTION_ATTRS:
            return _first_string_arg(dec)
    return None


def _scan_imports_and_apps(tree: ast.Module) -> tuple[set[str], bool, bool, bool]:
    """Return (typer_app_vars, click_imported, typer_imported, argparse_imported)."""
    typer_apps: set[str] = set()
    click_imported = typer_imported = False
    argparse_imported = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                click_imported |= root == "click"
                typer_imported |= root == "typer"
                argparse_imported |= root == "argparse"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            click_imported |= root == "click"
            typer_imported |= root == "typer"
            argparse_imported |= root == "argparse"
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            # `app = typer.Typer(...)` or `app = Typer(...)`
            is_typer = (isinstance(func, ast.Attribute) and func.attr == "Typer") or (
                isinstance(func, ast.Name) and func.id == "Typer"
            )
            if is_typer:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        typer_apps.add(target.id)

    return typer_apps, click_imported, typer_imported, argparse_imported


def _framework(
    base: str | None, typer_apps: set[str], click_imp: bool, typer_imp: bool
) -> str | None:
    """Resolve which CLI framework a ``.command`` decorator belongs to."""
    if base in typer_apps or base == "typer":
        return "typer"
    if base == "click":
        return "click"
    # `@cli.command` on a group variable — fall back to whatever the file imports.
    if typer_imp and not click_imp:
        return "typer"
    if click_imp:
        return "click"
    return None


def _decorated_commands(tree: ast.Module, path: str) -> list[dict]:
    typer_apps, click_imp, typer_imp, _ = _scan_imports_and_apps(tree)
    commands: list[dict] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        target = next(
            (t for dec in node.decorator_list if (t := _command_decorator(dec)) is not None),
            None,
        )
        if target is None:
            continue

        framework = _framework(_base_name(target.value), typer_apps, click_imp, typer_imp)
        if framework is None:
            continue

        decorator = next(d for d in node.decorator_list if _command_decorator(d) is target)
        name = None
        help_text = ""
        if isinstance(decorator, ast.Call):
            name = _first_string_arg(decorator) or _string_kwarg(decorator, "name")
            help_text = _string_kwarg(decorator, "help") or ""
        name = name or node.name.replace("_", "-")
        if not help_text:
            help_text = _docstring_summary(node)

        options = [f for dec in node.decorator_list if (f := _option_flag(dec))]
        commands.append(
            {
                "name": name,
                "framework": framework,
                "help": help_text,
                "options": options,
                "path": path,
                "line": node.lineno,
            }
        )

    return commands


def _argparse_commands(tree: ast.Module, path: str) -> list[dict]:
    commands: list[dict] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_parser":
            continue
        name = _first_string_arg(node)
        if not name:
            continue
        commands.append(
            {
                "name": name,
                "framework": "argparse",
                "help": _string_kwarg(node, "help") or "",
                "options": [],
                "path": path,
                "line": node.lineno,
            }
        )
    return commands


def find_cli_commands(file_contents: dict[str, str], *, limit: int = 60) -> dict:
    """Collect the CLI sub-commands a project exposes from its source.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many commands to return in the sorted list.

    Returns ``{"total", "frameworks", "commands"}`` where each command is
    ``{"name", "framework", "help", "options", "path", "line"}`` and
    ``framework`` is one of ``click`` / ``typer`` / ``argparse``.
    """
    seen: set[tuple[str, str]] = set()
    commands: list[dict] = []

    for path, content in file_contents.items():
        if not content or not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            continue

        _, _, _, argparse_imp = _scan_imports_and_apps(tree)
        found = _decorated_commands(tree, path)
        if argparse_imp:
            found += _argparse_commands(tree, path)

        for cmd in found:
            key = (cmd["path"], cmd["name"])
            if key in seen:
                continue
            seen.add(key)
            commands.append(cmd)

    commands.sort(key=lambda c: (c["path"], c["line"]))
    frameworks = sorted({c["framework"] for c in commands})
    return {"total": len(commands), "frameworks": frameworks, "commands": commands[:limit]}


def render_commands_markdown(project_name: str, data: dict | None) -> str:
    """Render the CLI command surface as Markdown, or ``""`` if none were found."""
    commands = (data or {}).get("commands") or []
    if not commands:
        return ""

    lines = [
        f"# {project_name} — 能运行哪些命令（CLI 命令）",
        "",
        "> 入口点告诉你“用哪个命令启动”，这里告诉你“启动后能敲哪些子命令”——"
        "作者用 argparse / click / typer 声明的子命令，以及每个命令的一句话说明。",
        "",
    ]
    for cmd in commands:
        head = f"- `{cmd['name']}`"
        if cmd["help"]:
            head += f" — {cmd['help']}"
        head += f"  （{cmd['framework']}，{cmd['path']}）"
        lines.append(head)
        if cmd["options"]:
            lines.append(f"  - 选项：{', '.join(f'`{o}`' for o in cmd['options'])}")

    return "\n".join(lines).rstrip() + "\n"
