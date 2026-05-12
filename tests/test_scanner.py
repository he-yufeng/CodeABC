from backend.services.scanner import scan_directory, scan_uploaded_files


def test_scan_directory_skips_minified_bundle(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "vendor.min.js").write_text("const a=1;\n", encoding="utf-8")

    files = scan_directory(tmp_path)
    paths = {f["path"] for f in files}

    assert "app.py" in paths
    assert "vendor.min.js" not in paths


def test_scan_directory_skips_generated_long_line(tmp_path):
    (tmp_path / "normal.js").write_text(
        "function add(a, b) {\n  return a + b;\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text("var x='" + ("a" * 2500) + "';\n", encoding="utf-8")

    files = scan_directory(tmp_path)
    paths = {f["path"] for f in files}

    assert "normal.js" in paths
    assert "app.js" not in paths


def test_uploaded_files_skip_generated_bundle():
    files = scan_uploaded_files(
        [
            {"path": "src/main.ts", "content": "export const answer = 42;\n"},
            {"path": "dist/app.bundle.js", "content": "const x=1;\n"},
            {"path": "dist/app.js", "content": "var x='" + ("a" * 2500) + "';\n"},
        ]
    )

    paths = {f["path"] for f in files}
    assert paths == {"src/main.ts"}
