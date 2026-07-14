"""Hardware provider port protocols."""

from __future__ import annotations

from typing import Protocol

from quantum_cq._hardware.models import (
    ExecutionTargetDescriptor,
    TargetArchitecture,
    TargetStateSnapshot,
)


class HardwareProviderPort(Protocol):
    provider_id: str


class TargetDiscoveryPort(HardwareProviderPort, Protocol):
    def list_targets(self) -> tuple[ExecutionTargetDescriptor, ...]: ...


class TargetArchitecturePort(HardwareProviderPort, Protocol):
    def architecture(self, descriptor: ExecutionTargetDescriptor) -> TargetArchitecture: ...


class TargetSnapshotPort(HardwareProviderPort, Protocol):
    def snapshot(self, descriptor: ExecutionTargetDescriptor) -> TargetStateSnapshot | None: ...
