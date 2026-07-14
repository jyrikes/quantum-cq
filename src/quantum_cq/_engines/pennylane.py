"""PennyLane engine ports."""

from __future__ import annotations

import importlib.util
from importlib import metadata
from typing import Any

import numpy as np

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
from quantum_cq._engines.results import (
    CompiledArtifact,
    EngineResult,
    NativeExecutionResult,
    NativeTranspilationResult,
)


ENGINE_ID = "pennylane"


class PennyLaneAvailabilityPort:
    engine_id = ENGINE_ID

    def availability(self) -> EngineAvailability:
        installed = importlib.util.find_spec("pennylane") is not None
        if not installed:
            return EngineAvailability(
                engine=self.engine_id,
                installed=False,
                compatible=False,
                reason="PennyLane is not installed; install quantum-cq[pennylane].",
            )
        try:
            version = metadata.version("pennylane")
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


class PennyLaneCapabilitiesPort:
    engine_id = ENGINE_ID

    def __init__(self, availability: PennyLaneAvailabilityPort | None = None) -> None:
        self._availability = availability or PennyLaneAvailabilityPort()

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
                "gradients": "not_tested",
                "statevector": "not_tested",
                "noise": "unsupported",
                "local_execution": "supported",
                "remote_execution": "unsupported",
                "async_jobs": "unsupported",
                "logical_input": "supported",
                "native_circuit_input": "not_tested",
                "neutralization": "not_tested",
                "native_transpilation": "unsupported",
                "compiler": "supported",
                "executor": "supported",
                "renderer": "not_tested",
            },
            metadata={"version": availability.version},
        )


class PennyLaneEmitterPort:
    engine_id = ENGINE_ID

    def emit(
        self,
        circuit_ir: CircuitIR,
        *,
        measurement_contract: MeasurementContract | None = None,
        capabilities: EngineCapabilities | None = None,
        **options: Any,
    ) -> Any:
        qml = _require_pennylane()
        capabilities = capabilities or PennyLaneCapabilitiesPort().capabilities()
        ir = lower_for_capabilities(circuit_ir, capabilities)
        measurement_contract = measurement_contract or measurement_contract_from_ir(ir)
        operations = [
            _operation(qml, operation)
            for operation in iter_operations(ir)
            if operation.kind != "measure"
        ]
        measurements = []
        if measurement_contract.effective_mappings:
            wires = [mapping.qubit for mapping in measurement_contract.effective_mappings]
            measurements.append(qml.sample(wires=wires))
        return qml.tape.QuantumScript(operations, measurements, shots=options.get("shots"))


class PennyLaneCompilerPort:
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
        if source_ir is None:
            raise ExecutionError("PennyLane compiler requires source CircuitIR")
        qml = _require_pennylane()
        capabilities = capabilities or PennyLaneCapabilitiesPort().capabilities()
        ir = lower_for_capabilities(source_ir, capabilities)
        measurement_contract = measurement_contract or measurement_contract_from_ir(ir)
        device = options.get("device") or qml.device(
            options.get("device_name", "default.qubit"),
            wires=ir.n_qubits,
            shots=options.get("shots", 1024),
        )

        @qml.qnode(device)
        def executable():
            for operation in iter_operations(ir):
                if operation.kind == "measure":
                    continue
                _apply(qml, operation)
            if measurement_contract and measurement_contract.effective_mappings:
                wires = [mapping.qubit for mapping in measurement_contract.effective_mappings]
                return qml.sample(wires=wires)
            return qml.sample(wires=range(ir.n_qubits))

        return CompiledArtifact(
            engine=self.engine_id,
            emitted_circuit=emitted_circuit,
            native_compiled=executable,
            device=device,
            options=dict(options),
            metadata={"logical_qubits": ir.n_qubits, "compiled": True},
            measurement_contract=measurement_contract,
            capabilities_considered=dict(capabilities.statuses),
            lowering_rules=lowering_rules,
            engine_version=availability.version if availability is not None else None,
        )


class PennyLaneExecutorPort:
    engine_id = ENGINE_ID

    def execute(
        self,
        artifact: CompiledArtifact,
        *,
        shots: int = 1024,
        **options: Any,
    ) -> NativeExecutionResult:
        _ = shots, options
        _validate_artifact_engine(self.engine_id, artifact)
        try:
            samples = artifact.native_compiled()
        except Exception as exc:
            raise ExecutionError("PennyLane execution failed") from exc
        return NativeExecutionResult(
            engine=self.engine_id,
            native_result=samples,
            device=artifact.device,
            metadata={"shots": shots, "device": str(artifact.device)},
        )


class PennyLaneResultDecoderPort:
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
            raise ResultDecodingError(
                f"PennyLane decoder recebeu resultado da engine '{execution.engine}'"
            )
        contract = artifact.measurement_contract
        if contract is None or not contract.effective_mappings:
            raise ResultDecodingError("PennyLane result requires a measurement contract")
        rows = _samples_to_rows(execution.native_result)
        counts = canonical_counts_from_rows(rows, contract.effective_mappings)
        contract = contract.with_native_order(
            tuple(mapping.clbit for mapping in contract.effective_mappings),
            materialized=True,
            note="PennyLane samples normalized to canonical clbit-desc order",
        )
        return EngineResult(
            engine=self.engine_id,
            counts=counts,
            samples=execution.native_result,
            metadata={
                **dict(execution.metadata),
                "measurement": contract.to_metadata(),
                "bit_order": "canonical_clbit_desc",
                "native_bit_order": "pennylane_sample_wire_order",
                "normalized": True,
            },
            raw=execution.native_result,
            measurement_contract=contract,
            canonical_bit_order=contract.canonical_bit_order,
            native_bit_order=contract.native_bit_order,
            endianness=contract.endianness,
            normalized=True,
        )


class PennyLaneEngineAdapter:
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
        contract = measurement_contract_from_ir(ir)
        return self._bundle.emitter.emit(
            ir,
            measurement_contract=contract,
            capabilities=self.capabilities(),
            **options,
        )

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        from quantum_cq._engines.logical import to_logical_ir

        ir = to_logical_ir(circuit_like)
        contract = measurement_contract_from_ir(ir)
        emitted = self.emit(ir, **options)
        return self._bundle.compiler.compile(
            emitted,
            source_ir=ir,
            measurement_contract=contract,
            capabilities=self.capabilities(),
            availability=self._bundle.availability.availability(),
            **options,
        )

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        artifact = circuit_like if isinstance(circuit_like, CompiledArtifact) else self.compile(circuit_like, **options)
        execution = self._bundle.executor.execute(artifact, shots=shots, **options)
        return self._bundle.decoder.decode(execution, artifact, shots=shots, **options)


class PennyLaneTranspilerPort:
    engine_id = ENGINE_ID

    def transpile(
        self,
        emitted_circuit: Any,
        *,
        measurement_contract: MeasurementContract | None = None,
        context: Any = None,
        target: Any = None,
        policy: str = "allow_native_refinement",
        **options: Any,
    ) -> NativeTranspilationResult:
        _ = context, target, policy, options
        return NativeTranspilationResult(
            engine=self.engine_id,
            before=emitted_circuit,
            after=emitted_circuit,
            status="not_applicable",
            measurement_contract=measurement_contract,
            native_metadata={"native_transpilation": "not_applicable"},
        )


def create_bundle() -> EngineBundle:
    availability = PennyLaneAvailabilityPort()
    return EngineBundle(
        engine_id=ENGINE_ID,
        availability=availability,
        capabilities=PennyLaneCapabilitiesPort(availability),
        emitter=PennyLaneEmitterPort(),
        compiler=PennyLaneCompilerPort(),
        executor=PennyLaneExecutorPort(),
        decoder=PennyLaneResultDecoderPort(),
        transpiler=PennyLaneTranspilerPort(),
    )


def _require_pennylane():
    try:
        import pennylane as qml
    except ImportError as exc:
        raise EngineNotInstalledError(
            "PennyLane is not installed; install quantum-cq[pennylane]."
        ) from exc
    return qml


def _operation(qml, operation):
    with qml.queuing.QueuingManager.stop_recording():
        return _make_operation(qml, operation)


def _apply(qml, operation) -> None:
    _make_operation(qml, operation)


def _make_operation(qml, operation):
    kind = operation.kind
    if kind == "x":
        return qml.PauliX(wires=operation.qubits[0])
    if kind == "y":
        return qml.PauliY(wires=operation.qubits[0])
    if kind == "z":
        return qml.PauliZ(wires=operation.qubits[0])
    if kind == "h":
        return qml.Hadamard(wires=operation.qubits[0])
    if kind == "rx":
        return qml.RX(operation.params["theta"], wires=operation.qubits[0])
    if kind == "ry":
        return qml.RY(operation.params["theta"], wires=operation.qubits[0])
    if kind == "rz":
        return qml.RZ(operation.params["theta"], wires=operation.qubits[0])
    if kind == "p":
        return qml.PhaseShift(operation.params["theta"], wires=operation.qubits[0])
    if kind == "cx":
        return qml.CNOT(wires=[operation.params["control"], operation.params["target"]])
    if kind == "cz":
        return qml.CZ(wires=[operation.params["control"], operation.params["target"]])
    if kind == "swap":
        return qml.SWAP(wires=[operation.params["left"], operation.params["right"]])
    if kind == "ccx":
        return qml.Toffoli(wires=list(operation.qubits))
    raise ExecutionError(f"PennyLane adapter does not support operation '{kind}'")


def _samples_to_rows(samples: Any) -> list[list[int]]:
    array = np.asarray(samples)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    return [[int(bit) for bit in row.tolist()] for row in array]


def _validate_artifact_engine(engine: str, artifact: CompiledArtifact) -> None:
    if artifact.engine != engine:
        raise ExecutionError(
            f"CompiledArtifact engine '{artifact.engine}' nao pode ser executado por '{engine}'"
        )
