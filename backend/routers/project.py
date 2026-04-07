"""Project management routes: upload files, clone from GitHub."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from backend.models import AnalyzeRequest, FileInfo, GitHubRequest, ProjectMeta
from backend.services import github_clone, scanner

router = APIRouter(tags=["project"])

# in-memory project store (good enough for MVP, single-process)
_projects: dict[str, dict] = {}


@router.post("/project/upload", response_model=ProjectMeta)
async def upload_project(req: AnalyzeRequest):
    """Receive files uploaded from the frontend (webkitdirectory)."""
    if not req.files:
        raise HTTPException(400, "No files provided")

    scanned = scanner.scan_uploaded_files([f.model_dump() for f in req.files])
    if not scanned:
        raise HTTPException(400, "No readable source files found")

    project_id = uuid.uuid4().hex[:12]
    _projects[project_id] = {
        "name": req.project_name,
        "files": scanned,
        # also keep full content for annotation later
        "file_contents": {f.path: f.content for f in req.files},
    }

    return ProjectMeta(
        id=project_id,
        name=req.project_name,
        total_files=len(scanned),
        files=[
            FileInfo(
                path=f["path"],
                size=f["size"],
                language=f["language"],
                preview="",  # don't send preview back in listing
            )
            for f in scanned
        ],
    )


@router.post("/project/github", response_model=ProjectMeta)
async def clone_github_project(req: GitHubRequest):
    """Clone a GitHub repo and scan it."""
    try:
        repo_path = await github_clone.clone_repo(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    scanned = scanner.scan_directory(repo_path)
    if not scanned:
        raise HTTPException(400, "No readable source files in this repo")

    project_id = uuid.uuid4().hex[:12]

    # read full file contents for later annotation
    file_contents = {}
    for f in scanned:
        fpath = repo_path / f["path"]
        try:
            file_contents[f["path"]] = fpath.read_text(errors="replace")
        except Exception:
            pass

    repo_name = req.url.rstrip("/").split("/")[-1].replace(".git", "")
    _projects[project_id] = {
        "name": repo_name,
        "files": scanned,
        "file_contents": file_contents,
        "repo_path": str(repo_path),
    }

    return ProjectMeta(
        id=project_id,
        name=repo_name,
        total_files=len(scanned),
        files=[
            FileInfo(
                path=f["path"],
                size=f["size"],
                language=f["language"],
                preview="",
            )
            for f in scanned
        ],
    )


@router.get("/project/{project_id}")
async def get_project(project_id: str):
    """Get project metadata."""
    proj = _projects.get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return ProjectMeta(
        id=project_id,
        name=proj["name"],
        total_files=len(proj["files"]),
        files=[
            FileInfo(
                path=f["path"],
                size=f["size"],
                language=f["language"],
                preview="",
            )
            for f in proj["files"]
        ],
    )


@router.get("/project/{project_id}/file/{file_path:path}")
async def get_file_content(project_id: str, file_path: str):
    """Return full content of a specific file."""
    proj = _projects.get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    content = proj.get("file_contents", {}).get(file_path)
    if content is None:
        raise HTTPException(404, f"File not found: {file_path}")

    # detect language
    lang = "unknown"
    for f in proj["files"]:
        if f["path"] == file_path:
            lang = f["language"]
            break

    return {"path": file_path, "language": lang, "content": content}


def get_project_data(project_id: str) -> dict | None:
    """Internal helper for analyze router to access project data."""
    return _projects.get(project_id)
