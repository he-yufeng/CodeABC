"""Data-model map — what shape the data this project moves around actually has.

The symbol index tells you *where* a class named ``User`` is declared. It does
not tell you what a ``User`` *is*: which fields it carries, and of what type.
For someone trying to understand an unfamiliar codebase without reading every
file, that second question is often the important one — "an Order has a total, a
list of items and a status" says more about the program than any call graph.

This map reads those shapes straight from the source CodeABC already loaded — no
LLM, nothing to install or run — by recognising the four ways Python code
declares a data record explicitly:

  dataclass    ``@dataclass class User: id: int; name: str = ""``
  pydantic     ``class Order(BaseModel): total: float``
  TypedDict    ``class Movie(TypedDict): title: str``
  NamedTuple   ``class Coord(NamedTuple): lat: float``

Each model carries its name, which of the four kinds it is, the fields it
declares (name, type annotation, and whether it has a default), and the file and
line where it is defined.

:func:`find_data_models` is pure over the file contents, so it is unit-testable
with plain strings and needs no repository.

Limitations (kept honest on purpose):

  * Only the four class-based declaration styles above. The functional forms
    (``TypedDict("Movie", {...})``, ``namedtuple("Coord", [...])``) and ORM
    bases (SQLAlchemy ``Base``, Django ``models.Model``) are out of scope — the
    latter are too easy to confuse with ordinary classes to flag safely.
  * Only statically-declared, annotated fields. Attributes assigned in
    ``__init__`` or built dynamically are not counted.
  * Inherited fields are not flattened in; each model lists only what it
    declares itself.
  * A file that does not parse as Python is skipped, not guessed at.
"""

from __future__ import annotations

import ast

# Base-class names that mark a class as a typed data record, mapped to the kind
# label we report for them.
_BASE_KINDS = {
    "BaseModel": "pydantic",
    "TypedDict": "typeddict",
    "NamedTuple": "namedtuple",
}


def _base_name(node: ast.expr) -> str | None:
    """Return the right-most attribute name of a base/decorator expression.

    ``BaseModel`` -> ``BaseModel``; ``pydantic.BaseModel`` -> ``BaseModel``.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_dataclass(cls: ast.ClassDef) -> bool:
    """True when the class carries a ``@dataclass`` decorator in any form."""
    for dec in cls.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if _base_name(target) == "dataclass":
            return True
    return False


def _classify(cls: ast.ClassDef) -> str | None:
    """Resolve which data-model kind a class is, or ``None`` if it is not one."""
    if _is_dataclass(cls):
        return "dataclass"
    for base in cls.bases:
        name = _base_name(base)
        if name and name in _BASE_KINDS:
            return _BASE_KINDS[name]
    return None


def _annotation_str(node: ast.expr | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _fields(cls: ast.ClassDef) -> list[dict]:
    """Collect the annotated fields declared directly in the class body."""
    fields: list[dict] = []
    for stmt in cls.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        name = stmt.target.id
        # Skip private (_x) and dunder (__x__) names: ORM table hints like
        # __tablename__ and internal bookkeeping are not part of the data shape.
        if name.startswith("_"):
            continue
        fields.append(
            {
                "name": name,
                "type": _annotation_str(stmt.annotation),
                "has_default": stmt.value is not None,
            }
        )
    return fields


def find_data_models(file_contents: dict[str, str], *, limit: int = 60) -> dict:
    """Collect the explicitly-declared data models a project defines.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many models to return in the sorted list.

    Returns ``{"total", "kinds", "models"}`` where each model is
    ``{"name", "kind", "fields", "path", "line"}``, ``kind`` is one of
    ``dataclass`` / ``pydantic`` / ``typeddict`` / ``namedtuple``, and each field
    is ``{"name", "type", "has_default"}``.
    """
    seen: set[tuple[str, str, int]] = set()
    models: list[dict] = []

    for path, content in file_contents.items():
        if not content or not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            kind = _classify(node)
            if kind is None:
                continue
            key = (path, node.name, node.lineno)
            if key in seen:
                continue
            seen.add(key)
            models.append(
                {
                    "name": node.name,
                    "kind": kind,
                    "fields": _fields(node),
                    "path": path,
                    "line": node.lineno,
                }
            )

    models.sort(key=lambda m: (m["path"], m["line"]))
    kinds = sorted({m["kind"] for m in models})
    return {"total": len(models), "kinds": kinds, "models": models[:limit]}


def render_data_models_markdown(project_name: str, data: dict | None) -> str:
    """Render the data-model map as Markdown, or ``""`` if none were found."""
    models = (data or {}).get("models") or []
    if not models:
        return ""

    lines = [
        f"# {project_name} — 数据长什么样（数据模型）",
        "",
        "> 符号索引告诉你一个类“在哪声明”，这里告诉你它“装了什么”——"
        "项目用 dataclass / pydantic / TypedDict / NamedTuple 显式声明的数据记录，"
        "以及每条记录有哪些字段、各是什么类型。",
        "",
    ]
    for model in models:
        lines.append(f"## `{model['name']}`  （{model['kind']}，{model['path']}:{model['line']}）")
        if not model["fields"]:
            lines.append("- （未声明带类型标注的字段）")
            lines.append("")
            continue
        for field in model["fields"]:
            entry = f"- `{field['name']}`"
            if field["type"]:
                entry += f"：{field['type']}"
            if field["has_default"]:
                entry += "（有默认值）"
            lines.append(entry)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
