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


class EnvVar(BaseModel):
    name: str
    required: bool  # read via os.environ["X"] somewhere, so it must be set
    count: int = 1  # how many places read it


class EntryPoint(BaseModel):
    path: str
    kind: str  # "command" (declared CLI) | "script" (__main__ guard) | "convention"
    command: str  # how to invoke it (e.g. "python run.py" or a console command name)
    reason: str = ""


class ComplexFile(BaseModel):
    path: str
    complexity: int  # approximate cyclomatic complexity (decision points + 1)
    functions: int = 0
    reason: str = ""


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
    complexity_files: list[ComplexFile] = []


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


class GitHubRequest(BaseModel):
    url: str = Field(..., pattern=r"^https?://github\.com/.+/.+")


class UploadedFile(BaseModel):
    path: str
    content: str


class AnalyzeRequest(BaseModel):
    """Sent from frontend with uploaded files."""

    files: list[UploadedFile]
    project_name: str = "untitled"
