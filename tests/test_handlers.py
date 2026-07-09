import pytest

from quantum_cq.handlers import (
    AlgorithmRegistry,
    EncodingRegistry,
    HandlerRegistry,
    OracleRegistry,
    PrimitiveRegistry,
    default_algorithm_registry,
    default_encoding_registry,
    default_navigation_registry,
    default_oracle_registry,
    default_primitive_registry,
)


def test_handler_registry_register_get_names_and_contains():
    registry = HandlerRegistry()

    class Handler:
        name = "basis"

    handler = Handler()

    registry.register(handler)

    assert "basis" in registry
    assert registry.contains("basis") is True
    assert registry.has("basis") is True
    assert registry.get("basis") is handler
    assert registry.names() == ["basis"]
    assert registry.all() == [handler]


def test_handler_registry_keeps_legacy_register_signature():
    registry = HandlerRegistry()
    handler = object()

    registry.register("legacy", handler)

    assert registry.get("legacy") is handler


def test_handler_registry_rejects_duplicate_without_override():
    registry = HandlerRegistry()

    class Handler:
        name = "basis"

    registry.register(Handler())

    with pytest.raises(ValueError, match="ja registrado"):
        registry.register(Handler())

    replacement = Handler()
    registry.register(replacement, override=True)

    assert registry.get("basis") is replacement


def test_handler_registry_get_missing_name_raises_clear_error():
    registry = HandlerRegistry()

    with pytest.raises(KeyError, match="Handler 'missing' nao registrado"):
        registry.get("missing")


def test_default_encoding_registry_registers_standard_encoders():
    class CircuitFactory:
        def create(self, num_qubits, num_clbits=0):
            raise AssertionError("not used here")

    circuit_factory = CircuitFactory()
    registry = default_encoding_registry(circuit_factory=circuit_factory)

    assert isinstance(registry, EncodingRegistry)
    assert "basis" in registry.names()
    assert "angle" in registry.names()
    assert "feature_map" not in registry.names()
    assert registry.get("basis").circuit_factory is circuit_factory


def test_factory_registries_return_new_instances_for_classes_and_factories():
    class Item:
        name = "item"

    for registry_type in (AlgorithmRegistry, OracleRegistry, PrimitiveRegistry):
        registry = registry_type()
        registry.register(Item)

        first = registry.get("item")
        second = registry.get("item")

        assert isinstance(first, Item)
        assert isinstance(second, Item)
        assert first is not second

    registry = AlgorithmRegistry()
    registry.register("factory_item", lambda: Item())

    assert registry.get("factory_item") is not registry.get("factory_item")


def test_default_algorithm_registry_injects_factory_and_returns_new_instances():
    class CircuitFactory:
        def create(self, num_qubits, num_clbits=0):
            raise AssertionError("not used here")

    circuit_factory = CircuitFactory()
    registry = default_algorithm_registry(circuit_factory=circuit_factory)

    assert {"deutsch", "deutsch_jozsa", "bernstein_vazirani"}.issubset(registry.names())
    assert {"grover", "phase_estimation", "qpe"}.issubset(registry.names())

    first = registry.get("deutsch")
    second = registry.get("deutsch")

    assert first is not second
    assert first.circuit_factory is circuit_factory


def test_default_oracle_and_primitive_registries_expose_factories():
    oracle_registry = default_oracle_registry()
    primitive_registry = default_primitive_registry(circuit_factory=object())

    assert {"deutsch", "deutsch_jozsa", "bernstein_vazirani", "phase_marked_state"}.issubset(
        oracle_registry.names()
    )
    assert {"uniform_superposition", "standard_diffuser", "qft", "inverse_qft"}.issubset(
        primitive_registry.names()
    )
    assert oracle_registry.get("deutsch") is not oracle_registry.get("deutsch")
    assert primitive_registry.get("qft") is not primitive_registry.get("qft")


def test_default_algorithm_operator_and_facade_registries_include_run2_items():
    from quantum_cq import CQ

    assert {"grover", "phase_estimation", "qpe"}.issubset(CQ.available_algorithms())
    assert "phase_marked_state" in CQ.available_oracles()
    assert {"standard_diffuser", "qft", "inverse_qft", "coined_quantum_walk"}.issubset(
        CQ.available_primitives()
    )
    assert "phase_rotation" in CQ.available_operators()

    assert CQ.algorithm("grover") is not CQ.algorithm("grover")
    assert CQ.algorithm("phase_estimation") is not CQ.algorithm("phase_estimation")
    assert CQ.primitive("qft") is not CQ.primitive("qft")
    assert CQ.operator("phase_rotation") is not CQ.operator("phase_rotation")


def test_default_navigation_registry_and_facade_return_new_instances():
    class CircuitFactory:
        def create(self, num_qubits, num_clbits=0):
            raise AssertionError("not used here")

    circuit_factory = CircuitFactory()
    registry = default_navigation_registry(circuit_factory=circuit_factory)

    assert {"addressed_memory", "graph_navigation"}.issubset(registry.names())
    assert registry.get("addressed_memory") is not registry.get("addressed_memory")
    assert registry.get("graph_navigation") is not registry.get("graph_navigation")
    assert registry.get("addressed_memory").circuit_factory is circuit_factory
