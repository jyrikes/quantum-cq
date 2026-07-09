import pytest
from typing import Any, Sequence

from quantum_cq.data import QuantumData
from quantum_cq.encodings import (
    AngleEncoding,
    AmplitudeEncoding,
    BasisEncoding,
    DataReUploadingEncoding,
    DenseAngleEncoding,
    FeatureMapEncoder,
    IQPEncoding,
    PauliFeatureMapEncoding,
    PhaseEncoding,
    ZFeatureMapEncoding,
    ZZFeatureMapEncoding,
)
from quantum_cq.interfaces import EncodingHandler, EncodingProtocol
from quantum_cq.results import EncodedCircuit


class FakeCircuitBuilder:
    def __init__(self, num_qubits: int):
        self.num_qubits = num_qubits
        self.ops: list[tuple[Any, ...]] = []
        self.qubits = list(range(num_qubits))

    def x(self, qubit: int) -> None:
        self.ops.append(("x", qubit))

    def h(self, qubit: int) -> None:
        self.ops.append(("h", qubit))

    def rx(self, theta: float, qubit: int) -> None:
        self.ops.append(("rx", theta, qubit))

    def ry(self, theta: float, qubit: int) -> None:
        self.ops.append(("ry", theta, qubit))

    def rz(self, theta: float, qubit: int) -> None:
        self.ops.append(("rz", theta, qubit))

    def p(self, theta: float, qubit: int) -> None:
        self.ops.append(("p", theta, qubit))

    def cx(self, control: int, target: int) -> None:
        self.ops.append(("cx", control, target))

    def cz(self, control: int, target: int) -> None:
        self.ops.append(("cz", control, target))

    def cp(self, theta: float, control: int, target: int) -> None:
        self.ops.append(("cp", theta, control, target))

    def mcx(self, controls: Sequence[int], target: int) -> None:
        self.ops.append(("mcx", tuple(controls), target))

    def swap(self, left: int, right: int) -> None:
        self.ops.append(("swap", left, right))

    def unitary(self, matrix: Any, qubits: Sequence[int], label: str | None = None) -> None:
        raise NotImplementedError("FakeCircuitBuilder nao suporta unitary")

    def measure(self, qubit: int, clbit: int) -> None:
        self.ops.append(("measure", qubit, clbit))

    def barrier(self) -> None:
        self.ops.append(("barrier",))

    def initialize(self, amplitudes: Sequence[complex], qubits: Sequence[int]) -> None:
        self.ops.append(("initialize", tuple(amplitudes), tuple(qubits)))

    def measure_all(self) -> None:
        self.ops.append(("measure_all",))

    def count_ops(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for op in self.ops:
            counts[op[0]] = counts.get(op[0], 0) + 1
        return counts

    @property
    def data(self):
        class Operation:
            def __init__(self, name):
                self.name = name

        class Instruction:
            def __init__(self, name):
                self.operation = Operation(name)

        return [Instruction(op[0]) for op in self.ops]

    def build(self) -> "FakeCircuitBuilder":
        return self


class FakeCircuitFactory:
    def __init__(self) -> None:
        self.builders: list[FakeCircuitBuilder] = []

    def create(self, num_qubits: int, num_clbits: int = 0) -> FakeCircuitBuilder:
        builder = FakeCircuitBuilder(num_qubits)
        self.builders.append(builder)
        return builder


def make_encoder(encoder_type):
    return encoder_type(circuit_factory=FakeCircuitFactory())


def test_encoded_circuit_dataclass_exposes_core_fields():
    assert EncodedCircuit.__name__ == "EncodedCircuit"


def test_encoder_without_circuit_factory_fails_clearly():
    with pytest.raises(ValueError, match="circuit_factory"):
        BasisEncoding()


def test_new_encoders_implement_interface():
    encoders = [
        make_encoder(DenseAngleEncoding),
        make_encoder(PauliFeatureMapEncoding),
        make_encoder(ZFeatureMapEncoding),
        make_encoder(ZZFeatureMapEncoding),
        make_encoder(IQPEncoding),
        make_encoder(DataReUploadingEncoding),
        make_encoder(FeatureMapEncoder),
    ]

    assert all(isinstance(encoder, EncodingHandler) for encoder in encoders)
    assert EncodingHandler is EncodingProtocol


def test_basis_encoding_handles_binary_sequences_and_encodes_x_gates():
    factory = FakeCircuitFactory()
    encoder = BasisEncoding(circuit_factory=factory)
    data = QuantumData([1, 0, 1])

    assert encoder.name == "basis"
    assert encoder.family == "basis"
    assert encoder.auto_selectable is True
    assert encoder.can_handle(data) is True
    assert encoder.can_handle([True, False]) is False
    assert encoder.can_handle([1.0, 0.0, 1.5]) is False

    encoded = encoder.encode(data)

    assert encoded.circuit is factory.builders[0]
    assert encoded.encoding_name == "basis"
    assert encoded.metadata["encoding_name"] == "basis"
    assert encoded.metadata["num_qubits"] == 3
    assert encoded.metadata["family"] == "basis"
    assert encoded.metadata["input_size"] == 3
    assert encoded.metadata["bitstring"] == "101"
    assert encoded.metadata["gates_applied"] == ["x", "x"]
    assert encoded.circuit.ops == [("x", 0), ("x", 2)]


def test_angle_encoding_handles_numeric_non_binary_sequences():
    encoder = make_encoder(AngleEncoding)

    assert encoder.name == "angle"
    assert encoder.family == "rotation"
    assert encoder.auto_selectable is True
    assert encoder.can_handle(QuantumData([0.1, 1.25, -0.5])) is True
    assert encoder.can_handle([0, 1, 0]) is False

    encoded = encoder.encode(QuantumData([0.1, 1.25, -0.5]))

    assert encoded.encoding_name == "angle"
    assert encoded.metadata["rotation_axis"] == "ry"
    assert encoded.metadata["family"] == "rotation"
    assert encoded.metadata["input_size"] == 3
    assert encoded.metadata["num_qubits"] == 3
    assert [op[0] for op in encoded.circuit.ops] == ["ry", "ry", "ry"]


def test_phase_encoding_uses_phase_gates_without_hint_policy():
    encoder = make_encoder(PhaseEncoding)

    assert encoder.auto_selectable is False
    assert encoder.can_handle(QuantumData([0.1, 0.2])) is True

    encoded = encoder.encode(QuantumData([0.1, 0.2]))

    assert encoded.encoding_name == "phase"
    assert encoded.metadata["gate"] == "p"
    assert encoded.metadata["family"] == "rotation"
    assert encoded.metadata["input_size"] == 2
    assert encoded.metadata["num_qubits"] == 2
    assert [op[0] for op in encoded.circuit.ops] == ["p", "p"]


def test_amplitude_encoding_normalizes_when_needed():
    encoder = make_encoder(AmplitudeEncoding)

    assert encoder.auto_selectable is False
    assert encoder.can_handle(QuantumData([1.0, 1.0, 1.0, 1.0])) is True

    encoded = encoder.encode(QuantumData([1.0, 1.0, 1.0, 1.0]))

    assert encoded.encoding_name == "amplitude"
    assert encoded.metadata["family"] == "amplitude"
    assert encoded.metadata["input_size"] == 4
    assert encoded.metadata["num_qubits"] == 2
    assert encoded.metadata["normalized"] is True
    assert encoded.metadata["norm"] == pytest.approx(2.0)
    assert encoded.circuit.ops[0][0] == "initialize"


def test_amplitude_encoding_rejects_non_power_of_two_size():
    encoder = make_encoder(AmplitudeEncoding)

    with pytest.raises(ValueError, match="potencia de 2"):
        encoder.encode(QuantumData([1.0, 0.0, 0.0]))


def test_dense_angle_encoding_uses_two_features_per_qubit():
    encoder = make_encoder(DenseAngleEncoding)

    assert encoder.auto_selectable is False
    assert encoder.can_handle(QuantumData([0.1, 0.2, 0.3, 0.4])) is True

    encoded = encoder.encode(QuantumData([0.1, 0.2, 0.3, 0.4]))

    assert encoded.encoding_name == "dense_angle"
    assert encoded.metadata["family"] == "rotation"
    assert encoded.metadata["features_per_qubit"] == 2
    assert encoded.metadata["input_size"] == 4
    assert encoded.metadata["num_qubits"] == 2
    assert [op[0] for op in encoded.circuit.ops] == ["ry", "rz", "ry", "rz"]


def test_pauli_feature_map_encoding_builds_layered_feature_map():
    encoder = make_encoder(PauliFeatureMapEncoding)

    assert encoder.auto_selectable is False
    assert encoder.can_handle(QuantumData([0.1, 0.2])) is True

    encoded = encoder.encode(QuantumData([0.1, 0.2], metadata={"paulis": ["x", "zz"]}))

    assert encoded.encoding_name == "pauli_feature_map"
    assert encoded.metadata["family"] == "feature_map"
    assert encoded.metadata["feature_map"] == "pauli"
    assert encoded.metadata["paulis"] == ["x", "zz"]
    assert "h" in encoded.circuit.count_ops()
    assert "rx" in encoded.circuit.count_ops()
    assert "cx" in encoded.circuit.count_ops()


def test_pauli_feature_map_encoding_rejects_invalid_pauli():
    encoder = make_encoder(PauliFeatureMapEncoding)

    with pytest.raises(ValueError, match="pauli invalido"):
        encoder.encode(QuantumData([0.1, 0.2], metadata={"paulis": ["abc"]}))


def test_z_feature_map_encoding_uses_z_phases():
    encoder = make_encoder(ZFeatureMapEncoding)

    encoded = encoder.encode(QuantumData([0.1, 0.2]))

    assert encoded.encoding_name == "z_feature_map"
    assert encoded.metadata["family"] == "feature_map"
    assert encoded.metadata["feature_map"] == "z"
    assert encoded.circuit.count_ops()["h"] == 2
    assert encoded.circuit.count_ops()["p"] == 2


def test_zz_feature_map_encoding_adds_pairwise_interactions():
    encoder = make_encoder(ZZFeatureMapEncoding)

    encoded = encoder.encode(QuantumData([0.1, 0.2]))

    assert encoded.encoding_name == "zz_feature_map"
    assert encoded.metadata["family"] == "feature_map"
    assert encoded.metadata["feature_map"] == "zz"
    assert "cx" in encoded.circuit.count_ops()
    assert "p" in encoded.circuit.count_ops()


def test_iqp_encoding_uses_h_diagonal_h_structure():
    encoder = make_encoder(IQPEncoding)

    encoded = encoder.encode(QuantumData([0.1, 0.2]))

    assert encoded.encoding_name == "iqp"
    assert encoded.metadata["family"] == "feature_map"
    assert encoded.metadata["feature_map"] == "iqp"
    assert encoded.circuit.ops[0][0] == "h"
    assert encoded.circuit.ops[-1][0] == "h"


def test_data_reuploading_encoding_repeats_layers():
    encoder = make_encoder(DataReUploadingEncoding)

    encoded = encoder.encode(QuantumData([0.1, 0.2], metadata={"repetitions": 3}))

    assert encoded.encoding_name == "data_reuploading"
    assert encoded.metadata["family"] == "feature_map"
    assert encoded.metadata["repetitions"] == 3
    assert encoded.metadata["num_layers"] == 3
    assert encoded.circuit.count_ops()["ry"] == 6
    assert encoded.circuit.count_ops()["barrier"] == 2


def test_feature_map_encoder_remains_available_but_not_auto_selectable():
    encoder = make_encoder(FeatureMapEncoder)

    assert encoder.name == "feature_map"
    assert encoder.family == "feature_map"
    assert encoder.auto_selectable is False
    assert encoder.can_handle(QuantumData([0.1, 0.2])) is True


def test_encoders_use_injected_circuit_factory():
    factory = FakeCircuitFactory()
    encoder = BasisEncoding(circuit_factory=factory)

    encoded = encoder.encode(QuantumData([1, 0, 1]))

    assert encoded.circuit is factory.builders[0]
    assert factory.builders[0].num_qubits == 3
    assert factory.builders[0].ops == [("x", 0), ("x", 2)]
