"""Cirq engine ports."""

from __future__ import annotations

import importlib.util
from importlib import metadata
from typing import Any

from quantum_cq._circuits.compact import CircuitIR
from quantum_cq._engines.availability import EngineAvailability
from quantum_cq._engines.bundle import EngineBundle
from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import EngineNotInstalledError, ExecutionError, ResultDecodingError
from quantum_cq._engines.logical import iter_operations
from quantum_cq._engines.lowering import lower_for_capabilities
from quantum_cq._engines.measurement import (
    MeasurementContract,
    canonical_counts_from_rows,
    measurement_contract_from_ir,
)
from quantum_cq._engines.results import CompiledArtifact, EngineResult, NativeExecutionResult


ENGINE_ID = "cirq"


class CirqAvailabilityPort:
    engine_id = ENGINE_ID

    def availability(self) -> EngineAvailability:
        installed = importlib.util.find_spec("cirq") is not None
        if not installed:
            return EngineAvailability(
                engine=self.engine_id,
                installed=False,
                compatible=False,
                reason="Cirq is not installed; install quantum-cq[cirq].",
            )
        try:
            version = metadata.version("cirq")
        except metadata.PackageNotFoundError:
            version = None
        return EngineAvailability(
            engine=self.engine_id,
            installed=True,
            compatible=True,
            version=version,
        )

    def is_installed(self) -> bool:
        return self.availability().installed


class CirqCapabilitiesPort:
    engine_id = ENGINE_ID

    def __init__(self, availability: CirqAvailabilityPort | None = None) -> None:
        self._availability = availability or CirqAvailabilityPort()

    def capabilities(self) -> EngineCapabilities:
        availability = self._availability.availability()
        return EngineCapabilities(
            engine=self.engine_id,
            installed=availability.installed,
            statuses={
                "x": "supported",
                "y": "supported",
                "z": "supported",
                "h": "supported",
                "p": "supported",
                "rx": "supported",
                "ry": "supported",
                "rz": "supported",
                "cx": "supported",
                "cz": "supported",
                "cp": "not_tested",
                "swap": "supported",
                "measure": "supported",
                "partial_measurement": "supported",
                "mapped_measurement": "supported",
                "auto_measure_all": "supported",
                "intermediate_measurement": "not_tested",
                "parameterized": "supported",
                "mcx": "lowered",
                "ccx": "supported",
                "unitary": "not_tested",
                "observables": "not_tested",
                "gradients": "unsupported",
                "statevector": "not_tested",
                "noise": "not_tested",
                "local_execution": "supported",
                "remote_execution": "unsupported",
                "async_jobs": "unsupported",
            },
            metadata={"version": availability.version},
        )


class CirqEmitterPort:
    engine_id = ENGINE_ID

    def emit(
        self,
        circuit_ir: CircuitIR,
        *,
        measurement_contract: MeasurementContract | None = None,
        capabilities: EngineCapabilities | None = None,
        **options: Any,
    ) -> Any:
        _ = options
        cirq = _require_cirq()
        capabilities = capabilities or CirqCapabilitiesPort().capabilities()
        ir = lower_for_capabilities(circuit_ir, capabilities)
        qubits = [cirq.LineQubit(index) for index in range(ir.n_qubits)]
        circuit = cirq.Circuit()
        for operation in iter_operations(ir):
            _append(cirq, circuit, qubits, operation)
        return circuit


class CirqCompilerPort:
    engine_id = ENGINE_ID

    def compile(
        self,
        emitted_circuit: Any,
        *,
        source_ir: CircuitIR | None = None,
        measurement_contract: MeasurementContract | None = None,
        capabilities: EngineCapabilities | None = None,
        availability: EngineAvailability | None = None,
        lowering_rules: tuple[str, ...] = (),
        **options: Any,
    ) -> CompiledArtifact:
        if source_ir is not None and measurement_contract is None:
            measurement_contract = measurement_contract_from_ir(source_ir)
        return CompiledArtifact(
            engine=self.engine_id,
            emitted_circuit=emitted_circuit,
            native_compiled=emitted_circuit,
            device=options.get("device"),
            options=dict(options),
            metadata={"compiled": False},
            measurement_contract=measurement_contract,
            capabilities_considered=dict(capabilities.statuses) if capabilities is not None else {},
            lowering_rules=lowering_rules,
            engine_version=availability.version if availability is not None else None,
        )


class CirqExecutorPort:
    engine_id = ENGINE_ID

    def execute(
        self,
        artifact: CompiledArtifact,
        *,
        shots: int = 1024,
        **options: Any,
    ) -> NativeExecutionResult:
        cirq = _require_cirq()
        _validate_artifact_engine(self.engine_id, artifact)
        try:
            simulator = options.get("simulator") or cirq.Simulator()
            raw = simulator.run(artifact.native_compiled, repetitions=shots)
        except Exception as exc:
            raise ExecutionError("Cirq execution failed") from exc
        return NativeExecutionResult(
            engine=self.engine_id,
            native_result=raw,
            metadata={"shots": shots, "simulator": type(simulator).__name__},
        )


class CirqResultDecoderPort:
    engine_id = ENGINE_ID

    def decode(
        self,
        execution: NativeExecutionResult,
        artifact: CompiledArtifact,
        *,
        shots: int = 1024,
        **options: Any,
    ) -> EngineResult:
        _ = shots, options
        if execution.engine != self.engine_id:
            raise ResultDecodingError(f"Cirq decoder recebeu resultado da engine '{execution.engine}'")
        contract = artifact.measurement_contract
        if contract is None or not contract.effective_mappings:
            raise ResultDecodingError("Cirq result requires a measurement contract")
        rows = _cirq_rows(execution.native_result, contract)
        counts = canonical_counts_from_rows(rows, contract.effective_mappings)
        contract = contract.with_native_order(
            tuple(mapping.clbit for mapping in contract.effective_mappings),
            materialized=True,
            note="Cirq measurements normalized from cN keys to canonical clbit-desc order",
        )
        return EngineResult(
            engine=self.engine_id,
            counts=counts,
            metadata={
                **dict(execution.metadata),
                "measurement": contract.to_metadata(),
                "bit_order": "canonical_clbit_desc",
                "native_bit_order": "cirq_measurement_key_order",
                "normalized": True,
            },
            raw=execution.native_result,
            measurement_contract=contract,
            canonical_bit_order=contract.canonical_bit_order,
            native_bit_order=contract.native_bit_order,
            endianness=contract.endianness,
            normalized=True,
        )


class CirqEngineAdapter:
    engine_id = ENGINE_ID

    def __init__(self) -> None:
        self._bundle = create_bundle()

    def is_installed(self) -> bool:
        return self._bundle.availability.is_installed()

    def capabilities(self) -> EngineCapabilities:
        return self._bundle.capabilities.capabilities()

    def emit(self, circuit_like: Any, **options: Any) -> Any:
        from quantum_cq._engines.logical import to_logical_ir

        ir = to_logical_ir(circuit_like)
        return self._bundle.emitter.emit(
            ir,
            measurement_contract=measurement_contract_from_ir(ir),
            capabilities=self.capabilities(),
            **options,
        )

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        from quantum_cq._engines.logical import to_logical_ir

        ir = to_logical_ir(circuit_like)
        emitted = self.emit(ir, **options)
        return self._bundle.compiler.compile(
            emitted,
            source_ir=ir,
            measurement_contract=measurement_contract_from_ir(ir),
            capabilities=self.capabilities(),
            availability=self._bundle.availability.availability(),
            **options,
        )

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        artifact = circuit_like if isinstance(circuit_like, CompiledArtifact) else self.compile(circuit_like, **options)
        execution = self._bundle.executor.execute(artifact, shots=shots, **options)
        return self._bundle.decoder.decode(execution, artifact, shots=shots, **options)


def create_bundle() -> EngineBundle:
    availability = CirqAvailabilityPort()
    return EngineBundle(
        engine_id=ENGINE_ID,
        availability=availability,
        capabilities=CirqCapabilitiesPort(availability),
        emitter=CirqEmitterPort(),
        compiler=CirqCompilerPort(),
        executor=CirqExecutorPort(),
        decoder=CirqResultDecoderPort(),
    )


def _require_cirq():
    try:
        import cirq
    except ImportError as exc:
        raise EngineNotInstalledError("Cirq is not installed; install quantum-cq[cirq].") from exc
    return cirq


def _append(cirq, circuit, qubits, operation) -> None:
    kind = operation.kind
    if kind == "x":
        circuit.append(cirq.X(qubits[operation.qubits[0]]))
    elif kind == "y":
        circuit.append(cirq.Y(qubits[operation.qubits[0]]))
    elif kind == "z":
        circuit.append(cirq.Z(qubits[operation.qubits[0]]))
    elif kind == "h":
        circuit.append(cirq.H(qubits[operation.qubits[0]]))
    elif kind == "p":
        circuit.append(cirq.ZPowGate(exponent=operation.params["theta"] / 3.141592653589793)(qubits[operation.qubits[0]]))
    elif kind == "rx":
        circuit.append(cirq.rx(operation.params["theta"])(qubits[operation.qubits[0]]))
    elif kind == "ry":
        circuit.append(cirq.ry(operation.params["theta"])(qubits[operation.qubits[0]]))
    elif kind == "rz":
        circuit.append(cirq.rz(operation.params["theta"])(qubits[operation.qubits[0]]))
    elif kind == "cx":
        circuit.append(cirq.CNOT(qubits[operation.params["control"]], qubits[operation.params["target"]]))
    elif kind == "cz":
        circuit.append(cirq.CZ(qubits[operation.params["control"]], qubits[operation.params["target"]]))
    elif kind == "swap":
        circuit.append(cirq.SWAP(qubits[operation.params["left"]], qubits[operation.params["right"]]))
    elif kind == "ccx":
        circuit.append(cirq.CCX(*(qubits[index] for index in operation.qubits)))
    elif kind == "measure":
        circuit.append(cirq.measure(qubits[operation.qubits[0]], key=f"c{operation.clbits[0]}"))
    else:
        raise ExecutionError(f"Cirq adapter does not support operation '{kind}'")


def _cirq_rows(result, contract: MeasurementContract) -> list[list[int]]:
    rows: list[list[int]] = []
    keys = [f"c{mapping.clbit}" for mapping in contract.effective_mappings]
    for key in keys:
        if key not in result.measurements:
            raise ResultDecodingError(f"Cirq result missing measurement key '{key}'")
    shot_count = len(result.measurements[keys[0]]) if keys else 0
    for shot in range(shot_count):
        rows.append([int(result.measurements[key][shot][0]) for key in keys])
    return rows


def _validate_artifact_engine(engine: str, artifact: CompiledArtifact) -> None:
    if artifact.engine != engine:
        raise ExecutionError(
            f"CompiledArtifact engine '{artifact.engine}' nao pode ser executado por '{engine}'"
        )
