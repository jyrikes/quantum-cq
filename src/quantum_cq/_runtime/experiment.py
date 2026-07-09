"""Pipeline matricial de experimentos."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qiskit import QuantumCircuit
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from quantum_cq._circuits.adapters import export_to_qiskit
from quantum_cq._core.data import QuantumData
from quantum_cq._core.handlers import default_encoding_registry
from quantum_cq._core.metrics import MetricsCollector
from quantum_cq._runtime.runtime import IBMRuntimeConfig, Mode, RuntimeFactory
from quantum_cq._core.settings import RuntimeSettings


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pandas as pd


def _require_pandas():
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError(
            "Para usar PipelineResult.to_dataframe, instale quantum-cq[notebook]."
        ) from exc

    return pd


def _listify(single: Any = None, multiple: Any = None) -> list[Any]:
    if multiple is not None:
        return list(multiple)
    if single is None:
        return []
    return [single]


def _mode_name(mode: Any) -> str:
    value = getattr(mode, "value", mode)
    return str(value).lower()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            key if isinstance(key, (str, int, float, bool)) or key is None else str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _has_measurements(circuit: QuantumCircuit) -> bool:
    return circuit.count_ops().get("measure", 0) > 0 and circuit.num_clbits > 0


def apply_measurement_policy(
    circuit: QuantumCircuit,
    measurement: str = "auto",
    *,
    require_counts: bool = True,
) -> QuantumCircuit:
    """Aplica politica de medicao em copia do circuito."""

    measurement = measurement.lower()
    if measurement not in {"auto", "preserve", "all", "none"}:
        raise ValueError(f"measurement invalido: {measurement}")

    if measurement == "none":
        if require_counts:
            raise ValueError("measurement='none' nao pode ser usado quando counts sao exigidos")
        return circuit.copy()

    if measurement == "preserve":
        if require_counts and not _has_measurements(circuit):
            raise ValueError("measurement='preserve' exige circuito com medicoes para produzir counts")
        return circuit.copy()

    if measurement == "auto" and _has_measurements(circuit):
        return circuit.copy()

    prepared = circuit.remove_final_measurements(inplace=False)
    if prepared is None:
        prepared = circuit.copy()
    prepared.measure_all()
    return prepared


def _pub_result_at(result: Any, index: int) -> Any:
    if hasattr(result, "data"):
        return result
    try:
        return result[index]
    except Exception as exc:
        raise RuntimeError("Resultado do sampler nao contem pub results indexaveis") from exc


def _counts_from_data_bin(data: Any) -> dict[str, int]:
    for name in ("meas", "c"):
        if hasattr(data, name):
            register = getattr(data, name)
            if hasattr(register, "get_counts"):
                return dict(register.get_counts())

    try:
        iterator = data.items()
    except Exception:
        iterator = []

    for _, register in iterator:
        if hasattr(register, "get_counts"):
            return dict(register.get_counts())

    for name in dir(data):
        if name.startswith("_"):
            continue
        try:
            register = getattr(data, name)
        except Exception:
            continue
        if hasattr(register, "get_counts"):
            return dict(register.get_counts())

    raise RuntimeError("Resultado do sampler nao possui dados classicos com get_counts()")


def extract_counts_from_sampler_result(result: Any, index: int = 0) -> dict[str, int]:
    """Extrai counts de PrimitiveResult/SamplerPubResult do Qiskit Runtime atual."""

    pub_result = _pub_result_at(result, index)
    data = getattr(pub_result, "data", None)
    if data is None:
        raise RuntimeError("Resultado do sampler nao possui dados classicos")
    return _counts_from_data_bin(data)


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    source: str
    mode: str
    circuit: Any | None = None
    data: Any | None = None
    circuit_id: str | None = None
    dataset_id: str | None = None
    encoder: str | None = None


@dataclass
class ExperimentPlan:
    experiments: list[ExperimentSpec] = field(default_factory=list)

    @classmethod
    def from_inputs(
        cls,
        *,
        circuit: Any = None,
        circuits: list[Any] | None = None,
        data: Any = None,
        datasets: list[Any] | None = None,
        encoder: str | None = None,
        encoders: list[str] | None = None,
        mode: str | None = None,
        modes: list[str] | None = None,
    ) -> "ExperimentPlan":
        circuit_items = _listify(circuit, circuits)
        dataset_items = _listify(data, datasets)
        mode_items = [_mode_name(item) for item in _listify(mode or "ideal", modes)]
        encoder_items = list(encoders) if encoders is not None else [encoder or "auto"]
        experiments: list[ExperimentSpec] = []

        for circuit_index, circuit_item in enumerate(circuit_items):
            circuit_id = f"circuit-{circuit_index:03d}"
            for mode_name in mode_items:
                experiments.append(
                    ExperimentSpec(
                        experiment_id=f"{circuit_id}__{circuit_id}__mode-{mode_name}",
                        source="circuit",
                        circuit=circuit_item,
                        circuit_id=circuit_id,
                        mode=mode_name,
                    )
                )

        for dataset_index, dataset_item in enumerate(dataset_items):
            dataset_id = f"dataset-{dataset_index:03d}"
            for encoder_name in encoder_items:
                for mode_name in mode_items:
                    experiments.append(
                        ExperimentSpec(
                            experiment_id=f"{dataset_id}__encoder-{encoder_name}__mode-{mode_name}",
                            source="dataset",
                            data=dataset_item,
                            dataset_id=dataset_id,
                            encoder=encoder_name,
                            mode=mode_name,
                        )
                    )

        if not experiments:
            raise ValueError("ExperimentPlan requer circuit/circuits ou data/datasets")

        return cls(experiments=experiments)


@dataclass
class ExperimentResult:
    experiment_id: str
    mode: str
    circuit_id: str | None = None
    dataset_id: str | None = None
    encoder: str | None = None
    counts: dict[str, int] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    job_id: str | None = None
    backend_name: str | None = None
    status: str = "pending"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "mode": self.mode,
            "circuit_id": self.circuit_id,
            "dataset_id": self.dataset_id,
            "encoder": self.encoder,
            "counts": _json_safe(self.counts),
            "metrics": _json_safe(self.metrics),
            "job_id": self.job_id,
            "backend_name": self.backend_name,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class PipelineResult:
    experiments: list[ExperimentResult] = field(default_factory=list)
    title: str | None = None

    def counts_for(
        self,
        mode: str | None = None,
        *,
        encoder: str | None = None,
        circuit_id: str | None = None,
        dataset_id: str | None = None,
    ) -> dict[str, dict[str, int]]:
        selected = self._filter(
            mode=mode,
            encoder=encoder,
            circuit_id=circuit_id,
            dataset_id=dataset_id,
        )
        return {
            experiment.experiment_id: experiment.counts
            for experiment in selected
            if experiment.counts is not None
        }

    def summary(self) -> dict[str, Any]:
        by_status: dict[str, int] = defaultdict(int)
        for experiment in self.experiments:
            by_status[experiment.status] += 1
        return {
            "title": self.title,
            "total_experiments": len(self.experiments),
            "by_status": dict(by_status),
            "modes": sorted({experiment.mode for experiment in self.experiments}),
        }

    def global_metrics(self) -> dict[str, Any]:
        aggregate = {
            "original": {"total_size": 0, "total_depth": 0},
            "transpiled": {"total_size": 0, "total_depth": 0},
        }
        total_shots = 0
        job_ids = set()
        failed = 0

        for experiment in self.experiments:
            if experiment.status == "failed":
                failed += 1
            if experiment.counts:
                total_shots += sum(experiment.counts.values())
            if experiment.job_id:
                job_ids.add(experiment.job_id)
            for group in ("original", "transpiled"):
                metrics = experiment.metrics.get(group) or {}
                aggregate[group]["total_size"] += metrics.get("size", 0) or 0
                aggregate[group]["total_depth"] += metrics.get("depth", 0) or 0

        return {
            "total_experiments": len(self.experiments),
            "failed_experiments": failed,
            "total_shots": total_shots,
            "total_jobs": len(job_ids),
            "metrics": aggregate,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": _json_safe(self.summary()),
            "global_metrics": _json_safe(self.global_metrics()),
            "experiments": [experiment.to_dict() for experiment in self.experiments],
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def by_mode(self) -> dict[str, list[ExperimentResult]]:
        return self._group_by("mode")

    def by_encoder(self) -> dict[str, list[ExperimentResult]]:
        return self._group_by("encoder")

    def by_circuit(self) -> dict[str, list[ExperimentResult]]:
        return self._group_by("circuit_id")

    def show(self) -> "PipelineResult":
        print(self.summary())
        return self

    def classify(self, algorithm: str) -> str:
        normalized = algorithm.lower()
        if normalized != "deutsch":
            return "unknown"

        completed = [item for item in self.experiments if item.counts]
        if not completed:
            return "unknown"

        counts = completed[0].counts or {}
        if not counts:
            return "unknown"

        dominant = max(counts, key=lambda key: counts[key])
        bitstring = str(dominant).replace(" ", "")
        return "balanced" if "1" in bitstring else "constant"

    def to_dataframe(self) -> pd.DataFrame:
        pd = _require_pandas()
        rows = []
        for experiment in self.experiments:
            rows.append(
                {
                    "experiment_id": experiment.experiment_id,
                    "mode": experiment.mode,
                    "circuit_id": experiment.circuit_id,
                    "dataset_id": experiment.dataset_id,
                    "encoder": experiment.encoder,
                    "status": experiment.status,
                    "job_id": experiment.job_id,
                    "backend_name": experiment.backend_name,
                    "error": experiment.error,
                    "counts": experiment.counts,
                }
            )
        return pd.DataFrame(rows)

    def _filter(self, **criteria: Any) -> list[ExperimentResult]:
        selected = self.experiments
        for key, expected in criteria.items():
            if expected is not None:
                selected = [item for item in selected if getattr(item, key) == expected]
        return selected

    def _group_by(self, field_name: str) -> dict[str, list[ExperimentResult]]:
        grouped: dict[str, list[ExperimentResult]] = defaultdict(list)
        for experiment in self.experiments:
            key = getattr(experiment, field_name) or ""
            grouped[str(key)].append(experiment)
        return dict(grouped)


class ExperimentMatrixRunner:
    def __init__(
        self,
        *,
        plan: ExperimentPlan,
        ibm: IBMRuntimeConfig | None = None,
        shots: int = 1024,
        backend: str = "least_busy",
        measurement: str = "auto",
        fail_fast: bool = False,
        timeout: int | None = None,
        title: str | None = None,
    ) -> None:
        self.plan = plan
        self.ibm = ibm
        self.shots = shots
        self.backend = backend
        self.measurement = measurement
        self.fail_fast = fail_fast
        self.timeout = timeout
        self.title = title
        self.metrics = MetricsCollector()
        self._runtime_cache: dict[str, Any] = {}

    def run(self) -> PipelineResult:
        real_specs = [spec for spec in self.plan.experiments if spec.mode == "real"]
        other_specs = [spec for spec in self.plan.experiments if spec.mode != "real"]
        results: list[ExperimentResult] = []

        for spec in other_specs:
            try:
                results.append(self._run_single(spec))
            except Exception as exc:
                if self.fail_fast:
                    raise
                results.append(self._failed_result(spec, exc))

        if real_specs:
            results.extend(self._run_real_grouped(real_specs))

        order = {spec.experiment_id: index for index, spec in enumerate(self.plan.experiments)}
        results.sort(key=lambda result: order.get(result.experiment_id, 0))
        return PipelineResult(experiments=results, title=self.title)

    def _runtime(self, mode: str) -> Any:
        if mode not in self._runtime_cache:
            settings = self.ibm.to_runtime_settings() if self.ibm else None
            self._runtime_cache[mode] = RuntimeFactory.create(
                mode,
                settings=settings,
                backend_name=self.backend if mode in {"real", "noisy"} else None,
            )
        return self._runtime_cache[mode]

    def _build_original_circuit(self, spec: ExperimentSpec) -> QuantumCircuit:
        if spec.source == "circuit":
            return export_to_qiskit(spec.circuit)

        registry = default_encoding_registry()
        data = QuantumData(spec.data)
        if spec.encoder == "auto":
            from quantum_cq._core.selectors import EncodingSelector

            encoder = EncodingSelector(registry).select(data)
        else:
            encoder = registry.get(str(spec.encoder))
            if not encoder.can_handle(data):
                raise ValueError(f"Encoding '{spec.encoder}' nao pode lidar com dataset {spec.dataset_id}")
        return export_to_qiskit(encoder.encode(data))

    def _prepare(self, spec: ExperimentSpec, runtime: Any) -> tuple[QuantumCircuit, QuantumCircuit, dict[str, Any]]:
        original = self._build_original_circuit(spec)
        measured = apply_measurement_policy(original, self.measurement, require_counts=True)
        original_metrics = self.metrics.collect(measured)
        logger.info("Iniciando transpilacao: experiment=%s mode=%s", spec.experiment_id, spec.mode)
        try:
            pass_manager = generate_preset_pass_manager(backend=runtime.backend, optimization_level=1)
            transpiled = pass_manager.run(measured)
        except Exception as exc:
            logger.warning(
                "Transpilacao indisponivel; usando circuito original: experiment=%s erro=%s",
                spec.experiment_id,
                type(exc).__name__,
            )
            transpiled = measured.copy()
        logger.info("Fim da transpilacao: experiment=%s", spec.experiment_id)
        transpiled_metrics = self.metrics.collect(transpiled)
        return measured, transpiled, {"original": original_metrics, "transpiled": transpiled_metrics}

    def _run_single(self, spec: ExperimentSpec) -> ExperimentResult:
        runtime = self._runtime(spec.mode)
        _, transpiled, metrics = self._prepare(spec, runtime)
        job = runtime.sampler.run([transpiled], shots=self.shots)
        job_id = _job_id(job)
        logger.info("Job enviado: experiment=%s job_id=%s", spec.experiment_id, job_id)
        result = job.result()
        counts = extract_counts_from_sampler_result(result, 0)
        logger.info("Resultado recebido: experiment=%s", spec.experiment_id)
        return self._completed_result(
            spec,
            counts=counts,
            metrics=metrics,
            job_id=job_id,
            backend_name=_backend_name(runtime.backend),
        )

    def _run_real_grouped(self, specs: list[ExperimentSpec]) -> list[ExperimentResult]:
        runtime = self._runtime("real")
        prepared: list[tuple[ExperimentSpec, QuantumCircuit, dict[str, Any]]] = []
        results: list[ExperimentResult] = []
        for spec in specs:
            try:
                _, transpiled, metrics = self._prepare(spec, runtime)
                prepared.append((spec, transpiled, metrics))
            except Exception as exc:
                if self.fail_fast:
                    raise
                results.append(self._failed_result(spec, exc))

        groups: dict[tuple[str, int, str], list[tuple[ExperimentSpec, QuantumCircuit, dict[str, Any]]]] = defaultdict(list)
        for item in prepared:
            groups[(_backend_name(runtime.backend), self.shots, self.measurement)].append(item)

        for _, group in groups.items():
            circuits = [item[1] for item in group]
            try:
                job = runtime.sampler.run(circuits, shots=self.shots)
                job_id = _job_id(job)
                logger.info("Job real enviado: job_id=%s circuitos=%s", job_id, len(circuits))
                primitive_result = job.result()
                logger.info("Resultado real recebido: job_id=%s", job_id)
                for index, (spec, _, metrics) in enumerate(group):
                    counts = extract_counts_from_sampler_result(primitive_result, index)
                    results.append(
                        self._completed_result(
                            spec,
                            counts=counts,
                            metrics=metrics,
                            job_id=job_id,
                            backend_name=_backend_name(runtime.backend),
                        )
                    )
            except Exception as exc:
                if self.fail_fast:
                    raise
                for spec, _, _ in group:
                    results.append(self._failed_result(spec, exc))

        return results

    def _completed_result(
        self,
        spec: ExperimentSpec,
        *,
        counts: dict[str, int],
        metrics: dict[str, Any],
        job_id: str | None,
        backend_name: str | None,
    ) -> ExperimentResult:
        return ExperimentResult(
            experiment_id=spec.experiment_id,
            mode=spec.mode,
            circuit_id=spec.circuit_id,
            dataset_id=spec.dataset_id,
            encoder=spec.encoder,
            counts=counts,
            metrics=metrics,
            job_id=job_id,
            backend_name=backend_name,
            status="completed",
        )

    def _failed_result(self, spec: ExperimentSpec, exc: Exception) -> ExperimentResult:
        logger.exception("Experimento falhou: %s", spec.experiment_id)
        return ExperimentResult(
            experiment_id=spec.experiment_id,
            mode=spec.mode,
            circuit_id=spec.circuit_id,
            dataset_id=spec.dataset_id,
            encoder=spec.encoder,
            status="failed",
            error=str(exc),
        )


def run_experiment_matrix(
    *,
    circuit: Any = None,
    circuits: list[Any] | None = None,
    data: Any = None,
    datasets: list[Any] | None = None,
    encoder: str | None = None,
    encoders: list[str] | None = None,
    mode: str | None = None,
    modes: list[str] | None = None,
    ibm: IBMRuntimeConfig | None = None,
    shots: int = 1024,
    backend: str = "least_busy",
    measurement: str = "auto",
    fail_fast: bool = False,
    timeout: int | None = None,
    title: str | None = None,
) -> PipelineResult:
    plan = ExperimentPlan.from_inputs(
        circuit=circuit,
        circuits=circuits,
        data=data,
        datasets=datasets,
        encoder=encoder,
        encoders=encoders,
        mode=mode,
        modes=modes,
    )
    return ExperimentMatrixRunner(
        plan=plan,
        ibm=ibm,
        shots=shots,
        backend=backend,
        measurement=measurement,
        fail_fast=fail_fast,
        timeout=timeout,
        title=title,
    ).run()


def _job_id(job: Any) -> str | None:
    try:
        return str(job.job_id())
    except Exception:
        return None


def _backend_name(backend: Any) -> str:
    name = getattr(backend, "name", None)
    if callable(name):
        return str(name())
    if name is not None:
        return str(name)
    return str(backend)


__all__ = [
    "ExperimentSpec",
    "ExperimentPlan",
    "ExperimentResult",
    "PipelineResult",
    "ExperimentMatrixRunner",
    "apply_measurement_policy",
    "extract_counts_from_sampler_result",
    "run_experiment_matrix",
]
