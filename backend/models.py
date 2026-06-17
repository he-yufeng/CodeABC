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
