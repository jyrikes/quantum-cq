import logging
from types import SimpleNamespace

import pytest
from qiskit import QuantumCircuit

from quantum_cq import CQ
from quantum_cq.experiment import (
    ExperimentPlan,
    PipelineResult,
    apply_measurement_policy,
    extract_counts_from_sampler_result,
)
from quantum_cq.runtime import IBMRuntimeConfig
from quantum_cq.runtime import RuntimeFactory


TOKEN = "secret-token-value"


class IBMInputValueError(Exception):
    pass


class FakeCountsRegister:
    def __init__(self, counts):
        self._counts = counts

    def get_counts(self):
        return self._counts


class FakePubResult:
    def __init__(self, counts=None, register_name="meas"):
        if counts is None:
            self.data = SimpleNamespace()
        else:
            self.data = SimpleNamespace(**{register_name: FakeCountsRegister(counts)})


class FakePrimitiveResult:
    def __init__(self, counts_list):
        self._items = [FakePubResult(counts) for counts in counts_list]

    def __getitem__(self, index):
        return self._items[index]


def _one_qubit_circuit(name="circuit"):
    qc = QuantumCircuit(1, name=name)
    qc.h(0)
    return qc


def test_cq_ibm_normalizes_and_never_leaks_token(caplog):
    caplog.set_level(logging.INFO, logger="quantum_cq")

    config = CQ.ibm(TOKEN, channel="ibm_quantum_platform", instance="")

    assert isinstance(config, IBMRuntimeConfig)
    assert config.instance is None
    assert TOKEN not in repr(config)
    assert TOKEN not in str(config.safe_summary())

    with pytest.raises(ValueError, match="ibm_cloud"):
        CQ.ibm(TOKEN, instance="ibm_cloud")

    with pytest.warns(DeprecationWarning, match="legado"):
        legacy = CQ.ibm(TOKEN, channel="ibm_cloud", instance=None)

    assert legacy.channel == "ibm_cloud"
    assert TOKEN not in caplog.text


def test_ibm_service_kwargs_keep_instance_optional():
    config = CQ.ibm(
        TOKEN,
        channel="ibm_quantum_platform",
        instance=None,
        region="us-east",
        plans_preference="premium",
        tags=("research",),
    )

    kwargs = RuntimeFactory._service_kwargs(config.to_runtime_settings(), config.instance)

    assert kwargs["channel"] == "ibm_quantum_platform"
    assert kwargs["token"] == TOKEN
    assert "instance" not in kwargs
    assert kwargs["region"] == "us-east"
    assert kwargs["plans_preference"] == "premium"
    assert kwargs["tags"] == ["research"]


def test_ibm_cloud_autodiscovery_is_allowed_and_omits_instance(monkeypatch):
    import quantum_cq.runtime as runtime_module
    from quantum_cq.settings import RuntimeSettings

    captured = {}

    class FakeService:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def instances(self):
            return []

        def active_instance(self):
            return None

        def backends(self):
            return []

    monkeypatch.setattr(runtime_module, "QiskitRuntimeService", FakeService)

    settings = RuntimeSettings(
        ibm_channel="ibm_cloud",
        ibm_token=TOKEN,
        ibm_instance=None,
    )

    RuntimeFactory._service(settings)

    assert captured["channel"] == "ibm_cloud"
    assert captured["token"] == TOKEN
    assert "instance" not in captured


def test_ibm_platform_autodiscovery_is_allowed_and_omits_instance(monkeypatch):
    import quantum_cq.runtime as runtime_module
    from quantum_cq.settings import RuntimeSettings

    captured = {}

    class FakeService:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def instances(self):
            return []

        def active_instance(self):
            return None

        def backends(self):
            return []

    monkeypatch.setattr(runtime_module, "QiskitRuntimeService", FakeService)

    settings = RuntimeSettings(
        ibm_channel="ibm_quantum_platform",
        ibm_token=TOKEN,
        ibm_instance=None,
    )

    RuntimeFactory._service(settings)

    assert captured["channel"] == "ibm_quantum_platform"
    assert captured["token"] == TOKEN
    assert "instance" not in captured


def test_ibm_autodiscovery_error_is_didactic_and_hides_token(monkeypatch):
    import quantum_cq.runtime as runtime_module
    from quantum_cq.settings import RuntimeSettings

    class BrokenService:
        def __init__(self, **kwargs):
            raise IBMInputValueError(
                "No matching instances found for the following filters:",
                ".",
            )

    monkeypatch.setattr(runtime_module, "QiskitRuntimeService", BrokenService)

    settings = RuntimeSettings(
        ibm_channel="ibm_cloud",
        ibm_token=TOKEN,
        ibm_instance=None,
    )

    with pytest.raises(RuntimeError) as error:
        RuntimeFactory._service(settings)

    message = str(error.value)
    assert "resolver a instancia automaticamente" in message
    assert "ibm_quantum_platform" in message
    assert "ibm_cloud" in message
    assert "IBM_QUANTUM_INSTANCE" in message
    assert TOKEN not in message


def test_experiment_plan_expands_sources_with_deterministic_ids():
    circuits = [_one_qubit_circuit("a"), _one_qubit_circuit("b")]

    plan = ExperimentPlan.from_inputs(
        circuits=circuits,
        datasets=[[1, 0], [0.1, 0.2]],
        encoders=["basis", "angle"],
        modes=["ideal", "noisy"],
    )

    specs = plan.experiments

    assert len(specs) == 12
    assert specs[0].experiment_id == "circuit-000__circuit-000__mode-ideal"
    assert all(spec.experiment_id for spec in specs)
    assert {spec.mode for spec in specs} == {"ideal", "noisy"}
    assert {spec.encoder for spec in specs if spec.source == "dataset"} == {"basis", "angle"}


def test_measurement_policy_auto_preserve_all_and_none():
    qc = _one_qubit_circuit()

    auto = apply_measurement_policy(qc, "auto", require_counts=True)
    forced = apply_measurement_policy(qc, "all", require_counts=True)

    assert qc.num_clbits == 0
    assert auto.count_ops()["measure"] == 1
    assert forced.count_ops()["measure"] == 1

    with pytest.raises(ValueError, match="measurement='preserve'"):
        apply_measurement_policy(qc, "preserve", require_counts=True)

    with pytest.raises(ValueError, match="measurement='none'"):
        apply_measurement_policy(qc, "none", require_counts=True)

    untouched = apply_measurement_policy(qc, "none", require_counts=False)
    assert untouched.count_ops().get("measure", 0) == 0


def test_extract_counts_from_sampler_result_supports_common_shapes():
    assert extract_counts_from_sampler_result(FakePrimitiveResult([{"0": 2}])) == {"0": 2}
    assert extract_counts_from_sampler_result(FakePubResult({"1": 3}, register_name="c")) == {"1": 3}

    with pytest.raises(RuntimeError, match="dados classicos"):
        extract_counts_from_sampler_result(FakePubResult())


def test_cq_run_multiple_circuits_ideal_returns_pipeline_result():
    circuits = [_one_qubit_circuit("a"), _one_qubit_circuit("b")]

    result = CQ.run(circuits=circuits, modes=["ideal"], shots=32, measurement="auto")

    assert isinstance(result, PipelineResult)
    assert len(result.experiments) == 2
    assert all(experiment.status == "completed" for experiment in result.experiments)
    assert result.counts_for(mode="ideal")
    assert result.global_metrics()["total_experiments"] == 2
    try:
        import pandas as pd
    except ImportError:
        with pytest.raises(ImportError, match="notebook"):
            result.to_dataframe()
    else:
        frame = result.to_dataframe()
        assert isinstance(frame, pd.DataFrame)
        assert {"experiment_id", "circuit_id", "mode", "status"}.issubset(frame.columns)


def test_cq_run_multiple_encoders_tracks_encoder_metrics():
    result = CQ.run(
        datasets=[[1, 0, 1], [0.1, 0.2, 0.3]],
        encoders=["basis", "angle"],
        modes=["ideal"],
        shots=16,
    )

    assert {experiment.encoder for experiment in result.experiments} == {"basis", "angle"}
    assert set(result.by_encoder()) == {"basis", "angle"}
    assert result.global_metrics()["metrics"]["original"]["total_size"] >= 0


def test_cq_run_fail_fast_false_records_failed_experiment():
    result = CQ.run(
        circuit=_one_qubit_circuit(),
        modes=["ideal"],
        measurement="preserve",
        fail_fast=False,
    )

    assert result.experiments[0].status == "failed"
    assert "preserve" in result.experiments[0].error

    with pytest.raises(ValueError, match="preserve"):
        CQ.run(
            circuit=_one_qubit_circuit(),
            modes=["ideal"],
            measurement="preserve",
            fail_fast=True,
        )


def test_real_execution_groups_compatible_circuits_with_mock(monkeypatch):
    import quantum_cq.experiment as experiment_module

    calls = []

    class FakeJob:
        def job_id(self):
            return "job-123"

        def status(self):
            return "DONE"

        def result(self):
            return FakePrimitiveResult([{"0": 4}, {"1": 4}])

    class FakeSampler:
        def run(self, pubs, *, shots=None):
            calls.append((list(pubs), shots))
            return FakeJob()

    fake_runtime = SimpleNamespace(
        backend=SimpleNamespace(name="fake_backend"),
        sampler=FakeSampler(),
        service=None,
        noise_model=None,
    )

    monkeypatch.setattr(
        experiment_module.RuntimeFactory,
        "create",
        staticmethod(lambda mode, **kwargs: fake_runtime),
    )

    result = CQ.run(
        circuits=[_one_qubit_circuit("a"), _one_qubit_circuit("b")],
        modes=["real"],
        ibm=CQ.ibm(TOKEN),
        shots=4,
        measurement="auto",
    )

    assert len(calls) == 1
    assert len(calls[0][0]) == 2
    assert [experiment.job_id for experiment in result.experiments] == ["job-123", "job-123"]
    assert [experiment.status for experiment in result.experiments] == ["completed", "completed"]
