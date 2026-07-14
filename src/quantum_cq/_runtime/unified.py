"""Feature-driven pipeline core used by the public pipeline facade.

The module is intentionally SDK-free except when it delegates to EngineService
through its public service boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Protocol

from quantum_cq._circuits.compact import CircuitIR, Layer, LogicalCircuitBuilder, Operation, QuantumState
from quantum_cq._core.data import QuantumData
from quantum_cq._core.results import EncodedCircuit
from quantum_cq._core.selectors import EncodingSelector
from quantum_cq._engines.results import CompiledArtifact, EngineResult


STAGE_STATUSES = {
    "pending",
    "completed",
    "not_requested",
    "not_applicable",
    "insufficient_information",
    "incompatible",
    "failed",
    "skipped_by_policy",
}

KNOWN_STAGES = {
    "encoding",
    "input_adapt",
    "mqt_lower",
    "placement",
    "routing",
    "scheduling",
    "native_transpile",
    "compile",
    "execute",
}

KNOWN_PIPELINE_OPTIONS = {
    "metadata",
    "parameters",
    "symbols",
    "engine",
    "target",
    "snapshot",
    "shots",
    "measurement",
    "placement",
    "routing",
    "scheduling",
    "stages",
    "stop_after",
    "scenarios",
    "render",
    "input_adapter",
    "runtime_options",
}


class PipelineInputAdapterProtocol(Protocol):
    adapter_id: str

    def supports(self, value: Any) -> bool: ...

    def adapt(self, value: Any, context: "PipelineExecutionConfig") -> CircuitIR | Any: ...


@dataclass(frozen=True)
class PipelineDiagnostic:
    level: str
    message: str
    stage_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "stage_id": self.stage_id,
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class MetricValue:
    value: Any
    unit: str | None = None
    status: str = "computed"
    source: str = "pipeline"
    stage: str | None = None
    scenario: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": _json_safe(self.value),
            "unit": self.unit,
            "status": self.status,
            "source": self.source,
            "stage": self.stage,
            "scenario": self.scenario,
        }


@dataclass(frozen=True)
class CircuitSnapshot:
    snapshot_id: str
    scenario_id: str
    stage_id: str
    format: str
    circuit: Any = None
    engine: str | None = None
    target: str | None = None
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    def descriptor(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "scenario_id": self.scenario_id,
            "stage_id": self.stage_id,
            "format": self.format,
            "engine": self.engine,
            "target": self.target,
            "metrics": {key: value.to_dict() for key, value in self.metrics.items()},
            "provenance": dict(self.provenance),
            "circuit": _circuit_descriptor(self.circuit),
        }


@dataclass(frozen=True)
class TransformationEvent:
    event_id: str
    scenario_id: str
    stage_id: str
    input_snapshot_ids: tuple[str, ...] = ()
    output_snapshot_ids: tuple[str, ...] = ()
    transformation_type: str = "analysis"
    changes: dict[str, Any] = field(default_factory=dict)
    metrics_delta: dict[str, Any] = field(default_factory=dict)
    diagnostics: tuple[PipelineDiagnostic, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_snapshot_ids", tuple(self.input_snapshot_ids))
        object.__setattr__(self, "output_snapshot_ids", tuple(self.output_snapshot_ids))
        object.__setattr__(self, "changes", MappingProxyType(dict(self.changes)))
        object.__setattr__(self, "metrics_delta", MappingProxyType(dict(self.metrics_delta)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "scenario_id": self.scenario_id,
            "stage_id": self.stage_id,
            "input_snapshot_ids": list(self.input_snapshot_ids),
            "output_snapshot_ids": list(self.output_snapshot_ids),
            "transformation_type": self.transformation_type,
            "changes": _json_safe(dict(self.changes)),
            "metrics_delta": _json_safe(dict(self.metrics_delta)),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "provenance": _json_safe(dict(self.provenance)),
        }


@dataclass(frozen=True)
class TransformationGraph:
    scenario_id: str
    events: tuple[TransformationEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True)
class StageResult:
    stage_id: str
    status: str
    started_at: datetime
    finished_at: datetime
    requires: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    diagnostics: tuple[PipelineDiagnostic, ...] = ()
    transformations: tuple[TransformationEvent, ...] = ()
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STAGE_STATUSES:
            raise ValueError(f"status de stage invalido: {self.status}")
        if self.status == "completed" and self.provides:
            missing = [feature for feature in self.provides if not feature]
            if missing:
                raise ValueError("stage completed declarou feature vazia")
        object.__setattr__(self, "requires", tuple(self.requires))
        object.__setattr__(self, "provides", tuple(self.provides))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "transformations", tuple(self.transformations))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "requires": list(self.requires),
            "provides": list(self.provides),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "transformations": [item.to_dict() for item in self.transformations],
            "metrics": {key: value.to_dict() for key, value in self.metrics.items()},
            "provenance": _json_safe(dict(self.provenance)),
        }


@dataclass(frozen=True)
class PipelineScenario:
    scenario_id: str
    primary_input_kind: str
    primary_input: Any = None
    engine: str | None = None
    target: Any = None
    snapshot: Any = None
    strategies: dict[str, Any] = field(default_factory=dict)
    runtime_options: dict[str, Any] = field(default_factory=dict)
    render_options: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    diagnostics: tuple[PipelineDiagnostic, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategies", MappingProxyType(dict(self.strategies)))
        object.__setattr__(self, "runtime_options", MappingProxyType(dict(self.runtime_options)))
        object.__setattr__(self, "render_options", MappingProxyType(dict(self.render_options)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


@dataclass(frozen=True)
class PipelineState:
    scenario: PipelineScenario
    features: dict[str, Any] = field(default_factory=dict)
    stage_results: tuple[StageResult, ...] = ()
    snapshots: tuple[CircuitSnapshot, ...] = ()
    transformation_events: tuple[TransformationEvent, ...] = ()
    diagnostics: tuple[PipelineDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))
        object.__setattr__(self, "stage_results", tuple(self.stage_results))
        object.__setattr__(self, "snapshots", tuple(self.snapshots))
        object.__setattr__(self, "transformation_events", tuple(self.transformation_events))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def with_feature(self, key: str, value: Any) -> "PipelineState":
        features = dict(self.features)
        features[key] = value
        return replace(self, features=features)

    def with_stage(
        self,
        stage: StageResult,
        *,
        snapshots: tuple[CircuitSnapshot, ...] = (),
        events: tuple[TransformationEvent, ...] = (),
        diagnostics: tuple[PipelineDiagnostic, ...] = (),
    ) -> "PipelineState":
        if stage.status == "completed":
            missing = [feature for feature in stage.provides if feature not in self.features]
            if missing:
                raise ValueError(
                    f"stage '{stage.stage_id}' completed sem produzir features: {missing}"
                )
        return replace(
            self,
            stage_results=(*self.stage_results, stage),
            snapshots=(*self.snapshots, *snapshots),
            transformation_events=(*self.transformation_events, *events),
            diagnostics=(*self.diagnostics, *diagnostics),
        )


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    status: str
    stage_results: tuple[StageResult, ...] = ()
    snapshots: tuple[CircuitSnapshot, ...] = ()
    transformation_graph: TransformationGraph | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    diagnostics: tuple[PipelineDiagnostic, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_results", tuple(self.stage_results))
        object.__setattr__(self, "snapshots", tuple(self.snapshots))
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    @property
    def logical_circuit(self) -> CircuitIR | None:
        return self.artifacts.get("logical_circuit")

    @property
    def before_transpile(self) -> CircuitSnapshot | None:
        return self.artifacts.get("before_transpile")

    @property
    def after_transpile(self) -> CircuitSnapshot | None:
        return self.artifacts.get("after_transpile")

    @property
    def transpilation_record(self) -> Any:
        return self.artifacts.get("transpilation_record")

    @property
    def compiled_artifact(self) -> CompiledArtifact | None:
        return self.artifacts.get("compiled_artifact")

    @property
    def engine_result(self) -> EngineResult | None:
        return self.artifacts.get("engine_result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "status": self.status,
            "stage_results": [item.to_dict() for item in self.stage_results],
            "snapshots": [snapshot.descriptor() for snapshot in self.snapshots],
            "transformation_graph": None
            if self.transformation_graph is None
            else self.transformation_graph.to_dict(),
            "artifacts": _artifact_payload(dict(self.artifacts)),
            "metrics": {key: value.to_dict() for key, value in self.metrics.items()},
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "provenance": _json_safe(dict(self.provenance)),
        }


@dataclass(frozen=True)
class PipelineExecutionConfig:
    data: Any = None
    equation: str | None = None
    circuit: Any = None
    input: Any = None
    input_adapter: PipelineInputAdapterProtocol | None = None
    encoding: str | None = None
    registry: Any = None
    selector: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    symbols: dict[str, Any] = field(default_factory=dict)
    engine: str | None = None
    target: Any = None
    snapshot: Any = None
    shots: int = 1024
    measurement: str = "auto"
    placement: str | None = None
    routing: str | None = None
    scheduling: str | None = None
    stages: tuple[str, ...] = ()
    stop_after: str | None = None
    scenarios: tuple[dict[str, Any], ...] = ()
    render: dict[str, Any] = field(default_factory=dict)
    runtime_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if int(self.shots) < 0:
            raise ValueError("shots deve ser nao negativo")
        if self.measurement not in {"auto", "preserve", "all", "none"}:
            raise ValueError(f"measurement policy invalida: {self.measurement}")
        object.__setattr__(self, "shots", int(self.shots))
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "parameters", dict(self.parameters))
        object.__setattr__(self, "symbols", dict(self.symbols))
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "scenarios", tuple(dict(item) for item in self.scenarios))
        object.__setattr__(self, "render", dict(self.render))
        object.__setattr__(self, "runtime_options", dict(self.runtime_options))

    @property
    def is_legacy_encoding_flow(self) -> bool:
        return (
            self.data is not None
            and self.equation is None
            and self.circuit is None
            and self.input is None
            and self.engine is None
            and self.target is None
            and not self.stages
            and not self.scenarios
        )

    def primary_inputs(self) -> dict[str, Any]:
        candidates = {
            "data": self.data,
            "equation": self.equation,
            "circuit": self.circuit,
            "input": self.input,
        }
        return {key: value for key, value in candidates.items() if value is not None}

    def validate(self, *, terminal: str | None = None) -> None:
        primaries = self.primary_inputs()
        if len(primaries) > 1:
            names = ", ".join(sorted(primaries))
            raise ValueError(f"Cada execucao requer uma unica entrada primaria; recebidas: {names}")
        if len(primaries) == 0 and terminal != "legacy":
            raise ValueError("Pipeline requer uma entrada primaria")
        if self.input is not None and self.input_adapter is None:
            raise TypeError("Entrada generica requer input_adapter explicito")
        unknown_stages = set(self.stages) - KNOWN_STAGES
        if unknown_stages:
            raise ValueError(f"stage desconhecido: {sorted(unknown_stages)}")
        if self.stop_after is not None and self.stages and self.stop_after not in self.stages:
            raise ValueError("stop_after deve pertencer aos stages habilitados")
        scenario_ids = [
            str(item.get("scenario_id"))
            for item in self.scenarios
            if item.get("scenario_id") is not None
        ]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("scenario_id duplicado")


class PipelineCore:
    """Single orchestration core for enriched pipeline runs."""

    def __init__(self, config: PipelineExecutionConfig) -> None:
        self.config = config
        self.config.validate()

    def transpile(self) -> list[ScenarioResult]:
        return [self._run_scenario(scenario, terminal="transpile") for scenario in self._scenarios()]

    def compile(self, *, engine: str | None = None, **options: Any) -> list[ScenarioResult]:
        return [
            self._run_scenario(scenario, terminal="compile", engine=engine, terminal_options=options)
            for scenario in self._scenarios()
        ]

    def run_engine(self, *, engine: str | None = None, shots: int | None = None, **options: Any) -> list[ScenarioResult]:
        return [
            self._run_scenario(
                scenario,
                terminal="run_engine",
                engine=engine,
                shots=shots,
                terminal_options=options,
            )
            for scenario in self._scenarios()
        ]

    def _scenarios(self) -> tuple[PipelineScenario, ...]:
        if self.config.scenarios:
            scenarios = []
            seen: set[str] = set()
            for index, raw in enumerate(self.config.scenarios):
                merged = self._scenario_config(raw)
                scenario_id = str(raw.get("scenario_id") or _scenario_id(index, merged))
                if scenario_id in seen:
                    raise ValueError("scenario_id duplicado")
                seen.add(scenario_id)
                kind, value = _primary_input(merged)
                scenarios.append(
                    PipelineScenario(
                        scenario_id=scenario_id,
                        primary_input_kind=kind,
                        primary_input=value,
                        engine=merged.engine,
                        target=merged.target,
                        snapshot=merged.snapshot,
                        strategies={
                            "placement": merged.placement,
                            "routing": merged.routing,
                            "scheduling": merged.scheduling,
                        },
                        runtime_options={
                            "shots": merged.shots,
                            "measurement": merged.measurement,
                            **merged.runtime_options,
                        },
                        render_options=merged.render,
                    )
                )
            return tuple(scenarios)

        kind, value = _primary_input(self.config)
        return (
            PipelineScenario(
                scenario_id=_scenario_id(0, self.config),
                primary_input_kind=kind,
                primary_input=value,
                engine=self.config.engine,
                target=self.config.target,
                snapshot=self.config.snapshot,
                strategies={
                    "placement": self.config.placement,
                    "routing": self.config.routing,
                    "scheduling": self.config.scheduling,
                },
                runtime_options={
                    "shots": self.config.shots,
                    "measurement": self.config.measurement,
                    **self.config.runtime_options,
                },
                render_options=self.config.render,
            ),
        )

    def _scenario_config(self, overrides: dict[str, Any]) -> PipelineExecutionConfig:
        allowed = {
            "data",
            "equation",
            "circuit",
            "input",
            "input_adapter",
            "encoding",
            "metadata",
            "parameters",
            "symbols",
            "engine",
            "target",
            "snapshot",
            "shots",
            "measurement",
            "placement",
            "routing",
            "scheduling",
            "render",
            "runtime_options",
            "scenario_id",
        }
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(f"opcao desconhecida em scenario: {sorted(unknown)}")
        data = {
            field: getattr(self.config, field)
            for field in PipelineExecutionConfig.__dataclass_fields__
            if field not in {"scenarios"}
        }
        data.update({key: value for key, value in overrides.items() if key != "scenario_id"})
        data["scenarios"] = ()
        config = PipelineExecutionConfig(**data)
        config.validate()
        return config

    def _run_scenario(
        self,
        scenario: PipelineScenario,
        *,
        terminal: str,
        engine: str | None = None,
        shots: int | None = None,
        terminal_options: dict[str, Any] | None = None,
    ) -> ScenarioResult:
        state = PipelineState(scenario=scenario)
        state = self._adapt_input(state)
        state = self._maybe_place(state)
        state = self._maybe_route(state)
        state = self._maybe_schedule(state)
        state = self._native_transpile(state, engine=engine or scenario.engine or self.config.engine or "qiskit")
        artifacts = {
            "logical_circuit": state.features.get("logical_circuit"),
            "semantic_ir": state.features.get("semantic_ir"),
            "before_transpile": state.features.get("before_transpile"),
            "after_transpile": state.features.get("after_transpile"),
            "transpilation_record": state.features.get("transpilation_record"),
        }
        if terminal in {"compile", "run_engine"}:
            from quantum_cq._engines.service import default_engine_service

            target_engine = engine or scenario.engine or self.config.engine or "qiskit"
            circuit = state.features.get("after_transpile_circuit") or state.features["logical_circuit"]
            artifact = default_engine_service().compile(
                circuit,
                engine=target_engine,
                measurement=self.config.measurement,
                target=self.config.target,
                **(terminal_options or {}),
            )
            artifacts["compiled_artifact"] = artifact
            state = state.with_feature("compiled_artifact", artifact).with_stage(
                _stage("compile", "completed", requires=("logical_circuit",), provides=("compiled_artifact",))
            )
        if terminal == "run_engine":
            from quantum_cq._engines.service import default_engine_service

            target_engine = engine or scenario.engine or self.config.engine or "qiskit"
            circuit = state.features.get("after_transpile_circuit") or state.features["logical_circuit"]
            result = default_engine_service().run(
                circuit,
                engine=target_engine,
                shots=shots if shots is not None else self.config.shots,
                measurement=self.config.measurement,
                **(terminal_options or {}),
            )
            artifacts["engine_result"] = result
            state = state.with_feature("engine_result", result).with_stage(
                _stage("execute", "completed", requires=("compiled_artifact",), provides=("engine_result",))
            )

        graph = TransformationGraph(scenario.scenario_id, state.transformation_events)
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            status="completed",
            stage_results=state.stage_results,
            snapshots=state.snapshots,
            transformation_graph=graph,
            artifacts={key: value for key, value in artifacts.items() if value is not None},
            diagnostics=state.diagnostics,
            provenance={"terminal": terminal},
        )

    def _adapt_input(self, state: PipelineState) -> PipelineState:
        kind = state.scenario.primary_input_kind
        value = state.scenario.primary_input
        if kind == "equation":
            from quantum_cq._mqt import parse_equation, semantic_program, lower_to_circuit

            ast = parse_equation(str(value))
            semantic = semantic_program(ast, parameters=self.config.parameters, symbols=self.config.symbols)
            circuit = lower_to_circuit(semantic)
            snapshot = _snapshot(state.scenario.scenario_id, "mqt_lower", circuit, "ir")
            state = state.with_feature("ast", ast).with_feature("semantic_ir", semantic).with_feature("logical_circuit", circuit)
            return state.with_stage(
                _stage("mqt_lower", "completed", requires=("equation",), provides=("ast", "semantic_ir", "logical_circuit")),
                snapshots=(snapshot,),
            ).with_feature("before_transpile", snapshot)
        if kind == "circuit":
            if _native_engine(value) not in {None, self.config.engine or "qiskit"}:
                raise ValueError("Circuito nativo restrito a engine de origem; conversao cross-engine rejeitada")
            circuit = _normalize_circuit(value)
            snapshot = _snapshot(state.scenario.scenario_id, "input_adapt", circuit, _format_for(circuit))
            return (
                state.with_feature("logical_circuit", circuit)
                .with_feature("before_transpile", snapshot)
                .with_stage(_stage("input_adapt", "completed", requires=("circuit",), provides=("logical_circuit",)), snapshots=(snapshot,))
            )
        if kind == "input":
            adapter = self.config.input_adapter
            if adapter is None or not adapter.supports(value):
                raise TypeError("Entrada generica requer input_adapter compativel")
            adapted = adapter.adapt(value, self.config)
            circuit = _normalize_circuit(adapted)
            snapshot = _snapshot(state.scenario.scenario_id, "input_adapt", circuit, _format_for(circuit))
            return (
                state.with_feature("logical_circuit", circuit)
                .with_feature("before_transpile", snapshot)
                .with_stage(_stage("input_adapt", "completed", requires=("input",), provides=("logical_circuit",)), snapshots=(snapshot,))
            )
        if kind == "data":
            encoded = _encode_data(value, self.config)
            circuit = _normalize_circuit(encoded)
            snapshot = _snapshot(state.scenario.scenario_id, "encoding", circuit, _format_for(circuit))
            return (
                state.with_feature("encoded", encoded)
                .with_feature("logical_circuit", circuit)
                .with_feature("before_transpile", snapshot)
                .with_stage(_stage("encoding", "completed", requires=("data",), provides=("encoded", "logical_circuit")), snapshots=(snapshot,))
            )
        raise ValueError(f"Entrada primaria nao suportada: {kind}")

    def _maybe_place(self, state: PipelineState) -> PipelineState:
        strategy = state.scenario.strategies.get("placement")
        if strategy is None:
            return state.with_stage(_stage("placement", "not_requested"))
        from quantum_cq._planning import place

        plan = place(state.features["logical_circuit"], target=self.config.target, strategy=strategy)
        return state.with_feature("placement_plan", plan).with_stage(
            _stage("placement", "completed", requires=("logical_circuit",), provides=("placement_plan",))
        )

    def _maybe_route(self, state: PipelineState) -> PipelineState:
        strategy = state.scenario.strategies.get("routing")
        if strategy is None:
            return state.with_stage(_stage("routing", "not_requested"))
        from quantum_cq._planning import route

        route_plan = route(
            state.features["logical_circuit"],
            target=self.config.target,
            placement=state.features.get("placement_plan"),
            strategy=strategy,
        )
        return state.with_feature("routing_plan", route_plan).with_stage(
            _stage("routing", "completed", requires=("logical_circuit",), provides=("routing_plan",))
        )

    def _maybe_schedule(self, state: PipelineState) -> PipelineState:
        strategy = state.scenario.strategies.get("scheduling")
        if strategy is None:
            return state.with_stage(_stage("scheduling", "not_requested"))
        from quantum_cq._planning import schedule

        schedule_plan = schedule(
            state.features["logical_circuit"],
            target=self.config.target,
            strategy=strategy,
        )
        status = "completed" if getattr(schedule_plan, "complete", False) else "insufficient_information"
        return state.with_feature("schedule", schedule_plan).with_stage(
            _stage("scheduling", status, requires=("logical_circuit",), provides=("schedule",) if status == "completed" else ())
        )

    def _native_transpile(self, state: PipelineState, *, engine: str) -> PipelineState:
        from quantum_cq._engines.measurement import measurement_contract_from_ir
        from quantum_cq._engines.registry import get_engine_bundle

        before = state.features.get("before_transpile")
        circuit = state.features["logical_circuit"]
        bundle = get_engine_bundle(engine)
        contract = measurement_contract_from_ir(circuit) if isinstance(circuit, CircuitIR) else None
        emitted = bundle.emitter.emit(circuit, measurement_contract=contract)
        if bundle.transpiler is None:
            transpilation = None
            native_after = emitted
            status = "not_applicable"
            native_metadata = {"native_transpilation": "not_applicable"}
        else:
            transpilation = bundle.transpiler.transpile(
                emitted,
                measurement_contract=contract,
                target=self.config.target,
                policy="allow_native_refinement",
                **self.config.runtime_options,
            )
            native_after = transpilation.after
            status = transpilation.status
            native_metadata = dict(transpilation.native_metadata)
        before_native = _snapshot(
            state.scenario.scenario_id,
            "native_emit",
            emitted,
            type(emitted).__name__,
            engine=engine,
            target=self.config.target,
        )
        after = _snapshot(
            state.scenario.scenario_id,
            "native_transpile",
            native_after,
            type(native_after).__name__,
            engine=engine,
            target=self.config.target,
        )
        event = TransformationEvent(
            event_id=f"{state.scenario.scenario_id}:native_transpile:identity",
            scenario_id=state.scenario.scenario_id,
            stage_id="native_transpile",
            input_snapshot_ids=(before_native.snapshot_id,),
            output_snapshot_ids=(after.snapshot_id,),
            transformation_type="native_transpile",
            changes={"status": status, **native_metadata},
            provenance={"engine": engine, "analysis_snapshot": None if before is None else before.snapshot_id},
        )
        record = {
            "neutral_stages": [
                result.stage_id
                for result in state.stage_results
                if result.stage_id in {"mqt_lower", "placement", "routing", "scheduling"}
            ],
            "native_stage": "native_transpile",
            "engine": engine,
            "target_usage": "analysis" if self.config.target is not None else "none",
            "options": {},
            "snapshots": [snapshot.snapshot_id for snapshot in (before, before_native, after) if snapshot is not None],
            "transformations": [event.event_id],
            "metrics": {} if transpilation is None else dict(transpilation.metrics),
            "status": status,
        }
        return (
            state.with_feature("after_transpile", after)
            .with_feature("after_transpile_circuit", native_after if engine == "qiskit" else circuit)
            .with_feature("transpilation_record", record)
            .with_stage(
                _stage("native_transpile", record["status"], requires=("logical_circuit",), provides=("after_transpile",)),
                snapshots=(before_native, after),
                events=(event,),
            )
        )


def legacy_build(config: PipelineExecutionConfig) -> EncodedCircuit:
    config.validate(terminal="legacy")
    if config.data is None:
        raise ValueError("CQ.pipeline requer dados antes de build")
    return _encode_data(config.data, config)


def _encode_data(value: Any, config: PipelineExecutionConfig) -> EncodedCircuit:
    data = value if isinstance(value, QuantumData) else QuantumData(value, metadata=config.metadata)
    registry = config.registry
    if config.encoding is not None and config.encoding != "auto":
        encoder = registry.get(config.encoding)
        if not encoder.can_handle(data):
            raise ValueError(f"Encoding '{config.encoding}' nao pode lidar com os dados informados")
        return encoder.encode(data)
    selector = config.selector or EncodingSelector(registry)
    return selector.select(data).encode(data)


def _primary_input(config: PipelineExecutionConfig) -> tuple[str, Any]:
    primaries = config.primary_inputs()
    if len(primaries) != 1:
        config.validate()
    return next(iter(primaries.items()))


def _scenario_id(index: int, config: PipelineExecutionConfig) -> str:
    payload = {
        "index": index,
        "primary": sorted(config.primary_inputs()),
        "engine": config.engine,
        "target": _target_id(config.target),
        "measurement": config.measurement,
        "shots": config.shots,
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:8]
    return f"scenario-{index:03d}-{digest}"


def _normalize_circuit(value: Any) -> Any:
    if isinstance(value, LogicalCircuitBuilder):
        return value.build()
    if isinstance(value, CircuitIR):
        return value
    if isinstance(value, EncodedCircuit):
        return value.circuit
    if hasattr(value, "circuit") and getattr(value, "circuit_format", None) == "ir":
        return value.circuit
    return value


def _native_engine(value: Any) -> str | None:
    module = type(value).__module__.split(".")[0]
    if module == "qiskit":
        return "qiskit"
    if module == "cirq":
        return "cirq"
    if module == "braket":
        return "braket"
    return None


def _format_for(circuit: Any) -> str:
    if isinstance(circuit, CircuitIR):
        return "ir"
    return type(circuit).__name__


def _snapshot(
    scenario_id: str,
    stage_id: str,
    circuit: Any,
    fmt: str,
    *,
    engine: str | None = None,
    target: Any = None,
) -> CircuitSnapshot:
    metrics = _circuit_metrics(circuit, stage_id=stage_id, scenario_id=scenario_id)
    digest = hashlib.sha1(
        json.dumps(_circuit_descriptor(circuit), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:10]
    return CircuitSnapshot(
        snapshot_id=f"{scenario_id}:{stage_id}:{digest}",
        scenario_id=scenario_id,
        stage_id=stage_id,
        format=fmt,
        circuit=circuit,
        engine=engine,
        target=_target_id(target),
        metrics=metrics,
        provenance={"created_at": datetime.now(timezone.utc).isoformat()},
    )


def _stage(
    stage_id: str,
    status: str,
    *,
    requires: tuple[str, ...] = (),
    provides: tuple[str, ...] = (),
    diagnostics: tuple[PipelineDiagnostic, ...] = (),
    metrics: dict[str, MetricValue] | None = None,
    provenance: dict[str, Any] | None = None,
) -> StageResult:
    now = datetime.now(timezone.utc)
    return StageResult(
        stage_id=stage_id,
        status=status,
        started_at=now,
        finished_at=now,
        requires=requires,
        provides=provides,
        diagnostics=diagnostics,
        metrics=metrics or {},
        provenance=provenance or {},
    )


def _circuit_metrics(circuit: Any, *, stage_id: str, scenario_id: str) -> dict[str, MetricValue]:
    if isinstance(circuit, CircuitIR):
        size = sum(len(layer.operations) for layer in circuit.layers) + len(circuit.outputs)
        return {
            "size": MetricValue(size, unit="operations", stage=stage_id, scenario=scenario_id),
            "depth": MetricValue(len(circuit.layers), unit="layers", stage=stage_id, scenario=scenario_id),
            "qubits": MetricValue(circuit.n_qubits, unit="qubits", stage=stage_id, scenario=scenario_id),
        }
    size = getattr(circuit, "size", None)
    depth = getattr(circuit, "depth", None)
    metrics: dict[str, MetricValue] = {}
    if callable(size):
        metrics["size"] = MetricValue(size(), unit="operations", stage=stage_id, scenario=scenario_id)
    if callable(depth):
        metrics["depth"] = MetricValue(depth(), unit="layers", stage=stage_id, scenario=scenario_id)
    return metrics


def _circuit_descriptor(circuit: Any) -> dict[str, Any]:
    if isinstance(circuit, CircuitIR):
        return {
            "type": "CircuitIR",
            "name": circuit.name,
            "n_qubits": circuit.n_qubits,
            "n_clbits": circuit.n_clbits,
            "layers": [
                [
                    {
                        "kind": op.kind,
                        "qubits": list(op.qubits),
                        "clbits": list(op.clbits),
                        "label": op.label,
                    }
                    for op in layer.operations
                ]
                for layer in circuit.layers
            ],
            "outputs": [
                {"kind": op.kind, "qubits": list(op.qubits), "clbits": list(op.clbits)}
                for op in circuit.outputs
            ],
        }
    return {
        "type": type(circuit).__name__,
        "module": type(circuit).__module__,
        "name": getattr(circuit, "name", None),
        "num_qubits": getattr(circuit, "num_qubits", None),
        "num_clbits": getattr(circuit, "num_clbits", None),
    }


def _artifact_payload(artifacts: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in artifacts.items():
        if isinstance(value, CircuitSnapshot):
            payload[key] = value.descriptor()
        elif isinstance(value, CircuitIR):
            payload[key] = _circuit_descriptor(value)
        elif isinstance(value, CompiledArtifact):
            payload[key] = {
                "engine": value.engine,
                "options": _json_safe(dict(value.options)),
                "metadata": _json_safe(dict(value.metadata)),
                "target_fingerprint": value.target_fingerprint,
                "measurement_contract": _json_safe(
                    value.measurement_contract.to_metadata()
                    if value.measurement_contract is not None
                    else None
                ),
                "native_compiled": _circuit_descriptor(value.native_compiled),
            }
        elif isinstance(value, EngineResult):
            payload[key] = {
                "engine": value.engine,
                "counts": _json_safe(dict(value.counts) if value.counts is not None else None),
                "metadata": _json_safe(dict(value.metadata)),
                "canonical_bit_order": list(value.canonical_bit_order),
                "normalized": value.normalized,
                "target_usage": value.target_usage,
            }
        else:
            payload[key] = _json_safe(value)
    return payload


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, MetricValue):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    return {
        "type": type(value).__name__,
        "module": type(value).__module__,
    }


def _target_id(target: Any) -> str | None:
    if target is None:
        return None
    descriptor = getattr(target, "descriptor", None)
    if descriptor is not None:
        return getattr(descriptor, "target_id", None)
    return getattr(target, "target_id", None)


def canonical_gate_name(name: str) -> str:
    return name.strip().lower()


def operation_for_gate(name: str, qubits: tuple[int, ...], params: dict[str, Any] | None = None) -> Operation:
    kind = canonical_gate_name(name)
    params = dict(params or {})
    if kind in {"h", "x", "y", "z", "s", "t"}:
        return Operation(kind, qubits=qubits)
    if kind in {"rx", "ry", "rz", "p"}:
        return Operation(kind, qubits=qubits, params={"theta": params["theta"]})
    if kind == "cx":
        return Operation("cx", qubits=qubits, params={"control": qubits[0], "target": qubits[1]})
    if kind == "cz":
        return Operation("cz", qubits=qubits, params={"control": qubits[0], "target": qubits[1]})
    if kind == "cp":
        return Operation("cp", qubits=qubits, params={"theta": params["theta"], "control": qubits[0], "target": qubits[1]})
    if kind == "swap":
        return Operation("swap", qubits=qubits, params={"left": qubits[0], "right": qubits[1]})
    raise ValueError(f"Operador MQT nao suportado: {name}")


def basis_inputs(bitstring: str) -> list[QuantumState]:
    return [
        QuantumState("ket", bit, (index,))
        for index, bit in enumerate(bitstring)
        if bit in {"0", "1"}
    ]


def parse_qubit_token(token: str) -> int:
    match = re.fullmatch(r"q(\d+)", token.strip())
    if not match:
        raise ValueError(f"Qubit invalido: {token}")
    return int(match.group(1))


def parse_clbit_token(token: str) -> int:
    token = token.strip()
    if token.startswith("c"):
        token = token[1:]
    if not token.isdigit():
        raise ValueError(f"Clbit invalido: {token}")
    return int(token)
