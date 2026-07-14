"""Service layer orchestrating engine ports."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from quantum_cq._circuits.compact import CircuitIR
from quantum_cq._core.circuits import CircuitRequirements, CircuitService
from quantum_cq._engines.availability import EngineAvailability
from quantum_cq._engines.bundle import EngineBundle
from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.compatibility import (
    CompatibilityEvaluator,
    CompatibilityReport,
    ComponentRequirement,
)
from quantum_cq._engines.errors import CapabilityMismatchError, EngineNotInstalledError
from quantum_cq._engines.logical import iter_operations, to_logical_ir
from quantum_cq._engines.measurement import (
    MeasurementContract,
    MeasurementPolicy,
    empty_contract,
    measurement_contract_from_ir,
    prepare_ir_for_execution,
)
from quantum_cq._engines.results import CompiledArtifact, EngineResult


class EngineService:
    def __init__(
        self,
        bundle_resolver: Any,
        evaluator: CompatibilityEvaluator | None = None,
        circuit_service: CircuitService | None = None,
        hardware_service: Any = None,
    ) -> None:
        self._bundle_resolver = bundle_resolver
        self._evaluator = evaluator or CompatibilityEvaluator()
        self._circuit_service = circuit_service or CircuitService()
        self._hardware_service = hardware_service

    def engines(self) -> list[dict[str, Any]]:
        from quantum_cq._engines.registry import engine_names

        catalog = []
        for name in engine_names():
            bundle = self._bundle(name)
            availability = bundle.availability.availability()
            catalog.append(
                {
                    "engine": name,
                    "installed": availability.installed,
                    "compatible": availability.compatible,
                    "available": availability.available,
                    "default": name == "qiskit",
                    "status": "supported" if name == "qiskit" else "optional",
                    "reason": availability.reason,
                }
            )
        return catalog

    def capabilities(self, engine: str) -> dict[str, Any]:
        bundle = self._bundle(engine)
        capabilities = bundle.capabilities.capabilities()
        data = capabilities.to_dict()
        data["availability"] = bundle.availability.availability().to_dict()
        return data

    def capability_model(self, engine: str) -> EngineCapabilities:
        return self._bundle(engine).capabilities.capabilities()

    def emit(self, circuit_like: Any, engine: str = "qiskit", **options: Any) -> Any:
        bundle = self._available_bundle(engine)
        capabilities = bundle.capabilities.capabilities()
        source, contract = self._source_and_contract(
            circuit_like,
            bundle=bundle,
            policy="preserve",
            for_execution=False,
        )
        self._require_compatible(bundle.engine_id, source, capabilities, contract)
        return bundle.emitter.emit(
            source,
            measurement_contract=contract,
            capabilities=capabilities,
            **options,
        )

    def compile(self, circuit_like: Any, engine: str = "qiskit", **options: Any) -> CompiledArtifact:
        target = options.pop("target", None)
        context = options.pop("context", None)
        bundle = self._available_bundle(engine)
        capabilities = bundle.capabilities.capabilities()
        availability = bundle.availability.availability()
        source, contract = self._source_and_contract(
            circuit_like,
            bundle=bundle,
            policy="preserve",
            for_execution=False,
        )
        descriptor = self._circuit_service.descriptor(circuit_like, engine=bundle.engine_id)
        circuit_requirements = self._circuit_service.requirements(circuit_like, engine=bundle.engine_id)
        execution_context = self._execution_context(
            engine=bundle.engine_id,
            target=target,
            context=context,
            measurement_policy="preserve",
            shots=options.get("shots"),
            options=options,
        )
        report = self._require_compatible(bundle.engine_id, source, capabilities, contract)
        report = self._with_hardware_context(report, execution_context, circuit_requirements)
        emitted = bundle.emitter.emit(
            source,
            measurement_contract=contract,
            capabilities=capabilities,
            **options,
        )
        artifact = bundle.compiler.compile(
            emitted,
            source_ir=source if isinstance(source, CircuitIR) else None,
            measurement_contract=contract,
            capabilities=capabilities,
            availability=availability,
            lowering_rules=report.lowerings,
            **options,
        )
        return replace(
            artifact,
            context=execution_context,
            compatibility_report=report,
            circuit_descriptor=descriptor,
            circuit_requirements=circuit_requirements,
            target_fingerprint=None
            if execution_context is None or execution_context.architecture is None
            else execution_context.architecture.fingerprint,
        )

    def run(
        self,
        circuit_like: Any,
        engine: str = "qiskit",
        *,
        shots: int = 1024,
        **options: Any,
    ) -> EngineResult:
        target = options.pop("target", None)
        context = options.pop("context", None)
        bundle = self._available_bundle(engine)
        if isinstance(circuit_like, CompiledArtifact):
            artifact = circuit_like
            if artifact.engine != bundle.engine_id:
                raise CapabilityMismatchError(
                    f"CompiledArtifact engine '{artifact.engine}' nao pode ser executado por '{bundle.engine_id}'"
                )
            compiled_shots = artifact.options.get("shots")
            if compiled_shots is not None and int(compiled_shots) != int(shots):
                raise CapabilityMismatchError(
                    f"CompiledArtifact foi compilado com shots={compiled_shots}, "
                    f"mas a execucao solicitou shots={shots}"
                )
            if target is not None or context is not None:
                raise CapabilityMismatchError(
                    "target/context nao podem ser alterados em um CompiledArtifact ja criado"
                )
        else:
            policy = str(options.pop("measurement", "auto")).lower()
            if policy not in {"auto", "preserve", "all", "none"}:
                raise ValueError(f"measurement invalido: {policy}")
            capabilities = bundle.capabilities.capabilities()
            availability = bundle.availability.availability()
            source, contract = self._source_and_contract(
                circuit_like,
                bundle=bundle,
                policy=policy,  # type: ignore[arg-type]
                for_execution=True,
            )
            report = self._require_compatible(bundle.engine_id, source, capabilities, contract)
            descriptor = self._circuit_service.descriptor(circuit_like, engine=bundle.engine_id)
            circuit_requirements = self._circuit_service.requirements(circuit_like, engine=bundle.engine_id)
            execution_context = self._execution_context(
                engine=bundle.engine_id,
                target=target,
                context=context,
                measurement_policy=policy,
                shots=shots,
                options=options,
            )
            report = self._with_hardware_context(report, execution_context, circuit_requirements)
            emitted = bundle.emitter.emit(
                source,
                measurement_contract=contract,
                capabilities=capabilities,
                **options,
            )
            compile_options = dict(options)
            compile_options["shots"] = shots
            if bundle.engine_id == "qiskit":
                compile_options["__execution_measurement_policy"] = policy
            artifact = bundle.compiler.compile(
                emitted,
                source_ir=source if isinstance(source, CircuitIR) else None,
                measurement_contract=contract,
                capabilities=capabilities,
                availability=availability,
                lowering_rules=report.lowerings,
                **compile_options,
            )
            artifact = replace(
                artifact,
                context=execution_context,
                compatibility_report=report,
                circuit_descriptor=descriptor,
                circuit_requirements=circuit_requirements,
                target_fingerprint=None
                if execution_context is None or execution_context.architecture is None
                else execution_context.architecture.fingerprint,
            )

        self._reject_unimplemented_physical_execution(artifact)
        execution = bundle.executor.execute(artifact, shots=shots, **options)
        return bundle.decoder.decode(execution, artifact, shots=shots, **options)

    def compatibility(
        self,
        circuit_like: Any = None,
        *,
        component: str | None = None,
        engine: str,
        requirements: tuple[ComponentRequirement, ...] | None = None,
        target: Any = None,
    ) -> CompatibilityReport:
        bundle = self._available_bundle(engine)
        if requirements is None:
            if circuit_like is None:
                raise TypeError("compatibility requer circuit_like ou requirements")
            circuit_requirements = self._circuit_service.requirements(circuit_like, engine=engine)
            requirements = _requirements_from_circuit_requirements(circuit_requirements)
            component = component or getattr(circuit_like, "name", type(circuit_like).__name__)
        else:
            circuit_requirements = None
        report = self._evaluator.evaluate(
            component=component or "circuit",
            capabilities=bundle.capabilities.capabilities(),
            requirements=requirements,
            circuit_requirements=circuit_requirements,
            target=target,
        )
        if target is not None and circuit_requirements is not None:
            execution_context = self._execution_context(
                engine=bundle.engine_id,
                target=target,
                context=None,
                measurement_policy="preserve",
                shots=None,
                options={},
            )
            report = self._with_hardware_context(report, execution_context, circuit_requirements)
        return report

    def _bundle(self, engine: str) -> EngineBundle:
        return self._bundle_resolver(engine)

    def _available_bundle(self, engine: str) -> EngineBundle:
        bundle = self._bundle(engine)
        availability = bundle.availability.availability()
        if not availability.available:
            raise EngineNotInstalledError(availability.reason or f"Engine '{engine}' indisponivel")
        return bundle

    def _source_and_contract(
        self,
        circuit_like: Any,
        *,
        bundle: EngineBundle,
        policy: MeasurementPolicy,
        for_execution: bool,
    ) -> tuple[Any, MeasurementContract | None]:
        if bundle.engine_id == "qiskit" and self._circuit_service._is_qiskit_native(circuit_like):
            return circuit_like, None

        try:
            ir = self._circuit_service.to_ir(circuit_like)
        except TypeError:
            ir = to_logical_ir(circuit_like)
        if for_execution:
            return prepare_ir_for_execution(ir, policy=policy)
        return ir, measurement_contract_from_ir(ir, policy=policy)

    def _require_compatible(
        self,
        engine: str,
        source: Any,
        capabilities: EngineCapabilities,
        contract: MeasurementContract | None,
    ) -> CompatibilityReport:
        requirements: list[ComponentRequirement] = []
        if isinstance(source, CircuitIR):
            requirements.extend(_requirements_from_ir(source, contract))
        elif contract is not None and contract.effective_mappings:
            requirements.append(ComponentRequirement("measure"))

        report = self._evaluator.evaluate(
            component=getattr(source, "name", type(source).__name__),
            capabilities=capabilities,
            requirements=tuple(requirements),
        )
        if report.status == "incompatible":
            raise CapabilityMismatchError(
                f"Engine '{engine}' nao atende aos requisitos: {report.reason}"
            )
        if report.status == "not_tested":
            raise CapabilityMismatchError(
                f"Engine '{engine}' possui requisitos sem evidencia de teste: {report.reason}"
            )
        return report

    def _execution_context(
        self,
        *,
        engine: str,
        target: Any,
        context: Any,
        measurement_policy: str,
        shots: int | None,
        options: dict[str, Any],
    ) -> Any:
        if context is not None:
            return context
        if target is None:
            return None
        hardware_service = self._hardware_service
        if hardware_service is None:
            from quantum_cq._hardware.service import default_hardware_service

            hardware_service = default_hardware_service()
        return hardware_service.execution_context(
            engine=engine,
            target=target,
            measurement_policy=measurement_policy,
            shots=shots,
            options=options,
        )

    def _with_hardware_context(
        self,
        report: CompatibilityReport,
        context: Any,
        circuit_requirements: CircuitRequirements,
    ) -> CompatibilityReport:
        if context is None or getattr(context, "target", None) is None:
            return replace(report, circuit_requirements=circuit_requirements)
        hardware_service = self._hardware_service
        if hardware_service is None:
            from quantum_cq._hardware.service import default_hardware_service

            hardware_service = default_hardware_service()
        hints = hardware_service.compatibility_hints(
            context.target,
            required_qubits=circuit_requirements.min_qubits,
        )
        missing = report.missing
        status = report.status
        reason = report.reason
        if hints.get("insufficient_qubits"):
            missing = (*missing, "target_qubits")
            status = "incompatible"
            reason = "target has insufficient physical qubits"
        return replace(
            report,
            circuit_requirements=circuit_requirements,
            target=context.target,
            hardware=hints,
            unknowns=tuple(hints.get("unknowns", ())),
            placement_required=bool(hints.get("placement_required", False)),
            routing_required=bool(hints.get("routing_required", False)),
            scheduling_required=bool(hints.get("scheduling_required", False)),
            missing=missing,
            status=status,
            reason=reason,
            physical_execution_claimed=False,
        )

    def _reject_unimplemented_physical_execution(self, artifact: CompiledArtifact) -> None:
        context = artifact.context
        target = getattr(context, "target", None)
        descriptor = getattr(target, "descriptor", None)
        if descriptor is not None and getattr(descriptor, "target_type", None) == "physical":
            raise CapabilityMismatchError(
                "Execucao em target fisico/remoto ainda nao foi implementada nesta run"
            )


def _requirements_from_ir(
    ir: CircuitIR,
    contract: MeasurementContract | None,
) -> tuple[ComponentRequirement, ...]:
    features: set[str] = set()
    for operation in iter_operations(ir):
        if operation.kind == "barrier":
            continue
        features.add(operation.kind)
    if contract and contract.effective_mappings:
        features.add("measure")
        if len(contract.effective_mappings) < ir.n_qubits:
            features.add("partial_measurement")
        if any(mapping.qubit != mapping.clbit for mapping in contract.effective_mappings):
            features.add("mapped_measurement")
    if contract and contract.automatic:
        features.add("auto_measure_all")
    return tuple(ComponentRequirement(feature) for feature in sorted(features))


def _requirements_from_circuit_requirements(
    requirements: CircuitRequirements,
) -> tuple[ComponentRequirement, ...]:
    return tuple(
        ComponentRequirement(feature, category="circuit")
        for feature in requirements.features
    )


def default_engine_service() -> EngineService:
    from quantum_cq._engines.registry import get_engine_bundle

    return EngineService(get_engine_bundle)
