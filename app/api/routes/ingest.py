from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.ingest import IngestRunRequest, IngestRunResponse
from scripts.etl.bootstrap_schema import run_schema_bootstrap
from scripts.etl.real_ingest import run_real_ingest
from scripts.etl.sample_ingest import run_sample_ingest

router = APIRouter()


@router.post("/run", response_model=IngestRunResponse)
def run_ingest(request: IngestRunRequest) -> IngestRunResponse:
    settings = get_settings()
    source_url = request.source_url or settings.app_ingest_default_source_url
    run_schema_bootstrap()
    loaded_rows = run_real_ingest(
        source_format=request.source_format,
        source_name=request.source_name,
        source_url=source_url,
        source_path=request.source_path,
    )
    if loaded_rows == 0 and request.include_sample_if_empty:
        run_sample_ingest()
        return IngestRunResponse(
            status="ok",
            message="Schema bootstrap done; source empty, sample ingestion completed.",
            loaded_rows=0,
        )

    return IngestRunResponse(
        status="ok",
        message="Schema bootstrap and real source ingestion completed.",
        loaded_rows=loaded_rows,
    )
