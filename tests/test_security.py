"""Tests for backend.services.security — security-pattern scanner."""

from __future__ import annotations

from backend.services.security import (
    _is_real_secret,
    _is_test_file,
    render_security_markdown,
    scan_security,
)

# ---------------------------------------------------------------------------
# _is_real_secret helper
# ---------------------------------------------------------------------------


class TestIsRealSecret:
    def test_too_short_returns_false(self):
        assert not _is_real_secret("abc")

    def test_empty_returns_false(self):
        assert not _is_real_secret("")

    def test_your_placeholder_returns_false(self):
        assert not _is_real_secret("YOUR_API_KEY_HERE")

    def test_angle_bracket_placeholder_returns_false(self):
        assert not _is_real_secret("<your-token>")

    def test_curly_placeholder_returns_false(self):
        assert not _is_real_secret("{api_key}")

    def test_example_returns_false(self):
        assert not _is_real_secret("example-value-here-extra")

    def test_uniform_chars_returns_false(self):
        assert not _is_real_secret("xxxxxxxxxxxx")

    def test_real_looking_secret_returns_true(self):
        assert _is_real_secret("sk-abc123xyz789qrs")

    def test_hex_string_returns_true(self):
        assert _is_real_secret("a3f8c2d1e9b74f50")

    def test_changeme_returns_false(self):
        assert not _is_real_secret("changeme-secret-value")


# ---------------------------------------------------------------------------
# _is_test_file helper
# ---------------------------------------------------------------------------


class TestIsTestFile:
    def test_test_prefix(self):
        assert _is_test_file("tests/test_auth.py")

    def test_test_directory(self):
        assert _is_test_file("src/tests/auth.py")

    def test_spec_suffix_ts(self):
        assert _is_test_file("src/auth.spec.ts")

    def test_normal_file_is_not_test(self):
        assert not _is_test_file("src/auth.py")

    def test_test_suffix(self):
        assert _is_test_file("auth_test.py")


# ---------------------------------------------------------------------------
# scan_security — hardcoded_secret
# ---------------------------------------------------------------------------


class TestHardcodedSecret:
    def test_detects_plain_password_assignment(self):
        code = 'db_password = "s3cr3t!abc123"\n'
        result = scan_security({"app.py": code})
        assert result["total"] == 1
        assert result["findings"][0]["category"] == "hardcoded_secret"
        assert result["critical"] == 1

    def test_detects_api_key(self):
        code = 'api_key = "sk-realkey-abc123xyz789"\n'
        result = scan_security({"config.py": code})
        assert any(f["category"] == "hardcoded_secret" for f in result["findings"])

    def test_detects_token(self):
        code = 'access_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"\n'
        result = scan_security({"auth.py": code})
        assert result["total"] >= 1
        assert result["findings"][0]["category"] == "hardcoded_secret"

    def test_skips_placeholder_value(self):
        code = 'password = "YOUR_PASSWORD_HERE"\n'
        result = scan_security({"app.py": code})
        assert result["total"] == 0

    def test_skips_env_read(self):
        code = 'password = os.getenv("DB_PASSWORD")\n'
        result = scan_security({"app.py": code})
        assert result["total"] == 0

    def test_skips_very_short_string(self):
        code = 'token = "abc"\n'
        result = scan_security({"app.py": code})
        assert result["total"] == 0

    def test_skips_comment_line(self):
        code = '# password = "hardcoded_secret_in_comment"\n'
        result = scan_security({"app.py": code})
        assert result["total"] == 0

    def test_type_annotated_secret_detected(self):
        code = 'secret_key: str = "super-secret-xyz9abc8"\n'
        result = scan_security({"settings.py": code})
        assert result["total"] == 1
        assert result["findings"][0]["category"] == "hardcoded_secret"


# ---------------------------------------------------------------------------
# scan_security — dangerous_call
# ---------------------------------------------------------------------------


class TestDangerousCall:
    def test_eval_detected(self):
        code = "result = eval(user_input)\n"
        result = scan_security({"handler.py": code})
        assert any(f["category"] == "dangerous_call" for f in result["findings"])

    def test_exec_detected(self):
        code = "exec(untrusted_code)\n"
        result = scan_security({"run.py": code})
        assert any(f["category"] == "dangerous_call" for f in result["findings"])

    def test_pickle_loads_detected(self):
        code = "obj = pickle.loads(data)\n"
        result = scan_security({"cache.py": code})
        assert any(f["category"] == "dangerous_call" for f in result["findings"])

    def test_pickle_load_detected(self):
        code = "obj = pickle.load(f)\n"
        result = scan_security({"cache.py": code})
        assert any(f["category"] == "dangerous_call" for f in result["findings"])

    def test_yaml_load_detected(self):
        code = "cfg = yaml.load(stream)\n"
        result = scan_security({"loader.py": code})
        assert any(f["category"] == "dangerous_call" for f in result["findings"])

    def test_yaml_safe_load_not_detected(self):
        code = "cfg = yaml.safe_load(stream)\n"
        result = scan_security({"loader.py": code})
        assert result["total"] == 0

    def test_eval_in_comment_skipped(self):
        code = "# eval(dangerous) — do not use\n"
        result = scan_security({"app.py": code})
        assert result["total"] == 0


# ---------------------------------------------------------------------------
# scan_security — shell_injection
# ---------------------------------------------------------------------------


class TestShellInjection:
    def test_os_system_detected(self):
        code = "os.system(cmd)\n"
        result = scan_security({"util.py": code})
        assert any(f["category"] == "shell_injection" for f in result["findings"])

    def test_os_popen_detected(self):
        code = "proc = os.popen(cmd)\n"
        result = scan_security({"util.py": code})
        assert any(f["category"] == "shell_injection" for f in result["findings"])

    def test_subprocess_shell_true_detected(self):
        code = "subprocess.run(cmd, shell=True)\n"
        result = scan_security({"deploy.py": code})
        assert any(f["category"] == "shell_injection" for f in result["findings"])

    def test_subprocess_shell_false_not_detected(self):
        code = 'subprocess.run(["ls", "-la"], shell=False)\n'
        result = scan_security({"deploy.py": code})
        assert result["total"] == 0

    def test_os_system_in_comment_skipped(self):
        code = "# os.system(cmd)  # avoid this\n"
        result = scan_security({"util.py": code})
        assert result["total"] == 0


# ---------------------------------------------------------------------------
# scan_security — debug_mode
# ---------------------------------------------------------------------------


class TestDebugMode:
    def test_debug_true_detected(self):
        code = "DEBUG = True\n"
        result = scan_security({"settings.py": code})
        assert any(f["category"] == "debug_mode" for f in result["findings"])

    def test_app_debug_detected(self):
        code = "app.debug = True\n"
        result = scan_security({"app.py": code})
        assert any(f["category"] == "debug_mode" for f in result["findings"])

    def test_app_run_debug_detected(self):
        code = 'app.run(host="0.0.0.0", debug=True)\n'
        result = scan_security({"main.py": code})
        assert any(f["category"] == "debug_mode" for f in result["findings"])

    def test_debug_false_not_detected(self):
        code = "DEBUG = False\n"
        result = scan_security({"settings.py": code})
        assert result["total"] == 0

    def test_debug_in_test_file_not_critical(self):
        # debug_mode in test files is skipped entirely
        code = "DEBUG = True\n"
        result = scan_security({"tests/test_settings.py": code})
        assert result["critical"] == 0
        # should not appear in findings (test files skipped for debug_mode)
        assert not any(f["category"] == "debug_mode" for f in result["findings"])


# ---------------------------------------------------------------------------
# scan_security — multi-file and edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_contents_returns_zero(self):
        result = scan_security({})
        assert result["total"] == 0
        assert result["critical"] == 0
        assert result["findings"] == []

    def test_empty_file_content_skipped(self):
        result = scan_security({"app.py": ""})
        assert result["total"] == 0

    def test_findings_sorted_critical_first(self):
        code = "DEBUG = True\ndb_password = 'realp4ssw0rdxyz'\n"
        result = scan_security({"app.py": code})
        cats = [f["category"] for f in result["findings"]]
        # hardcoded_secret (weight 0) must come before debug_mode (weight 3)
        assert cats.index("hardcoded_secret") < cats.index("debug_mode")

    def test_limit_caps_findings(self):
        # 5 separate files each with a secret
        contents = {f"file{i}.py": f'api_key = "secretkey{i}abcxyz"\n' for i in range(10)}
        result = scan_security(contents, limit=4)
        assert len(result["findings"]) == 4
        assert result["total"] == 10  # total is before capping

    def test_deduplication_same_file_line(self):
        # A line that could match multiple patterns still produces one finding per category.
        code = "eval(pickle.loads(data))\n"
        result = scan_security({"app.py": code})
        # eval and pickle.loads are both dangerous_call; dedup keeps only one per (file, line, cat)
        matches = [f for f in result["findings"] if f["category"] == "dangerous_call"]
        lines = [(f["file"], f["line"]) for f in matches]
        assert len(lines) == len(set(lines))  # at most one per (file, line)

    def test_snippet_truncated(self):
        long_line = "password = " + '"' + "x" * 8 + "realpart" + "y" * 200 + '"' + "\n"
        result = scan_security({"app.py": long_line})
        if result["findings"]:
            assert len(result["findings"][0]["snippet"]) <= 121  # 120 + "…"


# ---------------------------------------------------------------------------
# scan_security — notes
# ---------------------------------------------------------------------------


class TestNotes:
    def test_clean_code_returns_clean_note(self):
        result = scan_security({"clean.py": "x = 1\n"})
        assert result["notes"]
        assert result["total"] == 0
        # Should mention "未发现" or similar
        assert any("未发现" in note for note in result["notes"])

    def test_notes_mention_critical_count(self):
        code = 'db_password = "s3cr3t!abc123"\n'
        result = scan_security({"app.py": code})
        assert any("高危" in note for note in result["notes"])


# ---------------------------------------------------------------------------
# render_security_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_no_findings_returns_empty(self):
        data = {"total": 0, "critical": 0, "findings": [], "notes": []}
        assert render_security_markdown("MyProject", data) == ""

    def test_none_returns_empty(self):
        assert render_security_markdown("MyProject", None) == ""

    def test_renders_heading(self):
        data = {
            "total": 1,
            "critical": 1,
            "findings": [
                {
                    "file": "app.py",
                    "line": 10,
                    "category": "hardcoded_secret",
                    "snippet": "password = 'abc123xyz'",
                    "reason": "test reason",
                }
            ],
            "notes": ["note one"],
        }
        md = render_security_markdown("MyProject", data)
        assert "# 安全风险" in md
        assert "app.py:10" in md
        assert "hardcoded_secret" in md or "硬编码凭据" in md
        assert "note one" in md
