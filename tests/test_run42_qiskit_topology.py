from qiskit.circuit.library import CXGate, Measure, XGate
from qiskit.transpiler import InstructionProperties, Target

from quantum_cq import CQ
from quantum_cq._hardware.providers.qiskit import target_from_qiskit


def test_run42_qiskit_target_extracts_directional_topology_and_snapshot():
    native = Target(num_qubits=3)
    native.add_instruction(
        XGate(),
        {
            (0,): InstructionProperties(duration=1.0e-8, error=0.001),
            (1,): InstructionProperties(duration=1.1e-8, error=0.002),
            (2,): InstructionProperties(duration=1.2e-8, error=0.003),
        },
    )
    native.add_instruction(
        CXGate(),
        {
            (0, 1): InstructionProperties(duration=2.0e-7, error=0.01),
            (1, 2): InstructionProperties(duration=3.0e-7, error=0.02),
        },
    )
    native.add_instruction(
        Measure(),
        {
            (0,): InstructionProperties(duration=5.0e-7, error=0.04),
            (1,): InstructionProperties(duration=5.1e-7, error=0.05),
            (2,): InstructionProperties(duration=5.2e-7, error=0.06),
        },
    )

    target = target_from_qiskit(native, name="line3")

    assert target.descriptor.provider == "qiskit"
    assert target.descriptor.target_type == "unknown"
    assert target.architecture.qubits == ("q0", "q1", "q2")
    assert {instruction.name for instruction in target.architecture.instructions} == {"x", "cx", "measure"}
    cx = next(instruction for instruction in target.architecture.instructions if instruction.name == "cx")
    assert cx.arity == 2
    assert cx.valid_connections == (("q0", "q1"), ("q1", "q2"))
    assert cx.directional is True

    edges = {(edge.source, edge.target, edge.directed, edge.operations) for edge in target.architecture.topology}
    assert ("q0", "q1", True, ("cx",)) in edges
    assert ("q1", "q2", True, ("cx",)) in edges
    assert ("q1", "q0", True, ("cx",)) not in edges
    assert ("q2", "q1", True, ("cx",)) not in edges

    assert target.snapshot is not None
    assert target.snapshot.calibration_available == "known"
    assert target.snapshot.instruction_properties["cx:q0,q1"]["duration"].value == 2.0e-7
    assert target.snapshot.connection_properties["q1->q2:cx"]["error"].value == 0.02
    assert not target.architecture.topology[0].properties
    assert "target.qargs" in target.provenance.transformed_fields
    assert target.provenance.source == "explicit_object"


def test_run42_qiskit_fake_backend_uses_explicit_target_without_network():
    class FakeConfig:
        simulator = True

    class FakeBackend:
        name = "fake_line"
        num_qubits = 2

        def __init__(self):
            target = Target(num_qubits=2)
            target.add_instruction(CXGate(), {(0, 1): InstructionProperties(duration=1.0e-7, error=0.01)})
            self.target = target

        def configuration(self):
            return FakeConfig()

    target = CQ.target_from_qiskit(FakeBackend())

    assert target.descriptor.target_type == "simulator_ideal"
    assert target.architecture.qubits == ("q0", "q1")
    assert target.architecture.topology[0].source == "q0"
    assert target.architecture.topology[0].target == "q1"
    assert target.snapshot is not None
