from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IngestRunRequest(BaseModel):
    source_kind: str = Field(
        default="generic",
        description="Ingest source kind: generic or overpass.",
    )
    source_url: str | None = Field(
        default=None,
        description="Public URL to JSON/CSV source file.",
    )
    source_path: str | None = Field(
        default=None,
        description="Local path to JSON/CSV source file.",
    )
    source_format: str = Field(
        default="json",
        description="Input file format: json or csv.",
    )
    source_name: str = Field(
        default="custom_source",
        description="Source name for provenance in graph nodes.",
    )
    overpass_mode: str = Field(
        default="both",
        description="Overpass mode: streets, houses, or both.",
    )
    overpass_max_elements: int = Field(
        default=5000,
        ge=100,
        le=50000,
        description="Hard limit for returned Overpass elements.",
    )
    include_sample_if_empty: bool = Field(
        default=True,
        description="Fallback to built-in sample ingest when source has no valid rows.",
    )


class IngestRunResponse(BaseModel):
    status: str
    message: str
    loaded_rows: int


class OverpassIngestRequest(BaseModel):
    preset: str = Field(
        default="both",
        description="Preset: streets, houses, or both.",
    )
    source_name: str = Field(
        default="overpass_moscow",
        description="Source name for provenance in graph nodes.",
    )
    max_elements: int = Field(
        default=5000,
        ge=100,
        le=50000,
        description="Hard limit for returned Overpass elements.",
    )
    include_sample_if_empty: bool = Field(
        default=True,
        description="Fallback to built-in sample ingest when source has no valid rows.",
    )


class IngestJobStartRequest(BaseModel):
    mode: Literal["streets", "houses", "both"] = Field(
        default="both",
        description="Overpass mode: streets, houses, or both.",
    )
    source_name: str = Field(
        default="overpass_moscow",
        description="Source name for provenance in graph nodes.",
    )
    max_elements: int = Field(
        default=5000,
        ge=100,
        le=50000,
        description="Hard limit for returned Overpass elements.",
    )


class IngestJobProgress(BaseModel):
    stage: str = Field(
        default="queued",
        description="Current ingest stage.",
    )
    message: str = Field(
        default="Job created and waiting to start.",
        description="Human-readable progress message.",
    )
    completed_steps: int = Field(default=0, ge=0)
    total_steps: int = Field(default=4, ge=1)


class IngestJobStartResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]


class IngestJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: IngestJobProgress
    loaded_rows: int | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
