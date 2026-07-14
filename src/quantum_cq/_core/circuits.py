"""Circuit analysis service and SDK-free descriptors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from quantum_cq._circuits.compact import CircuitIR, CompactAdapter, LogicalCircuitBuilder, Operation, QC


@dataclass(frozen=True)
class CircuitOperationDescriptor:
    kind: str
    qubits: tuple[int, ...] = ()
    clbits: tuple[int, ...] = ()
    arity: int = 0
    controls: tuple[int, ...] = ()
    label: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "qubits", tuple(self.qubits))
        object.__setattr__(self, "clbits", tuple(self.clbits))
        object.__setattr__(self, "controls", tuple(self.controls))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class CircuitDescriptor:
    name: str
    circuit_format: str
    n_qubits: int
    n_clbits: int
    operations: tuple[str, ...] = ()
    operation_descriptors: tuple[CircuitOperationDescriptor, ...] = ()
    measurements: tuple[tuple[int, int], ...] = ()
    parameters: tuple[str, ...] = ()
    custom_unitaries: tuple[str, ...] = ()
    subcircuits: tuple[str, ...] = ()
    logical_depth: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    origin: str = ""
    wrapper_type: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "operation_descriptors", tuple(self.operation_descriptors))
        object.__setattr__(self, "measurements", tuple(self.measurements))
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "custom_unitaries", tuple(self.custom_unitaries))
        object.__setattr__(self, "subcircuits", tuple(self.subcircuits))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class CircuitRequirements:
    min_qubits: int
    clbits: int = 0
    operations: tuple[str, ...] = ()
    max_arity: int = 0
    max_controls: int = 0
    measurement_total: bool = False
    measurement_partial: bool = False
    measurement_mapped: bool = False
    measurement_intermediate: bool = False
    reset: bool = False
    classical_conditioning: bool = False
    symbolic_parameters: bool = False
    arbitrary_unitary: bool = False
    statevector: bool = False
    observables: bool = False
    local_execution: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def features(self) -> tuple[str, ...]:
        features = set(self.operations)
        if self.measurement_total or self.measurement_partial or self.measurement_mapped:
            features.add("measure")
        if self.measurement_partial:
            features.add("partial_measurement")
        if self.measurement_mapped:
            features.add("mapped_measurement")
        if self.measurement_intermediate:
            features.add("intermediate_measurement")
        if self.reset:
            features.add("reset")
        if self.classical_conditioning:
            features.add("classical_conditioning")
        if self.symbolic_parameters:
            features.add("parameterized")
        if self.arbitrary_unitary:
            features.add("unitary")
        if self.statevector:
            features.add("statevector")
        if self.observables:
            features.add("observables")
        if self.local_execution:
            features.add("local_execution")
        return tuple(sorted(features))


class CircuitService:
    """Read-only normalization and analysis for supported public circuit-like objects."""

    def normalize(self, circuit_like: Any, *, engine: str | None = None) -> Any:
        if self._is_qiskit_native(circuit_like):
            if engine not in {None, "qiskit"}:
                raise TypeError("QuantumCircuit nativo so pode ser usado no fluxo Qiskit")
            return circuit_like
        return self.to_ir(circuit_like)

    def to_ir(self, circuit_like: Any) -> CircuitIR:
        if isinstance(circuit_like, LogicalCircuitBuilder):
            return circuit_like.build()
        if isinstance(circuit_like, CircuitIR):
            return circuit_like
        if isinstance(circuit_like, QC):
            return CompactAdapter().parse(circuit_like)
        circuit_format = getattr(circuit_like, "circuit_format", None)
        if circuit_format == "ir" and hasattr(circuit_like, "circuit"):
            return self.to_ir(circuit_like.circuit)
        metadata = getattr(circuit_like, "metadata", {}) or {}
        if metadata.get("circuit_format") == "ir" and hasattr(circuit_like, "circuit"):
            return self.to_ir(circuit_like.circuit)
        if hasattr(circuit_like, "to_ir"):
            return self.to_ir(circuit_like.to_ir())
        raise TypeError(f"Circuit-like nao suportado para IR logica: {type(circuit_like).__name__}")

    def descriptor(self, circuit_like: Any, *, engine: str | None = None) -> CircuitDescriptor:
        if self._is_qiskit_native(circuit_like):
            if engine not in {None, "qiskit"}:
                raise TypeError("QuantumCircuit nativo so pode ser descrito para engine Qiskit")
            return self._qiskit_descriptor(circuit_like)
        return self._ir_descriptor(self.to_ir(circuit_like), wrapper_type=type(circuit_like).__name__)

    def requirements(self, circuit_like: Any, *, engine: str | None = None) -> CircuitRequirements:
        descriptor = self.descriptor(circuit_like, engine=engine)
        measurements = descriptor.measurements
        measured_qubits = {qubit for qubit, _ in measurements}
        mapped = any(qubit != clbit for qubit, clbit in measurements)
        operations = tuple(operation for operation in descriptor.operations if operation != "barrier")
        return CircuitRequirements(
            min_qubits=descriptor.n_qubits,
            clbits=descriptor.n_clbits,
            operations=operations,
            max_arity=max((operation.arity for operation in descriptor.operation_descriptors), default=0),
            max_controls=max((len(operation.controls) for operation in descriptor.operation_descriptors), default=0),
            measurement_total=bool(measurements) and len(measured_qubits) == descriptor.n_qubits,
            measurement_partial=bool(measurements) and len(measured_qubits) < descriptor.n_qubits,
            measurement_mapped=mapped,
            measurement_intermediate=_has_intermediate_measurement(descriptor.operation_descriptors),
            reset="reset" in operations,
            arbitrary_unitary="unitary" in operations,
            metadata={"source_format": descriptor.circuit_format},
        )

    def validate(self, circuit_like: Any, *, engine: str | None = None) -> CircuitDescriptor:
        descriptor = self.descriptor(circuit_like, engine=engine)
        if descriptor.n_qubits < 0 or descriptor.n_clbits < 0:
            raise ValueError("Circuit descriptor has invalid register sizes")
        return descriptor

    def _ir_descriptor(self, ir: CircuitIR, *, wrapper_type: str = "CircuitIR") -> CircuitDescriptor:
        operations = [_operation_descriptor(operation) for operation in _iter_operations(ir)]
        measurements = tuple(
            (operation.qubits[0], operation.clbits[0])
            for operation in _iter_operations(ir)
            if operation.kind == "measure"
        )
        return CircuitDescriptor(
            name=ir.name,
            circuit_format="ir",
            n_qubits=ir.n_qubits,
            n_clbits=ir.n_clbits,
            operations=tuple(operation.kind for operation in operations),
            operation_descriptors=tuple(operations),
            measurements=measurements,
            parameters=tuple(
                key
                for operation in _iter_operations(ir)
                for key in operation.params
                if key not in {"matrix", "unitary", "metadata"}
            ),
            custom_unitaries=tuple(
                str(operation.params.get("name") or operation.label or "unitary")
                for operation in _iter_operations(ir)
                if operation.kind == "unitary"
            ),
            subcircuits=tuple(ir.metadata.get("subcircuits", ())),
            logical_depth=len(ir.layers),
            metadata=ir.metadata,
            origin="logical",
            wrapper_type=wrapper_type,
        )

    def _qiskit_descriptor(self, circuit: Any) -> CircuitDescriptor:
        operation_descriptors: list[CircuitOperationDescriptor] = []
        measurements: list[tuple[int, int]] = []
        parameters: list[str] = []
        custom_unitaries: list[str] = []
        for item in getattr(circuit, "data", ()):
            operation = getattr(item, "operation", None)
            qubits = getattr(item, "qubits", None)
            clbits = getattr(item, "clbits", None)
            if operation is None and isinstance(item, tuple) and len(item) >= 3:
                operation, qubits, clbits = item[0], item[1], item[2]
            if operation is None:
                continue
            kind = str(getattr(operation, "name", type(operation).__name__))
            q_indices = tuple(int(circuit.find_bit(qubit).index) for qubit in (qubits or ()))
            c_indices = tuple(int(circuit.find_bit(clbit).index) for clbit in (clbits or ()))
            controls = _qiskit_controls(kind, q_indices, operation)
            operation_descriptors.append(
                CircuitOperationDescriptor(
                    kind=kind,
                    qubits=q_indices,
                    clbits=c_indices,
                    arity=len(q_indices),
                    controls=controls,
                    label=getattr(operation, "label", None),
                    metadata={
                        "params": tuple(str(param) for param in getattr(operation, "params", ())),
                    },
                )
            )
            parameters.extend(str(param) for param in getattr(operation, "params", ()))
            if kind == "measure" and q_indices and c_indices:
                measurements.append((q_indices[0], c_indices[0]))
            if kind == "unitary":
                custom_unitaries.append(str(getattr(operation, "label", None) or "unitary"))
        return CircuitDescriptor(
            name=getattr(circuit, "name", "qiskit_circuit"),
            circuit_format="qiskit",
            n_qubits=int(circuit.num_qubits),
            n_clbits=int(circuit.num_clbits),
            operations=tuple(operation.kind for operation in operation_descriptors),
            operation_descriptors=tuple(operation_descriptors),
            measurements=tuple(measurements),
            parameters=tuple(parameters),
            custom_unitaries=tuple(custom_unitaries),
            logical_depth=int(circuit.depth() or 0),
            metadata={"native": "qiskit"},
            origin="qiskit",
            wrapper_type=type(circuit).__name__,
        )

    def _is_qiskit_native(self, value: Any) -> bool:
        value_type = type(value)
        return value_type.__name__ == "QuantumCircuit" and value_type.__module__.startswith("qiskit")


def _operation_descriptor(operation: Operation) -> CircuitOperationDescriptor:
    controls: tuple[int, ...] = ()
    if "controls" in operation.params:
        controls = tuple(operation.params["controls"])
    elif "control" in operation.params:
        controls = (int(operation.params["control"]),)
    return CircuitOperationDescriptor(
        kind=operation.kind,
        qubits=operation.qubits,
        clbits=operation.clbits,
        arity=len(operation.qubits),
        controls=controls,
        label=operation.label,
        metadata={"params": tuple(sorted(str(key) for key in operation.params))},
    )


def _iter_operations(ir: CircuitIR):
    for layer in ir.layers:
        yield from layer.operations
    yield from ir.outputs


def _has_intermediate_measurement(operations: tuple[CircuitOperationDescriptor, ...]) -> bool:
    for index, operation in enumerate(operations):
        if operation.kind != "measure":
            continue
        later = operations[index + 1 :]
        if any(item.kind not in {"measure", "barrier", "separator"} for item in later):
            return True
    return False


def _qiskit_controls(kind: str, qubits: tuple[int, ...], operation: Any) -> tuple[int, ...]:
    if kind in {"cx", "cz", "cp"} and len(qubits) >= 2:
        return (qubits[0],)
    if kind == "ccx" and len(qubits) >= 3:
        return qubits[:2]
    count = int(getattr(operation, "num_ctrl_qubits", 0) or 0)
    if count:
        return qubits[:count]
    return ()
