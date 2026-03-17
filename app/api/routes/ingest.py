from fastapi import APIRouter, HTTPException
from threading import Thread

from app.core.config import get_settings
from app.schemas.ingest import (
    IngestJobProgress,
    IngestJobStartRequest,
    IngestJobStartResponse,
    IngestJobStatusResponse,
    IngestRunRequest,
    IngestRunResponse,
    OverpassIngestRequest,
)
from app.services.ingest_job_service import IngestJobService
from scripts.etl.bootstrap_schema import run_schema_bootstrap
from scripts.etl.overpass_ingest import OverpassFetchError, run_overpass_ingest
from scripts.etl.real_ingest import run_real_ingest
from scripts.etl.sample_ingest import run_sample_ingest

router = APIRouter()
job_service = IngestJobService()


@router.post("/run", response_model=IngestRunResponse)
def run_ingest(request: IngestRunRequest) -> IngestRunResponse:
    settings = get_settings()
    source_url = request.source_url or settings.app_ingest_default_source_url
    run_schema_bootstrap()
    source_kind = request.source_kind.lower().strip()

    if source_kind == "overpass":
        try:
            loaded_rows = run_overpass_ingest(
                source_name=request.source_name,
                mode=request.overpass_mode,
                max_elements=request.overpass_max_elements,
            )
        except OverpassFetchError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
    elif source_kind == "generic":
        loaded_rows = run_real_ingest(
            source_format=request.source_format,
            source_name=request.source_name,
            source_url=source_url,
            source_path=request.source_path,
        )
    else:
        raise HTTPException(status_code=400, detail="source_kind must be 'generic' or 'overpass'")
    return _build_ingest_response(
        loaded_rows=loaded_rows,
        include_sample_if_empty=request.include_sample_if_empty,
        success_message="Schema bootstrap and source ingestion completed.",
    )


@router.post("/overpass", response_model=IngestRunResponse)
def run_overpass_preset_ingest(request: OverpassIngestRequest) -> IngestRunResponse:
    preset = request.preset.lower().strip()
    if preset not in {"streets", "houses", "both"}:
        raise HTTPException(status_code=400, detail="preset must be 'streets', 'houses' or 'both'")

    run_schema_bootstrap()
    try:
        loaded_rows = run_overpass_ingest(
            source_name=request.source_name,
            mode=preset,
            max_elements=request.max_elements,
        )
    except OverpassFetchError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    return _build_ingest_response(
        loaded_rows=loaded_rows,
        include_sample_if_empty=request.include_sample_if_empty,
        success_message=f"Schema bootstrap and Overpass preset '{preset}' ingestion completed.",
    )


@router.post("/overpass/job", response_model=IngestJobStartResponse, status_code=202)
def start_overpass_ingest_job(request: IngestJobStartRequest) -> IngestJobStartResponse:
    job_id = job_service.create_job(
        source_name=request.source_name,
        mode=request.mode,
        max_elements=request.max_elements,
    )
    _spawn_job_worker(job_id)
    return IngestJobStartResponse(job_id=job_id, status="queued")


@router.get("/overpass/job/{job_id}", response_model=IngestJobStatusResponse)
def get_overpass_ingest_job_status(job_id: str) -> IngestJobStatusResponse:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Ingest job '{job_id}' not found.")

    return IngestJobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress=IngestJobProgress(**job.progress),
        loaded_rows=job.loaded_rows,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _spawn_job_worker(job_id: str) -> None:
    thread = Thread(target=_run_overpass_ingest_job, args=(job_id,), daemon=True)
    thread.start()


def _run_overpass_ingest_job(job_id: str) -> None:
    job = job_service.get_job(job_id)
    if job is None:
        return

    try:
        job_service.start_job(job_id)
        run_schema_bootstrap()

        loaded_rows = run_overpass_ingest(
            source_name=job.source_name,
            mode=job.mode,
            max_elements=job.max_elements,
            progress_callback=lambda stage, message, completed_steps: job_service.update_progress(
                job_id,
                stage=stage,
                message=message,
                completed_steps=completed_steps,
            ),
        )
        job_service.mark_succeeded(job_id, loaded_rows=loaded_rows)
    except Exception as exc:
        job_service.mark_failed(job_id, error=str(exc))


def _build_ingest_response(
    loaded_rows: int, include_sample_if_empty: bool, success_message: str
) -> IngestRunResponse:
    if loaded_rows == 0 and include_sample_if_empty:
        run_sample_ingest()
        return IngestRunResponse(
            status="ok",
            message="Schema bootstrap done; source empty, sample ingestion completed.",
            loaded_rows=0,
        )
    return IngestRunResponse(status="ok", message=success_message, loaded_rows=loaded_rows)
