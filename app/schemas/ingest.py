from pydantic import BaseModel, Field


class IngestRunRequest(BaseModel):
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
    include_sample_if_empty: bool = Field(
        default=True,
        description="Fallback to built-in sample ingest when source has no valid rows.",
    )


class IngestRunResponse(BaseModel):
    status: str
    message: str
    loaded_rows: int
