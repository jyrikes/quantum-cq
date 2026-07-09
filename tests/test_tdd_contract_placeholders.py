from quantum_cq import QuantumData
from quantum_cq.encodings import BasisEncoding, AngleEncoding, AmplitudeEncoding, PhaseEncoding


def test_quantum_data_preserves_value():
    data = QuantumData([1, 0, 1])
    assert data.value == [1, 0, 1]


def test_encoder_names_are_declared():
    assert BasisEncoding.name == "basis"
    assert AngleEncoding.name == "angle"
    assert AmplitudeEncoding.name == "amplitude"
    assert PhaseEncoding.name == "phase"
