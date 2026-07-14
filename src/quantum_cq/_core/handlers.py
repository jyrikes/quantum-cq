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


class DescriptorRegistry:
    """Read-only descriptor view over registered public components."""

    descriptor_only = True

    def __init__(self, descriptors: tuple[ComponentDescriptor, ...]) -> None:
        self._descriptors = {descriptor.name: descriptor for descriptor in descriptors}

    def names(self) -> list[str]:
        return list(self._descriptors)

    def descriptor(self, name: str) -> ComponentDescriptor:
        if name not in self._descriptors:
            raise KeyError(f"Descriptor '{name}' nao registrado")
        return self._descriptors[name]

    def descriptors(self) -> tuple[ComponentDescriptor, ...]:
        return tuple(self._descriptors[name] for name in self.names())


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


def default_encoding_descriptors() -> tuple[ComponentDescriptor, ...]:
    specs = {
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
    return tuple(
        _descriptor(
            name,
            "encoding",
            family=family,
            role="state_encoding",
            access_path=f"CQ.state(..., encoding='{name}')",
            requirements=requirements,
        )
        for name, (family, requirements) in specs.items()
    )


def default_oracle_descriptors() -> tuple[ComponentDescriptor, ...]:
    return (
        _descriptor(
            "deutsch",
            "oracle",
            family="boolean_oracle",
            role="predicate_oracle",
            access_path="CQ.oracle('deutsch', case=...)",
            requirements=("x", "cx"),
        ),
        _descriptor(
            "bernstein_vazirani",
            "oracle",
            family="boolean_oracle",
            role="predicate_oracle",
            access_path="CQ.oracle('bernstein_vazirani', secret=...)",
            requirements=("cx",),
        ),
        _descriptor(
            "deutsch_jozsa",
            "oracle",
            family="boolean_oracle",
            role="predicate_oracle",
            access_path="CQ.oracle('deutsch_jozsa', ...)",
            requirements=("x", "cx"),
        ),
        _descriptor(
            "phase_marked_state",
            "oracle",
            family="oracle",
            role="phase_oracle",
            access_path="CQ.oracle('phase_marked_state', marked_state=...)",
            requirements=("x", "h", "mcx"),
        ),
    )


def default_primitive_descriptors() -> tuple[ComponentDescriptor, ...]:
    return (
        _descriptor(
            "uniform_superposition",
            "primitive",
            family="state_preparation",
            role="state_preparation",
            access_path="CQ.primitive('uniform_superposition')",
            requirements=("h",),
        ),
        _descriptor(
            "standard_diffuser",
            "primitive",
            family="operator",
            role="diffuser",
            access_path="CQ.diffuser(num_qubits)",
            requirements=("x", "h", "mcx"),
        ),
        _descriptor(
            "qft",
            "primitive",
            family="fourier_transform",
            role="operator",
            access_path="CQ.qft(num_qubits)",
            requirements=("h", "cp", "swap"),
        ),
        _descriptor(
            "inverse_qft",
            "primitive",
            family="fourier_transform",
            role="operator",
            access_path="CQ.iqft(num_qubits)",
            requirements=("h", "cp", "swap"),
        ),
        _descriptor(
            "coined_quantum_walk",
            "primitive",
            family="navigation",
            role="walk",
            access_path="CQ.walk(graph, steps=...)",
            requirements=("h", "swap"),
        ),
    )


def default_navigation_descriptors() -> tuple[ComponentDescriptor, ...]:
    return (
        _descriptor(
            "addressed_memory",
            "navigation",
            family="navigation",
            role="memory_load_oracle",
            access_path="CQ.nav(values)",
            requirements=("x", "cx", "mcx"),
        ),
        _descriptor(
            "graph_navigation",
            "navigation",
            family="navigation",
            role="neighbor_oracle",
            access_path="CQ.graph_nav(graph)",
            requirements=("x", "cx", "mcx"),
        ),
        _descriptor(
            "structural_navigation_v2",
            "navigation",
            family="navigation",
            role="structural_navigation",
            access_path="CQ.navigation_v2(heap, operation=...)",
            requirements=("x", "cx", "mcx"),
            navigation_version="v2",
            exactness="exact",
            supported_structures=("typed_finite_heap",),
            lowering_strategies=("explicit_exact", "sparse_exact", "oracle_model"),
            limitations=(
                "finite exact domain only",
                "no dynamic allocation",
                "no approximate structural encoding",
            ),
        ),
    )


def default_operator_descriptors() -> tuple[ComponentDescriptor, ...]:
    return (
        _descriptor(
            "phase_rotation",
            "operator",
            family="operator",
            role="unitary",
            access_path="CQ.phase_rotation(phase)",
            requirements=("p",),
        ),
    )


def default_algorithm_descriptors() -> tuple[ComponentDescriptor, ...]:
    return (
        _descriptor(
            "deutsch",
            "algorithm",
            family="oracle_algorithm",
            role="classification",
            access_path="CQ.deutsch(case=...)",
            requirements=("x", "h", "cx", "measure"),
        ),
        _descriptor(
            "deutsch_jozsa",
            "algorithm",
            family="oracle_algorithm",
            role="classification",
            access_path="CQ.dj(kind=..., qubits=...)",
            requirements=("x", "h", "cx", "measure"),
        ),
        _descriptor(
            "bernstein_vazirani",
            "algorithm",
            family="oracle_algorithm",
            role="bitstring_recovery",
            access_path="CQ.bv(secret)",
            requirements=("x", "h", "cx", "measure"),
        ),
        _descriptor(
            "grover",
            "algorithm",
            family="search",
            role="amplitude_amplification",
            access_path="CQ.grover(marked_state)",
            requirements=("x", "h", "mcx", "measure"),
        ),
        _descriptor(
            "phase_estimation",
            "algorithm",
            family="phase_estimation",
            role="estimation",
            access_path="CQ.algorithm('phase_estimation')",
            requirements=("x", "h", "cp", "measure"),
        ),
        _descriptor(
            "qpe",
            "algorithm",
            family="phase_estimation",
            role="estimation",
            access_path="CQ.qpe(phase, precision)",
            requirements=("x", "h", "cp", "measure"),
        ),
    )


def default_component_descriptor_registries() -> dict[str, DescriptorRegistry]:
    return {
        "encoding": DescriptorRegistry(default_encoding_descriptors()),
        "oracle": DescriptorRegistry(default_oracle_descriptors()),
        "primitive": DescriptorRegistry(default_primitive_descriptors()),
        "operator": DescriptorRegistry(default_operator_descriptors()),
        "algorithm": DescriptorRegistry(default_algorithm_descriptors()),
        "navigation": DescriptorRegistry(default_navigation_descriptors()),
    }


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
    descriptors = {descriptor.name: descriptor for descriptor in default_encoding_descriptors()}
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
        registry.register(
            encoder,
            descriptor=descriptors[encoder.name],
        )

    return registry


def default_oracle_registry(circuit_factory: Any = None) -> OracleRegistry:
    from quantum_cq._circuits.oracles import BernsteinVaziraniOracle, DeutschJozsaOracle, DeutschOracle, PhaseMarkedStateOracle

    registry = OracleRegistry()
    descriptors = {descriptor.name: descriptor for descriptor in default_oracle_descriptors()}
    registry.register(
        DeutschOracle,
        descriptor=descriptors["deutsch"],
    )
    registry.register(
        BernsteinVaziraniOracle,
        descriptor=descriptors["bernstein_vazirani"],
    )
    registry.register(
        DeutschJozsaOracle,
        descriptor=descriptors["deutsch_jozsa"],
    )
    registry.register(
        "phase_marked_state",
        lambda *args, **kwargs: PhaseMarkedStateOracle(
            *args,
            circuit_factory=kwargs.pop("circuit_factory", circuit_factory),
            **kwargs,
        ),
        descriptor=descriptors["phase_marked_state"],
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
    descriptors = {descriptor.name: descriptor for descriptor in default_primitive_descriptors()}
    registry.register(
        "uniform_superposition",
        lambda: UniformSuperpositionPreparation(circuit_factory=circuit_factory),
        descriptor=descriptors["uniform_superposition"],
    )
    registry.register(
        "standard_diffuser",
        lambda: StandardDiffuser(circuit_factory=circuit_factory),
        descriptor=descriptors["standard_diffuser"],
    )
    registry.register(
        "qft",
        lambda: QFTPrimitive(circuit_factory=circuit_factory),
        descriptor=descriptors["qft"],
    )
    registry.register(
        "inverse_qft",
        lambda: InverseQFTPrimitive(circuit_factory=circuit_factory),
        descriptor=descriptors["inverse_qft"],
    )
    registry.register(
        "coined_quantum_walk",
        lambda: CoinedQuantumWalkPrimitive(circuit_factory=circuit_factory),
        descriptor=descriptors["coined_quantum_walk"],
    )
    return registry


def default_navigation_registry(circuit_factory: Any = None) -> NavigationRegistry:
    if circuit_factory is None:
        from quantum_cq._circuits.adapters import QiskitCircuitFactory

        circuit_factory = QiskitCircuitFactory()

    from quantum_cq._navigation.memory import AddressedMemoryEncoding, GraphNavigationEncoding

    registry = NavigationRegistry()
    descriptors = {descriptor.name: descriptor for descriptor in default_navigation_descriptors()}
    registry.register(
        "addressed_memory",
        lambda: AddressedMemoryEncoding(circuit_factory=circuit_factory),
        descriptor=descriptors["addressed_memory"],
    )
    registry.register(
        "graph_navigation",
        lambda: GraphNavigationEncoding(circuit_factory=circuit_factory),
        descriptor=descriptors["graph_navigation"],
    )
    return registry


def default_operator_registry(circuit_factory: Any = None) -> OperatorRegistry:
    from quantum_cq._circuits.primitives import PhaseRotationUnitary

    registry = OperatorRegistry()
    descriptors = {descriptor.name: descriptor for descriptor in default_operator_descriptors()}
    registry.register(
        "phase_rotation",
        lambda: PhaseRotationUnitary(circuit_factory=circuit_factory),
        descriptor=descriptors["phase_rotation"],
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
    descriptors = {descriptor.name: descriptor for descriptor in default_algorithm_descriptors()}
    registry.register(
        "deutsch",
        lambda: DeutschAlgorithm(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        ),
        descriptor=descriptors["deutsch"],
    )
    registry.register(
        "deutsch_jozsa",
        lambda: DeutschJozsaAlgorithm(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        ),
        descriptor=descriptors["deutsch_jozsa"],
    )
    registry.register(
        "bernstein_vazirani",
        lambda: BernsteinVaziraniAlgorithm(
            circuit_factory=circuit_factory,
            oracle_registry=oracle_registry,
        ),
        descriptor=descriptors["bernstein_vazirani"],
    )
    registry.register(
        "grover",
        lambda: GroverAlgorithm(circuit_factory=circuit_factory),
        descriptor=descriptors["grover"],
    )
    registry.register(
        "phase_estimation",
        lambda: PhaseEstimationAlgorithm(circuit_factory=circuit_factory),
        descriptor=descriptors["phase_estimation"],
    )
    registry.register(
        "qpe",
        lambda: PhaseEstimationAlgorithm(circuit_factory=circuit_factory, alias="qpe"),
        descriptor=descriptors["qpe"],
    )
    return registry
