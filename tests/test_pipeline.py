import threading
from types import SimpleNamespace
from typing import Any, NoReturn

from qiskit import QuantumCircuit

from quantum_cq.runtime import Mode
from quantum_cq.pipeline import BenchmarkingPipeline


class FakeJob:
    def result(self) -> Any:
        return None

    def job_id(self) -> str:
        return "fake-job"

    def status(self) -> str:
        return "DONE"

    def cancel(self) -> None:
        return None


class FakeSampler:
    def run(self, pubs: Any, *, shots: int | None = None) -> FakeJob:
        return FakeJob()


def _fake_runtime():
    backend = SimpleNamespace(name="fake_backend")

    return SimpleNamespace(
        backend=backend,
        sampler=FakeSampler(),
        service=None,
        noise_model=None,
    )


def test_benchmarking_pipeline_initializes_with_ideal_mode(monkeypatch):
    import quantum_cq.pipeline as pipeline_module

    created_modes = []

    def fake_create(mode, **kwargs):
        created_modes.append(mode)
        return _fake_runtime()

    monkeypatch.setattr(
        pipeline_module.RuntimeFactory,
        "create",
        staticmethod(fake_create),
    )
    monkeypatch.setattr(pipeline_module, "_pipe_title", lambda title: None)
    monkeypatch.setattr(pipeline_module, "_pipe_step", lambda title, lines=None: None)

    pipeline = BenchmarkingPipeline(modes=[Mode.IDEAL])

    assert pipeline.modes == [Mode.IDEAL]
    assert created_modes == [Mode.IDEAL]
    assert Mode.IDEAL in pipeline.runtimes
    assert pipeline.pipeline_ativo is True
    assert pipeline.historico_jobs == []


def test_pipeline_accepts_qiskit_quantum_circuit(monkeypatch):
    import quantum_cq.pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module.RuntimeFactory,
        "create",
        staticmethod(lambda mode, **kwargs: _fake_runtime()),
    )
    monkeypatch.setattr(pipeline_module, "_pipe_title", lambda title: None)
    monkeypatch.setattr(pipeline_module, "_pipe_step", lambda title, lines=None: None)

    pipeline = BenchmarkingPipeline(modes=[Mode.IDEAL])
    circuit = QuantumCircuit(1)

    assert pipeline._as_qiskit_circuit(circuit) is circuit


def test_pipeline_run_batch_can_execute_modes_in_parallel(monkeypatch):
    import quantum_cq.pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module.RuntimeFactory,
        "create",
        staticmethod(lambda mode, **kwargs: _fake_runtime()),
    )
    monkeypatch.setattr(pipeline_module, "_pipe_title", lambda title: None)
    monkeypatch.setattr(pipeline_module, "_pipe_step", lambda title, lines=None: None)
    monkeypatch.setattr(pipeline_module, "_pipe_display", lambda value: None)

    pipeline = BenchmarkingPipeline(modes=[Mode.IDEAL, Mode.NOISY])
    thread_names = set()

    def fake_executar_modo(circuit, mode, **kwargs):
        thread_names.add(threading.current_thread().name)
        return {mode.value: 1}

    monkeypatch.setattr(pipeline, "_mostrar_circuito_de_partida", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "_executar_modo", fake_executar_modo)

    result = pipeline.run_batch(
        QuantumCircuit(1),
        parallel=True,
        max_workers=2,
        show_transpiled=False,
    )

    assert result == {
        "ideal": {"ideal": 1},
        "noisy": {"noisy": 1},
    }
    assert any(name.startswith("quantum-cq-pipeline") for name in thread_names)


def test_real_mode_can_skip_submission_when_queue_is_too_large(monkeypatch):
    import quantum_cq.pipeline as pipeline_module

    class FakeBackend:
        name = "fake_real_backend"

        def status(self):
            return SimpleNamespace(pending_jobs=99)

    class NeverSubmittingSampler:
        def run(self, pubs: Any, *, shots: int | None = None) -> NoReturn:
            raise AssertionError("real job should not be submitted")

    fake_runtime = SimpleNamespace(
        backend=FakeBackend(),
        sampler=NeverSubmittingSampler(),
        service=None,
        noise_model=None,
    )

    monkeypatch.setattr(
        pipeline_module.RuntimeFactory,
        "create",
        staticmethod(lambda mode, **kwargs: fake_runtime),
    )
    monkeypatch.setattr(pipeline_module, "_pipe_title", lambda title: None)
    monkeypatch.setattr(pipeline_module, "_pipe_step", lambda title, lines=None: None)
    monkeypatch.setattr(pipeline_module, "_pipe_display", lambda value: None)

    pipeline = BenchmarkingPipeline(modes=[Mode.REAL], parallel=False)
    monkeypatch.setattr(pipeline, "_mostrar_circuito_de_partida", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "_transpilar", lambda circuit, runtime, **kwargs: circuit)

    result = pipeline.run_batch(
        QuantumCircuit(1),
        real_max_pending_jobs=1,
        cancel_real_on_queue_limit=True,
        show_transpiled=False,
    )

    assert result == {"real": {}}


def test_pipeline_accepts_settings_directly_in_code(monkeypatch):
    import quantum_cq.pipeline as pipeline_module
    from quantum_cq.settings import PipelineSettings, RuntimeSettings

    captured = {}

    def fake_create_many(modes, **kwargs):
        captured["modes"] = list(modes)
        captured["settings"] = kwargs["settings"]
        return {mode: _fake_runtime() for mode in modes}

    monkeypatch.setattr(
        pipeline_module.RuntimeFactory,
        "create_many",
        staticmethod(fake_create_many),
    )
    monkeypatch.setattr(pipeline_module, "_pipe_title", lambda title: None)
    monkeypatch.setattr(pipeline_module, "_pipe_step", lambda title, lines=None: None)

    pipeline = BenchmarkingPipeline(
        settings=PipelineSettings(
            modes=("ideal",),
            shots=256,
            parallel=False,
            show_transpiled=False,
        ),
        runtime_settings=RuntimeSettings(
            ibm_channel="ibm_cloud",
            ibm_token="token-direto",
            max_retries=1,
        ),
    )

    assert pipeline.modes == [Mode.IDEAL]
    assert pipeline.shots == 256
    assert pipeline.parallel is False
    assert captured["modes"] == [Mode.IDEAL]
    assert captured["settings"].ibm_token == "token-direto"
