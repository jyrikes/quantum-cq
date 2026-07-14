"""Qiskit target anti-corruption adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from typing import Any

from quantum_cq._hardware.models import (
    ExecutionTarget,
    ExecutionTargetDescriptor,
    NativeInstruction,
    TargetDatum,
    TargetArchitecture,
    TargetProvenance,
    TargetStateSnapshot,
    TopologyEdge,
)


def target_from_qiskit(value: Any, *, name: str | None = None) -> ExecutionTarget:
    target = getattr(value, "target", value)
    if not _is_supported_qiskit_target_like(value, target):
        raise TypeError(f"Objeto Qiskit nao suportado para target extraction: {type(value).__name__}")
    target_name = name or getattr(value, "name", None) or getattr(target, "name", None) or "qiskit_target"
    target_id = f"qiskit:{target_name}"
    num_qubits = _num_qubits(value, target)
    qubits = _physical_qubits(target, num_qubits)
    operations, topology, snapshot, warnings, transformed, omitted = _architecture_from_target(
        target,
        target_id=target_id,
        qubits=qubits,
    )
    descriptor = ExecutionTargetDescriptor(
        target_id=target_id,
        provider="qiskit",
        name=str(target_name),
        target_type=_target_type(value, target, warnings),
        provider_ids={"qiskit": str(target_name)},
        paradigm="gate_model",
    )
    architecture = TargetArchitecture(
        architecture_id=f"{target_id}:architecture",
        qubits=qubits,
        instructions=operations,
        topology=topology,
        connectivity="known" if topology else "unknown",
        measurement="known" if any(item.name == "measure" for item in operations) else "unknown",
        reset="known" if any(item.name == "reset" for item in operations) else "unknown",
        timing="known" if snapshot is not None and snapshot.instruction_properties else "unknown",
        paradigm="gate_model",
    )
    provenance = TargetProvenance(
        provider="qiskit",
        adapter="qiskit_target_from_object",
        engine="qiskit",
        sdk_version=_qiskit_version(),
        original_id=str(target_name),
        collected_at=datetime.now(timezone.utc),
        completeness="partial",
        transformed_fields=tuple(transformed),
        omitted_fields=tuple(omitted),
        warnings=tuple(warnings),
        source="explicit_object",
    )
    return ExecutionTarget(
        descriptor=descriptor,
        architecture=architecture,
        snapshot=snapshot,
        provenance=provenance,
        snapshots=() if snapshot is None else (snapshot,),
    )


def _is_supported_qiskit_target_like(value: Any, target: Any) -> bool:
    value_type = type(value).__name__
    target_type = type(target).__name__
    value_module = type(value).__module__.split(".")[0]
    target_module = type(target).__module__.split(".")[0]
    if value_type == "QuantumCircuit" and value_module == "qiskit":
        return True
    if target_type in {"Target", "CouplingMap"} and target_module == "qiskit":
        return True
    if target is not value and target_type == "Target" and target_module == "qiskit":
        return True
    if (
        target is not value
        and callable(getattr(value, "configuration", None))
        and (
            hasattr(target, "operation_names")
            or hasattr(target, "instructions")
        )
    ):
        return True
    return False


def _num_qubits(value: Any, target: Any) -> int:
    for candidate in (
        getattr(target, "num_qubits", None),
        getattr(value, "num_qubits", None),
    ):
        if candidate is not None:
            return int(candidate)
    try:
        return len(getattr(target, "qubit_properties"))
    except Exception:
        return 0


def _physical_qubits(target: Any, num_qubits: int) -> tuple[str, ...]:
    physical = getattr(target, "physical_qubits", None)
    if physical is not None:
        try:
            return tuple(f"q{int(index)}" for index in physical)
        except Exception:
            return tuple(str(item) for item in physical)
    return tuple(f"q{index}" for index in range(num_qubits))


def _architecture_from_target(
    target: Any,
    *,
    target_id: str,
    qubits: tuple[str, ...],
) -> tuple[
    tuple[NativeInstruction, ...],
    tuple[TopologyEdge, ...],
    TargetStateSnapshot | None,
    list[str],
    list[str],
    list[str],
]:
    if type(target).__name__ == "CouplingMap":
        return _architecture_from_coupling_map(target, target_id=target_id, qubits=qubits)
    operations, warnings, transformed, omitted = _operations(target)
    topology, instruction_properties, connection_properties = _topology_and_properties(target, qubits=qubits)
    snapshot = None
    if instruction_properties or connection_properties:
        snapshot = TargetStateSnapshot(
            snapshot_id=f"{target_id}:snapshot:{datetime.now(timezone.utc).isoformat()}",
            target_id=target_id,
            collected_at=datetime.now(timezone.utc),
            instruction_properties=instruction_properties,
            connection_properties=connection_properties,
            calibration_available="known",
        )
        transformed.append("calibration_properties")
    return operations, topology, snapshot, warnings, transformed, omitted


def _architecture_from_coupling_map(
    target: Any,
    *,
    target_id: str,
    qubits: tuple[str, ...],
) -> tuple[
    tuple[NativeInstruction, ...],
    tuple[TopologyEdge, ...],
    TargetStateSnapshot | None,
    list[str],
    list[str],
    list[str],
]:
    warnings = ["CouplingMap fornece conectividade sem operacoes nativas comprovadas"]
    edges = []
    try:
        raw_edges = target.get_edges()
    except Exception:
        raw_edges = ()
        warnings.append("CouplingMap nao expos get_edges")
    for left, right in raw_edges:
        edges.append(TopologyEdge(f"q{int(left)}", f"q{int(right)}", directed=True, operations=()))
    return (), tuple(edges), None, warnings, ["coupling_map"], ["operation_properties"]


def _operations(target: Any) -> tuple[tuple[NativeInstruction, ...], list[str], list[str], list[str]]:
    warnings: list[str] = []
    transformed: list[str] = []
    omitted: list[str] = []
    if type(target).__name__ == "Target":
        instructions: list[NativeInstruction] = []
        for name in tuple(getattr(target, "operation_names", ()) or ()):
            try:
                operation = target.operation_from_name(name)
            except Exception:
                operation = None
                warnings.append(f"instrucao '{name}' nao pode ser inspecionada")
            qargs = _qargs_for_operation(target, str(name))
            arity = int(getattr(operation, "num_qubits", 0) or _arity(str(name)))
            parameters = tuple(str(param) for param in getattr(operation, "params", ()) or ())
            valid_qubits = tuple(f"q{qargs_item[0]}" for qargs_item in qargs if len(qargs_item) == 1)
            valid_connections = tuple(tuple(f"q{index}" for index in qargs_item) for qargs_item in qargs if len(qargs_item) == arity)
            instructions.append(
                NativeInstruction(
                    name=str(name),
                    native_name=str(name),
                    arity=max(1, arity),
                    parameters=parameters,
                    valid_qubits=valid_qubits,
                    valid_connections=valid_connections,
                    directional=arity >= 2,
                )
            )
        transformed.append("target.operation_names")
        transformed.append("target.qargs")
        return tuple(instructions), warnings, transformed, omitted
    names = getattr(target, "operation_names", None)
    if callable(names):
        names = names()
    if names is None:
        names = getattr(target, "instructions", None)
        if callable(names):
            names = names()
    if names is None and hasattr(target, "count_ops"):
        names = tuple(dict(target.count_ops()).keys())
    if names is None:
        warnings.append("qiskit target did not expose operation names")
        omitted.append("operation_names")
        return (), warnings, transformed, omitted
    operations = []
    for name in names:
        candidate = name
        if isinstance(name, tuple) and name:
            candidate = name[0]
        op_name = str(getattr(candidate, "name", candidate))
        operations.append(NativeInstruction(name=op_name, native_name=op_name, arity=_arity(op_name)))
    transformed.append("operation_names")
    return tuple(operations), warnings, transformed, omitted


def _topology_and_properties(
    target: Any,
    *,
    qubits: tuple[str, ...],
) -> tuple[
    tuple[TopologyEdge, ...],
    dict[str, dict[str, TargetDatum]],
    dict[str, dict[str, TargetDatum]],
]:
    if type(target).__name__ != "Target":
        return (), {}, {}
    topology: list[TopologyEdge] = []
    instruction_properties: dict[str, dict[str, TargetDatum]] = {}
    connection_properties: dict[str, dict[str, TargetDatum]] = {}
    for name in tuple(getattr(target, "operation_names", ()) or ()):
        operation = target.operation_from_name(name)
        arity = int(getattr(operation, "num_qubits", 0) or _arity(str(name)))
        qargs = _qargs_for_operation(target, str(name))
        for qargs_item in qargs:
            properties = _instruction_properties(target, str(name), qargs_item)
            prop_payload = _properties_to_datums(properties)
            prop_key = f"{name}:{','.join(f'q{index}' for index in qargs_item)}"
            if prop_payload:
                instruction_properties[prop_key] = prop_payload
            if arity == 2 and len(qargs_item) == 2:
                left, right = f"q{qargs_item[0]}", f"q{qargs_item[1]}"
                if left in qubits and right in qubits:
                    topology.append(TopologyEdge(left, right, directed=True, operations=(str(name),)))
                    if prop_payload:
                        connection_properties[f"{left}->{right}:{name}"] = prop_payload
    return tuple(topology), instruction_properties, connection_properties


def _qargs_for_operation(target: Any, name: str) -> tuple[tuple[int, ...], ...]:
    try:
        qargs = target.qargs_for_operation_name(name)
    except Exception:
        qargs = getattr(target, name, None)
    if qargs is None:
        return ()
    return tuple(tuple(int(index) for index in item) for item in qargs)


def _instruction_properties(target: Any, name: str, qargs: tuple[int, ...]) -> Any:
    try:
        properties = target[name]
        if isinstance(properties, dict):
            return properties.get(qargs)
        return properties[qargs]
    except Exception:
        return None


def _properties_to_datums(properties: Any) -> dict[str, TargetDatum]:
    if properties is None:
        return {}
    payload: dict[str, TargetDatum] = {}
    duration = getattr(properties, "duration", None)
    error = getattr(properties, "error", None)
    if duration is not None:
        payload["duration"] = TargetDatum("known", value=float(duration), unit="s")
    if error is not None:
        payload["error"] = TargetDatum("known", value=float(error), unit="probability")
    return payload


def _target_type(value: Any, target: Any, warnings: list[str]) -> str:
    if type(value).__name__ == "QuantumCircuit":
        warnings.append("qiskit QuantumCircuit describes a circuit, not an executable target")
        return "unknown"
    simulator = _simulator_flag(value)
    if simulator is None and target is not value:
        simulator = _simulator_flag(target)
    if simulator is True:
        return "simulator_ideal"
    if simulator is False:
        return "physical"
    if type(target).__name__ == "Target":
        warnings.append("qiskit Target is structural; executor binding is not implied")
        return "unknown"
    warnings.append("qiskit target nature could not be determined")
    return "unknown"


def _simulator_flag(value: Any) -> bool | None:
    for attr in ("simulator", "is_simulator"):
        candidate = getattr(value, attr, None)
        if isinstance(candidate, bool):
            return candidate
        if callable(candidate):
            try:
                result = candidate()
            except Exception:
                result = None
            if isinstance(result, bool):
                return result
    configuration = getattr(value, "configuration", None)
    if callable(configuration):
        try:
            config = configuration()
        except Exception:
            return None
        candidate = getattr(config, "simulator", None)
        if isinstance(candidate, bool):
            return candidate
    return None


def _arity(name: str) -> int:
    if name in {"cx", "cz", "ecr", "swap"}:
        return 2
    if name in {"ccx"}:
        return 3
    return 1


def _qiskit_version() -> str | None:
    try:
        return metadata.version("qiskit")
    except metadata.PackageNotFoundError:
        return None
