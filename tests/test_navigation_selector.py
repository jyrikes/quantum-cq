import pytest

from quantum_cq import CQ
from quantum_cq.data import QuantumData
from quantum_cq.encodings import AngleEncoding, BasisEncoding
from quantum_cq.handlers import default_encoding_registry, default_navigation_registry
from quantum_cq.navigation import AddressedMemory, GraphData
from quantum_cq.selectors import EncodingSelectionContext, EncodingSelector


class DummyCircuitFactory:
    def create(self, num_qubits, num_clbits=0):
        raise AssertionError("selector should not build circuits")


def _encoder(encoder_type):
    return encoder_type(circuit_factory=DummyCircuitFactory())


def test_selector_preserves_state_role_behavior():
    selector = EncodingSelector([_encoder(BasisEncoding), _encoder(AngleEncoding)])

    assert selector.select(QuantumData([1, 0, 1])).name == "basis"
    assert selector.select(QuantumData([0.1, 0.2])).name == "angle"


def test_selector_navigation_role_chooses_addressed_memory_and_graph():
    selector = EncodingSelector(
        default_encoding_registry(circuit_factory=DummyCircuitFactory()),
        navigation_encoders=default_navigation_registry(circuit_factory=DummyCircuitFactory()),
    )

    memory_context = EncodingSelectionContext(data=AddressedMemory([1, 2]), role="navigation")
    graph = GraphData(edges=[(0, 1)], num_vertices=2)
    graph_context = EncodingSelectionContext(data=graph, role="navigation")

    assert selector.select(memory_context.data, context=memory_context).name == "addressed_memory"
    assert selector.select(graph_context.data, context=graph_context).name == "graph_navigation"


def test_selector_navigation_role_rejects_unknown_data_and_future_roles():
    selector = EncodingSelector(
        [_encoder(BasisEncoding)],
        navigation_encoders=default_navigation_registry(circuit_factory=DummyCircuitFactory()),
    )

    with pytest.raises(ValueError, match="navigation"):
        selector.select(object(), context=EncodingSelectionContext(data=object(), role="navigation"))

    for role in ("oracle", "operator"):
        with pytest.raises(NotImplementedError, match=role):
            selector.select([1, 0, 1], context=EncodingSelectionContext(data=[1, 0, 1], role=role))


def test_cq_encode_navigation_manual_does_not_use_state_selector():
    memory = AddressedMemory([1, 0])

    nav = CQ.encode(memory, role="navigation", encoding="addressed_memory")

    assert nav.navigation_name == "addressed_memory"
