"""Coherent hardware provider bundle."""

from __future__ import annotations

from dataclasses import dataclass

from quantum_cq._hardware.protocols import (
    TargetArchitecturePort,
    TargetDiscoveryPort,
    TargetSnapshotPort,
)


@dataclass(frozen=True)
class HardwareProviderBundle:
    provider_id: str
    discovery: TargetDiscoveryPort
    architecture: TargetArchitecturePort
    snapshot: TargetSnapshotPort | None = None

    def __post_init__(self) -> None:
        ports = (self.discovery, self.architecture, self.snapshot)
        mismatched = [
            getattr(port, "provider_id", None)
            for port in ports
            if port is not None and getattr(port, "provider_id", None) != self.provider_id
        ]
        if mismatched:
            raise ValueError(
                f"HardwareProviderBundle '{self.provider_id}' recebeu ports de providers diferentes: {mismatched}"
            )
