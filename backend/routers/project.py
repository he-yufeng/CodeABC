"""Project management routes: upload files, clone from GitHub."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.models import (
    AnalyzeRequest,
    ApiMap,
    ApiRoute,
    ArchitectureLayer,
    BlastRadiusHotspot,
    ChurnHotspot,
    CoChangeCoupling,
    CodeWalkStep,
    ComplexFile,
    CouplingHotspot,
    Dependency,
    EntryPoint,
    EnvVar,
    FileGlossary,
    FileInfo,
    GitHubRequest,
    GlossaryTerm,
    Hotspot,
    ImportCycle,
    KnowledgeSilo,
    OrphanModule,
    PackageDependency,
    ProjectHealth,
    ProjectMeta,
    ReadingStep,
    RiskHotspot,
    SecurityFinding,
    SecuritySummary,
    TechDebtFile,
    TestCoverageSummary,
    UploadedFile,
)
from backend.services import (
    apimap,
    cache,
    churn,
    complexity,
    coverage,
    dependencies,
    entrypoints,
    envscan,
    github_clone,
    glossary,
    importgraph,
    ownership,
    risk,
    scanner,
    security,
    techdebt,
)

router = APIRouter(tags=["project"])

# in-memory project store (good enough for MVP, single-process)
_projects: dict[str, dict] = {}


def _select_scanned_contents(files: list[UploadedFile], scanned: list[dict]) -> dict[str, str]:
    allowed_paths = {file["path"] for file in scanned}
    return {file.path: file.content for file in files if file.path in allowed_paths}


def _content_analyses(
    file_contents: dict[str, str], ownership_silos: list[dict] | None = None
) -> dict:
    """Build the file-content-derived ProjectMeta analyses (debt / env / silos).

    Tech-debt and env vars come straight from the file text, so they work for
    uploaded projects too; knowledge silos need git history, so callers pass the
    already-computed ``ownership['silos']`` (empty for non-git uploads).
    """
    tech_debt = techdebt.scan_tech_debt(file_contents)
    env = envscan.scan_env_vars(file_contents)
    entries = entrypoints.find_entry_points(file_contents)
    complex_files = complexity.scan_complexity(file_contents)
    deps = dependencies.scan_dependencies(file_contents)
    sec = security.scan_security(file_contents)
    api = apimap.scan_api_routes(file_contents)
    return {
        "knowledge_silos": [
            KnowledgeSilo(
                path=s["path"],
                primary_author=s["primary_author"],
                ownership=s["ownership"],
                commits=s["commits"],
                bus_factor=s["bus_factor"],
                reason=s["reason"],
            )
            for s in (ownership_silos or [])
        ],
        "tech_debt_files": [
            TechDebtFile(path=f["path"], count=f["count"]) for f in tech_debt["files"]
        ],
        "env_vars": [
            EnvVar(name=v["name"], required=v["required"], count=v["count"]) for v in env["vars"]
        ],
        "entry_points": [
            EntryPoint(path=e["path"], kind=e["kind"], command=e["command"], reason=e["reason"])
            for e in entries["entry_points"]
        ],
        "complexity_files": [
            ComplexFile(
                path=f["path"],
                complexity=f["complexity"],
                functions=f["functions"],
                reason=f["reason"],
            )
            for f in complex_files["files"]
        ],
        "dependencies": [
            Dependency(name=d["name"], version=d["version"], kind=d["kind"], manifest=d["manifest"])
            for d in deps["dependencies"]
        ],
        "security": SecuritySummary(
            total=sec["total"],
            critical=sec["critical"],
            findings=[SecurityFinding(**f) for f in sec["findings"]],
            notes=sec["notes"],
        ),
        "api_map": ApiMap(
            total=api["total"],
            routes=[ApiRoute(**r) for r in api["routes"]],
            frameworks=api["frameworks"],
            notes=api["notes"],
        ),
    }


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
        **_content_analyses(_select_scanned_contents(req.files, scanned)),
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
        **_content_analyses(file_contents, ownership_result.get("silos")),
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
        **_content_analyses(
            proj.get("file_contents", {}), (proj.get("ownership") or {}).get("silos")
        ),
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
    entrypoints_md = entrypoints.render_entrypoints_markdown(
        proj["name"], entrypoints.find_entry_points(proj.get("file_contents", {}))
    )
    if entrypoints_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{entrypoints_md}"
    complexity_md = complexity.render_complexity_markdown(
        proj["name"], complexity.scan_complexity(proj.get("file_contents", {}))
    )
    if complexity_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{complexity_md}"
    dependencies_md = dependencies.render_dependencies_markdown(
        proj["name"], dependencies.scan_dependencies(proj.get("file_contents", {}))
    )
    if dependencies_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{dependencies_md}"
    security_md = security.render_security_markdown(
        proj["name"], security.scan_security(proj.get("file_contents", {}))
    )
    if security_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{security_md}"
    apimap_md = apimap.render_apimap_markdown(
        proj["name"], apimap.scan_api_routes(proj.get("file_contents", {}))
    )
    if apimap_md:
        markdown = f"{markdown.rstrip()}\n\n---\n\n{apimap_md}"
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")


async def get_project_data(project_id: str) -> dict | None:
    """Internal helper for analyze router to access project data."""
    return await _resolve_project(project_id)
