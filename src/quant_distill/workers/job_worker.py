from __future__ import annotations

import logging
import threading
from typing import Any

from quant_distill.domain.schemas import ProcessRequest

log = logging.getLogger("quant_distill.job_worker")


class JobWorker(threading.Thread):
    """Pulls queued jobs off the store and runs the full pipeline outside the HTTP request."""

    def __init__(
        self,
        *,
        jobs_repository: Any,
        service: Any,
        poll_interval: float = 2.0,
        name: str = "job-worker",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.jobs = jobs_repository
        self.service = service
        self.poll_interval = poll_interval
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            if not self.run_once():
                self._stop.wait(self.poll_interval)

    def run_once(self) -> bool:
        """Claim and run at most one job. Returns True when a job was processed."""
        try:
            job = self.jobs.claim()
        except Exception:
            log.exception("job claim failed")
            return False
        if job is None:
            return False
        self._run_job(job)
        return True

    def _run_job(self, job: dict[str, Any]) -> None:
        job_id = job["job_id"]
        try:
            request = ProcessRequest.model_validate(job["request"])
            result = self.service.process(request)
        except Exception as exc:
            log.exception("job %s failed", job_id)
            try:
                self.jobs.fail(job_id, f"{type(exc).__name__}: {exc}")
            except Exception:
                log.exception("job %s failure write failed", job_id)
            return

        try:
            self.jobs.complete(job_id, result)
        except Exception:
            log.exception("job %s result write failed", job_id)
