"""Capability declarations for quantum engines."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
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
    "p",
    "rx",
    "ry",
    "rz",
    "cx",
    "cz",
    "cp",
    "swap",
    "measure",
    "partial_measurement",
    "mapped_measurement",
    "auto_measure_all",
    "intermediate_measurement",
    "parameterized",
    "mcx",
    "ccx",
    "unitary",
    "observables",
    "gradients",
    "statevector",
    "noise",
    "local_execution",
    "remote_execution",
    "async_jobs",
    "logical_input",
    "native_circuit_input",
    "neutralization",
    "native_transpilation",
    "compiler",
    "executor",
    "renderer",
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
        object.__setattr__(self, "statuses", MappingProxyType(dict(self.statuses)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

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
