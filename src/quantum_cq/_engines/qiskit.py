"""Qiskit engine ports."""

from __future__ import annotations

from importlib import metadata
from typing import Any

from quantum_cq._circuits.adapters import export_to_qiskit
from quantum_cq._engines.availability import EngineAvailability
from quantum_cq._engines.bundle import EngineBundle
from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import EngineNotInstalledError, ExecutionError, ResultDecodingError
from quantum_cq._engines.measurement import MeasurementContract, MeasurementMapping, measure_all_contract
from quantum_cq._engines.results import (
    CompiledArtifact,
    EngineResult,
    NativeExecutionResult,
    NativeTranspilationResult,
)


ENGINE_ID = "qiskit"


class QiskitAvailabilityPort:
    engine_id = ENGINE_ID

    def availability(self) -> EngineAvailability:
        try:
            version = metadata.version("qiskit")
        except metadata.PackageNotFoundError:
            return EngineAvailability(
                engine=self.engine_id,
                installed=False,
                compatible=False,
                reason="Qiskit e dependencia obrigatoria em quantum-cq 0.1.x.",
            )
        return EngineAvailability(
            engine=self.engine_id,
            installed=True,
            compatible=True,
            version=version,
        )

    def is_installed(self) -> bool:
        return self.availability().installed


class QiskitCapabilitiesPort:
    engine_id = ENGINE_ID

    def __init__(self, availability: QiskitAvailabilityPort | None = None) -> None:
        self._availability = availability or QiskitAvailabilityPort()

    def capabilities(self) -> EngineCapabilities:
        availability = self._availability.availability()
        return EngineCapabilities(
            engine=self.engine_id,
            installed=availability.installed,
            default=True,
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
                "cp": "supported",
                "swap": "supported",
                "measure": "supported",
                "partial_measurement": "supported",
                "mapped_measurement": "supported",
                "auto_measure_all": "supported",
                "intermediate_measurement": "not_tested",
                "parameterized": "supported",
                "mcx": "supported",
                "ccx": "supported",
                "unitary": "supported",
                "observables": "not_tested",
                "gradients": "not_tested",
                "statevector": "not_tested",
                "noise": "not_tested",
                "local_execution": "supported",
                "remote_execution": "not_tested",
                "async_jobs": "not_tested",
                "logical_input": "supported",
                "native_circuit_input": "supported",
                "neutralization": "supported",
                "native_transpilation": "supported",
                "compiler": "supported",
                "executor": "supported",
                "renderer": "supported",
            },
            metadata={"version": availability.version},
        )


class QiskitEmitterPort:
    engine_id = ENGINE_ID

    def emit(
        self,
        circuit_ir: Any,
        *,
        measurement_contract: MeasurementContract | None = None,
        capabilities: EngineCapabilities | None = None,
        **options: Any,
    ) -> Any:
        _ = measurement_contract, capabilities, options
        return export_to_qiskit(circuit_ir)


class QiskitCompilerPort:
    engine_id = ENGINE_ID

    def compile(
        self,
        emitted_circuit: Any,
        *,
        source_ir: Any = None,
        measurement_contract: MeasurementContract | None = None,
        capabilities: EngineCapabilities | None = None,
        availability: EngineAvailability | None = None,
        lowering_rules: tuple[str, ...] = (),
        **options: Any,
    ) -> CompiledArtifact:
        _ = source_ir
        backend = options.get("backend")
        pass_manager = options.get("pass_manager")
        optimization_level = options.get("optimization_level")
        execution_measurement_policy = options.pop("__execution_measurement_policy", None)
        native_compiled = emitted_circuit
        metadata_map = {"compiled": False}

        if measurement_contract is None:
            measurement_contract = _contract_from_qiskit_circuit(emitted_circuit)
            if (
                execution_measurement_policy in {"auto", "all"}
                and not measurement_contract.effective_mappings
            ):
                emitted_circuit = emitted_circuit.copy()
                emitted_circuit.measure_all()
                native_compiled = emitted_circuit
                measurement_contract = measure_all_contract(emitted_circuit.num_qubits)
                metadata_map["measurement_prepared_for_execution"] = True

        if pass_manager is not None:
            native_compiled = pass_manager.run(emitted_circuit)
            metadata_map["compiled"] = True
        elif backend is not None and optimization_level is not None:
            try:
                from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
            except ImportError as exc:
                raise EngineNotInstalledError("Qiskit transpiler is not available") from exc

            native_compiled = generate_preset_pass_manager(
                backend=backend,
                optimization_level=optimization_level,
            ).run(emitted_circuit)
            metadata_map["compiled"] = True

        return CompiledArtifact(
            engine=self.engine_id,
            emitted_circuit=emitted_circuit,
            native_compiled=native_compiled,
            backend=backend,
            options=dict(options),
            metadata=metadata_map,
            measurement_contract=measurement_contract,
            capabilities_considered=dict(capabilities.statuses) if capabilities is not None else {},
            lowering_rules=lowering_rules,
            engine_version=availability.version if availability is not None else None,
        )


class QiskitTranspilerPort:
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
        _ = context, target
        if policy not in {
            "preserve_physical_plan",
            "allow_native_refinement",
            "reject_unsupported_preservation",
        }:
            raise ValueError(f"Politica de transpilacao invalida: {policy}")
        before = emitted_circuit.copy() if hasattr(emitted_circuit, "copy") else emitted_circuit
        after = before.copy() if hasattr(before, "copy") else before
        status = "completed"
        metadata_map: dict[str, Any] = {"policy": policy, "native_transpilation": "identity"}
        pass_manager = options.get("pass_manager")
        backend = options.get("backend")
        optimization_level = options.get("optimization_level")
        if pass_manager is not None:
            after = pass_manager.run(before)
            metadata_map["native_transpilation"] = "pass_manager"
        elif backend is not None and optimization_level is not None:
            try:
                from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
            except ImportError as exc:
                raise EngineNotInstalledError("Qiskit transpiler is not available") from exc
            after = generate_preset_pass_manager(
                backend=backend,
                optimization_level=optimization_level,
            ).run(before)
            metadata_map["native_transpilation"] = "preset_pass_manager"
        elif policy == "reject_unsupported_preservation":
            raise ExecutionError("Qiskit transpiler preservation policy requires explicit backend or pass_manager")

        metrics = {
            "before_depth": before.depth() if hasattr(before, "depth") else None,
            "after_depth": after.depth() if hasattr(after, "depth") else None,
            "before_size": before.size() if hasattr(before, "size") else None,
            "after_size": after.size() if hasattr(after, "size") else None,
        }
        return NativeTranspilationResult(
            engine=self.engine_id,
            before=before,
            after=after,
            status=status,
            measurement_contract=measurement_contract,
            metrics=metrics,
            native_metadata=metadata_map,
        )


class QiskitExecutorPort:
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
            from qiskit_aer import AerSimulator
        except ImportError as exc:
            raise EngineNotInstalledError(
                "Qiskit local execution requires qiskit-aer; install quantum-cq[aer]."
            ) from exc

        try:
            simulator = options.get("simulator") or AerSimulator()
            job = simulator.run(artifact.native_compiled, shots=shots)
            raw = job.result()
        except Exception as exc:
            raise ExecutionError("Qiskit execution failed") from exc

        return NativeExecutionResult(
            engine=self.engine_id,
            native_result=raw,
            backend=simulator,
            metadata={"shots": shots, "backend": getattr(simulator, "name", None)},
        )


class QiskitResultDecoderPort:
    engine_id = ENGINE_ID

    def decode(
        self,
        execution: NativeExecutionResult,
        artifact: CompiledArtifact,
        *,
        shots: int = 1024,
        **options: Any,
    ) -> EngineResult:
        _ = options
        if execution.engine != self.engine_id:
            raise ResultDecodingError(
                f"Qiskit decoder recebeu resultado da engine '{execution.engine}'"
            )
        try:
            counts = execution.native_result.get_counts()
        except Exception as exc:
            raise ResultDecodingError("Qiskit result did not provide counts") from exc

        if not isinstance(counts, dict):
            raise ResultDecodingError("Qiskit result did not provide counts")

        contract = artifact.measurement_contract or _contract_from_qiskit_circuit(artifact.native_compiled)
        metadata_map = {
            **dict(execution.metadata),
            "measurement": contract.to_metadata(),
            "bit_order": "canonical_clbit_desc",
            "native_bit_order": "qiskit_counts_order",
            "normalized": True,
        }
        normalized_counts = _canonical_qiskit_counts(counts, contract)
        return EngineResult(
            engine=self.engine_id,
            counts=normalized_counts,
            metadata=metadata_map,
            raw=execution.native_result,
            measurement_contract=contract,
            canonical_bit_order=contract.canonical_bit_order,
            native_bit_order=contract.native_bit_order,
            endianness=contract.endianness,
            normalized=True,
        )


class QiskitEngineAdapter:
    """Run 1 compatibility wrapper around the separated ports."""

    engine_id = ENGINE_ID

    def __init__(self) -> None:
        bundle = create_bundle()
        self._bundle = bundle

    def is_installed(self) -> bool:
        return self._bundle.availability.is_installed()

    def capabilities(self) -> EngineCapabilities:
        return self._bundle.capabilities.capabilities()

    def emit(self, circuit_like: Any, **options: Any) -> Any:
        return self._bundle.emitter.emit(circuit_like, **options)

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        emitted = self.emit(circuit_like, **options)
        return self._bundle.compiler.compile(
            emitted,
            capabilities=self.capabilities(),
            availability=self._bundle.availability.availability(),
            **options,
        )

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        artifact = circuit_like if isinstance(circuit_like, CompiledArtifact) else self.compile(circuit_like, **options)
        execution = self._bundle.executor.execute(artifact, shots=shots, **options)
        return self._bundle.decoder.decode(execution, artifact, shots=shots, **options)


def create_bundle() -> EngineBundle:
    availability = QiskitAvailabilityPort()
    return EngineBundle(
        engine_id=ENGINE_ID,
        availability=availability,
        capabilities=QiskitCapabilitiesPort(availability),
        emitter=QiskitEmitterPort(),
        compiler=QiskitCompilerPort(),
        executor=QiskitExecutorPort(),
        decoder=QiskitResultDecoderPort(),
        transpiler=QiskitTranspilerPort(),
    )


def _validate_artifact_engine(engine: str, artifact: CompiledArtifact) -> None:
    if artifact.engine != engine:
        raise ExecutionError(
            f"CompiledArtifact engine '{artifact.engine}' nao pode ser executado por '{engine}'"
        )


def _contract_from_qiskit_circuit(circuit: Any) -> MeasurementContract:
    try:
        mappings = _qiskit_measurement_mappings(circuit)
        if circuit.num_clbits == 0 or not mappings:
            return MeasurementContract(n_qubits=circuit.num_qubits, n_clbits=circuit.num_clbits)
        return MeasurementContract(
            n_qubits=circuit.num_qubits,
            n_clbits=circuit.num_clbits,
            explicit_mappings=mappings,
            effective_mappings=mappings,
            explicit=True,
            materialized=True,
            canonical_bit_order=tuple(sorted((mapping.clbit for mapping in mappings), reverse=True)),
            native_bit_order=tuple(reversed(range(circuit.num_clbits))),
            native_positions=tuple(
                circuit.num_clbits - 1 - mapping.clbit
                for mapping in sorted(mappings, key=lambda item: item.clbit, reverse=True)
            ),
            notes=("qiskit native counts normalized to measured clbits only",),
        )
    except AttributeError:
        return MeasurementContract(n_qubits=0, n_clbits=0)


def _qiskit_measurement_mappings(circuit: Any) -> tuple[MeasurementMapping, ...]:
    mappings: list[MeasurementMapping] = []
    for item in getattr(circuit, "data", ()):
        operation = getattr(item, "operation", None)
        qubits = getattr(item, "qubits", None)
        clbits = getattr(item, "clbits", None)
        if operation is None and isinstance(item, tuple) and len(item) >= 3:
            operation, qubits, clbits = item[0], item[1], item[2]
        if getattr(operation, "name", None) != "measure":
            continue
        if not qubits or not clbits:
            continue
        qubit = int(circuit.find_bit(qubits[0]).index)
        clbit = int(circuit.find_bit(clbits[0]).index)
        mappings.append(MeasurementMapping(qubit=qubit, clbit=clbit, source="qiskit"))
    return tuple(mappings)


def _canonical_qiskit_counts(counts: dict[Any, Any], contract: MeasurementContract) -> dict[str, int]:
    if not contract.effective_mappings:
        return {str(key).replace(" ", ""): int(value) for key, value in counts.items()}

    canonical_clbits = contract.canonical_bit_order
    normalized: dict[str, int] = {}
    for raw_key, raw_value in counts.items():
        full = _qiskit_count_key_to_binary(str(raw_key), contract.n_clbits)
        values = {
            clbit: full[len(full) - 1 - clbit]
            for clbit in canonical_clbits
            if 0 <= clbit < len(full)
        }
        if len(values) != len(canonical_clbits):
            raise ResultDecodingError(
                f"Qiskit count key '{raw_key}' nao contem todos os clbits medidos"
            )
        key = "".join(values[clbit] for clbit in canonical_clbits)
        normalized[key] = normalized.get(key, 0) + int(raw_value)
    return normalized


def _qiskit_count_key_to_binary(key: str, n_clbits: int) -> str:
    compact = key.replace(" ", "")
    if compact.startswith("0x"):
        return format(int(compact, 16), f"0{n_clbits}b")
    if compact.startswith("0b"):
        compact = compact[2:]
    if not compact:
        return ""
    if any(bit not in {"0", "1"} for bit in compact):
        raise ResultDecodingError(f"Qiskit count key invalida: {key}")
    return compact.zfill(n_clbits)
