"""Project management routes: upload files, clone from GitHub."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.models import (
    ActionItem,
    ActionPlan,
    ActivityContributor,
    ActivitySummary,
    ActivityWindow,
    AnalyzeRequest,
    ApiMap,
    ApiRoute,
    ArchitectureLayer,
    BlastRadiusHotspot,
    ChurnHotspot,
    CiCheck,
    CliCommand,
    CoChangeCoupling,
    CodeWalkStep,
    ComplexFile,
    ConfigFile,
    ContributionGuide,
    ContributionRequirement,
    CouplingHotspot,
    DataModel,
    DataModelField,
    Definition,
    DefinitionMatches,
    Dependency,
    DocCoverage,
    DocCoverageFile,
    EntryPoint,
    EnvVar,
    ErrorHandling,
    ExternalService,
    FileDependencies,
    FileGlossary,
    FileInfo,
    FileOutline,
    GitHubRequest,
    GlossaryTerm,
    HealthScore,
    Hotspot,
    ImportCycle,
    Integrations,
    KnowledgeSilo,
    LicenseFinding,
    LicenseSummary,
    OrphanModule,
    PackageDependency,
    ProjectHealth,
    ProjectMeta,
    ProjectSummary,
    PublicApi,
    ReadingStep,
    Reference,
    ReferenceMatches,
    ReleaseAutomation,
    ReleaseSummary,
    RiskHotspot,
    ScheduledTask,
    SecurityFinding,
    SecuritySummary,
    SilentFailure,
    TechDebtFile,
    TestCoverageSummary,
    TunableSetting,
    UploadedFile,
)
from backend.services import (
    action_plan as action_plan_svc,
)
from backend.services import (
    activity,
    apimap,
    cache,
    churn,
    ci_checks,
    codemap_export,
    commands,
    complexity,
    config_files,
    contributing,
    coverage,
    datamodels,
    deep_nesting,
    dependencies,
    docs,
    entrypoints,
    envscan,
    error_handling,
    filenames,
    github_clone,
    glossary,
    importgraph,
    integrations,
    licenses,
    ownership,
    release_map,
    report_export,
    risk,
    scanner,
    schedules,
    security,
    settings_map,
    symbols,
    techdebt,
    typing_coverage,
)
from backend.services import (
    health_score as health_score_svc,
)

router = APIRouter(tags=["project"])

# in-memory project store (good enough for MVP, single-process)
_projects: dict[str, dict] = {}


def _select_scanned_contents(files: list[UploadedFile], scanned: list[dict]) -> dict[str, str]:
    allowed_paths = {file["path"] for file in scanned}
    return {file.path: file.content for file in files if file.path in allowed_paths}


def _reading_steps(files: list[dict]) -> list["ReadingStep"]:
    """Build the deterministic reading map, tagging each step with what kind of
    file it is so a non-coder can tell ``urls.py`` from ``models.py`` without
    opening either."""
    steps = []
    for step in scanner.build_reading_map(files):
        purpose = filenames.explain_path(step["path"])
        steps.append(ReadingStep(**step, kind=purpose["kind"] if purpose else None))
    return steps


def _activity_summary(data: dict | None) -> "ActivitySummary":
    """Reconstruct an ActivitySummary Pydantic model from a raw activity dict."""
    if not data:
        return ActivitySummary()
    return ActivitySummary(
        available=data.get("available", False),
        total_commits=data.get("total_commits", 0),
        first_commit_days_ago=data.get("first_commit_days_ago"),
        last_commit_days_ago=data.get("last_commit_days_ago"),
        label=data.get("label", ""),
        label_zh=data.get("label_zh", ""),
        windows={k: ActivityWindow(**v) for k, v in data.get("windows", {}).items()},
        top_contributors=[ActivityContributor(**c) for c in data.get("top_contributors", [])],
        recently_changed=data.get("recently_changed", []),
        notes=data.get("notes", []),
    )


def _health_score_summary(data: dict | None) -> "HealthScore":
    """Reconstruct a HealthScore Pydantic model from a raw compute_health_score dict."""
    if not data:
        return HealthScore()
    return HealthScore(
        score=data.get("score", 0),
        grade=data.get("grade", "F"),
        category_scores=data.get("category_scores", {}),
        weights=data.get("weights", {}),
        strengths=data.get("strengths", []),
        weaknesses=data.get("weaknesses", []),
        notes=data.get("notes", []),
    )


def _compute_health_score(
    meta: "ProjectMeta", file_contents: dict[str, str] | None = None
) -> dict:
    """Derive health score from an already-built ProjectMeta using .model_dump().

    ``file_contents`` (when available) lets the complexity dimension also account
    for deep nesting, a readability signal derived directly from the source text.
    """
    deep_nesting_files = None
    if file_contents:
        deep_nesting_files = deep_nesting.scan_deep_nesting(file_contents).get("files")
    return health_score_svc.compute_health_score(
        security=meta.security.model_dump() if meta.security else None,
        test_coverage=meta.test_coverage.model_dump() if meta.test_coverage else None,
        activity=meta.activity.model_dump() if meta.activity else None,
        complexity_files=[f.model_dump() for f in meta.complexity_files],
        tech_debt_files=[f.model_dump() for f in meta.tech_debt_files],
        import_cycles=[c.model_dump() for c in meta.import_cycles],
        orphan_modules=[o.model_dump() for o in meta.orphan_modules],
        deep_nesting_files=deep_nesting_files,
        total_files=meta.total_files,
    )


def _action_plan_summary(data: dict | None) -> "ActionPlan":
    """Reconstruct an ActionPlan Pydantic model from a raw build_action_plan dict."""
    if not data:
        return ActionPlan()
    return ActionPlan(
        total=data.get("total", 0),
        items=[ActionItem(**i) for i in data.get("items", [])],
        notes=data.get("notes", []),
    )


def _compute_action_plan(
    meta: "ProjectMeta", file_contents: dict[str, str] | None = None
) -> dict:
    """Derive the priority action plan from an already-built ProjectMeta.

    ``file_contents`` (when available) lets the plan also surface deep-nesting and
    low-type-coverage actions, which are derived directly from the source text
    rather than stored on ``ProjectMeta``.
    """
    deep_nesting_files = None
    typing_files = None
    if file_contents:
        deep_nesting_files = deep_nesting.scan_deep_nesting(file_contents).get("files")
        typing_files = typing_coverage.scan_typing_coverage(file_contents).get("files")
    return action_plan_svc.build_action_plan(
        security=meta.security.model_dump() if meta.security else None,
        test_coverage=meta.test_coverage.model_dump() if meta.test_coverage else None,
        complexity_files=[f.model_dump() for f in meta.complexity_files],
        tech_debt_files=[f.model_dump() for f in meta.tech_debt_files],
        import_cycles=[c.model_dump() for c in meta.import_cycles],
        deep_nesting_files=deep_nesting_files,
        typing_files=typing_files,
    )


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
    cli_commands = commands.find_cli_commands(file_contents)
    data_models = datamodels.find_data_models(file_contents)
    tunable = settings_map.find_tunable_settings(file_contents)
    cfg_files = config_files.find_config_files(file_contents)
    scheduled = schedules.find_scheduled_tasks(file_contents)
    ci_gates = ci_checks.find_ci_checks(file_contents)
    license_map = licenses.find_licenses(file_contents)
    complex_files = complexity.scan_complexity(file_contents)
    deps = dependencies.scan_dependencies(file_contents)
    sec = security.scan_security(file_contents)
    api = apimap.scan_api_routes(file_contents)
    doc = docs.assess_doc_coverage(file_contents)
    silent = error_handling.find_swallowed_errors(file_contents)
    integ = integrations.detect_external_services(file_contents)
    rel = release_map.find_release_info(file_contents)
    contrib = contributing.find_contribution_guide(file_contents)
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
        "cli_commands": [
            CliCommand(
                name=c["name"],
                framework=c["framework"],
                help=c["help"],
                options=c["options"],
                path=c["path"],
                line=c["line"],
            )
            for c in cli_commands["commands"]
        ],
        "data_models": [
            DataModel(
                name=m["name"],
                kind=m["kind"],
                fields=[
                    DataModelField(name=f["name"], type=f["type"], has_default=f["has_default"])
                    for f in m["fields"]
                ],
                path=m["path"],
                line=m["line"],
            )
            for m in data_models["models"]
        ],
        "tunable_settings": [
            TunableSetting(
                name=s["name"],
                kind=s["kind"],
                value=s["value"],
                path=s["path"],
                line=s["line"],
            )
            for s in tunable["settings"]
        ],
        "config_files": [
            ConfigFile(
                path=f["path"],
                kind=f["kind"],
                sections=f["sections"],
                keys=f["keys"],
                setting_count=f["setting_count"],
            )
            for f in cfg_files["files"]
        ],
        "scheduled_tasks": [
            ScheduledTask(
                name=t["name"],
                mechanism=t["mechanism"],
                schedule=t["schedule"],
                schedule_human=t["schedule_human"],
                path=t["path"],
                line=t["line"],
            )
            for t in scheduled["tasks"]
        ],
        "ci_checks": [
            CiCheck(
                tool=c["tool"],
                category=c["category"],
                system=c["system"],
                trigger=c["trigger"],
                path=c["path"],
                line=c["line"],
            )
            for c in ci_gates["checks"]
        ],
        "licenses": LicenseSummary(
            total=license_map["total"],
            primary=license_map["primary"],
            primary_category=license_map["primary_category"],
            found=[LicenseFinding(**f) for f in license_map["found"]],
            categories=license_map["categories"],
            notes=license_map["notes"],
        ),
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
            Dependency(
                name=d["name"],
                version=d["version"],
                kind=d["kind"],
                manifest=d["manifest"],
                purpose=d.get("purpose"),
            )
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
        "doc_coverage": DocCoverage(
            total_source_files=doc["total_source_files"],
            documented_files=doc["documented_files"],
            undocumented_files=doc["undocumented_files"],
            doc_percent=doc["doc_percent"],
            under_documented=[DocCoverageFile(**f) for f in doc["under_documented"]],
            notes=doc["notes"],
        ),
        "error_handling": ErrorHandling(
            total=silent["total"],
            files_affected=silent["files_affected"],
            findings=[SilentFailure(**f) for f in silent["findings"]],
            notes=silent["notes"],
        ),
        "integrations": Integrations(
            total=integ["total"],
            services=[ExternalService(**s) for s in integ["services"]],
            categories=integ["categories"],
            notes=integ["notes"],
        ),
        "release": ReleaseSummary(
            version=rel["version"],
            version_source=rel["version_source"],
            version_source_kind=rel["version_source_kind"],
            dynamic_from_vcs=rel["dynamic_from_vcs"],
            scheme=rel["scheme"],
            scheme_zh=rel["scheme_zh"],
            changelog_path=rel["changelog_path"],
            changelog_style=rel["changelog_style"],
            changelog_style_zh=rel["changelog_style_zh"],
            automation=[ReleaseAutomation(**a) for a in rel["automation"]],
            publish_targets=rel["publish_targets"],
            notes=rel["notes"],
        ),
        "contribution": ContributionGuide(
            has_guide=contrib["has_guide"],
            requirements=[ContributionRequirement(**r) for r in contrib["requirements"]],
            notes=contrib["notes"],
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

    meta = ProjectMeta(
        id=project_id,
        name=req.project_name,
        total_files=len(scanned),
        reading_map=_reading_steps(scanned),
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
    hs_result = _compute_health_score(meta, proj_data["file_contents"])
    ap_result = _compute_action_plan(meta, proj_data["file_contents"])
    proj_data["health_score"] = hs_result
    proj_data["action_plan"] = ap_result
    _projects[project_id] = proj_data
    await cache.save_project(project_id, proj_data)
    meta.health_score = _health_score_summary(hs_result)
    meta.action_plan = _action_plan_summary(ap_result)
    return meta


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
    activity_result = activity.analyze_activity(git_log)

    repo_name = req.url.rstrip("/").split("/")[-1].replace(".git", "")
    proj_data = {
        "name": repo_name,
        "files": scanned,
        "file_contents": file_contents,
        "churn": churn_result,
        "ownership": ownership_result,
        "activity": activity_result,
    }

    meta = ProjectMeta(
        id=project_id,
        name=repo_name,
        total_files=len(scanned),
        reading_map=_reading_steps(scanned),
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
        activity=_activity_summary(activity_result),
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
    hs_result = _compute_health_score(meta, proj_data["file_contents"])
    ap_result = _compute_action_plan(meta, proj_data["file_contents"])
    proj_data["health_score"] = hs_result
    proj_data["action_plan"] = ap_result
    _projects[project_id] = proj_data
    await cache.save_project(project_id, proj_data)
    meta.health_score = _health_score_summary(hs_result)
    meta.action_plan = _action_plan_summary(ap_result)
    return meta


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


@router.get("/projects", response_model=list[ProjectSummary])
async def list_projects():
    """List previously analyzed projects (the on-disk library), newest first.

    Lets you reopen a past analysis without re-cloning or re-scanning. The
    persisted SQLite store is the source of truth; a project created in this
    process that isn't persisted yet (e.g. the cache DB is unavailable) is
    merged in so it still shows up.
    """
    stored = await cache.list_projects()
    seen = {p["id"] for p in stored}
    summaries = [ProjectSummary(**p) for p in stored]
    summaries.extend(
        ProjectSummary(
            id=project_id,
            name=proj.get("name") or project_id,
            total_files=len(proj.get("files") or []),
        )
        for project_id, proj in _projects.items()
        if project_id not in seen
    )
    return summaries


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
        reading_map=_reading_steps(proj["files"]),
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
        activity=_activity_summary(proj.get("activity")),
        health_score=_health_score_summary(proj.get("health_score")),
        action_plan=_action_plan_summary(proj.get("action_plan")),
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

    return {
        "path": file_path,
        "language": lang,
        "content": content,
        "purpose": filenames.explain_path(file_path),
    }


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


@router.get(
    "/project/{project_id}/file/{file_path:path}/dependencies",
    response_model=FileDependencies,
)
async def get_file_dependencies(project_id: str, file_path: str):
    """Return what a single file connects to inside the project.

    Deterministic (no LLM): the in-project files this file imports, and the ones
    that import it — so a reader sees "this uses X" and "Y relies on this".
    """
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    if proj.get("file_contents", {}).get(file_path) is None:
        raise HTTPException(404, f"File not found: {file_path}")

    deps = importgraph.file_dependencies(proj["files"], file_path)
    return FileDependencies(
        path=file_path,
        imports=deps["imports"],
        imported_by=deps["imported_by"],
    )


@router.get("/project/{project_id}/definition", response_model=DefinitionMatches)
async def get_definition(project_id: str, name: str):
    """Return where a name is defined — the jump-to-definition lookup.

    Deterministic (no LLM): click a function, class, or import and find the
    file and line that declares it. Tries an exact match, then a
    case-insensitive one, and returns every place a shared name is defined.
    """
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    matches = symbols.find_definition(proj.get("file_contents", {}), name)
    return DefinitionMatches(
        name=name,
        total=len(matches),
        definitions=[Definition(**m) for m in matches],
        notes=[] if matches else [f"No definition of '{name}' found in this project."],
    )


@router.get("/project/{project_id}/references", response_model=ReferenceMatches)
async def get_references(project_id: str, name: str):
    """Return where a name is used — the find-all-references lookup.

    Deterministic (no LLM): the companion to jump-to-definition. Where the
    definition index answers "where is this declared?", this answers "where is
    it used?" — every call site with a one-line preview, with the declaration
    itself flagged so a reader can tell the source from the uses.
    """
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    result = symbols.find_references(proj.get("file_contents", {}), name)
    return ReferenceMatches(
        name=result["name"],
        total=result["total"],
        files=result["files"],
        references=[Reference(**r) for r in result["references"]],
        notes=result["notes"],
    )


@router.get("/project/{project_id}/outline", response_model=FileOutline)
async def get_file_outline(project_id: str, path: str):
    """Return one file's structure, top to bottom — its table of contents.

    Deterministic (no LLM): where the definition index spans the whole project
    alphabetically, this lists just the chosen file's functions and classes in
    the order they are written, with each class's methods nested underneath, so
    a reader can see the shape of an unfamiliar file before its detail.
    """
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    result = symbols.file_outline(proj.get("file_contents", {}), path)
    return FileOutline(**result)


@router.get("/project/{project_id}/public-api", response_model=PublicApi)
async def get_public_api(project_id: str):
    """Return the project's public surface — the names other code is meant to call.

    Deterministic (no LLM): filters the definition index down to the names a
    project exposes on purpose — non-underscore in Python, ``export``-ed in
    JS/TS — so a reader can see the interface before wading into the internals.
    """
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")

    result = symbols.public_api(proj.get("file_contents", {}))
    return PublicApi(
        total=result["total"],
        definitions=[Definition(**d) for d in result["definitions"]],
        notes=result["notes"],
    )


@router.get("/project/{project_id}/codemap.md")
async def get_codemap_markdown(project_id: str):
    """Export the deterministic code map (import-graph analyses) as Markdown."""
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    markdown = codemap_export.build_codemap_markdown(proj)
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")


@router.get("/project/{project_id}/report.html")
async def get_report_html(project_id: str):
    """Export the full analysis as one self-contained, offline HTML report."""
    proj = await _resolve_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    report = report_export.build_report_html(proj)
    return Response(content=report, media_type="text/html; charset=utf-8")


async def get_project_data(project_id: str) -> dict | None:
    """Internal helper for analyze router to access project data."""
    return await _resolve_project(project_id)
