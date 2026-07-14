"""SDK-free availability data for engine ports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EngineAvailability:
    engine: str
    installed: bool
    compatible: bool
    version: str | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.installed and self.compatible

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "installed": self.installed,
            "compatible": self.compatible,
            "available": self.available,
            "version": self.version,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }
