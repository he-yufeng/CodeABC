"""Tests for the tunable-settings (hard-coded constants) map."""

from backend.services.settings_map import find_tunable_settings, render_settings_markdown


def test_python_module_level_constants_by_kind():
    src = """
MAX_RETRIES = 3
DEFAULT_MODEL = "gpt-5"
DEBUG = False
TIMEOUT_SECONDS: float = 30.0
"""
    result = find_tunable_settings({"config.py": src})
    by_name = {s["name"]: s for s in result["settings"]}
    assert set(by_name) == {"MAX_RETRIES", "DEFAULT_MODEL", "DEBUG", "TIMEOUT_SECONDS"}
    assert by_name["MAX_RETRIES"]["kind"] == "number"
    assert by_name["MAX_RETRIES"]["value"] == "3"
    assert by_name["DEFAULT_MODEL"]["kind"] == "text"
    assert by_name["DEFAULT_MODEL"]["value"] == '"gpt-5"'
    assert by_name["DEBUG"]["kind"] == "flag"
    assert by_name["DEBUG"]["value"] == "False"
    assert by_name["TIMEOUT_SECONDS"]["kind"] == "number"  # AnnAssign form
    assert by_name["MAX_RETRIES"]["path"] == "config.py"
    assert by_name["MAX_RETRIES"]["line"] == 2


def test_list_and_mapping_literals():
    src = """
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
RETRY_BACKOFF = {"base": 1, "factor": 2}
"""
    by_name = {s["name"]: s for s in find_tunable_settings({"c.py": src})["settings"]}
    assert by_name["ALLOWED_HOSTS"]["kind"] == "list"
    assert by_name["RETRY_BACKOFF"]["kind"] == "mapping"


def test_skips_non_constants_and_non_literals():
    src = """
import os

PAGE_SIZE = 20                      # kept: a literal constant
BASE = 10
DERIVED = BASE * 2                  # computed, not a literal -> skipped
Vector = list                       # not UPPER_SNAKE -> skipped
N = 5                               # single-ish, too short -> skipped
PLACEHOLDER = None                  # None sentinel -> skipped
RETRIES = int(os.getenv("R", "3"))  # call, not a literal -> skipped
lower_case = 1                      # not a constant name -> skipped

def helper():
    LOCAL_CONST = 99                # inside a function -> skipped
    return LOCAL_CONST

class Cfg:
    CLASS_CONST = 7                 # inside a class -> skipped
"""
    names = {s["name"] for s in find_tunable_settings({"c.py": src})["settings"]}
    assert names == {"PAGE_SIZE", "BASE"}


def test_js_top_level_consts():
    src = """
export const PAGE_SIZE = 20;
const DEBUG_MODE = false;
const API_BASE = "https://api.example.com";
const SETTINGS = { a: 1 };        // object -> skipped
const GREETING = `hi ${name}`;    // template interpolation -> skipped

function f() {
  const INNER = 5;                // indented -> skipped
  return INNER;
}
"""
    by_name = {s["name"]: s for s in find_tunable_settings({"app.ts": src})["settings"]}
    assert set(by_name) == {"PAGE_SIZE", "DEBUG_MODE", "API_BASE"}
    assert by_name["PAGE_SIZE"]["kind"] == "number"
    assert by_name["DEBUG_MODE"]["kind"] == "flag"
    assert by_name["API_BASE"]["kind"] == "text"
    assert by_name["API_BASE"]["value"] == '"https://api.example.com"'


def test_sorted_by_path_then_line_and_total_and_kinds():
    files = {
        "b.py": "SECOND = 2\nFIRST_OF_B = 1\n",
        "a.py": "ALPHA = 1\nBETA = 2\n",
    }
    result = find_tunable_settings(files)
    order = [(s["path"], s["name"]) for s in result["settings"]]
    assert order == [
        ("a.py", "ALPHA"),
        ("a.py", "BETA"),
        ("b.py", "SECOND"),
        ("b.py", "FIRST_OF_B"),
    ]
    assert result["total"] == 4
    assert result["kinds"] == ["number"]


def test_limit_caps_the_list_but_total_counts_all():
    src = "\n".join(f"CONST_{i} = {i}" for i in range(10))
    result = find_tunable_settings({"c.py": src}, limit=3)
    assert result["total"] == 10
    assert len(result["settings"]) == 3


def test_syntax_error_file_is_skipped_not_crashed():
    files = {"broken.py": "MAX = (((", "ok.py": "GOOD = 1\n"}
    names = {s["name"] for s in find_tunable_settings(files)["settings"]}
    assert names == {"GOOD"}


def test_long_string_value_is_truncated():
    src = 'BANNER = "' + "x" * 100 + '"\n'
    setting = find_tunable_settings({"c.py": src})["settings"][0]
    assert setting["value"].endswith('..."')
    assert len(setting["value"]) <= 64


def test_markdown_render_empty_and_grouped():
    assert render_settings_markdown("Proj", {"settings": []}) == ""
    assert render_settings_markdown("Proj", None) == ""

    data = find_tunable_settings({"config.py": 'MAX_RETRIES = 3\nDEFAULT_MODEL = "x"\n'})
    md = render_settings_markdown("Proj", data)
    assert "# Proj — 能改哪些值（可调设置）" in md
    assert "`config.py`" in md
    assert "`MAX_RETRIES` = 3" in md
    assert "`DEFAULT_MODEL`" in md
