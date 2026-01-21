from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import uuid


@dataclass
class Job:
    id: str
    type: str
    status: str = "queued"
    progress: float = 0.0
    result_file: Optional[str] = None
    error: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class JobsStore:
    """In-Memory Job Store (Swagger-testbar)."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}

    def create(self, job_type: str) -> Job:
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, type=job_type)
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def set(self, job: Job) -> None:
        self._jobs[job.id] = job


jobs_store = JobsStore()
