from backend.services.importgraph import (
    assign_architecture_layers,
    find_import_cycles,
    find_orphan_modules,
    rank_blast_radius,
    rank_coupling,
    rank_hotspots,
    suggest_reading_order,
    summarize_package_dependencies,
)
from backend.services.scanner import scan_uploaded_files


def _py(path, content=""):
    return {"path": path, "language": "python", "preview": content}


def _ts(path, content=""):
    return {"path": path, "language": "typescript", "preview": content}


def test_ranks_python_files_by_fan_in():
    files = [
        _py("app.py", "from utils import helper\nimport config\n"),
        _py("service.py", "from utils import helper\n"),
        _py("utils.py", "def helper():\n    return 1\n"),
        _py("config.py", "DEBUG = True\n"),
    ]

    hotspots = rank_hotspots(files)

    assert hotspots[0]["path"] == "utils.py"
    assert hotspots[0]["fan_in"] == 2
    assert hotspots[0]["dependents"] == ["app.py", "service.py"]
    assert hotspots[1]["path"] == "config.py"
    assert hotspots[1]["fan_in"] == 1


def test_ranks_files_by_fan_out_coupling():
    files = [
        _py("app.py", "from utils import helper\nimport config\n"),
        _py("service.py", "from utils import helper\n"),
        _py("utils.py", "def helper():\n    return 1\n"),
        _py("config.py", "DEBUG = True\n"),
    ]

    coupling = rank_coupling(files)

    # app.py imports two local modules (utils, config) -> highest coupling.
    assert coupling[0]["path"] == "app.py"
    assert coupling[0]["fan_out"] == 2
    assert coupling[0]["dependencies"] == ["config.py", "utils.py"]
    assert coupling[1]["path"] == "service.py"
    assert coupling[1]["fan_out"] == 1
    # leaf modules that import nothing local are omitted.
    assert {c["path"] for c in coupling}.isdisjoint({"utils.py", "config.py"})


def test_coupling_ignores_third_party_imports():
    files = [
        _py("app.py", "import os\nimport requests\nimport numpy as np\n"),
        _py("config.py", "DEBUG = True\n"),
    ]
    # Nothing imports a local module, so there is no coupling to report.
    assert rank_coupling(files) == []


def test_resolves_relative_and_package_imports():
    files = [
        _py("pkg/__init__.py", ""),
        _py("pkg/core.py", "def run():\n    pass\n"),
        _py("pkg/api.py", "from .core import run\n"),
        _py("pkg/cli.py", "from pkg.core import run\n"),
    ]

    hotspots = rank_hotspots(files)

    assert hotspots[0]["path"] == "pkg/core.py"
    assert hotspots[0]["fan_in"] == 2
    assert hotspots[0]["dependents"] == ["pkg/api.py", "pkg/cli.py"]


def test_from_package_import_resolves_to_submodule_not_init():
    files = [
        _py("pkg/__init__.py", ""),
        _py("pkg/models.py", "class User:\n    pass\n"),
        _py("consumer.py", "from pkg import models\n"),
    ]

    hotspots = rank_hotspots(files)
    paths = {h["path"] for h in hotspots}

    assert paths == {"pkg/models.py"}


def test_third_party_and_stdlib_imports_are_ignored():
    files = [
        _py("main.py", "import os\nimport sys\nfrom collections import defaultdict\n"),
        _py("helper.py", "x = 1\n"),
    ]

    assert rank_hotspots(files) == []


def test_self_import_does_not_count():
    files = [_py("solo.py", "import solo\n")]

    assert rank_hotspots(files) == []


def test_resolves_js_imports_with_extension_and_index():
    main = (
        "import { run } from './app';\nimport store from './store';\nimport React from 'react';\n"
    )
    files = [
        _ts("src/main.ts", main),
        _ts("src/app.ts", "import store from './store';\n"),
        _ts("src/store/index.ts", "export const store = {};\n"),
    ]

    hotspots = rank_hotspots(files)

    assert hotspots[0]["path"] == "src/store/index.ts"
    assert hotspots[0]["fan_in"] == 2
    assert hotspots[0]["dependents"] == ["src/app.ts", "src/main.ts"]
    assert hotspots[1]["path"] == "src/app.ts"
    assert hotspots[1]["fan_in"] == 1


def test_resolves_require_and_dynamic_import():
    files = [
        {"path": "a.js", "language": "javascript", "preview": "const b = require('./b');\n"},
        {"path": "c.js", "language": "javascript", "preview": "const m = await import('./b');\n"},
        {"path": "b.js", "language": "javascript", "preview": "module.exports = {};\n"},
    ]

    hotspots = rank_hotspots(files)

    assert hotspots[0]["path"] == "b.js"
    assert hotspots[0]["fan_in"] == 2


def test_parent_relative_import_walks_up():
    files = [
        _py("pkg/shared.py", "VALUE = 1\n"),
        _py("pkg/sub/worker.py", "from ..shared import VALUE\n"),
    ]

    hotspots = rank_hotspots(files)

    assert hotspots[0]["path"] == "pkg/shared.py"
    assert hotspots[0]["fan_in"] == 1


def test_ties_break_by_path_and_limit_is_respected():
    files = [
        _py("a.py", "import core\n"),
        _py("b.py", "import core\n"),
        _py("first.py", "import b\n"),
        _py("second.py", "import a\n"),
        _py("core.py", "x = 1\n"),
    ]

    # core has fan_in 2; a and b each have fan_in 1 -> tie broken by path
    hotspots = rank_hotspots(files, limit=2)

    assert len(hotspots) == 2
    assert hotspots[0]["path"] == "core.py"
    assert hotspots[1]["path"] == "a.py"


def test_finds_imports_when_preview_is_truncated():
    # imports sit at the top, so the scanner's 80-line preview still captures them
    body = "\n".join(f"    x{i} = {i}" for i in range(200))
    files = scan_uploaded_files(
        [
            {"path": "utils.py", "content": "def helper():\n    return 1\n"},
            {"path": "big.py", "content": f"from utils import helper\n\ndef work():\n{body}\n"},
        ]
    )

    hotspots = rank_hotspots(files)

    assert hotspots[0]["path"] == "utils.py"
    assert hotspots[0]["fan_in"] == 1
    assert "big.py" in hotspots[0]["dependents"]


def test_reading_order_starts_at_entry_point():
    files = [
        _py("app.py", "from utils import helper\nimport config\n"),
        _py("utils.py", "def helper():\n    return 1\n"),
        _py("config.py", "DEBUG = True\n"),
    ]

    order = suggest_reading_order(files)

    assert order[0]["path"] == "app.py"
    assert order[0]["role"] == "entry"
    assert order[0]["step"] == 1
    paths = [s["path"] for s in order]
    # the modules the entry imports are read after it
    assert paths.index("app.py") < paths.index("utils.py")
    assert paths.index("app.py") < paths.index("config.py")
    roles = {s["path"]: s["role"] for s in order}
    assert roles["utils.py"] == "leaf"
    assert roles["config.py"] == "leaf"


def test_reading_order_prefers_conventional_entry_names():
    # nothing imports either top-level file; main.py should be read first
    files = [
        _py("zzz_top.py", "from lib import x\n"),
        _py("main.py", "from lib import x\n"),
        _py("lib.py", "x = 1\n"),
    ]

    order = suggest_reading_order(files)

    assert order[0]["path"] == "main.py"
    assert order[0]["role"] == "entry"


def test_reading_order_keeps_every_file_despite_cycles():
    files = [
        _py("a.py", "import b\n"),
        _py("b.py", "import a\n"),
    ]

    order = suggest_reading_order(files)

    assert {s["path"] for s in order} == {"a.py", "b.py"}
    assert [s["step"] for s in order] == [1, 2]


def test_cycles_detect_two_file_cycle():
    files = [
        _py("a.py", "import b\n"),
        _py("b.py", "import a\n"),
    ]

    cycles = find_import_cycles(files)

    assert len(cycles) == 1
    assert cycles[0]["files"] == ["a.py", "b.py"]
    assert cycles[0]["size"] == 2


def test_cycles_none_for_acyclic_graph():
    files = [
        _py("main.py", "from lib import x\n"),
        _py("lib.py", "x = 1\n"),
    ]

    assert find_import_cycles(files) == []


def test_cycles_detect_three_file_cycle_and_ignore_acyclic_tail():
    files = [
        _py("a.py", "import b\n"),
        _py("b.py", "import c\n"),
        _py("c.py", "import a\nimport util\n"),
        _py("util.py", "x = 1\n"),  # depended on, not part of the cycle
    ]

    cycles = find_import_cycles(files)

    assert len(cycles) == 1
    assert cycles[0]["files"] == ["a.py", "b.py", "c.py"]
    assert cycles[0]["size"] == 3


def test_cycles_report_disjoint_cycles_largest_first():
    files = [
        # 3-file cycle
        _py("x.py", "import y\n"),
        _py("y.py", "import z\n"),
        _py("z.py", "import x\n"),
        # 2-file cycle
        _py("p.py", "import q\n"),
        _py("q.py", "import p\n"),
    ]

    cycles = find_import_cycles(files)

    assert [c["size"] for c in cycles] == [3, 2]
    assert cycles[0]["files"] == ["x.py", "y.py", "z.py"]
    assert cycles[1]["files"] == ["p.py", "q.py"]


def test_orphans_detect_isolated_file():
    files = [
        _py("app.py", "from utils import helper\n"),
        _py("utils.py", "def helper():\n    return 1\n"),
        _py("scratch.py", "print('standalone')\n"),  # nothing imports it, imports nothing
    ]

    orphans = find_orphan_modules(files)

    assert [o["path"] for o in orphans] == ["scratch.py"]
    assert orphans[0]["language"] == "python"


def test_orphans_exclude_entry_points_and_leaves():
    # app imports utils: app is an entry (has out-edges), utils is a leaf (has in-edges)
    files = [
        _py("app.py", "from utils import helper\n"),
        _py("utils.py", "def helper():\n    return 1\n"),
    ]

    assert find_orphan_modules(files) == []


def test_orphans_ignore_non_code_files():
    files = [
        _py("app.py", "from utils import helper\n"),
        _py("utils.py", "def helper():\n    return 1\n"),
        {"path": "README.md", "language": "markdown", "preview": "# Docs\n"},
    ]

    # a docs file has no imports, but it must not be reported as an orphan module
    assert find_orphan_modules(files) == []


def test_orphans_detect_isolated_js_module():
    files = [
        _ts("src/main.ts", "import { run } from './app';\n"),
        _ts("src/app.ts", "export const run = () => {};\n"),
        _ts("src/legacy.ts", "export const dead = 1;\n"),  # disconnected
    ]

    orphans = find_orphan_modules(files)

    assert [o["path"] for o in orphans] == ["src/legacy.ts"]


def test_blast_radius_counts_transitive_dependents():
    files = [
        _py("a.py", "import b\n"),
        _py("b.py", "import c\n"),
        _py("c.py", "x = 1\n"),
    ]

    blast = rank_blast_radius(files)

    # c is imported by b directly and by a transitively -> blast radius 2.
    assert blast[0]["path"] == "c.py"
    assert blast[0]["blast_radius"] == 2
    assert blast[0]["direct_dependents"] == ["b.py"]
    # b is only reached through a.
    assert blast[1]["path"] == "b.py"
    assert blast[1]["blast_radius"] == 1
    # nothing depends on the entry point a, so it is omitted.
    assert {h["path"] for h in blast}.isdisjoint({"a.py"})


def test_blast_radius_handles_cycles_without_looping():
    files = [
        _py("a.py", "import b\n"),
        _py("b.py", "import a\n"),
    ]

    blast = rank_blast_radius(files)
    by_path = {h["path"]: h for h in blast}

    # a and b import each other; each counts only the other, the cycle neither
    # inflates the radius nor hangs the reverse walk.
    assert by_path["a.py"]["blast_radius"] == 1
    assert by_path["b.py"]["blast_radius"] == 1


def test_architecture_layers_stratify_dependency_chain():
    files = [
        _py("a.py", "import b\n"),
        _py("b.py", "import c\n"),
        _py("c.py", "x = 1\n"),
    ]

    layers = assign_architecture_layers(files)
    by_layer = {h["path"]: h["layer"] for h in layers}

    # c imports nothing local (foundation), b sits on c, a sits on b.
    assert by_layer == {"a.py": 2, "b.py": 1, "c.py": 0}
    # highest layer (closest to the entry point) is returned first.
    assert [h["path"] for h in layers] == ["a.py", "b.py", "c.py"]


def test_architecture_layers_condense_cycles_into_one_layer():
    files = [
        _py("a.py", "import b\nimport c\n"),
        _py("b.py", "import a\n"),
        _py("c.py", "x = 1\n"),
    ]

    layers = assign_architecture_layers(files)
    by_layer = {h["path"]: h["layer"] for h in layers}

    # a and b form a cycle; condensed to a single node that sits one layer above
    # the leaf c, so they share a layer instead of inflating into two.
    assert by_layer["c.py"] == 0
    assert by_layer["a.py"] == by_layer["b.py"] == 1


def test_package_dependencies_aggregate_to_directories():
    files = [
        _py("app/main.py", "from db.session import get\nfrom auth.login import check\n"),
        _py("auth/login.py", "from db.session import get\n"),
        _py("db/session.py", "POOL = 1\n"),
    ]

    pkgs = summarize_package_dependencies(files)
    by_pkg = {p["package"]: p for p in pkgs}

    # db is the foundation: two directories lean on it, it leans on nobody.
    assert by_pkg["db"]["depended_on_by"] == ["app", "auth"]
    assert by_pkg["db"]["depends_on"] == []
    assert by_pkg["db"]["fan_in"] == 2
    # app is the entry point: it pulls in both other directories.
    assert by_pkg["app"]["depends_on"] == ["auth", "db"]
    assert by_pkg["app"]["fan_in"] == 0
    # auth sits in the middle, depending on db and depended on by app.
    assert by_pkg["auth"]["depends_on"] == ["db"]
    assert by_pkg["auth"]["depended_on_by"] == ["app"]


def test_package_dependencies_ignore_same_directory_imports():
    files = [
        _py("pkg/a.py", "import pkg.b\n"),
        _py("pkg/b.py", "x = 1\n"),
    ]

    # The only edge is within a single directory, so there is no cross-package
    # structure to report.
    assert summarize_package_dependencies(files) == []
