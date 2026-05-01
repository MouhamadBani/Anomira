from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4


class JobNotFoundError(Exception):
    pass


@dataclass
class JobRecord:
    job_id: str
    job_type: str
    status: str
    stage: str
    progress: float
    message: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    dataset: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "stage": self.stage,
            "progress": round(float(self.progress), 2),
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "dataset": deepcopy(self.dataset),
            "analysis": deepcopy(self.analysis),
            "metadata": deepcopy(self.metadata),
        }


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, JobRecord] = {}

    def create(
        self,
        *,
        job_type: str,
        message: str = "Job queued.",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JobRecord:
        job = JobRecord(
            job_id=uuid4().hex,
            job_type=job_type,
            status="queued",
            stage="queued",
            progress=0.0,
            message=message,
            created_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(f"Job '{job_id}' was not found")
        return job

    def snapshot(self, job_id: str) -> Dict[str, Any]:
        job = self.get(job_id)
        return job.to_payload()

    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        started: bool = False,
        finished: bool = False,
        error: Optional[str] = None,
        dataset: Optional[Dict[str, Any]] = None,
        analysis: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JobRecord:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Job '{job_id}' was not found")

            if status is not None:
                job.status = status
            if stage is not None:
                job.stage = stage
            if progress is not None:
                safe_progress = max(0.0, min(100.0, float(progress)))
                job.progress = safe_progress
            if message is not None:
                job.message = message
            if started and job.started_at is None:
                job.started_at = datetime.now(timezone.utc)
            if finished:
                job.finished_at = datetime.now(timezone.utc)
            if error is not None:
                job.error = error
            if dataset is not None:
                job.dataset = deepcopy(dataset)
            if analysis is not None:
                job.analysis = deepcopy(analysis)
            if metadata is not None:
                merged = deepcopy(job.metadata)
                merged.update(deepcopy(metadata))
                job.metadata = merged
            return job


job_store = JobStore()
