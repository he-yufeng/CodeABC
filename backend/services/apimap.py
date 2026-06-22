"""API-endpoint map: extract HTTP routes from web-framework source code.

A non-programmer reviewing a backend — a founder auditing an outsourced API,
say — wants a single answer to "what does this service actually expose?". The
import graph shows what imports what; this answers the complementary question:
which URL paths exist, what HTTP methods they accept, and what they do.

Supports the most common frameworks by scanning for their decorator or function
patterns:

  FastAPI / APIRouter   @router.get / .post / .put / .delete / .patch / .options
  Flask / Blueprint     @app.route / @bp.route (methods= list)
  Django                urlpatterns = [path("...", view, name="...")]
  Express (JS)          app.get / app.post / router.get / etc.
  Next.js (App Router)  src/app/**/route.ts|js — export async function GET|POST|...

Each route entry carries method, path, handler name, brief description (from
the function's docstring if one is present), file, and line number.

Limitations:
  * Patterns are regex-based: computed paths (f-strings, concatenation,
    variables) may be missed or mis-parsed.
  * Dynamic prefix mounting (app.include_router with prefix=, app.register_blueprint
    with url_prefix=) is detected and annotated, but full prefix expansion would
    require data-flow analysis that's out of scope.
  * Results are best-effort — treat them as a navigational index, not a
    definitive spec.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_QUOTE_CONTENT = r"""['"]([^'"]+)['"]"""  # a quoted string, captured


def _lang(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in ("py",):
        return "python"
    if ext in ("js", "ts", "jsx", "tsx", "mjs", "cjs"):
        return "js"
    return ext


# ---------------------------------------------------------------------------
# FastAPI / Flask / Django (Python)
# ---------------------------------------------------------------------------

# @router.<method>("/<path>") or @app.<method>("/<path>")
_FASTAPI_DECORATOR_RE = re.compile(
    r"""@[\w.]+\.(get|post|put|delete|patch|options|head)\s*\("""
    r"""\s*""" + _QUOTE_CONTENT,
    re.IGNORECASE,
)

# @app.route("/path", methods=["GET", "POST"]) or @bp.route("/path")
_FLASK_ROUTE_RE = re.compile(
    r"""@[\w.]+\.route\s*\(\s*""" + _QUOTE_CONTENT + r"""[^)]*\)""",
    re.IGNORECASE,
)
_FLASK_METHODS_RE = re.compile(r"""methods\s*=\s*\[([^\]]+)\]""", re.IGNORECASE)

# def function_name(...):  immediately following decorator
_PY_FUNC_RE = re.compile(r"""^\s*(?:async\s+)?def\s+(\w+)\s*\(""")
# docstring: the first string literal after the def line
_DOCSTRING_RE = re.compile(r"""^\s+['"]{3}(.*?)(?:['"]{3}|$)|^\s+['"]([^'"]+)['"]""")

# Django: path("...", view_func, name="...")
_DJANGO_PATH_RE = re.compile(
    r"""(?:path|re_path|url)\s*\(\s*""" + _QUOTE_CONTENT + r"""\s*,\s*(\w[\w.]*)\s*""",
    re.IGNORECASE,
)
# include_router / register_blueprint prefix detection
_PY_PREFIX_RE = re.compile(
    r"""(?:include_router|register_blueprint)\s*\([^)]*prefix\s*=\s*""" + _QUOTE_CONTENT,
    re.IGNORECASE,
)


def _py_routes(path: str, content: str) -> list[dict]:
    """Extract routes from a Python file (FastAPI, Flask, Django)."""
    routes: list[dict] = []
    lines = content.splitlines()
    n = len(lines)
    prefix_hints: list[str] = []

    for m in _PY_PREFIX_RE.finditer(content):
        prefix_hints.append(m.group(1))

    i = 0
    while i < n:
        line = lines[i]

        # FastAPI-style: @router.get("/path")
        fm = _FASTAPI_DECORATOR_RE.search(line)
        if fm:
            method = fm.group(1).upper()
            route_path = fm.group(2)
            handler = ""
            description = ""
            # look ahead for the def
            for j in range(i + 1, min(i + 5, n)):
                dm = _PY_FUNC_RE.match(lines[j])
                if dm:
                    handler = dm.group(1)
                    # try to grab docstring
                    if j + 1 < n:
                        dsm = _DOCSTRING_RE.match(lines[j + 1])
                        if dsm:
                            description = (dsm.group(1) or dsm.group(2) or "").strip()
                    break
            routes.append(
                {
                    "method": method,
                    "path": route_path,
                    "handler": handler,
                    "description": description,
                    "file": path,
                    "line": i + 1,
                }
            )
            i += 1
            continue

        # Flask-style: @app.route("/path", methods=["GET", "POST"])
        flask_m = _FLASK_ROUTE_RE.search(line)
        if flask_m:
            route_path = flask_m.group(1)
            raw = line[flask_m.start() :]
            mm = _FLASK_METHODS_RE.search(raw)
            if mm:
                methods = [
                    m.strip().strip("'\"").upper()
                    for m in mm.group(1).split(",")
                    if m.strip().strip("'\"")
                ]
            else:
                methods = ["GET"]
            handler = ""
            description = ""
            for j in range(i + 1, min(i + 5, n)):
                dm = _PY_FUNC_RE.match(lines[j])
                if dm:
                    handler = dm.group(1)
                    if j + 1 < n:
                        dsm = _DOCSTRING_RE.match(lines[j + 1])
                        if dsm:
                            description = (dsm.group(1) or dsm.group(2) or "").strip()
                    break
            for method in methods:
                routes.append(
                    {
                        "method": method,
                        "path": route_path,
                        "handler": handler,
                        "description": description,
                        "file": path,
                        "line": i + 1,
                    }
                )
            i += 1
            continue

        # Django: path("...", view_func)
        dj_m = _DJANGO_PATH_RE.search(line)
        if dj_m:
            route_path = dj_m.group(1)
            handler = dj_m.group(2)
            routes.append(
                {
                    "method": "ANY",
                    "path": route_path,
                    "handler": handler,
                    "description": "",
                    "file": path,
                    "line": i + 1,
                }
            )
            i += 1
            continue

        i += 1

    # Annotate with prefix hints if found.
    if prefix_hints and routes:
        for r in routes:
            if not r.get("description"):
                r["description"] = f"(router mounted with prefix: {prefix_hints[0]})"

    return routes


# ---------------------------------------------------------------------------
# Express / Next.js (JavaScript / TypeScript)
# ---------------------------------------------------------------------------

# app.get("/path", handler) or router.post("/path", ...)
_EXPRESS_ROUTE_RE = re.compile(
    r"""(?:app|router)\.(get|post|put|delete|patch|options|head|all)\s*\(\s*""" + _QUOTE_CONTENT,
    re.IGNORECASE,
)

# Next.js App Router: export (async) function GET/POST/PUT/DELETE/PATCH
_NEXTJS_HANDLER_RE = re.compile(
    r"""export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s*\(""",
)

# Next.js route file pattern: app/**/route.(ts|js)
_NEXTJS_ROUTE_FILE_RE = re.compile(r"""(?:^|/)route\.[jt]sx?$""")


def _js_routes(path: str, content: str) -> list[dict]:
    """Extract routes from a JS/TS file (Express, Next.js)."""
    routes: list[dict] = []
    lines = content.splitlines()

    is_nextjs_route = bool(_NEXTJS_ROUTE_FILE_RE.search(path.replace("\\", "/")))

    for i, line in enumerate(lines):
        if is_nextjs_route:
            nm = _NEXTJS_HANDLER_RE.search(line)
            if nm:
                method = nm.group(1).upper()
                # Derive the URL path from the file path:
                # src/app/users/[id]/route.ts → /users/[id]
                fp = path.replace("\\", "/")
                # strip leading everything up to "app/"
                app_idx = fp.find("/app/")
                if app_idx >= 0:
                    rel = fp[app_idx + 5 :]  # after /app/
                    # drop trailing /route.ts
                    rel = re.sub(r"/route\.[jt]sx?$", "", rel)
                    route_path = "/" + rel if rel else "/"
                else:
                    route_path = "/" + fp.rsplit("/", 1)[-1].split(".")[0]
                routes.append(
                    {
                        "method": method,
                        "path": route_path,
                        "handler": f"export function {method}",
                        "description": "",
                        "file": path,
                        "line": i + 1,
                    }
                )
                continue

        em = _EXPRESS_ROUTE_RE.search(line)
        if em:
            method = em.group(1).upper()
            route_path = em.group(2)
            routes.append(
                {
                    "method": method,
                    "path": route_path,
                    "handler": "",
                    "description": "",
                    "file": path,
                    "line": i + 1,
                }
            )

    return routes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_METHOD_ORDER = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "ANY", "ALL"]


def scan_api_routes(file_contents: dict[str, str], *, limit: int = 80) -> dict:
    """Scan file contents for HTTP route declarations.

    Args:
        file_contents: mapping of path to file text.
        limit: cap on total routes returned.

    Returns::

        {
          "total": int,
          "routes": [
            {
              "method": str,   # GET / POST / … / ANY / ALL
              "path": str,     # route path string as declared
              "handler": str,  # handler function/class name
              "description": str,
              "file": str,
              "line": int,
            }, …
          ],
          "frameworks": [str, …],  # detected framework names
          "notes": [str, …],
        }
    """
    all_routes: list[dict] = []
    frameworks: set[str] = set()

    for path, content in file_contents.items():
        if not content:
            continue
        lang_id = _lang(path)
        if lang_id == "python":
            routes = _py_routes(path, content)
            if routes:
                # guess framework from imports in file
                if re.search(r"\bfastapi\b", content, re.IGNORECASE):
                    frameworks.add("FastAPI")
                elif re.search(r"\bflask\b", content, re.IGNORECASE):
                    frameworks.add("Flask")
                elif re.search(r"\bdjango\b", content, re.IGNORECASE):
                    frameworks.add("Django")
                else:
                    frameworks.add("Python HTTP")
            all_routes.extend(routes)
        elif lang_id == "js":
            routes = _js_routes(path, content)
            if routes:
                if _NEXTJS_ROUTE_FILE_RE.search(path.replace("\\", "/")):
                    frameworks.add("Next.js")
                elif re.search(r"\bexpress\b", content, re.IGNORECASE):
                    frameworks.add("Express")
                else:
                    frameworks.add("Node HTTP")
            all_routes.extend(routes)

    total = len(all_routes)

    # Sort: by path, then method order, then file+line.
    _method_idx = {m: i for i, m in enumerate(_METHOD_ORDER)}
    all_routes.sort(
        key=lambda r: (r["path"], _method_idx.get(r["method"], 99), r["file"], r["line"])
    )

    notes = _build_notes(total, list(frameworks))

    return {
        "total": total,
        "routes": all_routes[:limit],
        "frameworks": sorted(frameworks),
        "notes": notes,
    }


def _build_notes(total: int, frameworks: list[str]) -> list[str]:
    if total == 0:
        return ["未检测到已知 HTTP 框架的路由声明（FastAPI/Flask/Django/Express/Next.js）。"]
    notes = []
    if frameworks:
        notes.append(f"检测到框架：{', '.join(frameworks)}。")
    notes.append(
        f"共发现 {total} 条路由声明。"
        "动态生成的路径（变量、f-string 拼接）可能未被捕获，建议结合框架文档核查。"
    )
    return notes


def render_apimap_markdown(project_name: str, data: dict | None) -> str:
    """Render the API route map as a Markdown section, or ``""`` if empty."""
    if not data or not data.get("routes"):
        return ""
    total = data.get("total", 0)
    frameworks = data.get("frameworks", [])
    fw_str = f"（{', '.join(frameworks)}）" if frameworks else ""
    lines = [
        f"# HTTP 接口地图{fw_str}（{project_name}）",
        "",
        f"> 共发现 {total} 条路由声明。 动态路径可能未完整捕获，仅供导航参考。",
        "",
    ]
    lines.extend(f"- {note}" for note in data.get("notes", []))

    lines.append("")
    lines.append("## 路由清单")
    lines.append("")
    lines.append("| 方法 | 路径 | 处理函数 | 说明 | 文件 |")
    lines.append("|------|------|----------|------|------|")
    for r in data.get("routes", []):
        handler = r.get("handler") or "—"
        desc = r.get("description") or "—"
        file_link = f"`{r['file']}:{r['line']}`"
        lines.append(f"| `{r['method']}` | `{r['path']}` | `{handler}` | {desc} | {file_link} |")

    return "\n".join(lines).rstrip() + "\n"
