"""Tests for the external-services (integrations) detection."""

from __future__ import annotations

from backend.services.integrations import (
    detect_external_services,
    render_integrations_markdown,
)


def _names(result: dict) -> set[str]:
    return {s["name"] for s in result["services"]}


def test_detects_python_import_openai():
    result = detect_external_services({"a.py": "import openai\nx = 1\n"})
    assert "OpenAI" in _names(result)
    assert result["total"] == 1


def test_detects_python_from_import_anthropic():
    result = detect_external_services({"a.py": "from anthropic import Anthropic\n"})
    assert "Anthropic" in _names(result)


def test_detects_boto3_as_aws():
    result = detect_external_services({"a.py": "import boto3\n"})
    assert "AWS" in _names(result)
    assert result["services"][0]["category"] == "云服务"


def test_detects_dotted_google_cloud():
    result = detect_external_services({"a.py": "from google.cloud import storage\n"})
    assert "Google Cloud" in _names(result)


def test_detects_js_require_and_import():
    r1 = detect_external_services({"a.js": "const stripe = require('stripe')\n"})
    assert "Stripe" in _names(r1)
    r2 = detect_external_services({"a.ts": "import OpenAI from 'openai'\n"})
    assert "OpenAI" in _names(r2)


def test_relative_imports_not_detected():
    result = detect_external_services({"a.ts": "import { foo } from './openai-helper'\n"})
    assert result["total"] == 0


def test_detects_go_import_via_path_segment():
    src = 'import (\n\t"github.com/redis/go-redis/v9"\n)\n'
    result = detect_external_services({"main.go": src})
    assert "Redis" in _names(result)


def test_detects_service_by_hostname():
    src = 'URL = "https://api.openai.com/v1/chat/completions"\n'
    result = detect_external_services({"a.py": src})
    assert "OpenAI" in _names(result)


def test_unknown_imports_are_ignored():
    result = detect_external_services({"a.py": "import os\nimport json\nimport mypackage\n"})
    assert result["total"] == 0
    assert result["notes"]  # reassuring "probably runs offline" note


def test_test_files_are_skipped():
    result = detect_external_services({"tests/test_a.py": "import openai\n"})
    assert result["total"] == 0


def test_non_code_files_ignored():
    result = detect_external_services({"README.md": "import openai\n", "data.json": "{}"})
    assert result["total"] == 0


def test_file_count_aggregates_across_files():
    result = detect_external_services(
        {"a.py": "import openai\n", "b.py": "import openai\n", "c.py": "import stripe\n"}
    )
    openai = next(s for s in result["services"] if s["name"] == "OpenAI")
    assert openai["file_count"] == 2
    # most-used first
    assert result["services"][0]["name"] == "OpenAI"


def test_categories_counted():
    result = detect_external_services({"a.py": "import openai\nimport boto3\nimport stripe\n"})
    assert result["categories"].get("云服务") == 1
    assert result["categories"].get("支付") == 1


def test_same_service_deduped_across_import_styles():
    src = "import openai\nfrom openai import OpenAI\nx = 'https://api.openai.com'\n"
    result = detect_external_services({"a.py": src})
    assert _names(result) == {"OpenAI"}
    assert result["total"] == 1


def test_render_markdown_empty_when_none():
    result = detect_external_services({"a.py": "x = 1\n"})
    assert render_integrations_markdown("proj", result) == ""


def test_render_markdown_lists_services_in_plain_language():
    result = detect_external_services({"a.py": "import openai\nimport boto3\n"})
    md = render_integrations_markdown("proj", result)
    assert "proj — 外部服务依赖" in md
    assert "OpenAI" in md and "AWS" in md
    assert "密钥" in md  # beginner-friendly explanation present


def test_render_markdown_none_safe():
    assert render_integrations_markdown("proj", None) == ""
