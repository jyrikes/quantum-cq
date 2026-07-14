"""Qiskit target anti-corruption adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from typing import Any

from quantum_cq._hardware.models import (
    ExecutionTarget,
    ExecutionTargetDescriptor,
    NativeInstruction,
    TargetArchitecture,
    TargetProvenance,
)


def target_from_qiskit(value: Any, *, name: str | None = None) -> ExecutionTarget:
    target = getattr(value, "target", value)
    target_name = name or getattr(value, "name", None) or getattr(target, "name", None) or "qiskit_target"
    target_id = f"qiskit:{target_name}"
    num_qubits = _num_qubits(value, target)
    operations, warnings = _operations(target)
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
        qubits=tuple(f"q{index}" for index in range(num_qubits)),
        instructions=operations,
        connectivity="unknown",
        measurement="known" if any(item.name == "measure" for item in operations) else "unknown",
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
        warnings=tuple(warnings),
        source="explicit_object",
    )
    return ExecutionTarget(
        descriptor=descriptor,
        architecture=architecture,
        snapshot=None,
        provenance=provenance,
    )


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


def _operations(target: Any) -> tuple[tuple[NativeInstruction, ...], list[str]]:
    warnings: list[str] = []
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
        return (), warnings
    operations = []
    for name in names:
        candidate = name
        if isinstance(name, tuple) and name:
            candidate = name[0]
        op_name = str(getattr(candidate, "name", candidate))
        operations.append(NativeInstruction(name=op_name, native_name=op_name, arity=_arity(op_name)))
    return tuple(operations), warnings


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
