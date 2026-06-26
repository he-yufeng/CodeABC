"""Open-source license map — what a project is licensed under, and what that lets you do.

The other maps answer questions about the *code*. This one answers the question a
non-programmer asks before they ever read a line of it: **am I actually allowed to
use this — in a side project, in something I sell, after I change it?** A repository's
license is the legal answer, and it is usually buried in a ``LICENSE`` file written in
dense legalese, or hidden as one line in ``pyproject.toml`` / ``package.json``. Worse,
a project with *no* license is not "free to use" — by default it is *all rights
reserved*, which most people get exactly backwards.

This module reads what CodeABC already loaded — no LLM, nothing to run — and reports:

  * the project's own license, recognised from the ``LICENSE`` file's wording or the
    ``license`` field / SPDX tag / trove classifier in its manifest;
  * which plain-language family it belongs to (宽松型 / 弱著佐权 / 强著佐权 /
    网络著佐权 / 公有领域 / 源码可见但非自由), and what that family means for the
    four questions people actually have — 能不能商用、能不能闭源用、改了要不要公开、
    会不会"传染"你自己的项目;
  * a blunt warning when no license is found at all.

:func:`find_licenses` is pure over the file contents, so it is unit-testable with
plain strings and needs no repository.

Limitations (kept honest on purpose):

  * Recognition is signature based, not a legal parse. A heavily edited license, a
    dual-license expression, or an obscure license this module does not know will come
    back as "未识别" rather than guessed at. The first recognised license in priority
    order is reported as the primary one.
  * Only the *project's own* license is detected. The licenses of its dependencies are
    not resolved — a manifest lists dependency *names*, not their licenses — so this is
    not a compliance audit of the whole dependency tree.
  * Everything here is a plain-language summary to orient a newcomer, **not legal
    advice**. For anything that matters, read the license text or ask a lawyer.
"""

from __future__ import annotations

import re

# Plain-language obligations per license family. Each value answers the same four
# questions in the same order so the render stays a stable, scannable table.
_CATEGORY = {
    "permissive": {
        "label": "宽松型",
        "one_line": "几乎想怎么用都行：商用、改造、闭源都可以，只要保留原作者的版权和许可声明。",
        "commercial": "可以",
        "private_use": "可以（能用在闭源 / 商业产品里）",
        "share_changes": "不必（你的改动和新增代码可以不公开）",
        "copyleft_scope": "不会，不影响你自己的代码",
        "keep_notice": "保留原作者的版权声明和许可证全文",
    },
    "weak-copyleft": {
        "label": "弱著佐权（文件 / 库级）",
        "one_line": (
            "可以商用，但你改动它原有文件的部分要按同样许可公开；你自己新写的文件可以闭源。"
        ),
        "commercial": "可以",
        "private_use": "可以",
        "share_changes": "改动了它本身的源文件要公开，你新增的独立文件不用",
        "copyleft_scope": "只波及这个库 / 这些文件，不波及你的整个项目",
        "keep_notice": "保留版权与许可声明，并标明你的改动",
    },
    "strong-copyleft": {
        "label": "强著佐权",
        "one_line": (
            "可以商用、可以改，但只要把成品分发出去，整个衍生项目都得按同样的许可一起开源。"
        ),
        "commercial": "可以，但要连同开源义务一起",
        "private_use": "自己内部用、不对外分发，可以不开源",
        "share_changes": "一旦分发，必须公开包含改动在内的全部源码",
        "copyleft_scope": "会传染——和它合并 / 链接的代码通常都要一起开源",
        "keep_notice": "保留版权与许可声明，并标明你的改动",
    },
    "network-copyleft": {
        "label": "网络著佐权",
        "one_line": (
            "和强著佐权一样，而且更进一步：哪怕只是放在服务器上联网提供服务，也要把源码给用户。"
        ),
        "commercial": "可以，但要连同开源义务一起",
        "private_use": "纯自己用、不提供给任何外部用户才不触发",
        "share_changes": "分发或联网提供服务都要公开全部源码",
        "copyleft_scope": "最强——连 SaaS / 网络服务都会触发开源义务",
        "keep_notice": "保留版权与许可声明，并标明你的改动",
    },
    "public-domain": {
        "label": "公有领域 / 近似放弃版权",
        "one_line": "作者基本放弃了权利，你几乎可以无条件使用，通常连署名都不强制。",
        "commercial": "可以",
        "private_use": "可以",
        "share_changes": "不必",
        "copyleft_scope": "不会",
        "keep_notice": "通常不强制（保留出处仍是好习惯）",
    },
    "source-available": {
        "label": "源码可见但非自由许可",
        "one_line": (
            "源码能看，但不等于能随便用。这类许可常限制商用，"
            "或禁止拿去做与原产品竞争的服务，务必先读清楚条款。"
        ),
        "commercial": "受限——按条款，多数禁止与原产品竞争或限定用途",
        "private_use": "通常可以，但有时附带时间或用途限制",
        "share_changes": "看具体条款",
        "copyleft_scope": "看具体条款",
        "keep_notice": "保留声明，并遵守额外的使用限制",
    },
    "unknown": {
        "label": "未识别",
        "one_line": "扫描到了许可证，但没认出是哪一种——请人工读一下原文，或联系作者确认。",
        "commercial": "需人工确认",
        "private_use": "需人工确认",
        "share_changes": "需人工确认",
        "copyleft_scope": "需人工确认",
        "keep_notice": "需人工确认",
    },
}
_CATEGORY_ORDER = [
    "permissive",
    "weak-copyleft",
    "strong-copyleft",
    "network-copyleft",
    "public-domain",
    "source-available",
    "unknown",
]

# SPDX id -> (English name, plain-Chinese name, family). The id is the key the
# manifest / tag / classifier paths normalise to, so the three sources agree.
_LICENSES = {
    "MIT": ("MIT License", "MIT 许可证", "permissive"),
    "Apache-2.0": ("Apache License 2.0", "Apache 2.0 许可证", "permissive"),
    "BSD-2-Clause": ("BSD 2-Clause", "BSD 两条款许可证", "permissive"),
    "BSD-3-Clause": ("BSD 3-Clause", "BSD 三条款许可证", "permissive"),
    "ISC": ("ISC License", "ISC 许可证", "permissive"),
    "BSL-1.0": ("Boost Software License 1.0", "Boost 软件许可证", "permissive"),
    "Zlib": ("zlib License", "zlib 许可证", "permissive"),
    "Python-2.0": ("Python Software Foundation License", "Python PSF 许可证", "permissive"),
    "MPL-2.0": ("Mozilla Public License 2.0", "Mozilla 公共许可证 2.0", "weak-copyleft"),
    "EPL-2.0": ("Eclipse Public License 2.0", "Eclipse 公共许可证 2.0", "weak-copyleft"),
    "LGPL-2.1": ("GNU LGPL v2.1", "GNU 宽通用公共许可证 2.1", "weak-copyleft"),
    "LGPL-3.0": ("GNU LGPL v3.0", "GNU 宽通用公共许可证 3.0", "weak-copyleft"),
    "GPL-2.0": ("GNU GPL v2.0", "GNU 通用公共许可证 2.0", "strong-copyleft"),
    "GPL-3.0": ("GNU GPL v3.0", "GNU 通用公共许可证 3.0", "strong-copyleft"),
    "AGPL-3.0": ("GNU AGPL v3.0", "GNU Affero 通用公共许可证 3.0", "network-copyleft"),
    "Unlicense": ("The Unlicense", "Unlicense（公有领域）", "public-domain"),
    "CC0-1.0": ("Creative Commons Zero 1.0", "CC0 公有领域奉献", "public-domain"),
    "0BSD": ("BSD Zero Clause License", "BSD 零条款许可证", "public-domain"),
    "WTFPL": ("Do What The F*ck You Want To Public License", "WTFPL（随便用）", "public-domain"),
    "BUSL-1.1": ("Business Source License 1.1", "商业源码许可证 1.1", "source-available"),
    "SSPL-1.0": ("Server Side Public License 1.0", "服务器端公共许可证 1.0", "source-available"),
    "Elastic-2.0": ("Elastic License 2.0", "Elastic 许可证 2.0", "source-available"),
}

# Plain-language gloss for where a finding came from.
_SOURCE_LABEL = {
    "license-file": "许可证文件",
    "manifest": "项目清单的 license 字段",
    "classifier": "项目清单的分类标签",
    "spdx-tag": "源码里的 SPDX 标记",
}

# License-file body signatures, tried in order; the first to match a file wins. The
# AFFERO / LESSER variants are listed before the plain GPL because their text also
# contains the words "GNU GENERAL PUBLIC LICENSE", and the more specific ISC grant is
# listed before the bare 0BSD grant it would otherwise swallow.
_TEXT_SIGNATURES: list[tuple[str, str]] = [
    ("AGPL-3.0", r"GNU AFFERO GENERAL PUBLIC LICENSE"),
    ("LGPL-3.0", r"GNU LESSER GENERAL PUBLIC LICENSE.{0,400}Version 3"),
    ("LGPL-2.1", r"GNU LESSER GENERAL PUBLIC LICENSE"),
    ("GPL-3.0", r"GNU GENERAL PUBLIC LICENSE.{0,400}Version 3"),
    ("GPL-2.0", r"GNU GENERAL PUBLIC LICENSE.{0,400}Version 2"),
    ("Apache-2.0", r"Apache License.{0,40}Version 2\.0"),
    ("MPL-2.0", r"Mozilla Public License.{0,40}Version 2\.0"),
    ("EPL-2.0", r"Eclipse Public License.{0,40}v(?:ersion )?2\.0"),
    ("BSL-1.0", r"Boost Software License"),
    ("BUSL-1.1", r"Business Source License"),
    ("SSPL-1.0", r"Server Side Public License"),
    ("Elastic-2.0", r"Elastic License 2\.0"),
    ("BSD-3-Clause", r"Redistribution and use in source and binary forms.{0,1500}Neither the name"),
    ("BSD-2-Clause", r"Redistribution and use in source and binary forms"),
    ("MIT", r"Permission is hereby granted, free of charge, to any person obtaining a copy"),
    (
        "ISC",
        r"Permission to use, copy, modify, and(?:/or)? distribute this software for any "
        r"purpose with or without fee is hereby granted, provided that",
    ),
    ("0BSD", r"Permission to use, copy, modify, and/or distribute this software for any purpose"),
    ("Unlicense", r"This is free and unencumbered software released into the public domain"),
    ("CC0-1.0", r"CC0 1\.0 Universal|Creative Commons.{0,80}CC0"),
    ("WTFPL", r"DO WHAT THE F[^\n]{0,4}CK YOU WANT TO PUBLIC LICENSE"),
]
_COMPILED_TEXT = [
    (spdx, re.compile(pat, re.IGNORECASE | re.DOTALL)) for spdx, pat in _TEXT_SIGNATURES
]
_WHITESPACE = re.compile(r"\s+")

# Free-text aliases -> canonical SPDX id, for the manifest / tag / classifier paths.
_SPDX_ALIASES = {
    "mit": "MIT",
    "mit license": "MIT",
    "expat": "MIT",
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "asl 2.0": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "isc": "ISC",
    "mpl-2.0": "MPL-2.0",
    "mpl 2.0": "MPL-2.0",
    "epl-2.0": "EPL-2.0",
    "lgpl-3.0": "LGPL-3.0",
    "lgplv3": "LGPL-3.0",
    "lgpl-2.1": "LGPL-2.1",
    "lgplv2.1": "LGPL-2.1",
    "gpl-3.0": "GPL-3.0",
    "gplv3": "GPL-3.0",
    "gpl-3.0-or-later": "GPL-3.0",
    "gpl-3.0-only": "GPL-3.0",
    "gpl-2.0": "GPL-2.0",
    "gplv2": "GPL-2.0",
    "gpl-2.0-or-later": "GPL-2.0",
    "agpl-3.0": "AGPL-3.0",
    "agplv3": "AGPL-3.0",
    "agpl-3.0-or-later": "AGPL-3.0",
    "agpl-3.0-only": "AGPL-3.0",
    "unlicense": "Unlicense",
    "the unlicense": "Unlicense",
    "cc0-1.0": "CC0-1.0",
    "cc0": "CC0-1.0",
    "0bsd": "0BSD",
    "wtfpl": "WTFPL",
    "bsl-1.0": "BSL-1.0",
    "boost": "BSL-1.0",
    "zlib": "Zlib",
    "python-2.0": "Python-2.0",
    "psf": "Python-2.0",
    "busl-1.1": "BUSL-1.1",
    "bsl-1.1": "BUSL-1.1",
    "sspl-1.0": "SSPL-1.0",
    "sspl": "SSPL-1.0",
    "elastic-2.0": "Elastic-2.0",
}

# Trove classifier tail (after "License :: OSI Approved :: ") -> canonical SPDX id.
_CLASSIFIER_SPDX = {
    "mit license": "MIT",
    "apache software license": "Apache-2.0",
    "bsd license": "BSD-3-Clause",
    "isc license (iscl)": "ISC",
    "gnu general public license v3 (gplv3)": "GPL-3.0",
    "gnu general public license v2 (gplv2)": "GPL-2.0",
    "gnu lesser general public license v3 (lgplv3)": "LGPL-3.0",
    "gnu lesser general public license v2 or later (lgplv2+)": "LGPL-2.1",
    "gnu affero general public license v3": "AGPL-3.0",
    "gnu affero general public license v3 or later (agpl v3+)": "AGPL-3.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "the unlicense (unlicense)": "Unlicense",
}

_LICENSE_DOC_EXT = (".md", ".txt", ".rst", ".markdown")
_MANIFEST_NAMES = {"pyproject.toml", "cargo.toml", "setup.cfg", "setup.py"}
_JSON_MANIFEST_NAMES = {"package.json", "composer.json"}
_CLASSIFIER_BEARING = {"pyproject.toml", "setup.cfg", "setup.py"}

_SPDX_TAG = re.compile(r"SPDX-License-Identifier:\s*([^\s\n*/]+(?:[ +][^\s\n*/]+)*)")
_JSON_LICENSE = re.compile(r'"license"\s*:\s*"([^"]+)"')
_JSON_LICENSE_OBJ = re.compile(r'"license"\s*:\s*\{[^}]*?"type"\s*:\s*"([^"]+)"', re.DOTALL)
_TOML_LICENSE = re.compile(r'(?m)^\s*license\s*=\s*"([^"]+)"')
_TOML_LICENSE_OBJ = re.compile(r'(?m)^\s*license\s*=\s*\{[^}]*?text\s*=\s*"([^"]+)"')
_CFG_LICENSE = re.compile(r"(?im)^\s*license\s*=\s*([^\n]+)$")
_CLASSIFIER = re.compile(r"License :: (?:OSI Approved :: )?([^\n\"']+?)(?:[\"',]|$)", re.MULTILINE)


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _is_license_file(path: str) -> bool:
    """True if a path is a license file by its name (``LICENSE``, ``COPYING``, ...)."""
    low = _basename(path).lower()
    for ext in _LICENSE_DOC_EXT:
        if low.endswith(ext):
            low = low[: -len(ext)]
            break
    return low in {
        "license",
        "licence",
        "copying",
        "copying.lesser",
        "unlicense",
    } or low.startswith(("license-", "licence-", "license.", "licence."))


def _normalize_spdx(token: str) -> str | None:
    """Map a free-text license token (``"Apache 2.0"``, ``"GPLv3"``) to a known SPDX id."""
    text = token.split("#", 1)[0].strip().strip("\"'").strip()
    # keep only the first term of an "A OR B" / "A WITH B" / "A/B" expression
    text = re.split(r"\s+(?:OR|AND|WITH)\s+|[/|]", text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    low = text.lower().rstrip("+")
    if low in _SPDX_ALIASES:
        return _SPDX_ALIASES[low]
    for spdx in _LICENSES:
        if spdx.lower() == low:
            return spdx
    return None


def _manifest_findings(path: str, content: str) -> list[tuple[str, int, str]]:
    """Pull (spdx, line, source_kind) license declarations out of one manifest file."""
    name = _basename(path).lower()
    out: list[tuple[str, int, str]] = []

    if name in _JSON_MANIFEST_NAMES:
        for rx in (_JSON_LICENSE, _JSON_LICENSE_OBJ):
            m = rx.search(content)
            if m and (spdx := _normalize_spdx(m.group(1))):
                out.append((spdx, _line_of(content, m.start()), "manifest"))
    elif name in {"pyproject.toml", "cargo.toml"}:
        for rx in (_TOML_LICENSE, _TOML_LICENSE_OBJ):
            m = rx.search(content)
            if m and (spdx := _normalize_spdx(m.group(1))):
                out.append((spdx, _line_of(content, m.start()), "manifest"))
    elif name == "setup.cfg":
        m = _CFG_LICENSE.search(content)
        if m and (spdx := _normalize_spdx(m.group(1))):
            out.append((spdx, _line_of(content, m.start()), "manifest"))

    if name in _CLASSIFIER_BEARING:
        for m in _CLASSIFIER.finditer(content):
            tail = m.group(1).strip().lower()
            spdx = _CLASSIFIER_SPDX.get(tail) or _normalize_spdx(tail)
            if spdx:
                out.append((spdx, _line_of(content, m.start()), "classifier"))
    return out


def find_licenses(file_contents: dict[str, str], *, limit: int = 30) -> dict:
    """Identify the project's own license(s) from its files.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many findings to return in the list.

    Returns ``{"total", "primary", "primary_category", "found", "categories", "notes"}``
    where each finding is ``{"spdx", "name", "name_zh", "category", "source_path",
    "source_kind", "line"}``. ``primary`` is the best single guess of the project's
    license (``""`` when none was found), and ``primary_category`` its family.
    """
    # (spdx-or-"unknown", source_path, source_kind, line), deduped by (spdx, path).
    raw: list[tuple[str, str, str, int]] = []
    seen: set[tuple[str, str]] = set()
    saw_license_file = False

    def add(spdx: str, path: str, kind: str, line: int) -> None:
        key = (spdx, path)
        if key in seen:
            return
        seen.add(key)
        raw.append((spdx, path, kind, line))

    for path, content in file_contents.items():
        if not content:
            continue
        name = _basename(path).lower()

        if _is_license_file(path):
            saw_license_file = True
            # License prose is wrapped at whatever column width its author chose,
            # so collapse runs of whitespace before matching the grant-clause
            # signatures — otherwise a line break in the middle of "any purpose"
            # would hide an otherwise obvious match.
            flat = _WHITESPACE.sub(" ", content)
            matched = next((spdx for spdx, rx in _COMPILED_TEXT if rx.search(flat)), None)
            add(matched or "unknown", path, "license-file", 1)

        if name in _MANIFEST_NAMES or name in _JSON_MANIFEST_NAMES:
            for spdx, line, kind in _manifest_findings(path, content):
                add(spdx, path, kind, line)

        tag = _SPDX_TAG.search(content)
        if tag and (spdx := _normalize_spdx(tag.group(1))):
            add(spdx, path, "spdx-tag", _line_of(content, tag.start()))

    findings = [
        {
            "spdx": spdx,
            "name": _LICENSES.get(spdx, ("未识别的许可证", "", "unknown"))[0],
            "name_zh": _LICENSES.get(spdx, ("", "未识别的许可证", "unknown"))[1],
            "category": _LICENSES.get(spdx, ("", "", "unknown"))[2],
            "source_path": path,
            "source_kind": kind,
            "line": line,
        }
        for spdx, path, kind, line in raw
    ]

    # Primary = the highest-priority source, shallowest path as the tie-break.
    priority = {"license-file": 0, "manifest": 1, "classifier": 2, "spdx-tag": 3}
    recognised = [f for f in findings if f["spdx"] != "unknown"]
    primary, primary_category = "", ""
    if recognised:
        best = min(
            recognised,
            key=lambda f: (priority.get(f["source_kind"], 9), f["source_path"].count("/")),
        )
        primary, primary_category = best["spdx"], best["category"]
    elif saw_license_file:
        primary, primary_category = "unknown", "unknown"

    findings.sort(key=lambda f: (priority.get(f["source_kind"], 9), f["source_path"]))
    categories = [c for c in _CATEGORY_ORDER if any(f["category"] == c for f in findings)]

    notes: list[str] = []
    if not findings:
        notes.append(
            "在扫描到的文件里没找到许可证。没有许可证 ≠ 免费随便用——默认是“保留所有权利”，"
            "别人原则上不能合法使用或分发。如果这是你的项目，建议补一个 LICENSE；"
            "如果你只上传了部分目录，许可证可能在仓库根目录。"
        )
    elif primary == "unknown":
        notes.append("找到了许可证文件但没认出是哪一种，请人工读一下原文，或联系作者确认。")
    notes.append("以上是大白话概括，不是法律意见；正式用途请读许可证原文或咨询法务。")

    return {
        "total": len({f["spdx"] for f in recognised}),
        "primary": primary,
        "primary_category": primary_category,
        "found": findings[:limit],
        "categories": categories,
        "notes": notes,
    }


def render_licenses_markdown(project_name: str, data: dict | None) -> str:
    """Render the license map as Markdown, or ``""`` if there is nothing to show."""
    if not isinstance(data, dict):
        return ""
    findings = data.get("found") or []
    primary = data.get("primary") or ""
    notes = data.get("notes") or []
    if not findings and not notes:
        return ""

    lines = [
        f"# {project_name} — 开源许可证：你能不能用、能不能商用",
        "",
        "> 许可证决定了你能拿这份代码做什么。下面把它翻成大白话——"
        "能不能商用、能不能闭源用、改了要不要公开、会不会“传染”你自己的项目。",
        "",
    ]

    if primary and primary != "unknown":
        name_zh = _LICENSES[primary][1]
        family = _CATEGORY[data.get("primary_category") or _LICENSES[primary][2]]
        lines.append(f"## 主许可证：{name_zh}（{family['label']}）")
        lines.append("")
        lines.append(f"> {family['one_line']}")
        lines.append("")
        lines.append(f"- 能不能商用：{family['commercial']}")
        lines.append(f"- 能不能用在闭源 / 私有项目里：{family['private_use']}")
        lines.append(f"- 改了代码必须公开吗：{family['share_changes']}")
        lines.append(f"- 会不会“传染”你自己的整个项目：{family['copyleft_scope']}")
        lines.append(f"- 必须保留 / 遵守：{family['keep_notice']}")
        lines.append("")
    elif primary == "unknown":
        lines.append("## 主许可证：未识别")
        lines.append("")
        lines.append(f"> {_CATEGORY['unknown']['one_line']}")
        lines.append("")
    else:
        lines.append("## ⚠ 没找到许可证")
        lines.append("")
        lines.append(
            "> 没有许可证不等于可以随便用——默认是“保留所有权利”，"
            "别人原则上不能合法使用或分发这份代码。"
        )
        lines.append("")

    if findings:
        lines.append("## 全部发现")
        for f in findings:
            label = f["name_zh"] or f["name"] or "未识别的许可证"
            where = _SOURCE_LABEL.get(f["source_kind"], f["source_kind"])
            loc = f"`{f['source_path']}`"
            if f["source_kind"] != "license-file":
                loc += f" 第 {f['line']} 行"
            lines.append(f"- {loc} — {label}（来自{where}）")
        lines.append("")

    if notes:
        lines.append("## 提醒")
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines).rstrip() + "\n"
