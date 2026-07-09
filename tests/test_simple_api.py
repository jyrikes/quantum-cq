import json

import pytest

from quantum_cq import CQ
from quantum_cq.experiment import PipelineResult
from quantum_cq.results import (
    AlgorithmCircuit,
    EncodedCircuit,
    NavigationCircuit,
    OperatorCircuit,
)


def test_state_shortcuts_work():
    assert isinstance(CQ.state([1, 0, 1]), EncodedCircuit)
    assert CQ.state([0.1, 0.2], encoding="angle").encoding_name == "angle"
    assert CQ.state([0.1, 0.2], encoding="phase").encoding_name == "phase"
    assert CQ.state([1, 0, 0, 0], encoding="amplitude").encoding_name == "amplitude"


def test_navigation_shortcuts_and_engine_aliases_work():
    nav = CQ.nav([3, 5, 7, 9])
    old = CQ.encode(CQ.memory([3, 5, 7, 9]), role="navigation", engine="explicit_circuit")

    assert isinstance(nav, NavigationCircuit)
    assert nav.metadata["engine"] == old.metadata["engine"] == "explicit_circuit"
    assert CQ.addressed([3, 5, 7, 9]).metadata["engine"] == "explicit_circuit"
    assert CQ.nav([3, 5, 7, 9], engine="explicit").metadata["engine"] == "explicit_circuit"
    assert CQ.nav([3, 5, 7, 9], engine="sparse").metadata["engine"] == "sparse_explicit_circuit"
    assert CQ.nav([3, 5, 7, 9], engine="qram").metadata["engine"] == "qram_like"

    with pytest.raises(NotImplementedError, match="oracle_model"):
        CQ.nav([3, 5, 7, 9], engine="oracle")

    with pytest.raises(ValueError, match="Engines aceitos"):
        CQ.nav([3, 5, 7, 9], engine="invalido")


def test_graph_navigation_and_walk_shortcuts_work():
    graph = CQ.graph([(0, 1), (1, 2), (2, 3)], vertices=4)
    same = CQ.graph([(0, 1)], vertices=2, num_vertices=2)

    assert graph.num_vertices == 4
    assert same.num_vertices == 2
    assert isinstance(CQ.graph_nav(graph), NavigationCircuit)
    assert isinstance(CQ.walk(graph, steps=1), OperatorCircuit)

    with pytest.raises(ValueError, match="vertices e num_vertices"):
        CQ.graph([(0, 1)], vertices=3, num_vertices=2)


def test_algorithm_shortcuts_work():
    assert isinstance(CQ.deutsch(case=2), AlgorithmCircuit)
    assert CQ.bv("1011").metadata["expected_output"] == "1011"
    assert CQ.dj(kind="balanced", qubits=3).metadata["expected_output_type"] == "balanced"
    assert CQ.grover("11").metadata["marked_state"] == "11"
    assert CQ.grover("101", iterations=2).metadata["iterations"] == 2
    assert CQ.qpe(phase=0.25, precision=3).metadata["expected_output_bits"] == "010"

    with pytest.raises(ValueError, match="qubits e num_qubits"):
        CQ.dj(kind="balanced", qubits=3, num_qubits=4)


def test_operator_shortcuts_work():
    assert CQ.qft(3).metadata["operator_name"] == "qft"
    assert CQ.iqft(3).metadata["operator_name"] == "inverse_qft"
    assert CQ.diffuser(3).metadata["operator_name"] == "standard_diffuser"
    assert CQ.phase_rotation(0.25).metadata["operator_name"] == "phase_rotation"


def test_draw_describe_show_do_not_break(monkeypatch):
    obj = CQ.deutsch(case=2)

    description = CQ.describe(obj)
    assert "AlgorithmCircuit" in description
    assert "num_qubits" in description

    drawing = CQ.draw(obj, output="text")
    assert drawing is not None

    def broken_draw(*args, **kwargs):
        raise RuntimeError("mpl unavailable")

    qc = CQ.to_qiskit(obj)
    monkeypatch.setattr(qc, "draw", broken_draw)
    monkeypatch.setattr(CQ, "to_qiskit", staticmethod(lambda _: qc))

    assert CQ.draw(obj, output="mpl") is not None
    assert CQ.show(obj) is None


def test_pipeline_shortcuts_preserve_old_builder():
    assert isinstance(CQ.pipeline(data=[1, 0.3, 1]).build(), EncodedCircuit)
    assert isinstance(CQ.pipeline([1, 0.3, 1]).build(), EncodedCircuit)
    assert isinstance(CQ.pipeline().with_data([1, 0.3, 1]).build(), EncodedCircuit)
    assert CQ.pipeline(data=[1, 0.3, 1], encoding="angle").build().encoding_name == "angle"


def test_cq_run_simple_inputs_work():
    result = CQ.run(CQ.deutsch(case=2), mode="ideal", shots=16)
    assert isinstance(result, PipelineResult)
    assert result.experiments[0].status == "completed"

    data_result = CQ.run([1, 0.3, 1], shots=16)
    assert isinstance(data_result, PipelineResult)
    assert data_result.experiments[0].encoder == "auto"

    auto_result = CQ.run(data=[1, 0.3, 1], encoder="auto", shots=16)
    assert auto_result.experiments[0].encoder == "auto"

    multi_encoder = CQ.run(data=[0.1, 0.3, 0.5], encoders=["angle", "phase"], shots=16)
    assert {experiment.encoder for experiment in multi_encoder.experiments} == {"angle", "phase"}

    multi_circuit = CQ.run(circuits=[CQ.deutsch(case=2), CQ.bv("1011")], modes=["ideal"], shots=16)
    assert len(multi_circuit.experiments) == 2


def test_notebooks_and_ibm_docs_exist_without_real_token():
    simple = "notebooks/quantum_cq_simple_api_lab.ipynb"
    real = "notebooks/quantum_cq_ibm_real_smoke.ipynb"

    for path in (simple, real):
        with open(path, encoding="utf-8") as handle:
            notebook = json.load(handle)
        text = json.dumps(notebook, ensure_ascii=False)
        assert "r9ec-" not in text
        assert "COLE_SEU_TOKEN_AQUI" in text

    with open(simple, encoding="utf-8") as handle:
        simple_text = handle.read()
    assert "CQ.state" in simple_text
    assert "CQ.nav" in simple_text
    assert "CQ.deutsch" in simple_text
    assert "CQ.run" in simple_text
    assert "CQ.show" in simple_text

    with open(real, encoding="utf-8") as handle:
        real_text = handle.read()
    assert "RUN_REAL_IBM = True" in real_text
    assert "COLE_SEU_TOKEN_AQUI" in real_text

    with open("docs/ibm_real_testing.md", encoding="utf-8") as handle:
        docs = handle.read()
    assert "--run-ibm-real" in docs
    assert "quantum_cq_ibm_real_smoke.ipynb" in docs
