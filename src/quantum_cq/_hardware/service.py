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
    TopologyEdge,
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
        operations: tuple[Any, ...] | list[Any],
        target_type: TargetType | str,
        name: str | None = None,
        provider: str = "manual",
        aliases: tuple[str, ...] = (),
        topology: tuple[Any, ...] = (),
        snapshot: TargetStateSnapshot | None = None,
        provenance: TargetProvenance | None = None,
        paradigm: str = "gate_model",
    ) -> ExecutionTarget:
        provenance_source = "manual"
        normalized_target_type = str(target_type)
        warnings = ["manual target data is user-declared and not provider-verified"]
        if normalized_target_type == "manual":
            normalized_target_type = "hypothetical"
            warnings.append("target_type='manual' was treated as provenance, not computational nature")
        if normalized_target_type not in {"physical", "simulator_ideal", "simulator_noisy", "hypothetical", "unknown"}:
            raise ValueError(f"target_type invalido: {target_type}")
        qubit_ids = tuple(f"q{index}" for index in range(qubits)) if isinstance(qubits, int) else tuple(qubits)
        if isinstance(qubits, int) and qubits < 0:
            raise ValueError("quantidade de qubits nao pode ser negativa")
        descriptor = ExecutionTargetDescriptor(
            target_id=target_id,
            provider=provider,
            name=name or target_id,
            target_type=normalized_target_type,
            aliases=aliases,
            paradigm=paradigm,
        )
        instructions = tuple(_normalize_instruction(operation) for operation in operations)
        topology_edges = tuple(_normalize_edge(edge) for edge in topology)
        architecture = TargetArchitecture(
            architecture_id=f"{provider}:{target_id}:architecture",
            qubits=qubit_ids,
            instructions=instructions,
            topology=topology_edges,
            connectivity="unknown" if not topology_edges else "known",
            measurement="known" if any(item.name == "measure" for item in instructions) else "unknown",
            paradigm=paradigm,
        )
        provenance = provenance or TargetProvenance(
            provider=provider,
            adapter="manual",
            original_id=target_id,
            collected_at=datetime.now(timezone.utc),
            completeness="user_declared",
            source=provenance_source,
            warnings=tuple(warnings),
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

    def compatibility_hints(
        self,
        target: ExecutionTarget | None,
        *,
        required_qubits: int = 0,
        required_operations: tuple[str, ...] = (),
        max_arity: int = 0,
        requires_measurement: bool = False,
        requires_reset: bool = False,
        requires_classical_control: bool = False,
        paradigm: str = "gate_model",
    ) -> dict[str, Any]:
        if target is None:
            return {"unknowns": ("target_not_provided",)}
        unknowns: list[str] = []
        missing: list[str] = []
        if target.architecture.connectivity == "unknown":
            unknowns.append("connectivity")
        if target.snapshot is None:
            unknowns.append("snapshot")
        elif target.snapshot.stale:
            unknowns.append("snapshot_stale")
        insufficient_qubits = target.architecture.num_qubits < required_qubits
        if target.architecture.paradigm != paradigm:
            missing.append("target_paradigm")
        instructions = {instruction.name: instruction for instruction in target.architecture.instructions}
        missing_operations = tuple(
            operation
            for operation in sorted(set(required_operations))
            if operation not in {"barrier"} and operation not in instructions
        )
        missing.extend(f"operation:{operation}" for operation in missing_operations)
        arity_mismatches = tuple(
            operation
            for operation in sorted(set(required_operations))
            if operation in instructions and instructions[operation].arity < _operation_arity(operation)
        )
        if max_arity and max((instruction.arity for instruction in instructions.values()), default=0) < max_arity:
            missing.append("target_arity")
        if requires_measurement and target.architecture.measurement != "known":
            if target.architecture.measurement in {"unsupported", "unavailable"}:
                missing.append("measure")
            else:
                unknowns.append("measurement")
        if requires_reset and target.architecture.reset != "known":
            if target.architecture.reset in {"unsupported", "unavailable"}:
                missing.append("reset")
            else:
                unknowns.append("reset")
        if requires_classical_control and target.architecture.classical_control != "known":
            if target.architecture.classical_control in {"unsupported", "unavailable"}:
                missing.append("classical_control")
            else:
                unknowns.append("classical_control")
        has_multiqubit = max_arity > 1
        placement_status = "not_required" if not has_multiqubit else "may_be_required"
        routing_status = "not_required" if not has_multiqubit else "may_be_required"
        if has_multiqubit and target.architecture.connectivity == "unknown":
            routing_status = "not_analyzed"
        scheduling_status = "not_analyzed" if target.architecture.timing != "known" else "may_be_required"
        return {
            "target_id": target.descriptor.target_id,
            "target_type": target.descriptor.target_type,
            "architecture_fingerprint": target.architecture.fingerprint,
            "snapshot_id": None if target.snapshot is None else target.snapshot.snapshot_id,
            "unknowns": tuple(unknowns),
            "missing": tuple(missing),
            "missing_operations": missing_operations,
            "arity_mismatches": arity_mismatches,
            "insufficient_qubits": insufficient_qubits,
            "placement_status": placement_status,
            "routing_status": routing_status,
            "scheduling_status": scheduling_status,
            "placement_required": placement_status == "required",
            "routing_required": routing_status == "required",
            "scheduling_required": scheduling_status == "required",
        }


def default_hardware_service() -> HardwareService:
    return HardwareService()


def _operation_arity(operation: str) -> int:
    if operation in {"cx", "cz", "swap"}:
        return 2
    if operation in {"ccx"}:
        return 3
    return 1


def _normalize_instruction(operation: Any) -> NativeInstruction:
    if isinstance(operation, NativeInstruction):
        return operation
    if isinstance(operation, str):
        return NativeInstruction(name=operation, arity=_operation_arity(operation))
    if isinstance(operation, dict):
        return NativeInstruction(**operation)
    raise TypeError(f"instrucao de target invalida: {operation!r}")


def _normalize_edge(edge: Any) -> TopologyEdge:
    if isinstance(edge, TopologyEdge):
        return edge
    if isinstance(edge, dict):
        return TopologyEdge(**edge)
    if isinstance(edge, (tuple, list)) and len(edge) in {2, 3}:
        source, target = edge[0], edge[1]
        directed = bool(edge[2]) if len(edge) == 3 else False
        return TopologyEdge(str(source), str(target), directed=directed)
    raise TypeError(f"topologia de target invalida: {edge!r}")
