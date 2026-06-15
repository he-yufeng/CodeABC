from backend.models import UploadedFile
from backend.routers.project import _select_scanned_contents


def test_select_scanned_contents_does_not_retain_filtered_files():
    files = [
        UploadedFile(path="src/main.py", content="print('safe')\n"),
        UploadedFile(path=".env", content="OPENAI_API_KEY=secret\n"),
    ]
    scanned = [{"path": "src/main.py"}]

    contents = _select_scanned_contents(files, scanned)

    assert contents == {"src/main.py": "print('safe')\n"}
