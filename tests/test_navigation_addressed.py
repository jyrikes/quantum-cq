import pytest
import numpy as np
from qiskit.quantum_info import Operator

from quantum_cq import CQ
from quantum_cq.navigation import (
    AddressedMemory,
    AddressedMemoryEncoding,
    ExplicitCircuitMemoryEngine,
    OracleModelMemoryEngine,
    QRAMLikeMemoryEngine,
    SparseExplicitMemoryEngine,
)
from quantum_cq.results import NavigationCircuit


def _basis_output(matrix, input_index):
    column = matrix[:, input_index]
    output_index = max(range(len(column)), key=lambda index: abs(column[index]))
    assert abs(column[output_index]) == pytest.approx(1.0)
    return output_index


def _memory_index(memory, address, data_value):
    return address + (data_value << memory.address_qubits)


def test_addressed_memory_validates_and_calculates_metadata():
    memory = AddressedMemory([3, 1, 2], default_value=0)

    assert memory.memory_size == 3
    assert memory.address_qubits == 2
    assert memory.address_space_size == 4
    assert memory.data_qubits == 2
    assert memory.padded_values() == [3, 1, 2, 0]
    assert memory.value_at(3) == 0
    assert memory.to_metadata()["padded"] is True

    with pytest.raises(ValueError, match="vazio"):
        AddressedMemory([])
    with pytest.raises(ValueError, match="nao negativos"):
        AddressedMemory([1, -1])
    with pytest.raises(TypeError, match="bool"):
        AddressedMemory([True, False])
    with pytest.raises(ValueError, match="data_bit_width"):
        AddressedMemory([4], data_bit_width=2)
    with pytest.raises(ValueError, match="address_bit_width"):
        AddressedMemory([1, 2, 3], address_bit_width=1)


@pytest.mark.parametrize(
    ("engine", "model"),
    [
        (ExplicitCircuitMemoryEngine(), "explicit_circuit"),
        (SparseExplicitMemoryEngine(), "sparse_explicit_circuit"),
        (QRAMLikeMemoryEngine(), "qram_like"),
    ],
)
def test_memory_engines_implement_reversible_xor_load(engine, model):
    memory = AddressedMemory([3, 1, 2, 0])
    nav = engine.build_load_oracle(memory)

    assert isinstance(nav, NavigationCircuit)
    assert nav.navigation_name == "addressed_memory"
    assert nav.metadata["model"] == model
    assert nav.metadata["access_semantics"] == "xor_load"
    assert nav.metadata["reversible"] is True
    assert nav.metadata["physical_qram"] is False
    assert nav.metadata["simulates_qram_semantics"] is True
    assert nav.metadata["simulates_physical_qram"] is False

    matrix = np.asarray(Operator(CQ.to_qiskit(nav)).data, dtype=complex)
    for address in range(memory.address_space_size):
        for data_value in (0, 1, 2, 3):
            input_index = _memory_index(memory, address, data_value)
            output_index = _basis_output(matrix, input_index)
            expected = _memory_index(memory, address, data_value ^ memory.value_at(address))
            assert output_index == expected

    twice = matrix @ matrix
    assert twice == pytest.approx(np.eye(len(twice)))


def test_sparse_and_qram_like_metadata_are_honest():
    memory = AddressedMemory([3, 0, 2, 0])
    sparse = SparseExplicitMemoryEngine().build_load_oracle(memory)
    qram_like = QRAMLikeMemoryEngine().build_load_oracle(memory)

    assert sparse.metadata["nonzero_entries"] == 2
    assert sparse.metadata["skipped_zero_entries"] == 2
    assert sparse.metadata["model"] == "sparse_explicit_circuit"
    assert qram_like.metadata["model"] == "qram_like"
    assert qram_like.metadata["delegated_engine"] == "sparse_explicit_circuit"
    assert qram_like.metadata["physical_qram"] is False
    assert qram_like.metadata["simulates_qram_semantics"] is True
    assert qram_like.metadata["simulates_physical_qram"] is False


def test_oracle_model_memory_engine_does_not_return_fake_circuit():
    with pytest.raises(NotImplementedError, match="oracle_model"):
        OracleModelMemoryEngine().build_load_oracle(AddressedMemory([1, 2]))


def test_addressed_memory_encoding_and_facade_work_with_navigation_role():
    memory = CQ.memory([3, 5, 7, 9])

    nav = CQ.encode(memory, role="navigation", engine="explicit_circuit")
    sparse = CQ.encode(memory, role="navigation", engine="sparse_explicit_circuit")
    qram_like = CQ.encode(memory, role="navigation", engine="qram_like")
    manual = CQ.encode(memory, role="navigation", encoding="addressed_memory")

    assert isinstance(memory, AddressedMemory)
    assert isinstance(nav, NavigationCircuit)
    assert sparse.metadata["model"] == "sparse_explicit_circuit"
    assert qram_like.metadata["model"] == "qram_like"
    assert manual.navigation_name == "addressed_memory"
    assert CQ.metrics(nav)["navigation_name"] == "addressed_memory"
    assert CQ.to_qiskit(nav).num_qubits == memory.address_qubits + memory.data_qubits
    assert CQ.navigation("addressed_memory") is not CQ.navigation("addressed_memory")
    assert "addressed_memory" in CQ.available_navigation_encodings()

    with pytest.raises(NotImplementedError, match="oracle_model"):
        AddressedMemoryEncoding(engine="oracle_model").encode(memory)
