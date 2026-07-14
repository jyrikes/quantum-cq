"""Hardware service over neutral target provider ports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quantum_cq._hardware.bundle import HardwareProviderBundle
from quantum_cq._hardware.models import (
    ExecutionContext,
    ExecutionTarget,
    ExecutionTargetDescriptor,
    NativeInstruction,
    TargetArchitecture,
    TargetProvenance,
    TargetStateSnapshot,
    TargetType,
)
from quantum_cq._hardware.serialization import execution_target_from_dict, to_serializable


class HardwareService:
    def __init__(self, bundles: tuple[HardwareProviderBundle, ...] = ()) -> None:
        self._bundles = {bundle.provider_id: bundle for bundle in bundles}

    def list_targets(self) -> tuple[ExecutionTargetDescriptor, ...]:
        descriptors: list[ExecutionTargetDescriptor] = []
        for bundle in self._bundles.values():
            descriptors.extend(bundle.discovery.list_targets())
        return tuple(descriptors)

    def resolve(self, target: Any) -> ExecutionTarget | None:
        if target is None:
            return None
        if isinstance(target, ExecutionTarget):
            return target
        if isinstance(target, ExecutionTargetDescriptor):
            bundle = self._bundles.get(target.provider)
            if bundle is None:
                raise ValueError(f"Provider de hardware indisponivel: {target.provider}")
            architecture = bundle.architecture.architecture(target)
            snapshot = bundle.snapshot.snapshot(target) if bundle.snapshot is not None else None
            return ExecutionTarget(descriptor=target, architecture=architecture, snapshot=snapshot)
        if isinstance(target, dict):
            return execution_target_from_dict(target)
        raise TypeError(f"Target nao suportado: {type(target).__name__}")

    def execution_context(
        self,
        *,
        engine: str,
        target: Any = None,
        measurement_policy: str = "preserve",
        shots: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        resolved = self.resolve(target)
        return ExecutionContext(
            engine=engine,
            target=resolved,
            measurement_policy=measurement_policy,
            shots=shots,
            options=options or {},
        )

    def manual_target(
        self,
        *,
        target_id: str,
        qubits: int | tuple[str, ...],
        operations: tuple[str, ...] | list[str],
        target_type: TargetType,
        name: str | None = None,
        provider: str = "manual",
        aliases: tuple[str, ...] = (),
        topology: tuple[Any, ...] = (),
        snapshot: TargetStateSnapshot | None = None,
        provenance: TargetProvenance | None = None,
        paradigm: str = "gate_model",
    ) -> ExecutionTarget:
        if target_type not in {"physical", "simulator_ideal", "simulator_noisy", "manual", "hypothetical"}:
            raise ValueError(f"target_type invalido: {target_type}")
        qubit_ids = tuple(f"q{index}" for index in range(qubits)) if isinstance(qubits, int) else tuple(qubits)
        descriptor = ExecutionTargetDescriptor(
            target_id=target_id,
            provider=provider,
            name=name or target_id,
            target_type=target_type,
            aliases=aliases,
            paradigm=paradigm,
        )
        instructions = tuple(
            NativeInstruction(name=operation, arity=_operation_arity(operation))
            for operation in operations
        )
        architecture = TargetArchitecture(
            architecture_id=f"{provider}:{target_id}:architecture",
            qubits=qubit_ids,
            instructions=instructions,
            topology=tuple(topology),
            connectivity="unknown" if not topology else "known",
            measurement="known" if "measure" in operations else "unknown",
            paradigm=paradigm,
        )
        provenance = provenance or TargetProvenance(
            provider=provider,
            adapter="manual",
            original_id=target_id,
            collected_at=datetime.now(timezone.utc),
            completeness="user_declared",
            source="manual",
            warnings=("manual target data is user-declared and not provider-verified",),
        )
        return ExecutionTarget(
            descriptor=descriptor,
            architecture=architecture,
            snapshot=snapshot,
            provenance=provenance,
            snapshots=() if snapshot is None else (snapshot,),
        )

    def serialize(self, target: ExecutionTarget) -> dict[str, Any]:
        return to_serializable(target)

    def deserialize(self, data: dict[str, Any]) -> ExecutionTarget:
        return execution_target_from_dict(data)

    def compatibility_hints(self, target: ExecutionTarget | None, *, required_qubits: int = 0) -> dict[str, Any]:
        if target is None:
            return {"unknowns": ("target_not_provided",)}
        unknowns: list[str] = []
        if target.architecture.connectivity == "unknown":
            unknowns.append("connectivity")
        if target.snapshot is None:
            unknowns.append("snapshot")
        insufficient_qubits = target.architecture.num_qubits < required_qubits
        return {
            "target_id": target.descriptor.target_id,
            "target_type": target.descriptor.target_type,
            "architecture_fingerprint": target.architecture.fingerprint,
            "snapshot_id": None if target.snapshot is None else target.snapshot.snapshot_id,
            "unknowns": tuple(unknowns),
            "insufficient_qubits": insufficient_qubits,
            "placement_required": target.architecture.connectivity == "known",
            "routing_required": target.architecture.connectivity == "known",
            "scheduling_required": target.architecture.timing == "known",
        }


def default_hardware_service() -> HardwareService:
    return HardwareService()


def _operation_arity(operation: str) -> int:
    if operation in {"cx", "cz", "swap"}:
        return 2
    if operation in {"ccx"}:
        return 3
    return 1
