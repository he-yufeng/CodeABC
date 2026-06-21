"""Project management routes: upload files, clone from GitHub."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.models import (
    AnalyzeRequest,
    ArchitectureLayer,
    BlastRadiusHotspot,
    ChurnHotspot,
    CoChangeCoupling,
    CodeWalkStep,
    CouplingHotspot,
    FileGlossary,
    FileInfo,
    GitHubRequest,
    GlossaryTerm,
    Hotspot,
    ImportCycle,
    OrphanModule,
    PackageDependency,
    ProjectHealth,
    ProjectMeta,
    ReadingStep,
    RiskHotspot,
    TestCoverageSummary,
    UploadedFile,
)
from backend.services import (
    cache,
    churn,
    coverage,
    envscan,
    github_clone,
    glossary,
    importgraph,
    ownership,
    risk,
    scanner,
    techdebt,
)

router = APIRouter(tags=["project"])

# in-memory project store (good enough for MVP, single-process)
_projects: dict[str, dict] = {}


def _select_scanned_contents(files: list[UploadedFile], scanned: list[dict]) -> dict[str, str]:
    allowed_paths = {file["path"] for file in scanned}
    return {file.path: file.content for file in files if file.path in allowed_paths}


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
        "file_contents": _select_scanned_contents(req.files, scanned),
    }
    _projects[project_id] = proj_data
    await cache.save_project(project_id, proj_data)

    return ProjectMeta(
        id=project_id,
        name=req.project_name,
        total_files=len(scanned),
        reading_map=[ReadingStep(**step) for step in scanner.build_reading_map(scanned)],
        hotspots=[Hotspot(**h) for h in importgraph.rank_hotspots(scanned)],
        code_walk=[CodeWalkStep(**s) for s in importgraph.suggest_reading_order(scanned)],
        import_cycles=[ImportCycle(**c) for c in importgraph.find_import_cycles(scanned)],
        orphan_modules=[OrphanModule(**o) for o in importgraph.find_orphan_modules(scanned)],
        coupling_hotspots=[CouplingHotspot(**c) for c in importgraph.rank_coupling(scanned)],
        blast_radius=[BlastRadiusHotspot(**b) for b in importgraph.rank_blast_radius(scanned)],
        architecture_layers=[
            ArchitectureLayer(**a) for a in importgraph.assign_architecture_layers(scanned)
        ],
        package_dependencies=[
            PackageDependency(**p) for p in importgraph.summarize_package_dependencies(scanned)
        ],
        health=ProjectHealth(**importgraph.summarize_project_health(scanned)),
        test_coverage=TestCoverageSummary(**coverage.assess_test_coverage(scanned)),
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

    # Mine git history while the clone is still on disk: change hotspots,
    # co-change coupling and code ownership are dynamic signals the static
    # analyses can't see. Collect the log once and feed both analyses.
    git_log = churn.collect_git_log(repo_path)
    scanned_paths = {f["path"] for f in scanned}
    churn_result = churn.analyze_churn(git_log, scanned_paths=scanned_paths)
    ownership_result = ownership.analyze_ownership(git_log, scanned_paths=scanned_paths)

    repo_name = req.url.rstrip("/").split("/")[-1].replace(".git", "")
    proj_data = {
        "name": repo_name,
        "files": scanned,
        "file_contents": file_contents,
        "churn": churn_result,
        "ownership": ownership_result,
    }
    _projects[project_id] = proj_data
    await cache.save_project(project_id, proj_data)

    return ProjectMeta(
        id=project_id,
        name=repo_name,
        total_files=len(scanned),
        reading_map=[ReadingStep(**step) for step in scanner.build_reading_map(scanned)],
        hotspots=[Hotspot(**h) for h in importgraph.rank_hotspots(scanned)],
        code_walk=[CodeWalkStep(**s) for s in importgraph.suggest_reading_order(scanned)],
        import_cycles=[ImportCycle(**c) for c in importgraph.find_import_cycles(scanned)],
        orphan_modules=[OrphanModule(**o) for o in importgraph.find_orphan_modules(scanned)],
        coupling_hotspots=[CouplingHotspot(**c) for c in importgraph.rank_coupling(scanned)],
        blast_radius=[BlastRadiusHotspot(**b) for b in importgraph.rank_blast_radius(scanned)],
        architecture_layers=[
            ArchitectureLayer(**a) for a in importgraph.assign_architecture_layers(scanned)
        ],
        package_dependencies=[
            PackageDependency(**p) for p in importgraph.summarize_package_dependencies(scanned)
        ],
        health=ProjectHealth(**importgraph.summarize_project_health(scanned)),
        churn_hotspots=[ChurnHotspot(**h) for h in churn_result.get("hotspots", [])],
        co_change_couplings=[CoChangeCoupling(**c) for c in churn_result.get("couplings", [])],
        risk_hotspots=[
            RiskHotspot(**r)
            for r in risk.rank_risk(
                importgraph.rank_hotspots(scanned, limit=500),
                churn_result.get("hotspots", []),
            )
        ],
        test_coverage=TestCoverageSummary(**coverage.assess_test_coverage(scanned)),
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
        reading_map=[ReadingStep(**step) for step in scanner.build_reading_map(proj["files"])],
        hotspots=[Hotspot(**h) for h in importgraph.rank_hotspots(proj["files"])],
        code_walk=[CodeWalkStep(**s) for s in importgraph.suggest_reading_order(proj["files"])],
        import_cycles=[ImportCycle(**c) for c in importgraph.find_import_cycles(proj["files"])],
        orphan_modules=[OrphanModule(**o) for o in importgraph.find_orphan_modules(proj["files"])],
        coupling_hotspots=[CouplingHotspot(**c) for c in importgraph.rank_coupling(proj["files"])],
        blast_radius=[
            BlastRadiusHotspot(**b) for b in importgraph.rank_blast_radius(proj["files"])
        ],
        architecture_layers=[
            ArchitectureLayer(**a) for a in importgraph.assign_architecture_layers(proj["files"])
        ],
        package_dependencies=[
            PackageDependency(**p)
            for p in importgraph.summarize_package_dependencies(proj["files"])
        ],
        health=ProjectHealth(**importgraph.summarize_project_health(proj["files"])),
        churn_hotspots=[ChurnHotspot(**h) for h in (proj.get("churn") or {}).get("hotspots", [])],
        co_change_couplings=[
            CoChangeCoupling(**c) for c in (proj.get("churn") or {}).get("couplings", [])
        ],
        risk_hotspots=[
            RiskHotspot(**r)
            for r in risk.rank_risk(
                importgraph.rank_hotspots(proj["files"], limit=500),
                (proj.get("churn") or {}).get("hotspots", []),
            )
        ],
        test_coverage=TestCoverageSummary(**coverage.assess_test_coverage(proj["files"])),
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


@router.get("/project/{project_id}/file/{file_path:path}/glossary", response_model=FileGlossary)
async def get_file_glossary(project_id: str, file_path: str):
    """Return the jargon terms found in a file with plain-language definitions.

    Deterministic (no LLM): powers "hover a keyword, see what it means".
    """
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    content = proj.get("file_contents", {}).get(file_path)
    if content is None:
        raise HTTPException(404, f"File not found: {file_path}")

    return FileGlossary(
        path=file_path,
        terms=[GlossaryTerm(**t) for t in glossary.scan_terms(content)],
    )


@router.get("/project/{project_id}/codemap.md")
async def get_codemap_markdown(project_id: str):
    """Export the deterministic code map (import-graph analyses) as Markdown."""
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    markdown = importgraph.render_codemap_markdown(proj["name"], proj["files"])
    risk_md = risk.render_risk_markdown(
        risk.rank_risk(
            importgraph.rank_hotspots(proj["files"], limit=500),
            (proj.get("churn") or {}).get("hotspots", []),
        )
    )
    if risk_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{risk_md}"
    churn_md = churn.render_churn_markdown(proj["name"], proj.get("churn"))
    if churn_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{churn_md}"
    ownership_md = ownership.render_ownership_markdown(proj["name"], proj.get("ownership"))
    if ownership_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{ownership_md}"
    coverage_md = coverage.render_coverage_markdown(
        proj["name"], coverage.assess_test_coverage(proj["files"])
    )
    if coverage_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{coverage_md}"
    techdebt_md = techdebt.render_techdebt_markdown(
        proj["name"], techdebt.scan_tech_debt(proj.get("file_contents", {}))
    )
    if techdebt_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{techdebt_md}"
    env_md = envscan.render_env_markdown(
        proj["name"], envscan.scan_env_vars(proj.get("file_contents", {}))
    )
    if env_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{env_md}"
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")


async def get_project_data(project_id: str) -> dict | None:
    """Internal helper for analyze router to access project data."""
    return await _resolve_project(project_id)
