"""Delivery-manager flow: create projects, manage rubrics, checks, references."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from core.deterministic import list_common_checks, list_project_checks
from core.registry import (
    REPO_ROOT,
    Project,
    create_project,
    list_projects,
    list_tasks,
)

from . import files
from .deps import bad_request, get_project, listdir_names, rubric_criteria
from .models import (
    ProjectDetail,
    ProjectSummary,
    ProjectType,
    RubricBody,
    UploadResult,
    ValidationMode,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        name=project.name,
        type=project.type,
        description=project.description,
        validation_mode=project.validation_mode,
        include_common_checks=project.include_common_checks,
        has_rubric=project.rubric_path.is_file(),
        project_checks=len(list_project_checks(project)),
        common_checks=len(list_common_checks()) if project.include_common_checks else 0,
        tasks=len(list_tasks(project)),
    )


def _detail(project: Project) -> ProjectDetail:
    project_names = {p.name for p in list_project_checks(project)}
    common_names = (
        [p.name for p in list_common_checks() if p.name not in project_names]
        if project.include_common_checks
        else []
    )
    return ProjectDetail(
        **_summary(project).model_dump(),
        rubric_path=str(project.rubric_path.relative_to(REPO_ROOT)),
        rubric_criteria=rubric_criteria(project.rubric_path),
        project_check_names=sorted(project_names),
        common_check_names=common_names,
        extra_references=listdir_names(project.extra_references_dir),
        task_ids=list_tasks(project),
    )


@router.get("", response_model=list[ProjectSummary])
def get_projects() -> list[ProjectSummary]:
    return [_summary(p) for p in list_projects()]


@router.post("", response_model=ProjectDetail, status_code=201)
async def post_project(
    name: str = Form(...),
    type: ProjectType = Form(...),
    description: str = Form(""),
    validation_mode: ValidationMode | None = Form(None),
    rubric_text: str | None = Form(None),
    rubric_file: UploadFile | None = File(None),
    checks: list[UploadFile] = File(default_factory=list),
    extra_references: list[UploadFile] = File(default_factory=list),
) -> ProjectDetail:
    """Create a project and populate it in one call — the UI's Create button.

    Rolls the whole directory back if any uploaded file is rejected, so a
    failed create never leaves a half-built project behind.
    """
    try:
        project = create_project(name, type, description, validation_mode)
    except (ValueError, FileExistsError) as exc:
        raise bad_request(exc) from exc
    except FileNotFoundError as exc:  # template missing
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        if rubric_file is not None and rubric_file.filename:
            files.safe_filename(rubric_file.filename, files.RUBRIC_SUFFIXES)
            files.write_text(project.rubric_path, (await rubric_file.read()).decode())
        elif rubric_text and rubric_text.strip():
            files.write_text(project.rubric_path, rubric_text)

        for upload in checks:
            if not upload.filename:
                continue
            files.write_upload(
                project.checks_dir,
                upload.filename,
                await upload.read(),
                files.CHECK_SUFFIXES,
                executable=True,
            )
        for upload in extra_references:
            if not upload.filename:
                continue
            files.write_upload(
                project.extra_references_dir, upload.filename, await upload.read()
            )
    except files.UploadError as exc:
        shutil.rmtree(project.root, ignore_errors=True)
        raise bad_request(exc) from exc

    return _detail(get_project(name))


@router.get("/{name}", response_model=ProjectDetail)
def get_project_detail(name: str) -> ProjectDetail:
    return _detail(get_project(name))


@router.get("/{name}/rubric", response_model=RubricBody)
def get_rubric(name: str) -> RubricBody:
    project = get_project(name)
    if not project.rubric_path.is_file():
        raise HTTPException(status_code=404, detail=f"no rubric for project: {name}")
    return RubricBody(content=project.rubric_path.read_text())


@router.put("/{name}/rubric", response_model=ProjectDetail)
async def put_rubric(
    name: str,
    content: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> ProjectDetail:
    project = get_project(name)
    try:
        if file is not None and file.filename:
            files.safe_filename(file.filename, files.RUBRIC_SUFFIXES)
            files.write_text(project.rubric_path, (await file.read()).decode())
        elif content is not None:
            files.write_text(project.rubric_path, content)
        else:
            raise files.UploadError("provide either `content` or a `.toml` file")
    except files.UploadError as exc:
        raise bad_request(exc) from exc
    return _detail(project)


@router.get("/{name}/checks")
def get_checks(name: str) -> dict:
    project = get_project(name)
    project_names = [p.name for p in list_project_checks(project)]
    common = (
        [p.name for p in list_common_checks() if p.name not in set(project_names)]
        if project.include_common_checks
        else []
    )
    return {"project": sorted(project_names), "common": common}


@router.post("/{name}/checks", response_model=UploadResult)
async def post_checks(name: str, files_: list[UploadFile] = File(..., alias="files")) -> UploadResult:
    project = get_project(name)
    result = UploadResult()
    for upload in files_:
        if not upload.filename:
            continue
        try:
            path = files.write_upload(
                project.checks_dir,
                upload.filename,
                await upload.read(),
                files.CHECK_SUFFIXES,
                executable=True,
            )
            result.written.append(path.name)
        except files.UploadError as exc:
            result.skipped.append({"filename": upload.filename, "reason": str(exc)})
    if not result.written and result.skipped:
        raise HTTPException(status_code=400, detail=result.skipped)
    return result


@router.delete("/{name}/checks/{filename}", response_model=UploadResult)
def delete_check(name: str, filename: str) -> UploadResult:
    """Remove one of the project's own checks. The common set is read-only here."""
    project = get_project(name)
    try:
        safe = files.safe_filename(filename, files.CHECK_SUFFIXES)
    except files.UploadError as exc:
        raise bad_request(exc) from exc
    path = project.checks_dir / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"check not found: {safe}")
    path.unlink()
    return UploadResult(written=[], skipped=[{"filename": safe, "reason": "deleted"}])


@router.get("/{name}/extra-references")
def get_extra_references(name: str) -> dict:
    project = get_project(name)
    return {"files": listdir_names(project.extra_references_dir)}


@router.post("/{name}/extra-references", response_model=UploadResult)
async def post_extra_references(
    name: str, files_: list[UploadFile] = File(..., alias="files")
) -> UploadResult:
    project = get_project(name)
    result = UploadResult()
    for upload in files_:
        if not upload.filename:
            continue
        try:
            path = files.write_upload(
                project.extra_references_dir, upload.filename, await upload.read()
            )
            result.written.append(path.name)
        except files.UploadError as exc:
            result.skipped.append({"filename": upload.filename, "reason": str(exc)})
    if not result.written and result.skipped:
        raise HTTPException(status_code=400, detail=result.skipped)
    return result
