"""Tests for backend.services.apimap — HTTP route scanner."""

from __future__ import annotations

from backend.services.apimap import (
    render_apimap_markdown,
    scan_api_routes,
)

# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------


class TestFastAPI:
    def test_get_route(self):
        code = """\
from fastapi import APIRouter
router = APIRouter()

@router.get("/items")
async def list_items():
    \"\"\"List all items.\"\"\"
    pass
"""
        result = scan_api_routes({"router.py": code})
        assert result["total"] >= 1
        route = next(r for r in result["routes"] if r["path"] == "/items")
        assert route["method"] == "GET"
        assert route["handler"] == "list_items"

    def test_post_route(self):
        code = """\
@router.post("/items")
async def create_item():
    pass
"""
        result = scan_api_routes({"router.py": code})
        assert any(r["method"] == "POST" and r["path"] == "/items" for r in result["routes"])

    def test_delete_route(self):
        code = '@router.delete("/items/{item_id}")\nasync def delete_item():\n    pass\n'
        result = scan_api_routes({"router.py": code})
        assert any(r["method"] == "DELETE" for r in result["routes"])

    def test_put_route(self):
        code = '@router.put("/items/{id}")\ndef update_item():\n    pass\n'
        result = scan_api_routes({"router.py": code})
        assert any(r["method"] == "PUT" for r in result["routes"])

    def test_fastapi_framework_detected(self):
        code = """\
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    pass
"""
        result = scan_api_routes({"main.py": code})
        assert "FastAPI" in result["frameworks"]

    def test_multiple_routes_same_file(self):
        code = """\
@router.get("/a")
def get_a(): pass

@router.post("/b")
def post_b(): pass

@router.delete("/c")
def del_c(): pass
"""
        result = scan_api_routes({"routes.py": code})
        assert result["total"] == 3

    def test_docstring_captured(self):
        code = """\
@router.get("/status")
def check_status():
    \"\"\"Return service health.\"\"\"
    return {"ok": True}
"""
        result = scan_api_routes({"api.py": code})
        route = next((r for r in result["routes"] if r["path"] == "/status"), None)
        assert route is not None
        assert "health" in route["description"].lower() or route["description"]

    def test_file_and_line_set(self):
        code = '@router.get("/ping")\ndef ping(): pass\n'
        result = scan_api_routes({"health.py": code})
        assert result["routes"][0]["file"] == "health.py"
        assert result["routes"][0]["line"] == 1


# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------


class TestFlask:
    def test_simple_get(self):
        code = """\
from flask import Flask
app = Flask(__name__)

@app.route("/hello")
def hello():
    return "hello"
"""
        result = scan_api_routes({"app.py": code})
        routes = [r for r in result["routes"] if r["path"] == "/hello"]
        assert len(routes) >= 1
        assert routes[0]["method"] == "GET"

    def test_explicit_methods(self):
        code = """\
@app.route("/submit", methods=["POST", "PUT"])
def submit():
    pass
"""
        result = scan_api_routes({"app.py": code})
        methods = {r["method"] for r in result["routes"] if r["path"] == "/submit"}
        assert "POST" in methods
        assert "PUT" in methods

    def test_flask_framework_detected(self):
        code = """\
from flask import Flask
app = Flask(__name__)

@app.route("/")
def index(): pass
"""
        result = scan_api_routes({"app.py": code})
        assert "Flask" in result["frameworks"]


# ---------------------------------------------------------------------------
# Express
# ---------------------------------------------------------------------------


class TestExpress:
    def test_express_get(self):
        code = """\
const express = require('express');
const router = express.Router();

router.get('/users', (req, res) => {
    res.json([]);
});
"""
        result = scan_api_routes({"routes.js": code})
        assert any(r["method"] == "GET" and r["path"] == "/users" for r in result["routes"])

    def test_express_post(self):
        code = "app.post('/login', handler);\n"
        result = scan_api_routes({"server.js": code})
        assert any(r["method"] == "POST" and r["path"] == "/login" for r in result["routes"])

    def test_express_delete(self):
        code = "router.delete('/items/:id', deleteItem);\n"
        result = scan_api_routes({"items.js": code})
        assert any(r["method"] == "DELETE" for r in result["routes"])

    def test_express_framework_detected(self):
        code = """\
const express = require('express');
app.get('/health', (req, res) => res.send('ok'));
"""
        result = scan_api_routes({"app.js": code})
        assert "Express" in result["frameworks"]


# ---------------------------------------------------------------------------
# Next.js App Router
# ---------------------------------------------------------------------------


class TestNextJs:
    def test_nextjs_route_handler(self):
        code = """\
export async function GET(request) {
    return Response.json({ status: 'ok' });
}

export async function POST(request) {
    return Response.json({ created: true });
}
"""
        result = scan_api_routes({"src/app/api/items/route.ts": code})
        methods = {r["method"] for r in result["routes"]}
        assert "GET" in methods
        assert "POST" in methods

    def test_nextjs_path_derived(self):
        code = "export async function GET(req) { return Response.json({}); }\n"
        result = scan_api_routes({"src/app/users/[id]/route.ts": code})
        assert result["total"] >= 1
        # Path should be derived from directory structure
        paths = [r["path"] for r in result["routes"]]
        assert any("users" in p for p in paths)

    def test_nextjs_framework_detected(self):
        code = "export function GET() { return Response.json({}); }\n"
        result = scan_api_routes({"src/app/health/route.ts": code})
        assert "Next.js" in result["frameworks"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_returns_zero(self):
        result = scan_api_routes({})
        assert result["total"] == 0
        assert result["routes"] == []
        assert result["frameworks"] == []

    def test_no_routes_file(self):
        result = scan_api_routes({"utils.py": "def helper(): pass\n"})
        assert result["total"] == 0

    def test_limit_caps_routes(self):
        contents = {}
        for i in range(30):
            contents[f"router{i}.py"] = f'@router.get("/path{i}")\ndef h{i}(): pass\n'
        result = scan_api_routes(contents, limit=10)
        assert len(result["routes"]) == 10
        assert result["total"] == 30

    def test_sorted_by_path(self):
        code = """\
@router.get("/z-last")
def z(): pass

@router.get("/a-first")
def a(): pass
"""
        result = scan_api_routes({"r.py": code})
        paths = [r["path"] for r in result["routes"]]
        assert paths.index("/a-first") < paths.index("/z-last")

    def test_mixed_frameworks(self):
        py_code = "from fastapi import FastAPI\n@app.get('/api')\ndef api(): pass\n"
        js_code = "const express = require('express');\napp.get('/js', handler);\n"
        result = scan_api_routes({"main.py": py_code, "server.js": js_code})
        assert len(result["frameworks"]) >= 2


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class TestNotes:
    def test_no_routes_note(self):
        result = scan_api_routes({"clean.py": "x = 1\n"})
        assert any("未检测到" in note for note in result["notes"])

    def test_routes_found_note(self):
        result = scan_api_routes({"r.py": '@router.get("/x")\ndef x(): pass\n'})
        assert any(str(result["total"]) in note for note in result["notes"])


# ---------------------------------------------------------------------------
# render_apimap_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_no_routes_returns_empty(self):
        data = {"total": 0, "routes": [], "frameworks": [], "notes": []}
        assert render_apimap_markdown("MyProject", data) == ""

    def test_none_returns_empty(self):
        assert render_apimap_markdown("MyProject", None) == ""

    def test_renders_table(self):
        data = {
            "total": 1,
            "routes": [
                {
                    "method": "GET",
                    "path": "/users",
                    "handler": "list_users",
                    "description": "List all users",
                    "file": "routes.py",
                    "line": 5,
                }
            ],
            "frameworks": ["FastAPI"],
            "notes": [],
        }
        md = render_apimap_markdown("MyProject", data)
        assert "# HTTP 接口地图" in md
        assert "/users" in md
        assert "GET" in md
        assert "FastAPI" in md
        assert "list_users" in md
