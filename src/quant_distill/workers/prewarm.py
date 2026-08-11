from __future__ import annotations

import logging
import os
import time

from quant_distill.config import settings
from quant_distill.logging import configure_logging

log = logging.getLogger("quant_distill.prewarm")


def main() -> None:
    configure_logging()
    interval = int(os.environ.get("PREWARM_INTERVAL", "300"))
    if not settings.prewarm_enabled:
        log.info("prewarm worker disabled")
        return
    while True:
        log.info("prewarm tick")
        time.sleep(interval)


if __name__ == "__main__":
    main()
