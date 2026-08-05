"""Pydantic models for CodeABC API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    path: str
    size: int
    language: str = "unknown"
    preview: str = ""  # first N lines


class ReadingStep(BaseModel):
    order: int
    path: str
    reason: str
    # Plain-language category of the file (e.g. "数据结构", "测试代码"), inferred
    # from its name so a non-coder can tell entries apart at a glance. None when
    # the filename follows no known convention.
    kind: str | None = None


class Hotspot(BaseModel):
    path: str
    language: str = "unknown"
    fan_in: int
    dependents: list[str] = []
    reason: str


class CodeWalkStep(BaseModel):
    step: int
    path: str
    language: str = "unknown"
    role: str
    reason: str


class ImportCycle(BaseModel):
    files: list[str]
    size: int
    reason: str


class OrphanModule(BaseModel):
    path: str
    language: str = "unknown"
    reason: str


class CouplingHotspot(BaseModel):
    path: str
    language: str = "unknown"
    fan_out: int
    dependencies: list[str] = []
    reason: str


class BlastRadiusHotspot(BaseModel):
    path: str
    language: str = "unknown"
    blast_radius: int
    direct_dependents: list[str] = []
    reason: str


class ArchitectureLayer(BaseModel):
    path: str
    language: str = "unknown"
    layer: int
    reason: str


class PackageDependency(BaseModel):
    package: str
    depends_on: list[str] = []
    depended_on_by: list[str] = []
    fan_out: int
    fan_in: int
    reason: str


class ProjectHealth(BaseModel):
    total_code_files: int = 0
    total_directories: int = 0
    circular_dependency_groups: int = 0
    orphan_files: int = 0
    most_depended_on: str = ""
    most_depended_on_fan_in: int = 0
    widest_blast_radius_file: str = ""
    widest_blast_radius: int = 0
    notes: list[str] = []


class ChurnHotspot(BaseModel):
    path: str
    commits: int
    lines_changed: int = 0
    authors: int = 1
    reason: str


class CoChangeCoupling(BaseModel):
    file_a: str
    file_b: str
    co_changes: int
    coupling: int  # percentage of the rarer file's commits that touch both
    reason: str


class RiskHotspot(BaseModel):
    path: str
    fan_in: int
    commits: int
    score: int  # 0-100, high when a file is both central and frequently changed
    reason: str


class TestCoverageFile(BaseModel):
    path: str
    language: str = "unknown"
    fan_in: int = 0  # how many files depend on this untested file
    reason: str


class TestCoverageSummary(BaseModel):
    total_source_files: int = 0
    tested_files: int = 0
    untested_files: int = 0
    test_files: int = 0
    coverage_percent: int = 0  # 0-100, tested source files / total source files
    test_frameworks: list[str] = []  # detected runners, e.g. ["pytest"] / ["vitest"]
    run_command: str | None = None  # how to run the tests, e.g. "pytest" / "npm test"
    untested_core: list[TestCoverageFile] = []  # untested, ranked by fan-in
    notes: list[str] = []


class KnowledgeSilo(BaseModel):
    path: str
    primary_author: str
    ownership: int  # percent of the file's commits owned by the primary author
    commits: int
    bus_factor: int = 1  # 1 means a single person holds the majority of the history
    reason: str = ""


class TechDebtFile(BaseModel):
    path: str
    count: int  # number of TODO/FIXME/HACK/XXX markers in the file


class DocCoverageFile(BaseModel):
    path: str
    code_lines: int
    comment_lines: int
    ratio: int  # 0-100, comment/(code+comment) as a percentage
    reason: str


class DocCoverage(BaseModel):
    total_source_files: int = 0
    documented_files: int = 0
    undocumented_files: int = 0
    doc_percent: int = 0  # 0-100, documented source files / total source files
    under_documented: list[DocCoverageFile] = []  # ranked by code size
    notes: list[str] = []


class SilentFailure(BaseModel):
    path: str
    line: int
    category: str  # "bare_except" | "swallowed" | "empty_catch"
    snippet: str
    reason: str  # plain-language explanation for a non-programmer


class ErrorHandling(BaseModel):
    total: int = 0
    files_affected: int = 0
    findings: list[SilentFailure] = []  # ranked worst-first
    notes: list[str] = []


class UnusedExport(BaseModel):
    path: str
    name: str
    kind: str  # "function" | "class"
    line: int
    reason: str  # plain-language explanation for a non-programmer


class UnusedExports(BaseModel):
    total: int = 0
    files_affected: int = 0
    findings: list[UnusedExport] = []
    notes: list[str] = []


class ExternalService(BaseModel):
    name: str
    category: str  # AI / 大模型 | 云服务 | 数据库 | 支付 | 通讯 | ...
    note: str  # plain-language "what you need to run this"
    file_count: int = 1
    example: str = ""  # a sample import/usage line


class Integrations(BaseModel):
    total: int = 0
    services: list[ExternalService] = []  # most-used first
    categories: dict[str, int] = {}
    notes: list[str] = []


class EnvVar(BaseModel):
    name: str
    required: bool  # read via os.environ["X"] somewhere, so it must be set
    count: int = 1  # how many places read it
    documented: bool = True  # mentioned in .env.example / README / docs anywhere


class EntryPoint(BaseModel):
    path: str
    kind: str  # "command" (declared CLI) | "script" (__main__ guard) | "convention"
    command: str  # how to invoke it (e.g. "python run.py" or a console command name)
    reason: str = ""


class CliCommand(BaseModel):
    name: str
    framework: str  # "click" | "typer" | "argparse"
    help: str = ""  # one-line description, from help= or the function docstring
    options: list[str] = []  # declared --flags / argument names
    path: str
    line: int


class DataModelField(BaseModel):
    name: str
    type: str = ""  # the annotation as written, e.g. "int" or "list[str]"
    has_default: bool = False


class DataModel(BaseModel):
    name: str
    kind: str  # "dataclass" | "pydantic" | "typeddict" | "namedtuple"
    fields: list[DataModelField] = []
    path: str
    line: int


class TunableSetting(BaseModel):
    name: str  # the constant's UPPER_SNAKE name
    kind: str  # "number" | "text" | "flag" | "list" | "mapping" | "other"
    value: str  # the literal value, rendered short (strings quoted, long ones truncated)
    path: str
    line: int


class ConfigFile(BaseModel):
    path: str
    kind: str  # "yaml" | "toml" | "ini" | "json" | "properties"
    sections: list[str] = []  # [section] headers (TOML/INI)
    keys: list[str] = []  # top-level settings the reader can change
    setting_count: int = 0


class ScheduledTask(BaseModel):
    name: str  # what runs (function / job name, or the workflow file stem)
    # "github-actions" | "apscheduler" | "celery" | "schedule" | "repeat-every"
    # | "node-cron" | "nestjs" | "interval"
    mechanism: str
    schedule: str = ""  # the raw schedule as written ("*/5 * * * *", "seconds=30")
    schedule_human: str = ""  # plain-language gloss, "" when not derivable
    path: str
    line: int


class CiCheck(BaseModel):
    tool: str  # the tool that runs the gate ("ruff", "pytest", "tsc", ...)
    # "lint" | "format" | "typecheck" | "test" | "coverage" | "security"
    # | "build" | "deploy"
    category: str
    # "github-actions" | "pre-commit" | "gitlab-ci" | "circleci"
    # | "azure-pipelines" | "travis" | "jenkins"
    system: str
    trigger: str = ""  # plain-language trigger gloss (GitHub Actions only)
    path: str
    line: int


class LicenseFinding(BaseModel):
    spdx: str  # canonical SPDX id ("MIT", "GPL-3.0", ...) or "unknown"
    name: str  # English display name
    name_zh: str  # plain-Chinese name
    # "permissive" | "weak-copyleft" | "strong-copyleft" | "network-copyleft"
    # | "public-domain" | "source-available" | "unknown"
    category: str
    source_path: str  # the file the license was found in
    # "license-file" | "manifest" | "classifier" | "spdx-tag"
    source_kind: str
    line: int


class LicenseSummary(BaseModel):
    total: int = 0  # distinct recognised licenses
    primary: str = ""  # best-guess project license SPDX id, "" if none found
    primary_category: str = ""
    found: list[LicenseFinding] = []
    categories: list[str] = []
    notes: list[str] = []


class ReleaseAutomation(BaseModel):
    trigger: str = ""  # "tag-push" | "release" | "manual" | ""
    trigger_zh: str = ""  # plain-language gloss of what kicks the release off
    # "PyPI" | "npm" | "GitHub Release" | "crates.io" | "RubyGems" | "Docker 镜像"
    target: str
    path: str
    line: int


class ReleaseSummary(BaseModel):
    version: str = ""  # current version string, "" if none found
    version_source: str = ""  # path the version was read from
    # "pyproject" | "package-json" | "cargo" | "setup-py" | "setup-cfg"
    # | "version-file" | "dunder" | "pom" | "gradle"
    version_source_kind: str = ""
    dynamic_from_vcs: bool = False  # version derived from git tags at build time
    # "semver" | "zerover" | "calver" | "prerelease" | "twopart" | "single" | "other"
    scheme: str = ""
    scheme_zh: str = ""
    changelog_path: str = ""
    changelog_style: str = "none"  # "keepachangelog" | "versioned" | "freeform" | "none"
    changelog_style_zh: str = ""
    automation: list[ReleaseAutomation] = []
    publish_targets: list[str] = []
    notes: list[str] = []


class ContributionRequirement(BaseModel):
    # "guide" | "pr-template" | "issue-template" | "commit-convention" | "dco"
    # | "cla" | "codeowners" | "code-of-conduct" | "security"
    kind: str
    label_zh: str  # plain-Chinese label ("DCO 签署", "提交信息规范", ...)
    detail_zh: str  # one-line gloss a newcomer can act on
    path: str  # the community-health file this requirement was read from
    line: int = 0  # line of the matched text, 0 for a plain presence signal


class ContributionGuide(BaseModel):
    has_guide: bool = False  # a CONTRIBUTING file exists
    requirements: list[ContributionRequirement] = []
    notes: list[str] = []


class ComplexFile(BaseModel):
    path: str
    complexity: int  # approximate cyclomatic complexity (decision points + 1)
    functions: int = 0
    reason: str = ""


class Dependency(BaseModel):
    name: str
    version: str = ""  # the declared version constraint, if any
    kind: str  # "runtime" | "dev" | "optional"
    manifest: str  # the manifest file it was declared in (requirements.txt, etc.)
    # Plain-language note on what this library is for; None when the package is
    # not in the curated dictionary.
    purpose: str | None = None


class ActivityWindow(BaseModel):
    commits: int = 0
    authors: list[str] = []
    files: list[str] = []


class ActivityContributor(BaseModel):
    author: str
    commits: int


class ActivitySummary(BaseModel):
    available: bool = False
    total_commits: int = 0
    first_commit_days_ago: float | None = None
    last_commit_days_ago: float | None = None
    label: str = ""  # active | slowing | quiet | stale | abandoned | unknown
    label_zh: str = ""
    windows: dict[str, ActivityWindow] = {}
    top_contributors: list[ActivityContributor] = []
    recently_changed: list[str] = []
    notes: list[str] = []


class HealthScore(BaseModel):
    score: int = 0
    grade: str = "F"
    category_scores: dict[str, int] = {}
    weights: dict[str, float] = {}
    strengths: list[str] = []
    weaknesses: list[str] = []
    notes: list[str] = []


class ActionItem(BaseModel):
    priority: str  # "high" | "medium" | "low"
    category: str  # security | test_coverage | complexity | architecture | tech_debt
    title: str
    target: str = ""  # file path, or "" when not file-specific
    detail: str = ""
    effort: str = "medium"  # "small" | "medium" | "large"


class ActionPlan(BaseModel):
    total: int = 0
    items: list[ActionItem] = []
    notes: list[str] = []


class ApiRoute(BaseModel):
    method: str  # GET | POST | PUT | PATCH | DELETE | OPTIONS | HEAD | ANY | ALL
    path: str  # the route path as declared in the source
    handler: str = ""  # handler function / class name
    description: str = ""  # brief description from docstring or annotation
    file: str
    line: int


class ApiMap(BaseModel):
    total: int = 0
    routes: list[ApiRoute] = []
    frameworks: list[str] = []  # detected framework names
    notes: list[str] = []


class SecurityFinding(BaseModel):
    file: str
    line: int
    category: str  # "hardcoded_secret" | "dangerous_call" | "shell_injection" | "debug_mode"
    snippet: str  # the matching line, truncated
    reason: str  # plain-language explanation for a non-programmer


class SecuritySummary(BaseModel):
    total: int = 0
    critical: int = 0  # hardcoded_secret + dangerous_call count (non-test files)
    findings: list[SecurityFinding] = []
    notes: list[str] = []


class ProjectSummary(BaseModel):
    """A lightweight entry in the project library list (no file contents)."""

    id: str
    name: str
    total_files: int = 0
    created_at: float | None = None  # unix seconds; None for in-memory-only


class ProjectMeta(BaseModel):
    id: str
    name: str
    total_files: int
    files: list[FileInfo]
    reading_map: list[ReadingStep]
    hotspots: list[Hotspot] = []
    code_walk: list[CodeWalkStep] = []
    import_cycles: list[ImportCycle] = []
    orphan_modules: list[OrphanModule] = []
    coupling_hotspots: list[CouplingHotspot] = []
    blast_radius: list[BlastRadiusHotspot] = []
    architecture_layers: list[ArchitectureLayer] = []
    package_dependencies: list[PackageDependency] = []
    health: ProjectHealth | None = None
    churn_hotspots: list[ChurnHotspot] = []
    co_change_couplings: list[CoChangeCoupling] = []
    risk_hotspots: list[RiskHotspot] = []
    test_coverage: TestCoverageSummary | None = None
    knowledge_silos: list[KnowledgeSilo] = []
    tech_debt_files: list[TechDebtFile] = []
    env_vars: list[EnvVar] = []
    entry_points: list[EntryPoint] = []
    cli_commands: list[CliCommand] = []
    data_models: list[DataModel] = []
    tunable_settings: list[TunableSetting] = []
    config_files: list[ConfigFile] = []
    scheduled_tasks: list[ScheduledTask] = []
    ci_checks: list[CiCheck] = []
    licenses: LicenseSummary | None = None
    complexity_files: list[ComplexFile] = []
    dependencies: list[Dependency] = []
    security: SecuritySummary | None = None
    api_map: ApiMap | None = None
    activity: ActivitySummary | None = None
    health_score: HealthScore | None = None
    action_plan: ActionPlan | None = None
    doc_coverage: DocCoverage | None = None
    error_handling: ErrorHandling | None = None
    unused_exports: UnusedExports | None = None
    integrations: Integrations | None = None
    release: ReleaseSummary | None = None
    contribution: ContributionGuide | None = None


class FileRole(BaseModel):
    path: str
    role: str
    importance: str = "medium"


class ProjectOverview(BaseModel):
    summary: str = ""
    description: str = ""
    files: list[FileRole] = []
    how_to_run: list[str] = []
    quick_tips: list[str] = []


class Annotation(BaseModel):
    line_start: int
    line_end: int
    annotation: str


class FileAnnotations(BaseModel):
    path: str
    language: str
    annotations: list[Annotation]


class QARequest(BaseModel):
    question: str
    code: str = ""
    file_path: str = ""
    language: str = ""


class EditRequest(BaseModel):
    instruction: str
    code: str
    file_path: str = ""
    language: str = ""


class GlossaryTerm(BaseModel):
    term: str
    definition: str


class FileGlossary(BaseModel):
    path: str
    terms: list[GlossaryTerm] = []


class FileDependencies(BaseModel):
    path: str
    imports: list[str] = []  # in-project files this file imports
    imported_by: list[str] = []  # in-project files that import this file


class Definition(BaseModel):
    name: str
    qualname: str = ""  # "Class.method" for methods, plain name otherwise
    kind: str  # function | class | method
    parent: str | None = None  # enclosing class for a method
    lang: str = ""  # python | js
    file: str
    line: int
    exported: bool = False  # part of the public surface (non-underscore / exported)


class DefinitionMatches(BaseModel):
    """Where a clicked name is defined — the jump-to-definition payload."""

    name: str  # the queried name
    total: int = 0  # number of places that define it
    definitions: list[Definition] = []
    notes: list[str] = []


class PublicApi(BaseModel):
    """A project's public surface — the names it exposes for other code to call."""

    total: int = 0  # number of public definitions
    definitions: list[Definition] = []
    notes: list[str] = []


class Reference(BaseModel):
    name: str
    file: str
    line: int
    text: str = ""  # the trimmed source line, for a one-line preview
    is_definition: bool = False  # True when this occurrence is the declaration


class ReferenceMatches(BaseModel):
    """Where a clicked name is used — the find-all-references payload."""

    name: str  # the queried name
    total: int = 0  # number of use sites (including the definition)
    files: int = 0  # number of distinct files it appears in
    references: list[Reference] = []
    notes: list[str] = []


class OutlineNode(BaseModel):
    name: str
    qualname: str = ""  # "Class.method" for methods, plain name otherwise
    kind: str  # function | class | method
    parent: str | None = None  # enclosing class for a method
    lang: str = ""  # python | js
    file: str
    line: int
    exported: bool = False  # part of the public surface (non-underscore / exported)
    children: list["OutlineNode"] = []  # a class's methods (and nested classes)


class FileOutline(BaseModel):
    """One file's structure, in source order — the file's table of contents."""

    file: str
    lang: str = ""  # python | js
    total: int = 0  # number of definitions, nested ones included
    outline: list[OutlineNode] = []
    notes: list[str] = []


class GitHubRequest(BaseModel):
    url: str = Field(..., pattern=r"^https?://github\.com/.+/.+")


class UploadedFile(BaseModel):
    path: str
    content: str


class AnalyzeRequest(BaseModel):
    """Sent from frontend with uploaded files."""

    files: list[UploadedFile]
    project_name: str = "untitled"
