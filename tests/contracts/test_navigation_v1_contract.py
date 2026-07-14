import numpy as np
import pytest
from qiskit.quantum_info import Operator, Statevector

from quantum_cq import CQ
from quantum_cq.navigation import (
    AddressedMemory,
    AddressedMemoryEncoding,
    ExplicitCircuitMemoryEngine,
    OracleModelMemoryEngine,
    QRAMLikeMemoryEngine,
    SparseExplicitMemoryEngine,
)


MEMORY_CASES = [
    [0],
    [1],
    [3, 1, 2, 0],
    [3, 5, 7, 9],
    [3, 0, 2, 0],
]


def _basis_index(memory: AddressedMemory, address: int, data_value: int) -> int:
    return address + (data_value << memory.address_qubits)


def _basis_output(matrix: np.ndarray, input_index: int) -> int:
    column = matrix[:, input_index]
    output_index = int(np.argmax(np.abs(column)))
    assert column[output_index] == pytest.approx(1.0)
    assert np.count_nonzero(np.abs(column) > 1e-9) == 1
    return output_index


def _matrix(nav) -> np.ndarray:
    return np.asarray(Operator(CQ.to_qiskit(nav)).data, dtype=complex)


def _assert_navigation_v1_semantics(memory: AddressedMemory, matrix: np.ndarray) -> None:
    data_space = 2**memory.data_qubits
    for address in range(memory.address_space_size):
        for data_value in range(data_space):
            input_index = _basis_index(memory, address, data_value)
            output_index = _basis_output(matrix, input_index)
            expected_data = data_value ^ memory.value_at(address)
            assert output_index == _basis_index(memory, address, expected_data)
            assert output_index % memory.address_space_size == address


@pytest.mark.parametrize("values", MEMORY_CASES)
def test_navigation_v1_addressed_memory_shape_padding_and_width(values):
    memory = AddressedMemory(values)

    assert memory.memory_size == len(values)
    assert memory.address_space_size >= len(values)
    assert memory.address_space_size == 2**memory.address_qubits
    assert memory.data_qubits >= max(1, max(values).bit_length())
    assert memory.padded_values()[: len(values)] == values
    assert len(memory.padded_values()) == memory.address_space_size
    assert memory.to_metadata()["physical_qram"] is not True if "physical_qram" in memory.to_metadata() else True


@pytest.mark.parametrize(
    ("engine", "model"),
    [
        (ExplicitCircuitMemoryEngine(), "explicit_circuit"),
        (SparseExplicitMemoryEngine(), "sparse_explicit_circuit"),
        (QRAMLikeMemoryEngine(), "qram_like"),
    ],
)
@pytest.mark.parametrize("values", MEMORY_CASES)
def test_navigation_v1_engines_preserve_xor_load_and_metadata(engine, model, values):
    memory = AddressedMemory(values)
    nav = engine.build_load_oracle(memory)
    matrix = _matrix(nav)

    _assert_navigation_v1_semantics(memory, matrix)
    assert matrix.conj().T @ matrix == pytest.approx(np.eye(matrix.shape[0]))
    assert matrix @ matrix == pytest.approx(np.eye(matrix.shape[0]))

    metadata = nav.metadata
    assert nav.navigation_name == "addressed_memory"
    assert nav.circuit_format == "qiskit"
    assert metadata["model"] == model
    assert metadata["access_semantics"] == "xor_load"
    assert metadata["reversible"] is True
    assert metadata["physical_qram"] is False
    assert metadata["simulates_qram_semantics"] is True
    assert metadata["simulates_physical_qram"] is False
    assert metadata["address_bit_order"] == "little_endian_int"
    assert metadata["data_bit_order"] == "little_endian_int"
    assert metadata["address_qubits"] == memory.address_qubits
    assert metadata["data_qubits"] == memory.data_qubits
    assert metadata["memory_size"] == memory.memory_size
    assert metadata["address_space_size"] == memory.address_space_size
    assert CQ.to_qiskit(nav).num_qubits == memory.address_qubits + memory.data_qubits


def test_navigation_v1_sparse_and_qram_like_metadata_remain_honest():
    memory = AddressedMemory([3, 0, 2, 0])
    sparse = SparseExplicitMemoryEngine().build_load_oracle(memory)
    qram_like = QRAMLikeMemoryEngine().build_load_oracle(memory)

    assert sparse.metadata["nonzero_entries"] == 2
    assert sparse.metadata["skipped_zero_entries"] == 2
    assert sparse.metadata["physical_qram"] is False
    assert qram_like.metadata["model"] == "qram_like"
    assert qram_like.metadata["delegated_engine"] == "sparse_explicit_circuit"
    assert qram_like.metadata["physical_qram"] is False
    assert qram_like.metadata["simulates_physical_qram"] is False


def test_navigation_v1_superposition_query_matches_linear_xor_load():
    memory = AddressedMemory([3, 1, 2, 0])
    nav = ExplicitCircuitMemoryEngine().build_load_oracle(memory)
    circuit = CQ.to_qiskit(nav)

    initial = np.zeros(2 ** circuit.num_qubits, dtype=complex)
    inputs = [
        _basis_index(memory, 0, 0),
        _basis_index(memory, 1, 1),
        _basis_index(memory, 2, 2),
        _basis_index(memory, 3, 3),
    ]
    for index in inputs:
        initial[index] = 0.5

    evolved = Statevector(initial).evolve(circuit).data
    expected = np.zeros_like(initial)
    for address, data_value in [(0, 0), (1, 1), (2, 2), (3, 3)]:
        expected[_basis_index(memory, address, data_value ^ memory.value_at(address))] = 0.5

    assert evolved == pytest.approx(expected)


def test_navigation_v1_facade_and_encoding_apis_are_stable():
    memory = CQ.memory([3, 5, 7, 9])
    nav = CQ.nav(memory)
    addressed = CQ.addressed(memory, engine="sparse")
    encoded = CQ.encode(memory, role="navigation", encoding="addressed_memory")
    manual = AddressedMemoryEncoding(engine="explicit_circuit").encode(memory)

    assert isinstance(memory, AddressedMemory)
    assert nav.metadata["model"] == "explicit_circuit"
    assert addressed.metadata["model"] == "sparse_explicit_circuit"
    assert encoded.navigation_name == "addressed_memory"
    assert manual.metadata["access_semantics"] == "xor_load"
    assert CQ.metrics(nav)["navigation_name"] == "addressed_memory"


def test_navigation_v1_oracle_model_failure_remains_explicit():
    with pytest.raises(NotImplementedError, match="oracle_model"):
        OracleModelMemoryEngine().build_load_oracle(AddressedMemory([1, 2]))
