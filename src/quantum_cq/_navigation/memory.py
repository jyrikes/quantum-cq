"""Navegacao enderecada e grafos com semantica reversivel."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from numbers import Integral
from typing import Any, Protocol

from quantum_cq._core.interfaces import CircuitFactoryProtocol
from quantum_cq._core.results import NavigationCircuit


def _ceil_log2(value: int) -> int:
    if value <= 1:
        return 0
    return math.ceil(math.log2(value))


def _is_non_bool_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, Integral)


def _validate_non_negative_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} nao aceita bool como inteiro")
    if not isinstance(value, Integral):
        raise TypeError(f"{name} deve ser inteiro")
    integer = int(value)
    if integer < 0:
        raise ValueError(f"{name} deve conter inteiros nao negativos")
    return integer


def _factory_or_default(circuit_factory: CircuitFactoryProtocol | None) -> CircuitFactoryProtocol:
    if circuit_factory is not None:
        return circuit_factory

    from quantum_cq._circuits.adapters import QiskitCircuitFactory

    return QiskitCircuitFactory()


@dataclass
class AddressedMemory:
    values: Sequence[int]
    data_bit_width: int | None = None
    address_bit_width: int | None = None
    default_value: int = 0

    def __post_init__(self) -> None:
        values = list(self.values)
        if not values:
            raise ValueError("AddressedMemory nao pode ser vazio")

        validated_values = [_validate_non_negative_int("values", value) for value in values]
        default_value = _validate_non_negative_int("default_value", self.default_value)
        max_value = max([*validated_values, default_value])

        required_data_bits = max(1, max_value.bit_length())
        required_address_bits = max(1, _ceil_log2(len(validated_values)))

        if self.data_bit_width is not None:
            data_bit_width = _validate_non_negative_int("data_bit_width", self.data_bit_width)
            if data_bit_width <= 0 or data_bit_width < required_data_bits:
                raise ValueError("data_bit_width insuficiente para os valores da memoria")
        else:
            data_bit_width = required_data_bits

        if self.address_bit_width is not None:
            address_bit_width = _validate_non_negative_int("address_bit_width", self.address_bit_width)
            if address_bit_width <= 0 or 2**address_bit_width < len(validated_values):
                raise ValueError("address_bit_width insuficiente para o tamanho da memoria")
        else:
            address_bit_width = required_address_bits

        self.values = validated_values
        self.default_value = default_value
        self.data_bit_width = data_bit_width
        self.address_bit_width = address_bit_width

    @property
    def memory_size(self) -> int:
        return len(self.values)

    @property
    def address_qubits(self) -> int:
        return int(self.address_bit_width or 1)

    @property
    def address_space_size(self) -> int:
        return 2**self.address_qubits

    @property
    def data_qubits(self) -> int:
        return int(self.data_bit_width or 1)

    @property
    def max_value(self) -> int:
        return max([*self.values, self.default_value])

    def value_at(self, address: int) -> int:
        address = _validate_non_negative_int("address", address)
        if address >= self.address_space_size:
            raise ValueError("address fora do espaco enderecavel")
        if address < self.memory_size:
            return int(self.values[address])
        return self.default_value

    def padded_values(self) -> list[int]:
        return [self.value_at(address) for address in range(self.address_space_size)]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "memory_size": self.memory_size,
            "address_qubits": self.address_qubits,
            "address_space_size": self.address_space_size,
            "data_qubits": self.data_qubits,
            "default_value": self.default_value,
            "max_value": self.max_value,
            "padded": self.memory_size != self.address_space_size,
        }


class MemoryAccessEngineProtocol(Protocol):
    name: str
    model: str

    def build_load_oracle(
        self,
        memory: AddressedMemory,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> NavigationCircuit: ...


class ExplicitCircuitMemoryEngine:
    name = "explicit_circuit"
    model = "explicit_circuit"

    def build_load_oracle(
        self,
        memory: AddressedMemory,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> NavigationCircuit:
        return self._build(memory, circuit_factory=circuit_factory, sparse=False, model=self.model)

    def _build(
        self,
        memory: AddressedMemory,
        *,
        circuit_factory: CircuitFactoryProtocol | None,
        sparse: bool,
        model: str,
    ) -> NavigationCircuit:
        total_qubits = memory.address_qubits + memory.data_qubits
        builder = _factory_or_default(circuit_factory).create(total_qubits)
        controls = list(range(memory.address_qubits))
        skipped_zero_entries = 0
        nonzero_entries = 0

        for address in range(memory.address_space_size):
            value = memory.value_at(address)
            if value == 0:
                skipped_zero_entries += 1
                if sparse:
                    continue
            else:
                nonzero_entries += 1

            for data_bit in range(memory.data_qubits):
                if not (value >> data_bit) & 1:
                    continue

                flipped = self._prepare_address_controls(builder, address, memory.address_qubits)
                target = memory.address_qubits + data_bit
                if len(controls) == 1:
                    builder.cx(controls[0], target)
                else:
                    builder.mcx(controls, target)
                self._restore_address_controls(builder, flipped)

        metadata = self._metadata(memory, model=model)
        metadata["nonzero_entries"] = nonzero_entries
        metadata["skipped_zero_entries"] = skipped_zero_entries

        return NavigationCircuit(
            circuit=builder.build(),
            navigation_name="addressed_memory",
            circuit_format="qiskit",
            metadata=metadata,
        )

    def _prepare_address_controls(self, builder: Any, address: int, address_qubits: int) -> list[int]:
        flipped = []
        for bit in range(address_qubits):
            if ((address >> bit) & 1) == 0:
                builder.x(bit)
                flipped.append(bit)
        return flipped

    def _restore_address_controls(self, builder: Any, flipped: Sequence[int]) -> None:
        for bit in reversed(flipped):
            builder.x(bit)

    def _metadata(self, memory: AddressedMemory, *, model: str) -> dict[str, Any]:
        return {
            **memory.to_metadata(),
            "family": "navigation",
            "role": "access_oracle",
            "navigation_name": "addressed_memory",
            "model": model,
            "engine": model,
            "physical_qram": False,
            "simulates_qram_semantics": True,
            "simulates_physical_qram": False,
            "access_semantics": "xor_load",
            "reversible": True,
            "address_bit_order": "little_endian_int",
            "data_bit_order": "little_endian_int",
            "construction_cost": "O(address_space_size * data_qubits * address_qubits)",
            "oracle_calls": 1,
            "exportable_to_qiskit": True,
            "status": "implemented",
        }


class SparseExplicitMemoryEngine(ExplicitCircuitMemoryEngine):
    name = "sparse_explicit_circuit"
    model = "sparse_explicit_circuit"

    def build_load_oracle(
        self,
        memory: AddressedMemory,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> NavigationCircuit:
        return self._build(memory, circuit_factory=circuit_factory, sparse=True, model=self.model)


class QRAMLikeMemoryEngine:
    name = "qram_like"
    model = "qram_like"

    def __init__(self, delegated_engine: MemoryAccessEngineProtocol | None = None) -> None:
        self.delegated_engine = delegated_engine or SparseExplicitMemoryEngine()

    def build_load_oracle(
        self,
        memory: AddressedMemory,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> NavigationCircuit:
        delegated = self.delegated_engine.build_load_oracle(memory, circuit_factory=circuit_factory)
        metadata = dict(delegated.metadata)
        metadata.update(
            {
                "model": "qram_like",
                "engine": "qram_like",
                "delegated_engine": getattr(self.delegated_engine, "model", "explicit_circuit"),
                "physical_qram": False,
                "simulates_qram_semantics": True,
                "simulates_physical_qram": False,
                "status": "implemented_logical_simulation",
            }
        )
        return NavigationCircuit(
            circuit=delegated.circuit,
            navigation_name="addressed_memory",
            circuit_format=delegated.circuit_format,
            metadata=metadata,
        )


class OracleModelMemoryEngine:
    name = "oracle_model"
    model = "oracle_model"

    def build_load_oracle(
        self,
        memory: AddressedMemory,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> NavigationCircuit:
        raise NotImplementedError("oracle_model is abstract and cannot be exported to Qiskit in this run")

    def estimate_cost(self, memory: AddressedMemory) -> dict[str, Any]:
        return {
            **memory.to_metadata(),
            "model": self.model,
            "physical_qram": False,
            "simulates_qram_semantics": True,
            "simulates_physical_qram": False,
            "status": "abstract_model",
        }


class AddressedMemoryEncoding:
    name = "addressed_memory"
    family = "navigation"
    auto_selectable = False

    def __init__(
        self,
        engine: str | MemoryAccessEngineProtocol = "explicit_circuit",
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> None:
        self.engine = engine
        self.circuit_factory = circuit_factory

    def can_handle(self, data: Any) -> bool:
        return isinstance(_unwrap_value(data), AddressedMemory)

    def encode(
        self,
        memory: AddressedMemory,
        *,
        engine: str | MemoryAccessEngineProtocol | None = None,
    ) -> NavigationCircuit:
        return self.build_access_oracle(memory, engine=engine)

    def build_access_oracle(
        self,
        memory: AddressedMemory,
        *,
        engine: str | MemoryAccessEngineProtocol | None = None,
    ) -> NavigationCircuit:
        unwrapped = _unwrap_value(memory)
        if not isinstance(unwrapped, AddressedMemory):
            raise TypeError("AddressedMemoryEncoding espera AddressedMemory")
        resolved_engine = self._resolve_engine(engine or self.engine)
        return resolved_engine.build_load_oracle(unwrapped, circuit_factory=self.circuit_factory)

    def _resolve_engine(self, engine: str | MemoryAccessEngineProtocol) -> MemoryAccessEngineProtocol:
        if not isinstance(engine, str):
            return engine
        engines: dict[str, MemoryAccessEngineProtocol] = {
            "explicit_circuit": ExplicitCircuitMemoryEngine(),
            "sparse_explicit_circuit": SparseExplicitMemoryEngine(),
            "qram_like": QRAMLikeMemoryEngine(),
            "oracle_model": OracleModelMemoryEngine(),
        }
        if engine not in engines:
            raise ValueError(f"Engine de memoria nao registrado: {engine}")
        return engines[engine]


@dataclass
class GraphData:
    edges: Sequence[tuple[int, int]]
    num_vertices: int
    directed: bool = False
    default_neighbor: int = 0
    padding_policy: str = "self_loop"
    _neighbors: dict[int, list[int]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.num_vertices = _validate_positive_vertex_count(self.num_vertices)
        self.default_neighbor = _validate_vertex_value(
            "default_neighbor",
            self.default_neighbor,
            self.num_vertices,
            allow_equal=False,
        )
        if self.padding_policy not in {"self_loop", "constant"}:
            raise ValueError("padding_policy deve ser 'self_loop' ou 'constant'")

        adjacency: dict[int, set[int]] = {vertex: set() for vertex in range(self.num_vertices)}
        for left, right in self.edges:
            left_vertex = _validate_vertex_value("vertices", left, self.num_vertices)
            right_vertex = _validate_vertex_value("vertices", right, self.num_vertices)
            adjacency[left_vertex].add(right_vertex)
            if not self.directed:
                adjacency[right_vertex].add(left_vertex)

        self._neighbors = {vertex: sorted(values) for vertex, values in adjacency.items()}

    @property
    def max_degree(self) -> int:
        return max((len(values) for values in self._neighbors.values()), default=0)

    @property
    def degree_qubits(self) -> int:
        raw_space = _next_power_of_two(max(1, self.max_degree))
        return max(1, _ceil_log2(raw_space))

    @property
    def degree_space(self) -> int:
        return 2**self.degree_qubits

    @property
    def vertex_qubits(self) -> int:
        return max(1, _ceil_log2(self.num_vertices))

    @property
    def neighbor_qubits(self) -> int:
        return self.vertex_qubits

    def neighbors(self, vertex: int) -> list[int]:
        vertex = _validate_vertex_value("vertex", vertex, self.num_vertices)
        return list(self._neighbors[vertex])

    def neighbor(self, vertex: int, coin_index: int) -> int:
        vertex = _validate_vertex_value("vertex", vertex, self.num_vertices)
        coin_index = _validate_non_negative_int("k", coin_index)
        if coin_index >= self.degree_space:
            raise ValueError("k fora do espaco de grau")
        neighbors = self._neighbors[vertex]
        if coin_index < len(neighbors):
            return neighbors[coin_index]
        if self.padding_policy == "self_loop":
            return vertex
        return self.default_neighbor

    def reverse_index(self, vertex: int, coin_index: int) -> int:
        vertex = _validate_vertex_value("vertex", vertex, self.num_vertices)
        coin_index = _validate_non_negative_int("k", coin_index)
        neighbors = self._neighbors[vertex]
        if coin_index >= len(neighbors):
            return coin_index

        target = neighbors[coin_index]
        reverse_neighbors = self._neighbors[target]
        if vertex not in reverse_neighbors:
            raise ValueError("shift do grafo nao e reversivel para esta aresta")
        return reverse_neighbors.index(vertex)

    def to_flat_memory(self, default_value: int | None = None) -> AddressedMemory:
        default = self.default_neighbor if default_value is None else default_value
        values = [
            self.neighbor(vertex, coin_index)
            for vertex in range(self.num_vertices)
            for coin_index in range(self.degree_space)
        ]
        return AddressedMemory(
            values,
            data_bit_width=self.neighbor_qubits,
            address_bit_width=self.vertex_qubits + self.degree_qubits,
            default_value=default,
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "num_vertices": self.num_vertices,
            "directed": self.directed,
            "max_degree": self.max_degree,
            "degree_space": self.degree_space,
            "degree_qubits": self.degree_qubits,
            "vertex_qubits": self.vertex_qubits,
            "neighbor_qubits": self.neighbor_qubits,
            "padding_policy": self.padding_policy,
        }


class GraphNavigationEncoding:
    name = "graph_navigation"
    family = "navigation"
    auto_selectable = False

    def __init__(
        self,
        engine: str | MemoryAccessEngineProtocol = "explicit_circuit",
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> None:
        self.engine = engine
        self.circuit_factory = circuit_factory

    def can_handle(self, data: Any) -> bool:
        return isinstance(_unwrap_value(data), GraphData)

    def encode(
        self,
        graph: GraphData,
        *,
        engine: str | MemoryAccessEngineProtocol | None = None,
    ) -> NavigationCircuit:
        return self.build_neighbor_oracle(graph, engine=engine)

    def build_access_oracle(self, structure: GraphData) -> NavigationCircuit:
        return self.build_neighbor_oracle(structure)

    def build_neighbor_oracle(
        self,
        graph: GraphData,
        *,
        engine: str | MemoryAccessEngineProtocol | None = None,
    ) -> NavigationCircuit:
        unwrapped = _unwrap_value(graph)
        if not isinstance(unwrapped, GraphData):
            raise TypeError("GraphNavigationEncoding espera GraphData")
        memory = unwrapped.to_flat_memory()
        addressed = AddressedMemoryEncoding(
            engine=engine or self.engine,
            circuit_factory=self.circuit_factory,
        )
        built = addressed.build_access_oracle(memory)
        metadata = dict(built.metadata)
        metadata.update(
            {
                **unwrapped.to_metadata(),
                "family": "navigation",
                "role": "neighbor_oracle",
                "navigation_name": "graph_navigation",
                "uses_addressed_memory": True,
                "flat_addressing": "v * degree_space + k",
                "address_layout": "[k bits primeiro] + [v bits depois]",
                "oracle_calls": 1,
                "status": "implemented",
            }
        )
        return NavigationCircuit(
            circuit=built.circuit,
            navigation_name="graph_navigation",
            circuit_format=built.circuit_format,
            metadata=metadata,
        )


def _unwrap_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _validate_positive_vertex_count(value: Any) -> int:
    count = _validate_non_negative_int("num_vertices", value)
    if count <= 0:
        raise ValueError("num_vertices deve ser positivo")
    return count


def _validate_vertex_value(
    name: str,
    value: Any,
    num_vertices: int,
    *,
    allow_equal: bool = False,
) -> int:
    vertex = _validate_non_negative_int(name, value)
    upper_ok = vertex <= num_vertices if allow_equal else vertex < num_vertices
    if not upper_ok:
        raise ValueError("vertices devem estar no intervalo valido")
    return vertex


def _next_power_of_two(value: int) -> int:
    if value <= 1:
        return 1
    return 2 ** _ceil_log2(value)


__all__ = [
    "AddressedMemory",
    "MemoryAccessEngineProtocol",
    "ExplicitCircuitMemoryEngine",
    "SparseExplicitMemoryEngine",
    "QRAMLikeMemoryEngine",
    "OracleModelMemoryEngine",
    "AddressedMemoryEncoding",
    "GraphData",
    "GraphNavigationEncoding",
]
