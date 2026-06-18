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


class GitHubRequest(BaseModel):
    url: str = Field(..., pattern=r"^https?://github\.com/.+/.+")


class UploadedFile(BaseModel):
    path: str
    content: str


class AnalyzeRequest(BaseModel):
    """Sent from frontend with uploaded files."""

    files: list[UploadedFile]
    project_name: str = "untitled"
