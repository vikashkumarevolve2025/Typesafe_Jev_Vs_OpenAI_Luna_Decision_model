from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import chess

PlayerKind = Literal["llm", "system_one", "offline"]


def empty_usage() -> dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}


@dataclass
class CallRecord:
    """Everything the Call Inspector shows for one provider call."""

    attempt: int
    request: Any = None  # exact payload sent; None for offline players
    prompts: dict[str, Any] = field(default_factory=dict)
    reply: Any = None
    parsed_move: str | None = None
    stop_reason: str | None = None
    usage: dict[str, int] = field(default_factory=empty_usage)
    latency_ms: float = 0.0
    cost_usd: float | None = None
    signals: dict[str, Any] | None = None
    error: str | None = None
    diagnosis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Player(ABC):
    id: str
    label: str
    group: str
    kind: PlayerKind

    def availability(self) -> tuple[bool, str | None]:
        """(available, note). The note shows next to the name in the dropdown."""
        return True, None

    @abstractmethod
    def choose(
        self,
        board: chess.Board,
        enc: dict[str, Any],
        *,
        compact: bool,
        attempt: int,
        feedback: str | None,
    ) -> CallRecord: ...

    def info(self) -> dict[str, Any]:
        available, note = self.availability()
        return {"id": self.id, "label": self.label, "group": self.group, "kind": self.kind, "available": available, "note": note}
