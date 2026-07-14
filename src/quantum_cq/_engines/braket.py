"""Amazon Braket engine ports."""

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


ENGINE_ID = "braket"


class BraketAvailabilityPort:
    engine_id = ENGINE_ID

    def availability(self) -> EngineAvailability:
        installed = importlib.util.find_spec("braket") is not None
        if not installed:
            return EngineAvailability(
                engine=self.engine_id,
                installed=False,
                compatible=False,
                reason="Amazon Braket SDK is not installed; install quantum-cq[braket].",
            )
        try:
            version = metadata.version("amazon-braket-sdk")
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


class BraketCapabilitiesPort:
    engine_id = ENGINE_ID

    def __init__(self, availability: BraketAvailabilityPort | None = None) -> None:
        self._availability = availability or BraketAvailabilityPort()

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
                "p": "not_tested",
                "rx": "supported",
                "ry": "supported",
                "rz": "supported",
                "cx": "supported",
                "cz": "supported",
                "cp": "not_tested",
                "swap": "supported",
                "measure": "supported",
                "partial_measurement": "unsupported",
                "mapped_measurement": "unsupported",
                "auto_measure_all": "supported",
                "intermediate_measurement": "unsupported",
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


class BraketEmitterPort:
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
        Circuit = _require_circuit()
        capabilities = capabilities or BraketCapabilitiesPort().capabilities()
        ir = lower_for_capabilities(circuit_ir, capabilities)
        circuit = Circuit()
        for operation in iter_operations(ir):
            _append(circuit, operation)
        return circuit


class BraketCompilerPort:
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
        if measurement_contract is not None and measurement_contract.effective_mappings:
            measurement_contract = measurement_contract.with_native_order(
                tuple(range(source_ir.n_qubits if source_ir is not None else measurement_contract.n_qubits)),
                implicit_native=True,
                materialized=False,
                note="Braket LocalSimulator samples all qubits implicitly at run time",
            )
        return CompiledArtifact(
            engine=self.engine_id,
            emitted_circuit=emitted_circuit,
            native_compiled=emitted_circuit,
            device=options.get("device", "braket.local.qubit"),
            options=dict(options),
            metadata={"compiled": False},
            measurement_contract=measurement_contract,
            capabilities_considered=dict(capabilities.statuses) if capabilities is not None else {},
            lowering_rules=lowering_rules,
            engine_version=availability.version if availability is not None else None,
        )


class BraketExecutorPort:
    engine_id = ENGINE_ID

    def execute(
        self,
        artifact: CompiledArtifact,
        *,
        shots: int = 1024,
        **options: Any,
    ) -> NativeExecutionResult:
        _validate_artifact_engine(self.engine_id, artifact)
        try:
            from braket.devices import LocalSimulator
        except ImportError as exc:
            raise EngineNotInstalledError(
                "Amazon Braket local execution requires amazon-braket-sdk; install quantum-cq[braket]."
            ) from exc

        try:
            device = options.get("device") or LocalSimulator()
            task = device.run(artifact.native_compiled, shots=shots)
            raw = task.result()
        except Exception as exc:
            raise ExecutionError("Amazon Braket local execution failed") from exc

        return NativeExecutionResult(
            engine=self.engine_id,
            native_result=raw,
            device=device,
            metadata={"shots": shots, "device": str(device)},
        )


class BraketResultDecoderPort:
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
            raise ResultDecodingError(f"Braket decoder recebeu resultado da engine '{execution.engine}'")
        contract = artifact.measurement_contract
        if contract is None or not contract.effective_mappings:
            raise ResultDecodingError("Braket result requires a measurement contract")
        rows = _braket_rows(execution.native_result, contract)
        counts = canonical_counts_from_rows(rows, contract.effective_mappings)
        return EngineResult(
            engine=self.engine_id,
            counts=counts,
            metadata={
                **dict(execution.metadata),
                "measurement": contract.to_metadata(),
                "bit_order": "canonical_clbit_desc",
                "native_bit_order": "braket_measurement_order",
                "normalized": True,
            },
            raw=execution.native_result,
            measurement_contract=contract,
            canonical_bit_order=contract.canonical_bit_order,
            native_bit_order=contract.native_bit_order,
            endianness=contract.endianness,
            normalized=True,
        )


class BraketEngineAdapter:
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
    availability = BraketAvailabilityPort()
    return EngineBundle(
        engine_id=ENGINE_ID,
        availability=availability,
        capabilities=BraketCapabilitiesPort(availability),
        emitter=BraketEmitterPort(),
        compiler=BraketCompilerPort(),
        executor=BraketExecutorPort(),
        decoder=BraketResultDecoderPort(),
    )


def _require_circuit():
    try:
        from braket.circuits import Circuit
    except ImportError as exc:
        raise EngineNotInstalledError(
            "Amazon Braket SDK is not installed; install quantum-cq[braket]."
        ) from exc
    return Circuit


def _append(circuit, operation) -> None:
    kind = operation.kind
    if kind == "x":
        circuit.x(operation.qubits[0])
    elif kind == "y":
        circuit.y(operation.qubits[0])
    elif kind == "z":
        circuit.z(operation.qubits[0])
    elif kind == "h":
        circuit.h(operation.qubits[0])
    elif kind == "rx":
        circuit.rx(operation.qubits[0], operation.params["theta"])
    elif kind == "ry":
        circuit.ry(operation.qubits[0], operation.params["theta"])
    elif kind == "rz":
        circuit.rz(operation.qubits[0], operation.params["theta"])
    elif kind == "cx":
        circuit.cnot(operation.params["control"], operation.params["target"])
    elif kind == "cz":
        circuit.cz(operation.params["control"], operation.params["target"])
    elif kind == "swap":
        circuit.swap(operation.params["left"], operation.params["right"])
    elif kind == "ccx":
        circuit.ccnot(*operation.qubits)
    elif kind == "measure":
        return
    else:
        raise ExecutionError(f"Amazon Braket adapter does not support operation '{kind}'")


def _braket_rows(result, contract: MeasurementContract) -> list[list[int]]:
    if hasattr(result, "measurements"):
        rows = []
        for row in result.measurements:
            rows.append([int(row[mapping.qubit]) for mapping in contract.effective_mappings])
        return rows

    rows = []
    for bitstring, count in dict(result.measurement_counts).items():
        bits = [int(bit) for bit in str(bitstring)]
        values = [bits[mapping.qubit] for mapping in contract.effective_mappings]
        rows.extend([values] * int(count))
    return rows


def _validate_artifact_engine(engine: str, artifact: CompiledArtifact) -> None:
    if artifact.engine != engine:
        raise ExecutionError(
            f"CompiledArtifact engine '{artifact.engine}' nao pode ser executado por '{engine}'"
        )
