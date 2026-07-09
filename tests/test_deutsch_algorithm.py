import pytest

from quantum_cq.algorithms import twobit_block
from quantum_cq.compact import QC, m, obs, sep
from quantum_cq.pipeline import BenchmarkingPipeline
from quantum_cq.settings import PipelineSettings, RuntimeSettings


IDEAL_PIPELINE_SETTINGS = PipelineSettings(
    modes=("ideal",),
    shots=128,
    optimization_level=1,
    parallel=False,
    show_transpiled=False,
)

REAL_HARDWARE_ENABLED = False
REAL_PIPELINE_SETTINGS = PipelineSettings(
    modes=("real",),
    shots=128,
    optimization_level=1,
    parallel=True,
    show_transpiled=True,
    real_timeout_seconds=120,
    real_max_pending_jobs=20,
    cancel_real_on_timeout=True,
    cancel_real_on_queue_limit=True,
)
REAL_RUNTIME_SETTINGS = RuntimeSettings(
    ibm_channel="ibm_cloud",
    ibm_token="token-de-teste",

)


def _build_deutsch_circuit(case: int = 2) -> QC:
    uf0 = twobit_block(case)

    return QC(
        "Deutsch",
        [
            [0, "-", "H", obs("pre_oracle"), uf0, sep("after_oracle"), "H", m(0)],
            [0, "X", "H", obs("pre_oracle"), uf0, "-", "-", "-"],
        ],
        c=1,
    )


def _silence_pipeline_display(monkeypatch):
    import quantum_cq.pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "_pipe_title", lambda title: None)
    monkeypatch.setattr(pipeline_module, "_pipe_step", lambda title, lines=None: None)
    monkeypatch.setattr(pipeline_module, "_pipe_display", lambda value: None)


def _classify_deutsch(counts: dict) -> str:
    return "balanceada" if "1" in counts else "constante"


def test_deutsch_algorithm_standard_ideal_pipeline(monkeypatch):
    _silence_pipeline_display(monkeypatch)

    pipeline = BenchmarkingPipeline(
        settings=IDEAL_PIPELINE_SETTINGS,
        runtime_settings=RuntimeSettings(),
    )

    resultados_deutsch = pipeline.run_batch(
        _build_deutsch_circuit(case=2),
        title="Algoritmo de Deutsch",
        equation=(
            r"$f$ é constante se a leitura final for $0$; "
            r"$f$ é balanceada se a leitura final for $1$."
        ),
    )

    referencia_deutsch = resultados_deutsch["ideal"]

    assert referencia_deutsch == {"1": 128}
    assert _classify_deutsch(referencia_deutsch) == "balanceada"


@pytest.mark.real_hardware
def test_deutsch_algorithm_optional_real_hardware(monkeypatch):
    if not REAL_HARDWARE_ENABLED:
        pytest.skip("Ative REAL_HARDWARE_ENABLED no teste para rodar na IBM.")

    if not REAL_RUNTIME_SETTINGS.ibm_token:
        pytest.skip("Configure REAL_RUNTIME_SETTINGS.ibm_token para rodar na IBM.")

    _silence_pipeline_display(monkeypatch)

    pipeline = BenchmarkingPipeline(
        settings=REAL_PIPELINE_SETTINGS,
        runtime_settings=REAL_RUNTIME_SETTINGS,
    )

    resultados_deutsch = pipeline.run_batch(
        _build_deutsch_circuit(case=2),
        title="Algoritmo de Deutsch",
    )

    counts = resultados_deutsch["real"]
    if not counts:
        pytest.skip("Job real cancelado por timeout ou limite de fila.")

    assert "1" in counts
