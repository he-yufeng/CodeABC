from backend.models import ProjectMeta, UploadedFile
from backend.routers.project import _content_analyses, _select_scanned_contents


def test_select_scanned_contents_does_not_retain_filtered_files():
    files = [
        UploadedFile(path="src/main.py", content="print('safe')\n"),
        UploadedFile(path=".env", content="OPENAI_API_KEY=secret\n"),
    ]
    scanned = [{"path": "src/main.py"}]

    contents = _select_scanned_contents(files, scanned)

    assert contents == {"src/main.py": "print('safe')\n"}


def test_content_analyses_surfaces_debt_and_env_without_git():
    # Tech-debt and env vars come from the file text alone, so they populate even
    # for an uploaded (non-git) project; knowledge silos stay empty without git.
    contents = {
        "app.py": (
            '# TODO: wire retries\nkey = os.environ["API_KEY"]\nhost = os.getenv("HOST", "x")\n'
        ),
    }
    extras = _content_analyses(contents)

    assert extras["knowledge_silos"] == []
    assert [(f.path, f.count) for f in extras["tech_debt_files"]] == [("app.py", 1)]
    env = {v.name: v.required for v in extras["env_vars"]}
    assert env == {"API_KEY": True, "HOST": False}
    # the result is valid for ProjectMeta (the API response model)
    ProjectMeta(id="x", name="x", total_files=1, files=[], reading_map=[], **extras)


def test_content_analyses_maps_knowledge_silos_from_ownership():
    silos = [
        {
            "path": "core.py",
            "primary_author": "amy",
            "ownership": 100,
            "authors": 1,
            "commits": 4,
            "bus_factor": 1,
            "reason": "only amy",
        }
    ]
    extras = _content_analyses({}, silos)

    assert len(extras["knowledge_silos"]) == 1
    silo = extras["knowledge_silos"][0]
    assert silo.path == "core.py" and silo.primary_author == "amy" and silo.bus_factor == 1
