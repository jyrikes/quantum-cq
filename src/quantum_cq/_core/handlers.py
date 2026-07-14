"""Registries de handlers."""

from __future__ import annotations

from typing import Any, Generic, TypeVar, cast

from quantum_cq._core.components import ComponentDescriptor


T = TypeVar("T")


class HandlerRegistry(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}
        self._descriptors: dict[str, ComponentDescriptor] = {}

    def register(
        self,
        item_or_name: T | str,
        item: T | None = None,
        *,
        name: str | None = None,
        override: bool = False,
        descriptor: ComponentDescriptor | None = None,
    ) -> None:
        resolved_name, resolved_item = self._resolve_registration(item_or_name, item, name)

        if resolved_name in self._items and not override:
            raise ValueError(f"Handler '{resolved_name}' ja registrado")

        self._items[resolved_name] = resolved_item
        self._descriptors[resolved_name] = descriptor or ComponentDescriptor(
            name=resolved_name,
            category="handler",
            family=str(getattr(resolved_item, "family", "")),
            status=str(getattr(resolved_item, "status", "implemented")),
        )

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

    def descriptor(self, name: str) -> ComponentDescriptor:
        if name not in self._descriptors:
            raise KeyError(f"Descriptor '{name}' nao registrado")
        return self._descriptors[name]

    def descriptors(self) -> tuple[ComponentDescriptor, ...]:
        return tuple(self._descriptors[name] for name in self.names())

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


def _descriptor(
    name: str,
    category: str,
    *,
    family: str = "",
    role: str = "",
    access_path: str = "",
    requirements: tuple[str, ...] = (),
    status: str = "implemented",
    description: str = "",
    **metadata: Any,
) -> ComponentDescriptor:
    return ComponentDescriptor(
        name=name,
        category=category,
        family=family,
        role=role,
        access_path=access_path,
        requirements=requirements,
        status=status,
        description=description,
        metadata=metadata,
    )


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
    descriptors = {
        "basis": ("basis", ("x",)),
        "angle": ("rotation", ("ry",)),
        "phase": ("rotation", ("p",)),
        "amplitude": ("state_preparation", ("initialize",)),
        "dense_angle": ("rotation", ("rx", "ry")),
        "z_feature_map": ("feature_map", ("h", "p")),
        "zz_feature_map": ("feature_map", ("h", "cx", "rz")),
        "pauli_feature_map": ("feature_map", ("h", "rx", "ry", "rz")),
        "iqp": ("feature_map", ("h", "rz", "cx")),
        "data_reuploading": ("rotation", ("rx", "ry", "rz")),
    }
    for encoder in (
        BasisEncoding(circuit_factory=circuit_factory),
        AngleEncoding(circuit_factory=circuit_factory),
        PhaseEncoding(circuit_factory=circuit_factory),
        AmplitudeEncoding(circuit_factory=circuit_factory),
        DenseAngleEncoding(circuit_factory=circuit_factory),
        ZFeatureMapEncoding(circuit_factory=circuit_factory),
        ZZFeatureMapEncoding(circuit_factory=circuit_factory),
        PauliFeatureMapEncoding(circuit_factory=circuit_factory),
        IQPEncoding(circuit_factory=circuit_factory),
        DataReUploadingEncoding(circuit_factory=circuit_factory),
    ):
        family, requirements = descriptors[encoder.name]
        registry.register(
            encoder,
            descriptor=_descriptor(
                encoder.name,
                "encoding",
                family=family,
                role="state_encoding",
                access_path=f"CQ.state(..., encoding='{encoder.name}')",
                requirements=requirements,
            ),
        )

    return registry


def default_oracle_registry(circuit_factory: Any = None) -> OracleRegistry:
    from quantum_cq._circuits.oracles import BernsteinVaziraniOracle, DeutschJozsaOracle, DeutschOracle, PhaseMarkedStateOracle

    registry = OracleRegistry()
    registry.register(
        DeutschOracle,
        descriptor=_descriptor(
            "deutsch",
            "oracle",
            family="boolean_oracle",
            role="predicate_oracle",
            access_path="CQ.oracle('deutsch', case=...)",
            requirements=("x", "cx"),
        ),
    )
    registry.register(
        BernsteinVaziraniOracle,
        descriptor=_descriptor(
            "bernstein_vazirani",
            "oracle",
            family="boolean_oracle",
            role="predicate_oracle",
            access_path="CQ.oracle('bernstein_vazirani', secret=...)",
            requirements=("cx",),
        ),
    )
    registry.register(
        DeutschJozsaOracle,
        descriptor=_descriptor(
            "deutsch_jozsa",
            "oracle",
            family="boolean_oracle",
            role="predicate_oracle",
            access_path="CQ.oracle('deutsch_jozsa', ...)",
            requirements=("x", "cx"),
        ),
    )
    registry.register(
        "phase_marked_state",
        lambda *args, **kwargs: PhaseMarkedStateOracle(
            *args,
            circuit_factory=kwargs.pop("circuit_factory", circuit_factory),
            **kwargs,
        ),
        descriptor=_descriptor(
            "phase_marked_state",
            "oracle",
            family="oracle",
            role="phase_oracle",
            access_path="CQ.oracle('phase_marked_state', marked_state=...)",
            requirements=("x", "h", "mcx"),
        ),
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
        descriptor=_descriptor(
            "uniform_superposition",
            "primitive",
            family="state_preparation",
            role="state_preparation",
            access_path="CQ.primitive('uniform_superposition')",
            requirements=("h",),
        ),
    )
    registry.register(
        "standard_diffuser",
        lambda: StandardDiffuser(circuit_factory=circuit_factory),
        descriptor=_descriptor(
            "standard_diffuser",
            "primitive",
            family="operator",
            role="diffuser",
            access_path="CQ.diffuser(num_qubits)",
            requirements=("x", "h", "mcx"),
        ),
    )
    registry.register(
        "qft",
        lambda: QFTPrimitive(circuit_factory=circuit_factory),
        descriptor=_descriptor(
            "qft",
            "primitive",
            family="fourier_transform",
            role="operator",
            access_path="CQ.qft(num_qubits)",
            requirements=("h", "cp", "swap"),
        ),
    )
    registry.register(
        "inverse_qft",
        lambda: InverseQFTPrimitive(circuit_factory=circuit_factory),
        descriptor=_descriptor(
            "inverse_qft",
            "primitive",
            family="fourier_transform",
            role="operator",
            access_path="CQ.iqft(num_qubits)",
            requirements=("h", "cp", "swap"),
        ),
    )
    registry.register(
        "coined_quantum_walk",
        lambda: CoinedQuantumWalkPrimitive(circuit_factory=circuit_factory),
        descriptor=_descriptor(
            "coined_quantum_walk",
            "primitive",
            family="navigation",
            role="walk",
            access_path="CQ.walk(graph, steps=...)",
            requirements=("h", "swap"),
        ),
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
        descriptor=_descriptor(
            "addressed_memory",
            "navigation",
            family="navigation",
            role="memory_load_oracle",
            access_path="CQ.nav(values)",
            requirements=("x", "cx", "mcx"),
        ),
    )
    registry.register(
        "graph_navigation",
        lambda: GraphNavigationEncoding(circuit_factory=circuit_factory),
        descriptor=_descriptor(
            "graph_navigation",
            "navigation",
            family="navigation",
            role="neighbor_oracle",
            access_path="CQ.graph_nav(graph)",
            requirements=("x", "cx", "mcx"),
        ),
    )
    return registry


def default_operator_registry(circuit_factory: Any = None) -> OperatorRegistry:
    from quantum_cq._circuits.primitives import PhaseRotationUnitary

    registry = OperatorRegistry()
    registry.register(
        "phase_rotation",
        lambda: PhaseRotationUnitary(circuit_factory=circuit_factory),
        descriptor=_descriptor(
            "phase_rotation",
            "operator",
            family="operator",
            role="unitary",
            access_path="CQ.phase_rotation(phase)",
            requirements=("p",),
        ),
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
        descriptor=_descriptor(
            "deutsch",
            "algorithm",
            family="oracle_algorithm",
            role="classification",
            access_path="CQ.deutsch(case=...)",
            requirements=("x", "h", "cx", "measure"),
        ),
    )
    registry.register(
        "deutsch_jozsa",
        lambda: DeutschJozsaAlgorithm(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        ),
        descriptor=_descriptor(
            "deutsch_jozsa",
            "algorithm",
            family="oracle_algorithm",
            role="classification",
            access_path="CQ.dj(kind=..., qubits=...)",
            requirements=("x", "h", "cx", "measure"),
        ),
    )
    registry.register(
        "bernstein_vazirani",
        lambda: BernsteinVaziraniAlgorithm(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        ),
        descriptor=_descriptor(
            "bernstein_vazirani",
            "algorithm",
            family="oracle_algorithm",
            role="bitstring_recovery",
            access_path="CQ.bv(secret)",
            requirements=("x", "h", "cx", "measure"),
        ),
    )
    registry.register(
        "grover",
        lambda: GroverAlgorithm(circuit_factory=circuit_factory),
        descriptor=_descriptor(
            "grover",
            "algorithm",
            family="search",
            role="amplitude_amplification",
            access_path="CQ.grover(marked_state)",
            requirements=("x", "h", "mcx", "measure"),
        ),
    )
    registry.register(
        "phase_estimation",
        lambda: PhaseEstimationAlgorithm(circuit_factory=circuit_factory),
        descriptor=_descriptor(
            "phase_estimation",
            "algorithm",
            family="phase_estimation",
            role="estimation",
            access_path="CQ.algorithm('phase_estimation')",
            requirements=("x", "h", "cp", "measure"),
        ),
    )
    registry.register(
        "qpe",
        lambda: PhaseEstimationAlgorithm(circuit_factory=circuit_factory, alias="qpe"),
        descriptor=_descriptor(
            "qpe",
            "algorithm",
            family="phase_estimation",
            role="estimation",
            access_path="CQ.qpe(phase, precision)",
            requirements=("x", "h", "cp", "measure"),
        ),
    )
    return registry
