"""Facade principal do pacote quantum_cq."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from numbers import Real
from typing import Any

from quantum_cq._core.data import QuantumData
from quantum_cq._core.handlers import (
    AlgorithmRegistry,
    EncodingRegistry,
    HandlerRegistry,
    NavigationRegistry,
    OperatorRegistry,
    OracleRegistry,
    PrimitiveRegistry,
    default_algorithm_registry,
    default_encoding_registry,
    default_navigation_registry,
    default_operator_registry,
    default_oracle_registry,
    default_primitive_registry,
)
from quantum_cq._core.interfaces import EncodingProtocol
from quantum_cq._core.metrics import MetricsCollector
from quantum_cq._core.results import EncodedCircuit
from quantum_cq._runtime.runtime import IBMRuntimeConfig
from quantum_cq._core.selectors import EncodingSelectionContext, EncodingSelector
from quantum_cq._runtime.unified import PipelineCore, PipelineExecutionConfig, legacy_build


class _CQPipelineBuilder:
    def __init__(
        self,
        *,
        registry: HandlerRegistry[EncodingProtocol] | None = None,
        selector: Any = None,
    ) -> None:
        self.registry = registry or default_encoding_registry()
        self.selector = selector
        self._data: QuantumData | None = None
        self._raw_data: Any = None
        self._encoding_name: str | None = None
        self._auto = True
        self._equation: str | None = None
        self._parameters: dict[str, Any] = {}
        self._symbols: dict[str, Any] = {}
        self._circuit: Any = None
        self._input: Any = None
        self._input_adapter: Any = None
        self._engine: str | None = None
        self._target: Any = None
        self._snapshot: Any = None
        self._shots = 1024
        self._measurement = "auto"
        self._placement: str | None = None
        self._routing: str | None = None
        self._scheduling: str | None = None
        self._native_transpilation_policy = "allow_native_refinement"
        self._stages: tuple[str, ...] = ()
        self._stop_after: str | None = None
        self._scenarios: tuple[dict[str, Any], ...] = ()
        self._render: dict[str, Any] = {}
        self._runtime_options: dict[str, Any] = {}

    def with_data(self, value: Any, metadata: dict[str, Any] | None = None) -> "_CQPipelineBuilder":
        if isinstance(value, QuantumData):
            merged = dict(value.metadata)
            if metadata:
                merged.update(metadata)
            self._data = QuantumData(value.value, metadata=merged)
            self._raw_data = value.value
            return self

        self._data = QuantumData(value, metadata=metadata or {})
        self._raw_data = value
        return self

    def with_encoding(self, name: str) -> "_CQPipelineBuilder":
        self._encoding_name = name
        self._auto = False
        return self

    def auto_encoding(self) -> "_CQPipelineBuilder":
        self._encoding_name = None
        self._auto = True
        return self

    def with_metadata(self, **metadata: Any) -> "_CQPipelineBuilder":
        if self._data is None:
            self._data = QuantumData(None, metadata=metadata)
            return self

        merged = dict(self._data.metadata)
        merged.update(metadata)
        self._data = QuantumData(self._data.value, metadata=merged)
        return self

    def with_equation(
        self,
        equation: str,
        *,
        parameters: dict[str, Any] | None = None,
        symbols: dict[str, Any] | None = None,
    ) -> "_CQPipelineBuilder":
        self._equation = equation
        if parameters:
            self._parameters.update(parameters)
        if symbols:
            self._symbols.update(symbols)
        return self

    def with_parameters(self, **parameters: Any) -> "_CQPipelineBuilder":
        self._parameters.update(parameters)
        return self

    def with_symbols(self, **symbols: Any) -> "_CQPipelineBuilder":
        self._symbols.update(symbols)
        return self

    def with_circuit(self, circuit: Any) -> "_CQPipelineBuilder":
        self._circuit = circuit
        return self

    def with_input(self, value: Any, *, adapter: Any) -> "_CQPipelineBuilder":
        self._input = value
        self._input_adapter = adapter
        return self

    def with_engine(self, engine: str) -> "_CQPipelineBuilder":
        self._engine = engine
        return self

    def with_target(self, target: Any, *, snapshot: Any = None) -> "_CQPipelineBuilder":
        self._target = target
        self._snapshot = snapshot
        return self

    def with_runtime(
        self,
        *,
        shots: int | None = None,
        measurement: str | None = None,
        **options: Any,
    ) -> "_CQPipelineBuilder":
        if shots is not None:
            self._shots = int(shots)
        if measurement is not None:
            self._measurement = measurement
        self._runtime_options.update(options)
        return self

    def with_strategy(
        self,
        *,
        placement: str | None = None,
        routing: str | None = None,
        scheduling: str | None = None,
        native_transpilation_policy: str | None = None,
    ) -> "_CQPipelineBuilder":
        self._placement = placement
        self._routing = routing
        self._scheduling = scheduling
        if native_transpilation_policy is not None:
            self._native_transpilation_policy = native_transpilation_policy
        return self

    def with_stages(self, *stages: str, stop_after: str | None = None) -> "_CQPipelineBuilder":
        self._stages = tuple(stages)
        self._stop_after = stop_after
        return self

    def with_scenarios(self, scenarios: Sequence[dict[str, Any]]) -> "_CQPipelineBuilder":
        self._scenarios = tuple(dict(item) for item in scenarios)
        return self

    def build(self) -> EncodedCircuit:
        config = self._config()
        if config.is_legacy_encoding_flow:
            return legacy_build(config)
        from quantum_cq._runtime.experiment import PipelineResult

        return PipelineResult(scenario_results=PipelineCore(config).transpile())

    def run(self) -> Any:
        return self.build()

    def transpile(self) -> PipelineResult:
        config = self._config()
        from quantum_cq._runtime.experiment import PipelineResult

        return PipelineResult(scenario_results=PipelineCore(config).transpile())

    def compile(self, *, engine: str | None = None, **options: Any) -> PipelineResult:
        config = self._config()
        from quantum_cq._runtime.experiment import PipelineResult

        return PipelineResult(scenario_results=PipelineCore(config).compile(engine=engine, **options))

    def run_engine(
        self,
        *,
        engine: str | None = None,
        shots: int | None = None,
        **options: Any,
    ) -> PipelineResult:
        config = self._config()
        from quantum_cq._runtime.experiment import PipelineResult

        return PipelineResult(
            scenario_results=PipelineCore(config).run_engine(
                engine=engine,
                shots=shots,
                **options,
            )
        )

    def _build_manual(self, data: QuantumData, name: str) -> EncodedCircuit:
        encoder = self.registry.get(name)
        if not encoder.can_handle(data):
            raise ValueError(f"Encoding '{name}' nao pode lidar com os dados informados")

        return encoder.encode(data)

    def _selector(self) -> Any:
        if self.selector is not None:
            return self.selector

        return EncodingSelector(self.registry)

    def _config(self) -> PipelineExecutionConfig:
        return PipelineExecutionConfig(
            data=None if self._data is None else self._data.value,
            equation=self._equation,
            circuit=self._circuit,
            input=self._input,
            input_adapter=self._input_adapter,
            encoding=None if self._auto else self._encoding_name,
            registry=self.registry,
            selector=self.selector,
            metadata={} if self._data is None else dict(self._data.metadata),
            parameters=self._parameters,
            symbols=self._symbols,
            engine=self._engine,
            target=self._target,
            snapshot=self._snapshot,
            shots=self._shots,
            measurement=self._measurement,
            placement=self._placement,
            routing=self._routing,
            scheduling=self._scheduling,
            native_transpilation_policy=self._native_transpilation_policy,
            stages=self._stages,
            stop_after=self._stop_after,
            scenarios=self._scenarios,
            render=self._render,
            runtime_options=self._runtime_options,
        )


class CQ:
    """Facade simples para encoding."""

    @staticmethod
    def pipeline(
        data: Any = None,
        *,
        encoding: str | None = None,
        equation: str | None = None,
        parameters: dict[str, Any] | None = None,
        symbols: dict[str, Any] | None = None,
        circuit: Any = None,
        input: Any = None,
        input_adapter: Any = None,
        engine: str | None = None,
        target: Any = None,
        snapshot: Any = None,
        shots: int = 1024,
        measurement: str = "auto",
        placement: str | None = None,
        routing: str | None = None,
        scheduling: str | None = None,
        native_transpilation_policy: str = "allow_native_refinement",
        stages: Sequence[str] | None = None,
        stop_after: str | None = None,
        scenarios: Sequence[dict[str, Any]] | None = None,
        render: dict[str, Any] | None = None,
        registry: HandlerRegistry[EncodingProtocol] | None = None,
        selector: Any = None,
        metadata: dict[str, Any] | None = None,
        runtime_options: dict[str, Any] | None = None,
        **unknown_options: Any,
    ) -> _CQPipelineBuilder:
        if unknown_options:
            names = ", ".join(sorted(unknown_options))
            raise ValueError(f"opcao desconhecida para CQ.pipeline: {names}")
        builder = _CQPipelineBuilder(registry=registry, selector=selector)
        if data is not None:
            builder.with_data(data, metadata=metadata)
        if encoding is not None:
            if encoding == "auto":
                builder.auto_encoding()
            else:
                builder.with_encoding(encoding)
        if equation is not None:
            builder.with_equation(
                equation,
                parameters=parameters,
                symbols=symbols,
            )
        elif parameters:
            builder.with_parameters(**parameters)
        if symbols and equation is None:
            builder.with_symbols(**symbols)
        if circuit is not None:
            builder.with_circuit(circuit)
        if input is not None:
            if input_adapter is None:
                builder._input = input
            else:
                builder.with_input(input, adapter=input_adapter)
        elif input_adapter is not None:
            builder._input_adapter = input_adapter
        if engine is not None:
            builder.with_engine(engine)
        if target is not None:
            builder.with_target(target, snapshot=snapshot)
        builder.with_runtime(shots=shots, measurement=measurement, **(runtime_options or {}))
        builder.with_strategy(
            placement=placement,
            routing=routing,
            scheduling=scheduling,
            native_transpilation_policy=native_transpilation_policy,
        )
        if stages is not None or stop_after is not None:
            builder.with_stages(*(tuple(stages or ())), stop_after=stop_after)
        if scenarios is not None:
            builder.with_scenarios(scenarios)
        if render is not None:
            builder._render = dict(render)
        builder._config().validate(terminal="legacy" if data is None and equation is None and circuit is None and input is None else None)
        return builder

    @staticmethod
    def state(data: Any, encoding: str = "auto", **kwargs: Any) -> EncodedCircuit:
        if encoding == "auto":
            return CQ.encode(data, **kwargs)

        return CQ.encode(data, encoding=encoding, **kwargs)

    @staticmethod
    def encode(
        data: Any,
        *,
        encoding: str | None = None,
        metadata: dict[str, Any] | None = None,
        registry: HandlerRegistry[EncodingProtocol] | None = None,
        navigation_registry: NavigationRegistry | None = None,
        circuit_factory: Any = None,
        engine: str | None = None,
        quantum_engine: str | None = None,
        role: str = "state",
        **kwargs: Any,
    ) -> Any:
        normalized_role = "state" if role == "input" else role
        if normalized_role == "navigation":
            if engine is not None and "engine" not in kwargs:
                kwargs["engine"] = engine
            return CQ._encode_navigation(
                data,
                encoding=encoding,
                metadata=metadata,
                registry=navigation_registry,
                circuit_factory=CQ._component_circuit_factory(quantum_engine, circuit_factory),
                **kwargs,
            )
        if normalized_role in {"oracle", "operator"}:
            raise NotImplementedError(f"Encoding para role='{normalized_role}' ainda nao implementado")
        if normalized_role != "state":
            raise ValueError(f"Role de encoding invalido: {role}")

        selected_factory = CQ._component_circuit_factory(engine or quantum_engine, circuit_factory)
        resolved_registry = registry or default_encoding_registry(circuit_factory=selected_factory)
        builder = CQ.pipeline(registry=resolved_registry).with_data(data, metadata=metadata)
        if encoding is None:
            return builder.auto_encoding().build()

        return builder.with_encoding(encoding).build()

    @staticmethod
    def _encode_navigation(
        data: Any,
        *,
        encoding: str | None,
        metadata: dict[str, Any] | None,
        registry: NavigationRegistry | None,
        circuit_factory: Any = None,
        **kwargs: Any,
    ) -> Any:
        resolved = registry or default_navigation_registry(circuit_factory=circuit_factory)
        if encoding is not None:
            encoder = resolved.get(encoding)
            if not encoder.can_handle(data):
                raise ValueError(f"Encoding '{encoding}' nao pode lidar com os dados informados")
            return encoder.encode(data, **kwargs)

        selector = EncodingSelector(
            default_encoding_registry(),
            navigation_encoders=resolved,
        )
        context = EncodingSelectionContext(data=data, metadata=metadata or {}, role="navigation")
        encoder = selector.select(data, context=context)
        return encoder.encode(data, **kwargs)

    @staticmethod
    def auto_encode(
        data: Any,
        metadata: dict[str, Any] | None = None,
        *,
        registry: HandlerRegistry[EncodingProtocol] | None = None,
        selector: Any = None,
    ) -> EncodedCircuit:
        return (
            CQ.pipeline(registry=registry, selector=selector)
            .with_data(data, metadata=metadata)
            .auto_encoding()
            .build()
        )

    @staticmethod
    def nav(values_or_memory: Any, engine: str = "explicit", **kwargs: Any) -> Any:
        memory = values_or_memory
        from quantum_cq._navigation.memory import AddressedMemory

        if not isinstance(memory, AddressedMemory):
            memory = CQ.memory(values_or_memory)

        return CQ.encode(
            memory,
            role="navigation",
            encoding="addressed_memory",
            engine=CQ._normalize_navigation_engine(engine),
            **kwargs,
        )

    @staticmethod
    def addressed(values_or_memory: Any, engine: str = "explicit", **kwargs: Any) -> Any:
        return CQ.nav(values_or_memory, engine=engine, **kwargs)

    @staticmethod
    def graph_nav(graph: Any, engine: str = "explicit", **kwargs: Any) -> Any:
        return CQ.encode(
            graph,
            role="navigation",
            encoding="graph_navigation",
            engine=CQ._normalize_navigation_engine(engine),
            **kwargs,
        )

    @staticmethod
    def walk(graph: Any, steps: int = 1, **kwargs: Any) -> Any:
        return CQ.primitive("coined_quantum_walk").build(graph, steps=steps, **kwargs)

    @staticmethod
    def deutsch(case: int = 1, **kwargs: Any) -> Any:
        engine = kwargs.pop("engine", None)
        build_format = CQ._build_format_for_engine(engine, kwargs.pop("format", None))
        return CQ.algorithm("deutsch", engine=engine).with_case(case).build(format=build_format, **kwargs)

    @staticmethod
    def bv(secret: str, **kwargs: Any) -> Any:
        return CQ.algorithm("bernstein_vazirani").with_secret(secret).build(**kwargs)

    @staticmethod
    def dj(
        kind: str = "balanced",
        *,
        qubits: int | None = None,
        num_qubits: int | None = None,
        **kwargs: Any,
    ) -> Any:
        resolved = CQ._resolve_alias_pair(
            "qubits",
            qubits,
            "num_qubits",
            num_qubits,
            default=2,
        )
        return CQ.algorithm("deutsch_jozsa").with_num_qubits(resolved).with_kind(kind).build(**kwargs)

    @staticmethod
    def grover(marked_state: str, iterations: int | None = None, **kwargs: Any) -> Any:
        builder = CQ.algorithm("grover").with_marked_state(marked_state)
        if iterations is not None:
            builder.with_iterations(iterations)
        return builder.build(**kwargs)

    @staticmethod
    def qpe(phase: float, precision: int, **kwargs: Any) -> Any:
        return CQ.algorithm("qpe").with_phase(phase).with_precision(precision).build(**kwargs)

    @staticmethod
    def qft(num_qubits: int, **kwargs: Any) -> Any:
        return CQ.primitive("qft").build(num_qubits, **kwargs)

    @staticmethod
    def iqft(num_qubits: int, **kwargs: Any) -> Any:
        return CQ.primitive("inverse_qft").build(num_qubits, **kwargs)

    @staticmethod
    def diffuser(num_qubits: int, **kwargs: Any) -> Any:
        engine = kwargs.pop("engine", None)
        build_format = CQ._build_format_for_engine(engine, kwargs.pop("format", None))
        return CQ.primitive("standard_diffuser", engine=engine).build(num_qubits, format=build_format, **kwargs)

    @staticmethod
    def phase_rotation(phase: float, **kwargs: Any) -> Any:
        engine = kwargs.pop("engine", None)
        build_format = CQ._build_format_for_engine(engine, kwargs.pop("format", None))
        return CQ.operator("phase_rotation", engine=engine).with_phase(phase).build(format=build_format, **kwargs)

    @staticmethod
    def available_encodings(
        registry: HandlerRegistry[EncodingProtocol] | None = None,
    ) -> list[str]:
        return (registry or default_encoding_registry()).names()

    @staticmethod
    def default_encoding_registry(circuit_factory: Any = None) -> EncodingRegistry:
        return default_encoding_registry(circuit_factory=circuit_factory)

    @staticmethod
    def algorithm(
        name: str,
        *,
        registry: AlgorithmRegistry | None = None,
        circuit_factory: Any = None,
        engine: str | None = None,
        oracle_registry: OracleRegistry | None = None,
    ) -> Any:
        circuit_factory = CQ._component_circuit_factory(engine, circuit_factory)
        resolved = registry or default_algorithm_registry(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        )
        return resolved.get(name)

    @staticmethod
    def available_algorithms(registry: AlgorithmRegistry | None = None) -> list[str]:
        return (registry or default_algorithm_registry()).names()

    @staticmethod
    def available_oracles(registry: OracleRegistry | None = None) -> list[str]:
        return (registry or default_oracle_registry()).names()

    @staticmethod
    def oracle(
        name: str,
        *args: Any,
        registry: OracleRegistry | None = None,
        circuit_factory: Any = None,
        engine: str | None = None,
        **kwargs: Any,
    ) -> Any:
        circuit_factory = CQ._component_circuit_factory(engine, circuit_factory)
        resolved = registry or default_oracle_registry(circuit_factory=circuit_factory)
        try:
            if hasattr(resolved, "create"):
                return resolved.create(name, *args, **kwargs)
            if args or kwargs:
                raise TypeError("OracleRegistry informado nao aceita argumentos de construcao")
            return resolved.get(name)
        except KeyError as exc:
            raise KeyError(f"Oracle '{name}' nao registrado") from exc
        except TypeError as exc:
            raise TypeError(f"Argumentos invalidos para oracle '{name}': {exc}") from exc

    @staticmethod
    def available_primitives(registry: PrimitiveRegistry | None = None) -> list[str]:
        return (registry or default_primitive_registry()).names()

    @staticmethod
    def available_operators(registry: OperatorRegistry | None = None) -> list[str]:
        return (registry or default_operator_registry()).names()

    @staticmethod
    def available_navigation_encodings(registry: NavigationRegistry | None = None) -> list[str]:
        return (registry or default_navigation_registry()).names()

    @staticmethod
    def catalog(
        *,
        category: str | None = None,
        status: str | None = None,
        name: str | None = None,
        engine: str | None = None,
    ) -> tuple[Any, ...]:
        from quantum_cq._core.components import ComponentService
        from quantum_cq._engines.service import default_engine_service

        engine_service = default_engine_service()
        return ComponentService(
            capability_resolver=engine_service.capability_model,
        ).catalog(
            category=category,
            status=status,
            name=name,
            engine=engine,
        )

    @staticmethod
    def circuit(
        qubits: int,
        clbits: int = 0,
        *,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        from quantum_cq._circuits.compact import LogicalCircuitBuilder

        return LogicalCircuitBuilder(qubits, clbits, name=name, metadata=metadata)

    @staticmethod
    def unitary(
        matrix: Any,
        *,
        name: str | None = None,
        validate: bool = True,
        atol: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        from quantum_cq._circuits.unitary import create_unitary

        return create_unitary(
            matrix,
            name=name,
            validate=validate,
            atol=atol,
            metadata=metadata,
        )

    @staticmethod
    def compatibility(
        circuit_like: Any,
        *,
        engine: str | None = None,
        target: Any = None,
    ) -> Any:
        from quantum_cq._engines.service import default_engine_service

        return default_engine_service().compatibility(
            circuit_like,
            engine=engine or "qiskit",
            target=target,
        )

    @staticmethod
    def manual_target(
        *,
        target_id: str,
        qubits: int | tuple[str, ...],
        operations: tuple[Any, ...] | list[Any],
        target_type: str,
        name: str | None = None,
        provider: str = "manual",
        aliases: tuple[str, ...] = (),
        topology: tuple[Any, ...] = (),
        snapshot: Any = None,
        provenance: Any = None,
        paradigm: str = "gate_model",
    ) -> Any:
        from quantum_cq._hardware.service import default_hardware_service

        return default_hardware_service().manual_target(
            target_id=target_id,
            qubits=qubits,
            operations=operations,
            target_type=target_type,  # type: ignore[arg-type]
            name=name,
            provider=provider,
            aliases=aliases,
            topology=topology,
            snapshot=snapshot,
            provenance=provenance,
            paradigm=paradigm,
        )

    @staticmethod
    def target_from_qiskit(target_like: Any, *, name: str | None = None) -> Any:
        from quantum_cq._hardware.providers.qiskit import target_from_qiskit

        return target_from_qiskit(target_like, name=name)

    @staticmethod
    def primitive(
        name: str,
        *,
        registry: PrimitiveRegistry | None = None,
        circuit_factory: Any = None,
        engine: str | None = None,
    ) -> Any:
        circuit_factory = CQ._component_circuit_factory(engine, circuit_factory)
        resolved = registry or default_primitive_registry(circuit_factory=circuit_factory)
        return resolved.get(name)

    @staticmethod
    def operator(
        name: str,
        *,
        registry: OperatorRegistry | None = None,
        circuit_factory: Any = None,
        engine: str | None = None,
    ) -> Any:
        circuit_factory = CQ._component_circuit_factory(engine, circuit_factory)
        resolved = registry or default_operator_registry(circuit_factory=circuit_factory)
        return resolved.get(name)

    @staticmethod
    def navigation(
        name: str,
        *,
        registry: NavigationRegistry | None = None,
        circuit_factory: Any = None,
        quantum_engine: str | None = None,
    ) -> Any:
        circuit_factory = CQ._component_circuit_factory(quantum_engine, circuit_factory)
        resolved = registry or default_navigation_registry(circuit_factory=circuit_factory)
        return resolved.get(name)

    @staticmethod
    def memory(values: Any, **kwargs: Any) -> Any:
        from quantum_cq._navigation.memory import AddressedMemory

        return AddressedMemory(values, **kwargs)

    @staticmethod
    def graph(
        edges: Any = None,
        *,
        vertices: int | None = None,
        num_vertices: int | None = None,
        directed: bool = False,
        **kwargs: Any,
    ) -> Any:
        from quantum_cq._navigation.memory import GraphData

        if vertices is not None and num_vertices is not None and vertices != num_vertices:
            raise ValueError("vertices e num_vertices devem ser iguais quando ambos forem informados")

        resolved_vertices = num_vertices if num_vertices is not None else vertices
        if edges is None:
            edges = []

        if resolved_vertices is None:
            edge_list = list(edges)
            if not edge_list:
                raise ValueError("num_vertices deve ser informado para grafos sem arestas")
            resolved_vertices = max(max(left, right) for left, right in edge_list) + 1
            edges = edge_list
        return GraphData(edges=edges, num_vertices=resolved_vertices, directed=directed, **kwargs)

    @staticmethod
    def default_algorithm_registry(
        circuit_factory: Any = None,
        oracle_registry: OracleRegistry | None = None,
    ) -> AlgorithmRegistry:
        return default_algorithm_registry(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        )

    @staticmethod
    def default_oracle_registry() -> OracleRegistry:
        return default_oracle_registry()

    @staticmethod
    def default_primitive_registry(circuit_factory: Any = None) -> PrimitiveRegistry:
        return default_primitive_registry(circuit_factory=circuit_factory)

    @staticmethod
    def default_operator_registry(circuit_factory: Any = None) -> OperatorRegistry:
        return default_operator_registry(circuit_factory=circuit_factory)

    @staticmethod
    def default_navigation_registry(circuit_factory: Any = None) -> NavigationRegistry:
        return default_navigation_registry(circuit_factory=circuit_factory)

    @staticmethod
    def metrics(circuit_or_result: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        return MetricsCollector().collect(circuit_or_result, extra=extra)

    @staticmethod
    def draw(
        obj: Any,
        *,
        decompose: bool = False,
        reps: int = 1,
        idle_wires: bool = True,
        scale: float = 0.75,
        output: str = "mpl",
        fold: int = -1,
    ) -> Any:
        circuit = CQ.to_qiskit(obj)
        if decompose:
            circuit = circuit.decompose(reps=reps)

        try:
            return circuit.draw(
                output=output,
                idle_wires=idle_wires,
                scale=scale,
                fold=fold,
            )
        except Exception:
            try:
                return circuit.draw(output="text", idle_wires=idle_wires, fold=fold)
            except Exception:
                return (
                    f"QuantumCircuit(num_qubits={circuit.num_qubits}, "
                    f"num_clbits={circuit.num_clbits}, depth={circuit.depth()}, "
                    f"size={circuit.size()})"
                )

    @staticmethod
    def describe(obj: Any) -> str:
        circuit = CQ.to_qiskit(obj)
        metrics = CQ.metrics(obj)
        metadata = dict(getattr(obj, "metadata", {}) or {})
        circuit_format = getattr(obj, "circuit_format", metadata.get("circuit_format", "qiskit"))
        selected_metadata = {
            key: metadata[key]
            for key in (
                "algorithm_name",
                "encoding_name",
                "operator_name",
                "oracle_name",
                "navigation_name",
                "family",
                "role",
                "status",
            )
            if key in metadata
        }
        lines = [
            f"type: {type(obj).__name__}",
            f"circuit_format: {circuit_format}",
            f"num_qubits: {circuit.num_qubits}",
            f"num_clbits: {circuit.num_clbits}",
            f"depth: {metrics.get('depth')}",
            f"size: {metrics.get('size')}",
            f"count_ops: {metrics.get('count_ops')}",
            f"metadata: {selected_metadata}",
        ]
        description = "\n".join(lines)
        print(description)
        return description

    @staticmethod
    def show(
        obj: Any,
        *,
        draw: bool = True,
        metrics: bool = True,
        metadata: bool = True,
        decompose: bool = False,
        reps: int = 1,
        idle_wires: bool = True,
        scale: float = 0.75,
        output: str = "mpl",
    ) -> None:
        _ = metrics, metadata
        CQ.describe(obj)
        if draw:
            drawing = CQ.draw(
                obj,
                decompose=decompose,
                reps=reps,
                idle_wires=idle_wires,
                scale=scale,
                output=output,
            )
            try:
                from IPython.display import display

                display(drawing)
            except Exception:
                text = str(drawing)
                encoding = sys.stdout.encoding or "utf-8"
                print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))
        return None

    @staticmethod
    def notebook_logs(level: int | str = "INFO") -> None:
        from quantum_cq._core.logging_config import configure_logging

        configure_logging(level=level)

    @staticmethod
    def from_qc(qc: Any) -> Any:
        from quantum_cq._circuits.compact import QC

        if not isinstance(qc, QC):
            raise TypeError("CQ.from_qc espera um objeto QC")

        return qc

    @staticmethod
    def to_qiskit(circuit_like: Any) -> Any:
        from quantum_cq._circuits.adapters import export_to_qiskit

        return export_to_qiskit(circuit_like)

    @staticmethod
    def export(circuit_like: Any, *, target: str = "qiskit") -> Any:
        normalized_target = target.lower()
        if normalized_target == "qiskit":
            return CQ.to_qiskit(circuit_like)

        if normalized_target in {"mqt", "openqasm"}:
            raise NotImplementedError(f"Exportador '{normalized_target}' planejado para run futura")

        raise ValueError(f"Target de exportacao invalido: {target}")

    @staticmethod
    def available_exporters() -> list[str]:
        return ["qiskit"]

    @staticmethod
    def engines() -> list[dict[str, Any]]:
        from quantum_cq._engines.service import default_engine_service

        return default_engine_service().engines()

    @staticmethod
    def engine_capabilities(engine: str) -> dict[str, Any]:
        from quantum_cq._engines.service import default_engine_service

        return default_engine_service().capabilities(engine)

    @staticmethod
    def emit(circuit_like: Any, engine: str = "qiskit", **options: Any) -> Any:
        from quantum_cq._engines.service import default_engine_service

        return default_engine_service().emit(circuit_like, engine=engine, **options)

    @staticmethod
    def compile(circuit_like: Any, engine: str = "qiskit", **options: Any) -> Any:
        from quantum_cq._engines.service import default_engine_service

        return default_engine_service().compile(circuit_like, engine=engine, **options)

    @staticmethod
    def run_engine(
        circuit_like: Any,
        engine: str = "qiskit",
        *,
        shots: int = 1024,
        **options: Any,
    ) -> Any:
        from quantum_cq._engines.service import default_engine_service

        return default_engine_service().run(circuit_like, engine=engine, shots=shots, **options)

    @staticmethod
    def ibm(
        token: str,
        *,
        channel: str = "ibm_quantum_platform",
        instance: str | None = None,
        region: str | None = None,
        plans_preference: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
    ) -> IBMRuntimeConfig:
        return IBMRuntimeConfig(
            token=token,
            channel=channel,
            instance=instance,
            region=region,
            plans_preference=plans_preference,
            tags=tuple(tags) if tags is not None else None,
        )

    @staticmethod
    def run(
        first: Any = None,
        *,
        circuit: Any = None,
        circuits: list[Any] | None = None,
        data: Any = None,
        datasets: list[Any] | None = None,
        encoder: str | None = None,
        encoders: list[str] | None = None,
        mode: str | None = None,
        modes: list[str] | None = None,
        ibm: IBMRuntimeConfig | None = None,
        shots: int = 1024,
        backend: str = "least_busy",
        measurement: str = "auto",
        fail_fast: bool = False,
        timeout: int | None = None,
        title: str | None = None,
    ) -> Any:
        from quantum_cq._runtime.experiment import run_experiment_matrix

        if first is not None:
            if any(item is not None for item in (circuit, circuits, data, datasets)):
                raise ValueError("CQ.run recebeu primeiro argumento posicional e tambem fontes explicitas")
            if CQ._looks_like_dataset(first):
                data = first
            else:
                circuit = first

        return run_experiment_matrix(
            circuit=circuit,
            circuits=circuits,
            data=data,
            datasets=datasets,
            encoder=encoder,
            encoders=encoders,
            mode=mode,
            modes=modes,
            ibm=ibm,
            shots=shots,
            backend=backend,
            measurement=measurement,
            fail_fast=fail_fast,
            timeout=timeout,
            title=title,
        )

    @staticmethod
    def _normalize_navigation_engine(engine: str) -> str:
        aliases = {
            "explicit": "explicit_circuit",
            "explicit_circuit": "explicit_circuit",
            "sparse": "sparse_explicit_circuit",
            "sparse_explicit_circuit": "sparse_explicit_circuit",
            "qram": "qram_like",
            "qram_like": "qram_like",
            "oracle": "oracle_model",
            "oracle_model": "oracle_model",
        }
        if engine not in aliases:
            accepted = ", ".join(sorted(aliases))
            raise ValueError(f"Engine de navigation invalida: {engine}. Engines aceitos: {accepted}")
        return aliases[engine]

    @staticmethod
    def _component_circuit_factory(engine: str | None, circuit_factory: Any = None) -> Any:
        if circuit_factory is not None:
            return circuit_factory
        if engine is None or engine == "qiskit":
            return None
        from quantum_cq._circuits.adapters import LogicalCircuitFactory

        return LogicalCircuitFactory()

    @staticmethod
    def _build_format_for_engine(engine: str | None, explicit_format: str | None) -> str:
        if explicit_format is not None:
            return explicit_format
        if engine is None or engine == "qiskit":
            return "qiskit"
        return "ir"

    @staticmethod
    def _resolve_alias_pair(
        first_name: str,
        first_value: int | None,
        second_name: str,
        second_value: int | None,
        *,
        default: int,
    ) -> int:
        if first_value is not None and second_value is not None and first_value != second_value:
            raise ValueError(f"{first_name} e {second_name} devem ser iguais quando ambos forem informados")
        return int(second_value if second_value is not None else first_value if first_value is not None else default)

    @staticmethod
    def _looks_like_dataset(value: Any) -> bool:
        if isinstance(value, (str, bytes)):
            return False
        if not isinstance(value, Sequence):
            return False
        return bool(value) and all(isinstance(item, Real) and not isinstance(item, bool) for item in value)
