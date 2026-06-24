"""Export the whole analysis as one self-contained HTML report.

The browser UI is great for reading a codebase, but it needs a running server.
Sometimes you just want to hand the result to someone — a non-technical
stakeholder, a teammate, your future self — as a single file they can open in
any browser with no install, no server, and no internet.

This module turns the same deterministic code map that powers ``codemap.md``
into one HTML document with the styling baked in. Everything lives inside the
file: there are no external stylesheets, scripts, fonts, or images to go
missing when you email it or drop it in a shared drive.

The Markdown is produced by :mod:`backend.services.codemap_export` (every
section there is owned by the service for that analysis). This module only
renders that Markdown to HTML and wraps it in a readable, offline page. The
renderer escapes the source text *before* it adds any formatting, so content
pulled from the analysed codebase (file paths, code snippets, TODO text) can
never inject markup into the report.
"""

from __future__ import annotations

import html
import re

from backend.services import codemap_export

# Inline patterns are applied to text that has *already* been HTML-escaped, so
# the angle brackets in any real markup are long gone and only our own markers
# (backticks, asterisks, link syntax) remain to act on.
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_TABLE_DIVIDER = re.compile(r"^\s*\|?\s*:?-{2,}.*$")


def _render_inline(escaped: str) -> str:
    """Apply inline Markdown (code, bold, links) to an already-escaped line."""
    escaped = _INLINE_CODE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _LINK.sub(r'<a href="\2" rel="noopener noreferrer">\1</a>', escaped)
    return escaped


def _esc(text: str) -> str:
    return _render_inline(html.escape(text, quote=False))


def _split_row(line: str) -> list[str]:
    """Split a ``| a | b |`` table row into its trimmed cells."""
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip() for cell in inner.split("|")]


def _markdown_to_html(md: str) -> str:
    """Render the subset of Markdown the code-map services emit.

    Handled blocks: ``#``/``##``/``###`` headings, ``---`` rules, ``>`` quotes,
    ``-`` bullet lists (one level of nesting), pipe tables, and paragraphs.
    Unknown lines fall through as paragraph text, never as raw HTML.
    """
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    def close_list(stack: list[str]) -> None:
        while stack:
            out.append("</ul>")
            stack.pop()

    list_stack: list[str] = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Blank line: end any open list, otherwise it is just spacing.
        if not stripped:
            close_list(list_stack)
            i += 1
            continue

        # Horizontal rule.
        if stripped == "---":
            close_list(list_stack)
            out.append("<hr>")
            i += 1
            continue

        # Headings.
        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            close_list(list_stack)
            level = len(heading.group(1))
            out.append(f"<h{level}>{_esc(heading.group(2))}</h{level}>")
            i += 1
            continue

        # Blockquote: gather consecutive ``>`` lines into one quote.
        if stripped.startswith(">"):
            close_list(list_stack)
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(_esc(lines[i].strip()[1:].strip()))
                i += 1
            out.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
            continue

        # Table: a header row immediately followed by a divider row.
        if stripped.startswith("|") and i + 1 < n and _TABLE_DIVIDER.match(lines[i + 1]):
            header = _split_row(lines[i])
            out.append("<table><thead><tr>")
            out.extend(f"<th>{_esc(cell)}</th>" for cell in header)
            out.append("</tr></thead><tbody>")
            i += 2  # skip header + divider
            while i < n and lines[i].strip().startswith("|"):
                out.append("<tr>")
                out.extend(f"<td>{_esc(cell)}</td>" for cell in _split_row(lines[i]))
                out.append("</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        # Bullet list, with a single level of two-space nesting.
        bullet = re.match(r"^(\s*)-\s+(.*)$", line)
        if bullet:
            depth = 1 if len(bullet.group(1)) >= 2 else 0
            while len(list_stack) <= depth:
                out.append("<ul>")
                list_stack.append("ul")
            while len(list_stack) > depth + 1:
                out.append("</ul>")
                list_stack.pop()
            out.append(f"<li>{_esc(bullet.group(2))}</li>")
            i += 1
            continue

        # Anything else is a paragraph.
        close_list(list_stack)
        out.append(f"<p>{_esc(stripped)}</p>")
        i += 1

    close_list(list_stack)
    return "\n".join(out)


# Inlined so the exported file needs no external stylesheet to render.
_STYLE = """\
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  line-height: 1.65; color: #1f2328; background: #f6f8fa;
}
main { max-width: 860px; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }
header.report-head {
  background: linear-gradient(135deg, #0d9488, #0f766e);
  color: #fff; padding: 2rem 1.5rem;
}
header.report-head .inner { max-width: 860px; margin: 0 auto; }
header.report-head h1 { margin: 0; font-size: 1.6rem; }
header.report-head p { margin: .4rem 0 0; opacity: .9; font-size: .9rem; }
h1, h2, h3 { line-height: 1.3; margin-top: 2rem; }
h1 { font-size: 1.5rem; border-bottom: 1px solid #d0d7de; padding-bottom: .3rem; }
h2 { font-size: 1.2rem; }
h3 { font-size: 1.05rem; }
hr { border: none; border-top: 1px solid #d0d7de; margin: 2.5rem 0; }
blockquote {
  margin: 1rem 0; padding: .6rem 1rem; color: #57606a;
  background: #eef2f5; border-left: 3px solid #0d9488; border-radius: 4px;
}
code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  background: rgba(13, 148, 136, .1); padding: .1em .35em; border-radius: 4px;
  font-size: .9em;
}
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .92rem; }
th, td { border: 1px solid #d0d7de; padding: .45rem .7rem; text-align: left; }
th { background: #eef2f5; }
ul { padding-left: 1.4rem; }
li { margin: .2rem 0; }
footer { max-width: 860px; margin: 0 auto; padding: 1rem 1.5rem 3rem;
  color: #8b949e; font-size: .8rem; }
@media (prefers-color-scheme: dark) {
  body { color: #e6edf3; background: #0d1117; }
  h1 { border-bottom-color: #30363d; }
  hr { border-top-color: #30363d; }
  blockquote { background: #161b22; color: #9da7b3; }
  th, td { border-color: #30363d; }
  th, blockquote ~ * th { background: #161b22; }
}
"""


def build_report_html(proj: dict) -> str:
    """Build the downloadable self-contained HTML report for a scanned project.

    The body is the same deterministic code map as ``codemap.md``, rendered to
    HTML and wrapped in an offline page with all styling inlined.
    """
    name = proj.get("name", "project")
    body = _markdown_to_html(codemap_export.build_codemap_markdown(proj))
    title = html.escape(f"{name} — CodeABC report", quote=True)
    head_name = html.escape(name, quote=False)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_STYLE}</style>
</head>
<body>
<header class="report-head"><div class="inner">
<h1>{head_name}</h1>
<p>Plain-language code report · generated by CodeABC · self-contained, works offline</p>
</div></header>
<main>
{body}
</main>
<footer>This report was generated by CodeABC. Every section is a deterministic \
analysis of the source — no model was asked to write it.</footer>
</body>
</html>
"""
