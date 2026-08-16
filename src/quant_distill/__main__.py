from __future__ import annotations

from typing import Any

from waitress import create_server

from quant_distill.api.app import app
from quant_distill.config import settings
from quant_distill.domain.stats import set_server_info_provider


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
    server.run()


if __name__ == "__main__":
    main()
