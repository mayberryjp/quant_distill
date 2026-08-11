from __future__ import annotations

from waitress import serve

from quant_distill.api.app import app
from quant_distill.config import settings


def main() -> None:
    serve(app, host=settings.api_listen_address, port=settings.api_port, threads=8)


if __name__ == "__main__":
    main()
