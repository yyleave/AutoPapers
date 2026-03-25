from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class Agent(Protocol):
    name: str
    role: str

    def run(self, state: Any) -> Any: ...


@dataclass(frozen=True)
class BaseAgent:
    name: str
    role: str

    def run(self, state: Any) -> Any:
        raise NotImplementedError

