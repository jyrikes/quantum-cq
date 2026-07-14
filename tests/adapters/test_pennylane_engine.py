import pytest

pytest.importorskip("pennylane")

from quantum_cq import CQ, EngineResult
from quantum_cq.adapters import LogicalCircuitFactory


def _bell_ir():
    builder = LogicalCircuitFactory().create(2, 2)
    builder.h(0)
    builder.cx(0, 1)
    builder.measure(0, 0)
    builder.measure(1, 1)
    return builder.build()


def test_pennylane_emit_compile_and_run_local_result():
    ir = _bell_ir()

    emitted = CQ.emit(ir, engine="pennylane", shots=64)
    compiled = CQ.compile(ir, engine="pennylane", shots=64)
    result = CQ.run_engine(ir, engine="pennylane", shots=64)

    assert emitted.__class__.__name__ == "QuantumScript"
    assert compiled.engine == "pennylane"
    assert isinstance(result, EngineResult)
    assert sum(result.counts.values()) == 64
    assert set(result.counts).issubset({"00", "11"})
    assert result.raw is not None
