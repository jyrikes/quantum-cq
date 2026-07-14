import ast
from pathlib import Path

import numpy as np
import pytest
from qiskit import QuantumCircuit

from quantum_cq import CQ, CircuitDescriptor, CircuitRequirements, CustomUnitary
from quantum_cq._circuits.compact import CircuitValidationError, QC, m
from quantum_cq._core.circuits import CircuitService
from quantum_cq._engines.errors import CapabilityMismatchError


def _bell_builder():
    circuit = CQ.circuit(2, 2, name="bell", metadata={"purpose": "test"})
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure(0, 0)
    circuit.measure(1, 1)
    return circuit


def test_cq_circuit_builder_creates_logical_circuit_without_qiskit():
    circuit = _bell_builder()
    ir = circuit.build()
    descriptor = CircuitService().descriptor(circuit)
    requirements = CircuitService().requirements(circuit)

    assert ir.name == "bell"
    assert ir.metadata["purpose"] == "test"
    assert isinstance(descriptor, CircuitDescriptor)
    assert descriptor.circuit_format == "ir"
    assert descriptor.operations == ("h", "cx", "measure", "measure")
    assert isinstance(requirements, CircuitRequirements)
    assert requirements.measurement_total is True
    assert "cx" in requirements.features


def test_custom_unitary_is_defensive_immutable_and_qiskit_compatible():
    matrix = np.array([[0, 1], [1, 0]], dtype=complex)
    unitary = CQ.unitary(matrix, name="x_like", metadata={"source": "user"})
    matrix[0, 0] = 99

    assert isinstance(unitary, CustomUnitary)
    assert unitary.matrix[0][0] == 0
    assert unitary.num_qubits == 1
    with pytest.raises(TypeError):
        unitary.metadata["new"] = "forbidden"

    circuit = CQ.circuit(1, 1, name="with_unitary")
    circuit.unitary(unitary, [0])
    circuit.measure(0, 0)

    emitted = CQ.emit(circuit, engine="qiskit")
    assert isinstance(emitted, QuantumCircuit)
    assert emitted.count_ops().get("unitary", 0) == 1


def test_invalid_unitary_is_rejected_and_not_decomposed_silently():
    with pytest.raises(ValueError, match="not unitary"):
        CQ.unitary([[1, 1], [0, 1]], name="bad")

    unitary = CQ.unitary([[0, 1], [1, 0]])
    circuit = CQ.circuit(1)
    circuit.unitary(unitary, [0])

    if not CQ.engine_capabilities("cirq")["installed"]:
        pytest.skip("Cirq is not installed in the baseline environment")
    with pytest.raises(CapabilityMismatchError, match="not tested"):
        CQ.emit(circuit, engine="cirq")


def test_builder_rejects_structurally_invalid_operations():
    with pytest.raises(CircuitValidationError, match="qubits nao pode ser negativa|qubits nao pode ser"):
        CQ.circuit(-1)

    circuit = CQ.circuit(2, 1)
    with pytest.raises(CircuitValidationError, match="fora do intervalo"):
        circuit.x(5)
    with pytest.raises(CircuitValidationError, match="negativo"):
        circuit.measure(0, -1)
    with pytest.raises(CircuitValidationError, match="qubits distintos"):
        circuit.cx(0, 0)
    with pytest.raises(CircuitValidationError, match="duplicados"):
        circuit.mcx([0, 0], 1)
    with pytest.raises(CircuitValidationError, match="Alvo"):
        circuit.mcx([0, 1], 1)


def test_builder_unitary_uses_same_validation_and_single_payload_source():
    circuit = CQ.circuit(2)

    with pytest.raises(ValueError, match="not unitary"):
        circuit.unitary([[1, 1], [0, 1]], [0])
    with pytest.raises(ValueError, match="requires 1 qubits"):
        circuit.unitary([[0, 1], [1, 0]], [0, 1])
    with pytest.raises(CircuitValidationError, match="duplicados"):
        circuit.unitary(np.eye(4), [0, 0])

    unitary = CQ.unitary([[0, 1], [1, 0]], name="flip")
    circuit.unitary(unitary, [0])
    operation = circuit.build().layers[0].operations[0]

    assert "matrix" in operation.params
    assert "unitary" not in operation.params
    assert operation.params["name"] == "flip"


def test_public_builder_exposes_declared_logical_operations():
    circuit = CQ.circuit(3)
    circuit.y(0)
    circuit.z(1)
    circuit.ccx(0, 1, 2)

    descriptor = CircuitService().descriptor(circuit)

    assert descriptor.operations == ("y", "z", "ccx")


def test_composition_preserves_output_operations():
    sub = QC("measured", [[0, m(0)]], c=1).to_ir()
    parent = CQ.circuit(1, 1)
    parent.compose(sub)

    ir = parent.build()

    assert [op.kind for op in ir.outputs] == ["measure"]
    assert not any(op.kind == "measure" for layer in ir.layers for op in layer.operations)


def test_logical_composition_requires_explicit_mappings_when_registers_differ():
    sub = CQ.circuit(1, 1, name="sub")
    sub.x(0)
    sub.measure(0, 0)

    parent = CQ.circuit(2, 2, name="parent")
    with pytest.raises(CircuitValidationError, match="Mapeamento explicito"):
        parent.compose(sub)

    parent.compose(sub, qubit_map={0: 1}, clbit_map={0: 1}, label="sub_on_one")
    ir = parent.build()

    assert ir.metadata["subcircuits"] == ["sub_on_one"]
    operations = [op for layer in ir.layers for op in layer.operations]
    assert operations[0].qubits == (1,)
    assert operations[1].clbits == (1,)


def test_composition_does_not_convert_qiskit_to_ir():
    parent = CQ.circuit(1)
    native = QuantumCircuit(1)
    native.x(0)

    with pytest.raises(CircuitValidationError, match="Composicao logica requer"):
        parent.compose(native)


def test_qiskit_native_is_restricted_to_qiskit_flow():
    native = QuantumCircuit(1, 1)
    native.x(0)
    native.measure(0, 0)

    assert CircuitService().descriptor(native, engine="qiskit").circuit_format == "qiskit"
    descriptor = CircuitService().descriptor(native, engine="qiskit")
    assert descriptor.measurements == ((0, 0),)
    assert descriptor.operation_descriptors[0].kind == "x"
    assert descriptor.operation_descriptors[1].kind == "measure"
    with pytest.raises(TypeError, match="QuantumCircuit nativo"):
        CircuitService().descriptor(native, engine="cirq")


def test_intermediate_measurement_detects_real_operation_order():
    native = QuantumCircuit(1, 1)
    native.measure(0, 0)
    native.x(0)

    requirements = CircuitService().requirements(native, engine="qiskit")

    assert requirements.measurement_intermediate is True


def test_circuit_service_has_no_engine_or_provider_imports():
    path = Path("src/quantum_cq/_core/circuits.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert not any(module.startswith("quantum_cq._engines") for module in imported)
    assert not any(module.startswith("quantum_cq._hardware") for module in imported)
