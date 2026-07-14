"""Capability declarations for quantum engines."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal


CapabilityStatus = Literal["supported", "lowered", "experimental", "unsupported", "not_tested"]

VALID_CAPABILITY_STATUSES: frozenset[str] = frozenset(
    {"supported", "lowered", "experimental", "unsupported", "not_tested"}
)


COMMON_CAPABILITIES: tuple[str, ...] = (
    "x",
    "y",
    "z",
    "h",
    "rx",
    "ry",
    "rz",
    "cx",
    "cz",
    "swap",
    "measure",
    "parameterized",
    "mcx",
    "ccx",
    "observables",
    "gradients",
    "local_execution",
    "remote_execution",
    "async_jobs",
)


@dataclass(frozen=True)
class EngineCapabilities:
    engine: str
    statuses: Mapping[str, CapabilityStatus]
    installed: bool = True
    default: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        invalid = {
            feature: status
            for feature, status in self.statuses.items()
            if status not in VALID_CAPABILITY_STATUSES
        }
        if invalid:
            feature, status = next(iter(invalid.items()))
            raise ValueError(f"Capability '{feature}' has invalid status '{status}'")

    def status(self, feature: str) -> CapabilityStatus:
        return self.statuses.get(feature, "unsupported")

    def supports(self, feature: str) -> bool:
        return self.status(feature) in {"supported", "lowered"}

    def to_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "installed": self.installed,
            "default": self.default,
            "capabilities": {feature: self.status(feature) for feature in COMMON_CAPABILITIES},
            "metadata": dict(self.metadata),
        }
