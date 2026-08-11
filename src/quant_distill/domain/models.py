from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class DependencyHealth:
    name: str
    status: str
    detail: str | None = None


@dataclass(slots=True)
class RequestContext:
    request_id: str
    source: str
    source_item_id: str
    received_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
