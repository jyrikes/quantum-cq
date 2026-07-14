"""Small deterministic placement, routing and ASAP scheduling layer."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from quantum_cq._circuits.compact import CircuitIR, Operation


class PlanningError(ValueError):
    pass


@dataclass(frozen=True)
class PlacementPlan:
    strategy: str
    logical_to_physical: dict[int, str]
    physical_to_logical: dict[str, int]
    target_fingerprint: str | None = None
    status: str = "completed"

    def __post_init__(self) -> None:
        if len(set(self.logical_to_physical.values())) != len(self.logical_to_physical):
            raise PlanningError("Placement requer mapping bijetivo")
        object.__setattr__(self, "logical_to_physical", MappingProxyType(dict(self.logical_to_physical)))
        object.__setattr__(self, "physical_to_logical", MappingProxyType(dict(self.physical_to_logical)))


@dataclass(frozen=True)
class RoutingPlan:
    strategy: str
    initial_mapping: dict[int, str]
    final_mapping: dict[int, str]
    swaps: tuple[tuple[str, str], ...] = ()
    routed_circuit: CircuitIR | None = None
    status: str = "completed"
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial_mapping", MappingProxyType(dict(self.initial_mapping)))
        object.__setattr__(self, "final_mapping", MappingProxyType(dict(self.final_mapping)))
        object.__setattr__(self, "swaps", tuple(self.swaps))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True)
class ScheduleItem:
    operation_index: int
    operation_kind: str
    start: int | None
    duration: int | None
    resources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "resources", tuple(self.resources))


@dataclass(frozen=True)
class SchedulePlan:
    strategy: str
    items: tuple[ScheduleItem, ...]
    total_duration: int | None = None
    complete: bool = False
    status: str = "insufficient_information"
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


def place(circuit: CircuitIR, *, target: Any = None, strategy: str = "identity") -> PlacementPlan:
    if strategy not in {"identity", "first_available"}:
        raise PlanningError(f"placement strategy nao suportada: {strategy}")
    physical = _target_qubits(target)
    if physical is None:
        physical = tuple(str(index) for index in range(circuit.n_qubits))
    if len(physical) < circuit.n_qubits:
        raise PlanningError("Target possui quantidade insuficiente de qubits")
    selected = physical[: circuit.n_qubits]
    logical_to_physical = {logical: selected[logical] for logical in range(circuit.n_qubits)}
    physical_to_logical = {physical_id: logical for logical, physical_id in logical_to_physical.items()}
    return PlacementPlan(
        strategy=strategy,
        logical_to_physical=logical_to_physical,
        physical_to_logical=physical_to_logical,
        target_fingerprint=_target_fingerprint(target),
    )


def route(
    circuit: CircuitIR,
    *,
    target: Any = None,
    placement: PlacementPlan | None = None,
    strategy: str = "shortest_path",
) -> RoutingPlan:
    if strategy not in {"shortest_path", "none"}:
        raise PlanningError(f"routing strategy nao suportada: {strategy}")
    if placement is None:
        placement = place(circuit, target=target)
    mapping = dict(placement.logical_to_physical)
    if strategy == "none":
        return RoutingPlan(strategy=strategy, initial_mapping=dict(mapping), final_mapping=dict(mapping), status="not_requested")
    graph = _target_graph(target)
    supports_swap = _supports_operation(target, "swap")
    swaps: list[tuple[str, str]] = []
    for operation in _operations(circuit):
        if len(operation.qubits) < 2:
            continue
        left, right = mapping[operation.qubits[0]], mapping[operation.qubits[1]]
        if _edge_supports(graph, left, right, operation.kind):
            continue
        path = _shortest_path(graph, left, right, operation.kind)
        if path is None:
            raise PlanningError("routing incompatible: caminho fisico indisponivel")
        if len(path) > 2 and not supports_swap:
            raise PlanningError("routing incompatible: SWAP nao suportado pelo target")
        for swap in zip(path, path[1:]):
            swaps.append(swap)
            _apply_swap(mapping, swap)
    return RoutingPlan(
        strategy=strategy,
        initial_mapping=dict(placement.logical_to_physical),
        final_mapping=mapping,
        swaps=tuple(swaps),
        routed_circuit=circuit,
        status="completed",
    )


def schedule(
    circuit: CircuitIR,
    *,
    target: Any = None,
    strategy: str = "asap",
) -> SchedulePlan:
    if strategy != "asap":
        raise PlanningError(f"scheduling strategy nao suportada: {strategy}")
    durations = _operation_durations(target)
    items: list[ScheduleItem] = []
    resource_available: dict[str, int] = {}
    complete = True
    diagnostics: list[str] = []
    for index, operation in enumerate(_operations(circuit)):
        resources = tuple(f"q{qubit}" for qubit in operation.qubits) + tuple(f"c{clbit}" for clbit in operation.clbits)
        duration = durations.get(operation.kind)
        if duration is None:
            complete = False
            diagnostics.append(f"duracao desconhecida para {operation.kind}")
            items.append(ScheduleItem(index, operation.kind, None, None, resources))
            continue
        start = max((resource_available.get(resource, 0) for resource in resources), default=0)
        finish = start + duration
        for resource in resources:
            resource_available[resource] = finish
        items.append(ScheduleItem(index, operation.kind, start, duration, resources))
    total = max((item.start + item.duration for item in items if item.start is not None and item.duration is not None), default=None)
    return SchedulePlan(
        strategy=strategy,
        items=tuple(items),
        total_duration=total,
        complete=complete,
        status="completed" if complete else "insufficient_information",
        diagnostics=tuple(diagnostics),
    )


def _operations(circuit: CircuitIR) -> list[Operation]:
    return [operation for layer in circuit.layers for operation in layer.operations] + list(circuit.outputs)


def _target_qubits(target: Any) -> tuple[str, ...] | None:
    architecture = getattr(target, "architecture", None)
    qubits = getattr(architecture, "qubits", None)
    if qubits is None:
        return None
    return tuple(str(qubit) for qubit in qubits)


def _target_fingerprint(target: Any) -> str | None:
    architecture = getattr(target, "architecture", None)
    return getattr(architecture, "fingerprint", None)


def _target_graph(target: Any) -> dict[str, list[tuple[str, str, bool]]]:
    architecture = getattr(target, "architecture", None)
    graph: dict[str, list[tuple[str, str, bool]]] = {}
    for edge in getattr(architecture, "topology", ()) or ():
        operations = tuple(getattr(edge, "operations", ()) or ())
        if not operations:
            operations = ("cx", "cz", "swap")
        graph.setdefault(str(edge.source), []).append((str(edge.target), ",".join(operations), bool(edge.directed)))
        if not bool(edge.directed):
            graph.setdefault(str(edge.target), []).append((str(edge.source), ",".join(operations), bool(edge.directed)))
    return graph


def _edge_supports(graph: dict[str, list[tuple[str, str, bool]]], left: str, right: str, operation: str) -> bool:
    for neighbor, operations, _ in graph.get(left, []):
        if neighbor == right and operation in operations.split(","):
            return True
    return not graph


def _shortest_path(graph: dict[str, list[tuple[str, str, bool]]], start: str, goal: str, operation: str) -> tuple[str, ...] | None:
    if not graph:
        return (start, goal)
    queue: deque[tuple[str, tuple[str, ...]]] = deque([(start, (start,))])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        if node == goal:
            return path
        for neighbor, operations, _ in graph.get(node, []):
            if neighbor in seen:
                continue
            if operation not in operations.split(",") and "swap" not in operations.split(","):
                continue
            seen.add(neighbor)
            queue.append((neighbor, (*path, neighbor)))
    return None


def _supports_operation(target: Any, operation: str) -> bool:
    architecture = getattr(target, "architecture", None)
    for instruction in getattr(architecture, "instructions", ()) or ():
        if getattr(instruction, "name", None) == operation:
            return True
    return target is None


def _apply_swap(mapping: dict[int, str], swap: tuple[str, str]) -> None:
    left, right = swap
    logical_left = next((logical for logical, physical in mapping.items() if physical == left), None)
    logical_right = next((logical for logical, physical in mapping.items() if physical == right), None)
    if logical_left is not None:
        mapping[logical_left] = right
    if logical_right is not None:
        mapping[logical_right] = left


def _operation_durations(target: Any) -> dict[str, int]:
    architecture = getattr(target, "architecture", None)
    durations: dict[str, int] = {}
    for instruction in getattr(architecture, "instructions", ()) or ():
        restrictions = getattr(instruction, "restrictions", {}) or {}
        duration = restrictions.get("duration")
        if isinstance(duration, int | float):
            durations[getattr(instruction, "name")] = int(duration)
    return durations
