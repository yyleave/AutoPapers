from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


@dataclass(frozen=True)
class Message:
    type: Literal["info", "warning", "error", "result"]
    content: str
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    meta: dict[str, Any] = field(default_factory=dict)

