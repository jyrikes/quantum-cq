"""Registries de handlers."""

from __future__ import annotations

from typing import Any, Generic, TypeVar, cast


T = TypeVar("T")


class HandlerRegistry(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def register(
        self,
        item_or_name: T | str,
        item: T | None = None,
        *,
        name: str | None = None,
        override: bool = False,
    ) -> None:
        resolved_name, resolved_item = self._resolve_registration(item_or_name, item, name)

        if resolved_name in self._items and not override:
            raise ValueError(f"Handler '{resolved_name}' ja registrado")

        self._items[resolved_name] = resolved_item

    def get(self, name: str) -> T:
        if name not in self._items:
            raise KeyError(f"Handler '{name}' nao registrado")

        return self._items[name]

    def has(self, name: str) -> bool:
        return name in self._items

    def contains(self, name: str) -> bool:
        return self.has(name)

    def names(self) -> list[str]:
        return list(self._items)

    def all(self) -> list[T]:
        return list(self._items.values())

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def _resolve_registration(
        self,
        item_or_name: T | str,
        item: T | None,
        name: str | None,
    ) -> tuple[str, T]:
        if item is not None:
            return str(item_or_name), item

        resolved_item = cast(T, item_or_name)
        resolved_name = name or getattr(resolved_item, "name", None)
        if not resolved_name:
            raise ValueError("Handler requer nome explicito ou atributo name")

        return str(resolved_name), resolved_item


class EncodingRegistry(HandlerRegistry[Any]):
    pass


class FactoryRegistry(HandlerRegistry[Any]):
    def create(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in self._items:
            raise KeyError(f"Handler '{name}' nao registrado")

        item = self._items[name]
        if callable(item):
            return item(*args, **kwargs)

        return item

    def get(self, name: str) -> Any:
        return self.create(name)

    def all(self) -> list[Any]:
        return [self.get(name) for name in self.names()]


class AlgorithmRegistry(FactoryRegistry):
    pass


class OracleRegistry(FactoryRegistry):
    pass


class PrimitiveRegistry(FactoryRegistry):
    pass


class OperatorRegistry(FactoryRegistry):
    pass


class NavigationRegistry(FactoryRegistry):
    pass


def default_encoding_registry(circuit_factory: Any = None) -> EncodingRegistry:
    if circuit_factory is None:
        from quantum_cq._circuits.adapters import QiskitCircuitFactory

        circuit_factory = QiskitCircuitFactory()

    from quantum_cq._encodings.state import (
        AmplitudeEncoding,
        AngleEncoding,
        BasisEncoding,
        DataReUploadingEncoding,
        DenseAngleEncoding,
        IQPEncoding,
        PauliFeatureMapEncoding,
        PhaseEncoding,
        ZFeatureMapEncoding,
        ZZFeatureMapEncoding,
    )

    registry = EncodingRegistry()
    for encoder_cls in (
        BasisEncoding,
        AngleEncoding,
        PhaseEncoding,
        AmplitudeEncoding,
        DenseAngleEncoding,
        ZFeatureMapEncoding,
        ZZFeatureMapEncoding,
        PauliFeatureMapEncoding,
        IQPEncoding,
        DataReUploadingEncoding,
    ):
        registry.register(encoder_cls(circuit_factory=circuit_factory))

    return registry


def default_oracle_registry(circuit_factory: Any = None) -> OracleRegistry:
    from quantum_cq._circuits.oracles import BernsteinVaziraniOracle, DeutschJozsaOracle, DeutschOracle, PhaseMarkedStateOracle

    registry = OracleRegistry()
    registry.register(DeutschOracle)
    registry.register(BernsteinVaziraniOracle)
    registry.register(DeutschJozsaOracle)
    registry.register(
        "phase_marked_state",
        lambda: PhaseMarkedStateOracle(circuit_factory=circuit_factory),
    )
    return registry


def default_primitive_registry(circuit_factory: Any = None) -> PrimitiveRegistry:
    from quantum_cq._circuits.primitives import (
        InverseQFTPrimitive,
        PhaseRotationUnitary,
        QFTPrimitive,
        StandardDiffuser,
        UniformSuperpositionPreparation,
    )
    from quantum_cq._navigation.walks import CoinedQuantumWalkPrimitive

    registry = PrimitiveRegistry()
    registry.register(
        "uniform_superposition",
        lambda: UniformSuperpositionPreparation(circuit_factory=circuit_factory),
    )
    registry.register(
        "standard_diffuser",
        lambda: StandardDiffuser(circuit_factory=circuit_factory),
    )
    registry.register("qft", lambda: QFTPrimitive(circuit_factory=circuit_factory))
    registry.register(
        "inverse_qft",
        lambda: InverseQFTPrimitive(circuit_factory=circuit_factory),
    )
    registry.register(
        "coined_quantum_walk",
        lambda: CoinedQuantumWalkPrimitive(circuit_factory=circuit_factory),
    )
    return registry


def default_navigation_registry(circuit_factory: Any = None) -> NavigationRegistry:
    if circuit_factory is None:
        from quantum_cq._circuits.adapters import QiskitCircuitFactory

        circuit_factory = QiskitCircuitFactory()

    from quantum_cq._navigation.memory import AddressedMemoryEncoding, GraphNavigationEncoding

    registry = NavigationRegistry()
    registry.register(
        "addressed_memory",
        lambda: AddressedMemoryEncoding(circuit_factory=circuit_factory),
    )
    registry.register(
        "graph_navigation",
        lambda: GraphNavigationEncoding(circuit_factory=circuit_factory),
    )
    return registry


def default_operator_registry(circuit_factory: Any = None) -> OperatorRegistry:
    from quantum_cq._circuits.primitives import PhaseRotationUnitary

    registry = OperatorRegistry()
    registry.register(
        "phase_rotation",
        lambda: PhaseRotationUnitary(circuit_factory=circuit_factory),
    )
    return registry


def default_algorithm_registry(
    circuit_factory: Any = None,
    oracle_registry: OracleRegistry | None = None,
) -> AlgorithmRegistry:
    if circuit_factory is None:
        from quantum_cq._circuits.adapters import QiskitCircuitFactory

        circuit_factory = QiskitCircuitFactory()

    from quantum_cq._algorithms.standard import (
        BernsteinVaziraniAlgorithm,
        DeutschAlgorithm,
        DeutschJozsaAlgorithm,
        GroverAlgorithm,
        PhaseEstimationAlgorithm,
    )

    oracle_registry = oracle_registry or default_oracle_registry(circuit_factory=circuit_factory)
    registry = AlgorithmRegistry()
    registry.register(
        "deutsch",
        lambda: DeutschAlgorithm(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        ),
    )
    registry.register(
        "deutsch_jozsa",
        lambda: DeutschJozsaAlgorithm(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        ),
    )
    registry.register(
        "bernstein_vazirani",
        lambda: BernsteinVaziraniAlgorithm(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        ),
    )
    registry.register(
        "grover",
        lambda: GroverAlgorithm(circuit_factory=circuit_factory),
    )
    registry.register(
        "phase_estimation",
        lambda: PhaseEstimationAlgorithm(circuit_factory=circuit_factory),
    )
    registry.register(
        "qpe",
        lambda: PhaseEstimationAlgorithm(circuit_factory=circuit_factory, alias="qpe"),
    )
    return registry
