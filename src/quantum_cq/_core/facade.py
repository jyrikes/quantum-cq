"""Facade principal do pacote quantum_cq."""

from __future__ import annotations

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
        self._encoding_name: str | None = None
        self._auto = True

    def with_data(self, value: Any, metadata: dict[str, Any] | None = None) -> "_CQPipelineBuilder":
        if isinstance(value, QuantumData):
            merged = dict(value.metadata)
            if metadata:
                merged.update(metadata)
            self._data = QuantumData(value.value, metadata=merged)
            return self

        self._data = QuantumData(value, metadata=metadata or {})
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

    def build(self) -> EncodedCircuit:
        if self._data is None or self._data.value is None:
            raise ValueError("CQ.pipeline requer dados antes de build")

        if not self._auto and self._encoding_name is not None:
            return self._build_manual(self._data, self._encoding_name)

        encoder = self._selector().select(self._data)
        return encoder.encode(self._data)

    def run(self) -> EncodedCircuit:
        return self.build()

    def _build_manual(self, data: QuantumData, name: str) -> EncodedCircuit:
        encoder = self.registry.get(name)
        if not encoder.can_handle(data):
            raise ValueError(f"Encoding '{name}' nao pode lidar com os dados informados")

        return encoder.encode(data)

    def _selector(self) -> Any:
        if self.selector is not None:
            return self.selector

        return EncodingSelector(self.registry)


class CQ:
    """Facade simples para encoding."""

    @staticmethod
    def pipeline(
        data: Any = None,
        *,
        encoding: str | None = None,
        registry: HandlerRegistry[EncodingProtocol] | None = None,
        selector: Any = None,
    ) -> _CQPipelineBuilder:
        builder = _CQPipelineBuilder(registry=registry, selector=selector)
        if data is not None:
            builder.with_data(data)
        if encoding is not None:
            if encoding == "auto":
                builder.auto_encoding()
            else:
                builder.with_encoding(encoding)
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
        role: str = "state",
        **kwargs: Any,
    ) -> Any:
        normalized_role = "state" if role == "input" else role
        if normalized_role == "navigation":
            return CQ._encode_navigation(
                data,
                encoding=encoding,
                metadata=metadata,
                registry=navigation_registry,
                **kwargs,
            )
        if normalized_role in {"oracle", "operator"}:
            raise NotImplementedError(f"Encoding para role='{normalized_role}' ainda nao implementado")
        if normalized_role != "state":
            raise ValueError(f"Role de encoding invalido: {role}")

        builder = CQ.pipeline(registry=registry).with_data(data, metadata=metadata)
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
        **kwargs: Any,
    ) -> Any:
        resolved = registry or default_navigation_registry()
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
        return CQ.algorithm("deutsch").with_case(case).build(**kwargs)

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
        return CQ.primitive("standard_diffuser").build(num_qubits, **kwargs)

    @staticmethod
    def phase_rotation(phase: float, **kwargs: Any) -> Any:
        return CQ.operator("phase_rotation").with_phase(phase).build(**kwargs)

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
        oracle_registry: OracleRegistry | None = None,
    ) -> Any:
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
    def available_primitives(registry: PrimitiveRegistry | None = None) -> list[str]:
        return (registry or default_primitive_registry()).names()

    @staticmethod
    def available_operators(registry: OperatorRegistry | None = None) -> list[str]:
        return (registry or default_operator_registry()).names()

    @staticmethod
    def available_navigation_encodings(registry: NavigationRegistry | None = None) -> list[str]:
        return (registry or default_navigation_registry()).names()

    @staticmethod
    def primitive(
        name: str,
        *,
        registry: PrimitiveRegistry | None = None,
        circuit_factory: Any = None,
    ) -> Any:
        resolved = registry or default_primitive_registry(circuit_factory=circuit_factory)
        return resolved.get(name)

    @staticmethod
    def operator(
        name: str,
        *,
        registry: OperatorRegistry | None = None,
        circuit_factory: Any = None,
    ) -> Any:
        resolved = registry or default_operator_registry(circuit_factory=circuit_factory)
        return resolved.get(name)

    @staticmethod
    def navigation(
        name: str,
        *,
        registry: NavigationRegistry | None = None,
        circuit_factory: Any = None,
    ) -> Any:
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
    ) -> Any:
        _ = metrics, metadata
        CQ.describe(obj)
        if draw:
            drawing = CQ.draw(
                obj,
                decompose=decompose,
                reps=reps,
                idle_wires=idle_wires,
                scale=scale,
            )
            try:
                from IPython.display import display

                display(drawing)
            except Exception:
                print(drawing)
        return obj

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
