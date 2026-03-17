from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Literal
from uuid import uuid4

JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass
class IngestJobState:
    job_id: str
    source_name: str
    mode: str
    max_elements: int
    status: JobStatus = "queued"
    progress: dict = field(
        default_factory=lambda: {
            "stage": "queued",
            "message": "Job created and waiting to start.",
            "completed_steps": 0,
            "total_steps": 4,
        }
    )
    loaded_rows: int | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class IngestJobService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, IngestJobState] = {}

    def create_job(self, source_name: str, mode: str, max_elements: int) -> str:
        job_id = str(uuid4())
        state = IngestJobState(
            job_id=job_id,
            source_name=source_name,
            mode=mode,
            max_elements=max_elements,
        )
        with self._lock:
            self._jobs[job_id] = state
        return job_id

    def get_job(self, job_id: str) -> IngestJobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return deepcopy(job)

    def start_job(self, job_id: str) -> None:
        self._set_status(job_id, "running")
        self.update_progress(
            job_id,
            stage="bootstrap",
            message="Schema bootstrap is running.",
            completed_steps=0,
            total_steps=4,
        )

    def update_progress(
        self,
        job_id: str,
        *,
        stage: str,
        message: str,
        completed_steps: int,
        total_steps: int = 4,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.progress = {
                "stage": stage,
                "message": message,
                "completed_steps": completed_steps,
                "total_steps": total_steps,
            }

    def mark_succeeded(self, job_id: str, loaded_rows: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "succeeded"
            job.loaded_rows = loaded_rows
            job.finished_at = datetime.now(UTC)
            job.error = None
            job.progress = {
                "stage": "done",
                "message": "Ingest completed successfully.",
                "completed_steps": 4,
                "total_steps": 4,
            }

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error = error
            job.finished_at = datetime.now(UTC)
            job.progress = {
                "stage": "failed",
                "message": "Ingest failed.",
                "completed_steps": max(
                    int(job.progress.get("completed_steps", 0)),
                    1,
                ),
                "total_steps": int(job.progress.get("total_steps", 4)),
            }

    def _set_status(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = status
            now = datetime.now(UTC)
            if status == "running":
                job.started_at = now
                job.finished_at = None
