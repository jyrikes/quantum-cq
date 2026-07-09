"""Basic addressed navigation example for quantum-cq."""

from quantum_cq import CQ


def main() -> None:
    memory = CQ.memory([3, 5, 7, 9])
    nav = CQ.nav(memory, engine="explicit")

    print("Addressed memory values:", memory.values)
    print("Semantics: U_D |a>|b> = |a>|b xor D[a]>")
    print("With b = 0: U_D |a>|0> = |a>|D[a]>")
    print()
    qc = CQ.to_qiskit(nav)
    print({"num_qubits": qc.num_qubits, "depth": qc.depth(), "size": qc.size()})
    print(CQ.metrics(nav))


if __name__ == "__main__":
    main()
