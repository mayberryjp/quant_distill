from __future__ import annotations

import logging
from typing import Any

from waitress import create_server

from quant_distill.api.app import app, service
from quant_distill.config import settings
from quant_distill.domain.stats import set_server_info_provider
from quant_distill.workers.job_worker import JobWorker

log = logging.getLogger("quant_distill.main")


def _start_job_workers() -> list[JobWorker]:
    if service.jobs is None:
        log.warning("job store not configured; /v1/process submissions will be rejected")
        return []
    if settings.job_requeue_running_on_start:
        # A previous process may have died mid-job, leaving rows stuck in 'running'.
        requeued = service.jobs.requeue_stale_running()
        if requeued:
            log.warning("requeued %s job(s) left running by a previous process", requeued)

    workers = []
    for index in range(max(1, settings.job_workers)):
        worker = JobWorker(
            jobs_repository=service.jobs,
            service=service,
            poll_interval=settings.job_poll_interval,
            name=f"job-worker-{index + 1}",
        )
        worker.start()
        workers.append(worker)
    return workers


def main() -> None:
    server = create_server(
        app,
        host=settings.api_listen_address,
        port=settings.api_port,
        threads=settings.api_threads,
    )
    dispatcher = getattr(server, "task_dispatcher", None)
    adjustments = getattr(server, "adj", None)

    def server_info() -> dict[str, Any]:
        info: dict[str, Any] = {}
        if dispatcher is not None:
            info["queue_depth"] = len(dispatcher.queue)
            info["threads_total"] = len(dispatcher.threads)
            info["threads_busy"] = dispatcher.active_count
            info["threads_idle"] = max(0, len(dispatcher.threads) - dispatcher.active_count)
        if adjustments is not None:
            info["connection_limit"] = adjustments.connection_limit
            info["channel_timeout_s"] = adjustments.channel_timeout
        return info

    set_server_info_provider(server_info)
    _start_job_workers()
    server.run()


if __name__ == "__main__":
    main()
