"""Basic state encoding example for quantum-cq."""

from quantum_cq import CQ


def main() -> None:
    basis = CQ.state([1, 0, 1], encoding="basis")
    angle = CQ.state([0.1, 0.2, 0.3], encoding="angle")

    print("Basis encoding")
    basis_qc = CQ.to_qiskit(basis)
    print({"num_qubits": basis_qc.num_qubits, "depth": basis_qc.depth()})
    print(CQ.metrics(basis))

    print("\nAngle encoding")
    angle_qc = CQ.to_qiskit(angle)
    print({"num_qubits": angle_qc.num_qubits, "depth": angle_qc.depth()})
    print(CQ.metrics(angle))


if __name__ == "__main__":
    main()
