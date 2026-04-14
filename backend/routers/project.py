"""Project management routes: upload files, clone from GitHub."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from backend.models import AnalyzeRequest, FileInfo, GitHubRequest, ProjectMeta
from backend.services import cache, github_clone, scanner

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
    proj_data = {
        "name": req.project_name,
        "files": scanned,
        "file_contents": {f.path: f.content for f in req.files},
    }
    _projects[project_id] = proj_data
    await cache.save_project(project_id, proj_data)

    return ProjectMeta(
        id=project_id,
        name=req.project_name,
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
    proj_data = {
        "name": repo_name,
        "files": scanned,
        "file_contents": file_contents,
    }
    _projects[project_id] = proj_data
    await cache.save_project(project_id, proj_data)

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


async def _resolve_project(project_id: str) -> dict | None:
    """Look up project in memory, then fall back to SQLite."""
    proj = _projects.get(project_id)
    if proj:
        return proj
    # try loading from persistent storage
    proj = await cache.load_project(project_id)
    if proj:
        _projects[project_id] = proj  # re-populate memory cache
    return proj


@router.get("/project/{project_id}")
async def get_project(project_id: str):
    """Get project metadata."""
    proj = await _resolve_project(project_id)
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
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    content = proj.get("file_contents", {}).get(file_path)
    if content is None:
        raise HTTPException(404, f"File not found: {file_path}")

    lang = "unknown"
    for f in proj["files"]:
        if f["path"] == file_path:
            lang = f["language"]
            break

    return {"path": file_path, "language": lang, "content": content}


async def get_project_data(project_id: str) -> dict | None:
    """Internal helper for analyze router to access project data."""
    return await _resolve_project(project_id)
