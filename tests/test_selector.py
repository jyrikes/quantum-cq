import pytest

from quantum_cq.data import QuantumData
from quantum_cq.encodings import (
    AngleEncoding,
    BasisEncoding,
    DenseAngleEncoding,
    PhaseEncoding,
    ZFeatureMapEncoding,
)
from quantum_cq.handlers import default_encoding_registry
from quantum_cq.selectors import EncodingSelectionContext, EncodingSelector


class DummyCircuitFactory:
    def create(self, num_qubits, num_clbits=0):
        raise AssertionError("selector should not build circuits")


def encoder(encoder_type):
    return encoder_type(circuit_factory=DummyCircuitFactory())


def test_selector_resolves_external_hint_when_present():
    selector = EncodingSelector([encoder(BasisEncoding), encoder(AngleEncoding), encoder(PhaseEncoding)])

    chosen = selector.select(QuantumData([0.2, 0.4], metadata={"encoding_hint": "phase"}))

    assert chosen.name == "phase"


def test_selector_accepts_selection_context_without_changing_old_api():
    selector = EncodingSelector([encoder(BasisEncoding), encoder(AngleEncoding), encoder(PhaseEncoding)])
    context = EncodingSelectionContext(
        data=[0.2, 0.4],
        metadata={"encoding_hint": "phase"},
        algorithm_name="demo",
        role="input",
    )

    chosen = selector.select([0.2, 0.4], context=context)

    assert chosen.name == "phase"


@pytest.mark.parametrize("role", ["oracle", "operator"])
def test_selector_rejects_future_context_roles(role):
    selector = EncodingSelector([encoder(BasisEncoding), encoder(AngleEncoding)])
    context = EncodingSelectionContext(data=[1, 0, 1], role=role)

    with pytest.raises(NotImplementedError, match=role):
        selector.select([1, 0, 1], context=context)


def test_selector_raises_for_unknown_hint():
    selector = EncodingSelector([encoder(BasisEncoding), encoder(AngleEncoding)])

    with pytest.raises(ValueError, match="nao registrado"):
        selector.select(QuantumData([0.2, 0.4], metadata={"encoding_hint": "missing"}))


def test_selector_rejects_matching_hint_when_data_is_invalid():
    selector = EncodingSelector([encoder(ZFeatureMapEncoding), encoder(AngleEncoding)])

    with pytest.raises(ValueError, match="nao pode lidar"):
        selector.select(QuantumData(["a", "b"], metadata={"encoding_hint": "z_feature_map"}))


def test_selector_chooses_basis_for_binary_sequences():
    selector = EncodingSelector([encoder(AngleEncoding), encoder(BasisEncoding)])

    chosen = selector.select(QuantumData([1, 0, 1]))

    assert chosen.name == "basis"


def test_selector_chooses_angle_for_numeric_non_binary_sequences():
    selector = EncodingSelector([encoder(BasisEncoding), encoder(AngleEncoding)])

    chosen = selector.select(QuantumData([0.2, 1.4, -0.8]))

    assert chosen.name == "angle"


def test_selector_does_not_let_advanced_encoders_steal_angle_data():
    selector = EncodingSelector([encoder(DenseAngleEncoding), encoder(ZFeatureMapEncoding), encoder(AngleEncoding)])

    chosen = selector.select(QuantumData([0.2, 1.4, -0.8]))

    assert chosen.name == "angle"


def test_selector_rank_candidates_reports_auto_selectable_encoders_only():
    selector = EncodingSelector([encoder(DenseAngleEncoding), encoder(BasisEncoding), encoder(AngleEncoding)])

    ranked = selector.rank_candidates(QuantumData([0.2, 1.4]))

    assert [candidate["name"] for candidate in ranked] == ["angle"]


def test_selector_choose_alias_keeps_backward_compatibility():
    selector = EncodingSelector([encoder(BasisEncoding), encoder(AngleEncoding)])

    chosen = selector.choose(QuantumData([1, 0, 1]))

    assert chosen.name == "basis"


def test_selector_accepts_registry_by_injection():
    selector = EncodingSelector(default_encoding_registry())

    chosen = selector.select(QuantumData([1, 0, 1]))

    assert chosen.name == "basis"


def test_selector_raises_when_no_encoder_can_handle():
    class RefusingEncoder:
        name = "refusing"
        auto_selectable = True

        def can_handle(self, data):
            return False

    selector = EncodingSelector([RefusingEncoder()])

    with pytest.raises(ValueError, match="Nenhum encoding"):
        selector.select(QuantumData([0.1, 0.2]))
