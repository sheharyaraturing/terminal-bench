"""Request/response models for the autoreviewer API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ProjectType = Literal["harbor", "non-harbor"]
ValidationMode = Literal["oracle_nop", "skip"]


class ProjectSummary(BaseModel):
    name: str
    type: str
    description: str = ""
    validation_mode: str
    include_common_checks: bool
    has_rubric: bool
    project_checks: int
    common_checks: int
    tasks: int


class ProjectDetail(ProjectSummary):
    rubric_path: str
    rubric_criteria: list[str] = Field(default_factory=list)
    project_check_names: list[str] = Field(default_factory=list)
    common_check_names: list[str] = Field(default_factory=list)
    extra_references: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)


class RubricBody(BaseModel):
    content: str


class ExecuteData(BaseModel):
    """Payload carrying the task location.

    `task_id` points at a task already present under the project's tasks/
    directory (uploaded via the API or committed to the repo). `gcs_path` is
    accepted for forward compatibility but not yet fetched.
    """

    task_id: str | None = None
    gcs_path: str | None = None


class ExecuteRequest(BaseModel):
    project_name: str
    project_id: str | None = None
    project_type: ProjectType | None = None
    reviewer_email: str | None = None
    is_gcs: bool = False
    data: ExecuteData = Field(default_factory=ExecuteData)


class RunAccepted(BaseModel):
    run_id: str
    state: str
    project: str
    task_id: str


class LogChunk(BaseModel):
    run_id: str
    offset: int
    text: str
    state: str


class UploadResult(BaseModel):
    written: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
