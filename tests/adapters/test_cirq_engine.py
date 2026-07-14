import pytest

pytest.importorskip("cirq")

from quantum_cq import CQ, EngineResult
from quantum_cq.adapters import LogicalCircuitFactory


def _bell_ir():
    builder = LogicalCircuitFactory().create(2, 2)
    builder.h(0)
    builder.cx(0, 1)
    builder.measure(0, 0)
    builder.measure(1, 1)
    return builder.build()


def test_cirq_emit_compile_and_run_local_result():
    ir = _bell_ir()

    emitted = CQ.emit(ir, engine="cirq")
    compiled = CQ.compile(ir, engine="cirq")
    result = CQ.run_engine(ir, engine="cirq", shots=64)

    assert emitted.__class__.__name__ == "Circuit"
    assert compiled.engine == "cirq"
    assert isinstance(result, EngineResult)
    assert sum(result.counts.values()) == 64
    assert set(result.counts).issubset({"00", "11"})
    assert result.raw is not None
