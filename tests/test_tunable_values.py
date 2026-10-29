"""Tests for the tunable-value scanner."""

from __future__ import annotations

from backend.services.tunable_values import scan_tunable_values


class TestUrlDetection:
    def test_finds_https_url(self):
        report = scan_tunable_values({"app.py": 'API = "https://api.example.com/v1"'})
        urls = [v for v in report.values if v.category == "url"]
        assert len(urls) == 1
        assert urls[0].value == "https://api.example.com/v1"

    def test_finds_http_url(self):
        report = scan_tunable_values({"a.py": 'url = "http://localhost:8080/health"'})
        assert any(v.category == "url" for v in report.values)

    def test_url_in_comment_ignored(self):
        report = scan_tunable_values({"a.py": "# see https://docs.example.com for details"})
        assert not any(v.category == "url" for v in report.values)


class TestTimeoutDetection:
    def test_finds_timeout_keyword(self):
        report = scan_tunable_values({"a.py": "resp = client.get(url, timeout=30)"})
        timeouts = [v for v in report.values if v.category == "timeout"]
        assert len(timeouts) == 1
        assert "30" in timeouts[0].value

    def test_finds_sleep_call(self):
        report = scan_tunable_values({"a.py": "sleep(2.5)"})
        timeouts = [v for v in report.values if v.category == "timeout"]
        assert len(timeouts) == 1

    def test_finds_ttl(self):
        report = scan_tunable_values({"a.py": "cache_ttl = 3600"})
        assert any(v.category == "timeout" for v in report.values)


class TestLimitDetection:
    def test_finds_max_retries(self):
        report = scan_tunable_values({"a.py": "max_retries = 3"})
        limits = [v for v in report.values if v.category == "limit"]
        assert len(limits) == 1

    def test_finds_threshold(self):
        report = scan_tunable_values({"a.py": "threshold = 0.85"})
        assert any(v.category == "limit" for v in report.values)

    def test_finds_batch_size(self):
        report = scan_tunable_values({"a.py": "batch_size = 64"})
        assert any(v.category == "limit" for v in report.values)


class TestPathDetection:
    def test_finds_absolute_path(self):
        report = scan_tunable_values({"a.py": 'LOG = "/var/log/myapp/app.log"'})
        paths = [v for v in report.values if v.category == "path"]
        assert len(paths) == 1

    def test_finds_project_relative_path(self):
        report = scan_tunable_values({"a.py": 'f = open("src/data/input.csv")'})
        assert any(v.category == "path" for v in report.values)


class TestContactDetection:
    def test_finds_email(self):
        report = scan_tunable_values({"a.py": 'SUPPORT = "help@example.com"'})
        contacts = [v for v in report.values if v.category == "contact"]
        assert len(contacts) == 1
        assert contacts[0].value == "help@example.com"


class TestVersionDetection:
    def test_finds_semver(self):
        report = scan_tunable_values({"a.py": '__version__ = "1.2.3"'})
        versions = [v for v in report.values if v.category == "version"]
        assert len(versions) == 1
        assert versions[0].value == "1.2.3"


class TestNumberFallback:
    def test_plain_number_when_nothing_else(self):
        report = scan_tunable_values({"a.py": "port = 8080"})
        numbers = [v for v in report.values if v.category == "number"]
        assert len(numbers) == 1

    def test_no_number_when_other_category_matched(self):
        # URL already matched, so the trailing digits in the path should not
        # also appear as a plain number.
        report = scan_tunable_values({"a.py": 'url = "https://api.example.com:8443"'})
        numbers = [v for v in report.values if v.category == "number"]
        assert not numbers


class TestFiltering:
    def test_skips_comments(self):
        report = scan_tunable_values({"a.py": "# TODO: change timeout=999"})
        assert not report.values

    def test_skips_lock_files(self):
        report = scan_tunable_values({"package-lock.json": '"version": "1.2.3"'})
        assert not report.values

    def test_skips_non_source_extensions(self):
        report = scan_tunable_values({"image.png": "binary data 12345"})
        assert not report.values

    def test_skips_empty_lines(self):
        report = scan_tunable_values({"a.py": "\n\n   \n"})
        assert not report.values


class TestReport:
    def test_category_counts(self):
        report = scan_tunable_values(
            {
                "a.py": 'url = "https://x.com"\ntimeout = 30',
            }
        )
        counts = report.category_counts
        assert counts.get("url", 0) == 1
        assert counts.get("timeout", 0) == 1

    def test_by_category(self):
        report = scan_tunable_values({"a.py": 'url = "https://x.com"'})
        grouped = report.by_category()
        assert "url" in grouped
        assert len(grouped["url"]) == 1

    def test_snippet_is_truncated(self):
        long_line = 'x = "' + "a" * 200 + '"'
        report = scan_tunable_values({"a.py": long_line})
        if report.values:
            assert len(report.values[0].snippet) <= 120

    def test_file_and_line_recorded(self):
        report = scan_tunable_values({"a.py": "x = 1\ntimeout = 5\n"})
        timeouts = [v for v in report.values if v.category == "timeout"]
        assert timeouts[0].line == 2
        assert timeouts[0].file == "a.py"
