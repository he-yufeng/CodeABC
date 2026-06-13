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


def test_scan_directory_respects_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text(
        "scratch/\n*.local.py\n!important.local.py\n",
        encoding="utf-8",
    )
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch" / "notes.py").write_text("print('skip')\n", encoding="utf-8")
    (tmp_path / "settings.local.py").write_text("SECRET = 'skip'\n", encoding="utf-8")
    (tmp_path / "important.local.py").write_text("print('keep')\n", encoding="utf-8")
    (tmp_path / "src.py").write_text("print('keep')\n", encoding="utf-8")

    files = scan_directory(tmp_path)
    paths = {f["path"] for f in files}

    assert "src.py" in paths
    assert "important.local.py" in paths
    assert "settings.local.py" not in paths
    assert "scratch/notes.py" not in paths


def test_scan_directory_skips_secret_shaped_files(tmp_path):
    (tmp_path / "app.py").write_text("print('keep')\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=secret-value\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
    (tmp_path / "credentials.json").write_text('{"token": "secret"}\n', encoding="utf-8")
    (tmp_path / "server.pem").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")

    files = scan_directory(tmp_path)
    paths = {f["path"] for f in files}

    assert "app.py" in paths
    assert ".env.example" in paths
    assert ".env" not in paths
    assert "credentials.json" not in paths
    assert "server.pem" not in paths


def test_scan_directory_keeps_normal_token_source_files(tmp_path):
    (tmp_path / "tokenizer.py").write_text(
        "def tokenize(text): return text.split()\n",
        encoding="utf-8",
    )
    (tmp_path / "access_token.txt").write_text("secret\n", encoding="utf-8")

    files = scan_directory(tmp_path)
    paths = {f["path"] for f in files}

    assert "tokenizer.py" in paths
    assert "access_token.txt" not in paths


def test_uploaded_files_skip_secret_shaped_paths():
    files = scan_uploaded_files(
        [
            {"path": "src/main.py", "content": "print('keep')\n"},
            {"path": ".env.local", "content": "OPENAI_API_KEY=secret-value\n"},
            {"path": ".env.sample", "content": "OPENAI_API_KEY=\n"},
            {"path": ".ssh/id_ed25519", "content": "private key\n"},
        ]
    )

    paths = {f["path"] for f in files}
    assert paths == {"src/main.py", ".env.sample"}
