from __future__ import annotations

from quantum_cq._runtime.runtime import Mode, RuntimeFactory, QuantumRuntime
from quantum_cq._core.logging_config import configure_logging
from quantum_cq._core.settings import (
    PipelineSettings,
    RuntimeSettings,
    get_pipeline_settings,
    get_runtime_settings,
)

# ==========================================
# PIPELINE DE EXECUÇÃO QUÂNTICA
# Cria circuito -> transpila -> executa -> plota leituras
# Ideal | Ruído | Hardware Real IBM
# ==========================================

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from time import sleep, monotonic
from typing import Any


PIPELINE_ACCENTS = {
    "ideal": "#38bdf8",
    "noisy": "#f59e0b",
    "real": "#ef4444",
    "default": "#a78bfa",
}


logger = logging.getLogger(__name__)
_DISPLAY_LOCK = Lock()


def _require_notebook_display():
    try:
        from IPython.display import Markdown, display
    except ImportError as exc:
        raise ImportError(
            "Para usar visualizacao em notebook da pipeline, instale quantum-cq[notebook]."
        ) from exc

    return display, Markdown


def _require_plot_histogram():
    try:
        from qiskit.visualization import plot_histogram
    except ImportError as exc:
        raise ImportError(
            "Para usar histogramas da pipeline, instale quantum-cq[notebook]."
        ) from exc

    return plot_histogram


def _require_qiskit_pipeline():
    try:
        from qiskit.quantum_info import Statevector
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    except ImportError as exc:
        raise ImportError(
            "Para usar BenchmarkingPipeline, instale quantum-cq. "
            "Se a mensagem original mencionar matplotlib, instale quantum-cq[notebook]."
        ) from exc

    return Statevector, generate_preset_pass_manager


def _pipe_md(text: str):
    display, Markdown = _require_notebook_display()
    with _DISPLAY_LOCK:
        display(Markdown(text))


def _pipe_display(value):
    display, _ = _require_notebook_display()
    with _DISPLAY_LOCK:
        display(value)


def _pipe_title(title: str):
    _pipe_md(f"## {title}")


def _pipe_step(title: str, lines=None):
    if lines is None:
        lines = []

    if isinstance(lines, str):
        lines = [lines]

    body = "\n".join(f"- {line}" for line in lines)
    _pipe_md(f"### {title}\n{body}")


class BasePipeline:
    def __init__(self):
        self.historico_jobs = []
        self.pipeline_ativo = True

    def _run_unified_transpile(self, circuit: Any, *, engine: str = "qiskit", **options: Any) -> Any:
        from quantum_cq._runtime.unified import PipelineCore, PipelineExecutionConfig

        result = PipelineCore(
            PipelineExecutionConfig(
                circuit=circuit,
                engine=engine,
                runtime_options=options,
            )
        ).transpile()[0]
        snapshot = result.after_transpile
        return circuit if snapshot is None else snapshot.circuit


class BenchmarkingPipeline(BasePipeline):
    """
    Pipeline padrão do notebook.

    Contrato:
        1. A célula cria o circuito.
        2. A célula chama pipeline.run_batch(...).
        3. A pipeline mostra:
            - circuito lógico de partida
            - equação/interpretação
            - vetor de estado, quando viável
            - circuito transpilado
            - leituras em histograma para cada modo inserido
    """

    def __init__(
        self,
        modes: list[Mode | str] | None = None,
        *,
        settings: PipelineSettings | None = None,
        runtime_settings: RuntimeSettings | None = None,
        parallel: bool | None = None,
        max_workers: int | None = None,
        log_file: str | None = None,
        shots: int | None = None,
        optimization_level: int | None = None,
        queue_interval: int | None = None,
        show_transpiled: bool | None = None,
        real_timeout_seconds: int | None = None,
        real_max_pending_jobs: int | None = None,
        cancel_real_on_timeout: bool | None = None,
        cancel_real_on_queue_limit: bool | None = None,
        ibm_channel: str | None = None,
        ibm_token: str | None = None,
        ibm_instance: str | None = None,
        runtime_max_retries: int | None = None,
        runtime_wait_seconds: int | None = None,
    ):
        super().__init__()
        configure_logging(log_file)
        settings = (settings or get_pipeline_settings()).with_overrides(
            modes=modes,
            parallel=parallel,
            max_workers=max_workers,
            shots=shots,
            optimization_level=optimization_level,
            queue_interval=queue_interval,
            show_transpiled=show_transpiled,
            real_timeout_seconds=real_timeout_seconds,
            real_max_pending_jobs=real_max_pending_jobs,
            cancel_real_on_timeout=cancel_real_on_timeout,
            cancel_real_on_queue_limit=cancel_real_on_queue_limit,
        )
        runtime_settings = (runtime_settings or get_runtime_settings()).with_overrides(
            ibm_channel=ibm_channel,
            ibm_token=ibm_token,
            ibm_instance=ibm_instance,
            max_retries=runtime_max_retries,
            wait_seconds=runtime_wait_seconds,
        )

        self.modes = [
            Mode(mode.lower()) if isinstance(mode, str) else mode
            for mode in settings.modes
        ]
        self.settings = settings
        self.runtime_settings = runtime_settings
        self.parallel = settings.parallel
        self.max_workers = settings.max_workers
        self.shots = settings.shots
        self.optimization_level = settings.optimization_level
        self.queue_interval = settings.queue_interval
        self.show_transpiled = settings.show_transpiled
        self.real_timeout_seconds = settings.real_timeout_seconds
        self.real_max_pending_jobs = settings.real_max_pending_jobs
        self.cancel_real_on_timeout = settings.cancel_real_on_timeout
        self.cancel_real_on_queue_limit = settings.cancel_real_on_queue_limit

        modos = ", ".join(mode.value.upper() for mode in self.modes)
        logger.info("Inicializando pipeline com modos: %s", modos)

        _pipe_title("Pipeline de execução")
        _pipe_step("Modos selecionados", [modos])

        self.runtimes = RuntimeFactory.create_many(
            self.modes,
            parallel=self.parallel,
            max_workers=self.max_workers,
            settings=self.runtime_settings,
        )

        backends = [
            f"{mode.value.upper()}: {self._backend_name(runtime.backend)}"
            for mode, runtime in self.runtimes.items()
        ]

        _pipe_step("Runtimes carregados", backends)
        logger.info("Pipeline inicializada com runtimes: %s", backends)

    def _accent(self, mode: Mode):
        return PIPELINE_ACCENTS.get(mode.value, PIPELINE_ACCENTS["default"])

    def _backend_name(self, backend):
        try:
            name = getattr(backend, "name", None)

            if callable(name):
                return name()

            if name is not None:
                return name

        except Exception:
            pass

        return str(backend)

    def _as_qiskit_circuit(self, circuit) -> Any:
        """
        Aceita qualquer formato suportado pelo adapter Qiskit.
        """
        from quantum_cq._circuits.adapters import export_to_qiskit

        try:
            return export_to_qiskit(circuit)
        except TypeError as exc:
            raise TypeError(
                "A pipeline espera um circuito exportavel para Qiskit."
            ) from exc


    def _job_id(self, job):
        try:
            return job.job_id()
        except Exception:
            return "indisponivel"

    def _job_status_text(self, job):
        try:
            status = job.status()

            if hasattr(status, "name"):
                return status.name

            return str(status)

        except Exception as exc:
            return f"indisponivel ({type(exc).__name__})"

    def _job_status_normalized(self, job):
        status = self._job_status_text(job)
        status = str(status).upper().strip()

        if "." in status:
            status = status.split(".")[-1]

        return status

    def _backend_pending_jobs(self, backend):
        try:
            status = backend.status()
            return getattr(status, "pending_jobs", None)
        except Exception:
            return None

    def _monitorar_job_real(
        self,
        job,
        runtime,
        *,
        intervalo: int = 10,
        limite_segundos: int | None = None,
        limite_pendentes: int | None = None,
        cancelar_por_tempo: bool = False,
        cancelar_por_fila: bool = False,
    ) -> bool:
        """
        Mostra status da fila no modo REAL.

        Retorna False quando o job foi cancelado e o resultado nao deve ser
        aguardado por job.result().
        """
        inicio = monotonic()
        estados_finais = {"DONE", "ERROR", "CANCELLED", "CANCELED"}

        job_id = self._job_id(job)
        self.historico_jobs.append(job_id)
        logger.info(
            "Job IBM enviado: id=%s backend=%s",
            job_id,
            self._backend_name(runtime.backend),
        )

        _pipe_step(
            "Job IBM enviado",
            [
                f"ID: {job_id}",
                f"Backend: {self._backend_name(runtime.backend)}",
            ],
        )

        while True:
            status_normalizado = self._job_status_normalized(job)
            status_legivel = self._job_status_text(job)
            pendentes = self._backend_pending_jobs(runtime.backend)
            tempo = int(monotonic() - inicio)

            linhas = [
                f"Status: {status_legivel}",
                f"Tempo aguardando: {tempo} s",
            ]

            if pendentes is not None:
                linhas.append(f"Jobs pendentes no backend: {pendentes}")

            _pipe_step("Fila IBM Quantum", linhas)
            logger.info(
                "Fila IBM Quantum: job=%s status=%s tempo=%ss pendentes=%s",
                job_id,
                status_legivel,
                tempo,
                pendentes,
            )

            if status_normalizado in estados_finais:
                break

            if limite_segundos is not None and tempo >= limite_segundos:
                linhas_limite = [
                    f"Limite atingido: {limite_segundos} s",
                ]

                if cancelar_por_tempo:
                    if self._cancelar_job(job, "limite de tempo"):
                        linhas_limite.append("Job cancelado automaticamente.")
                        _pipe_step("Execução real cancelada", linhas_limite)
                        return False

                    linhas_limite.append(
                        "Não foi possível cancelar; o resultado será aguardado.",
                    )
                else:
                    linhas_limite.append(
                        "O resultado ainda será aguardado por job.result().",
                    )

                _pipe_step(
                    "Monitoramento pausado",
                    linhas_limite,
                )
                break

            if (
                limite_pendentes is not None
                and pendentes is not None
                and pendentes > limite_pendentes
            ):
                linhas_fila = [
                    f"Jobs pendentes no backend: {pendentes}",
                    f"Limite configurado: {limite_pendentes}",
                ]

                if cancelar_por_fila:
                    if self._cancelar_job(job, "fila acima do limite"):
                        linhas_fila.append("Job cancelado automaticamente.")
                        _pipe_step("Execução real cancelada", linhas_fila)
                        return False

                    linhas_fila.append(
                        "Não foi possível cancelar; o resultado será aguardado.",
                    )
                else:
                    linhas_fila.append(
                        "O resultado ainda será aguardado por job.result().",
                    )

                _pipe_step("Fila acima do limite", linhas_fila)
                break

            sleep(intervalo)

        return True

    def _cancelar_job(self, job, motivo: str) -> bool:
        try:
            job.cancel()
            logger.warning("Job IBM cancelado: motivo=%s job=%s", motivo, self._job_id(job))
            return True
        except Exception:
            logger.exception("Falha ao cancelar job IBM: motivo=%s", motivo)
            return False

    def _remover_medicoes_finais(self, circuit: Any) -> Any:
        try:
            circuito_sem_medicao = circuit.remove_final_measurements(inplace=False)
            if circuito_sem_medicao is not None:
                return circuito_sem_medicao
        except Exception:
            pass

        return circuit.copy()

    def _mostrar_circuito_de_partida(
        self,
        circuit: Any,
        *,
        title: str,
        equation: str | None = None,
        max_state_qubits: int = 4,
    ):
        _pipe_title(title)

        if equation:
            _pipe_step("Equação / interpretação", [equation])

        _pipe_step(
            "Circuito lógico de partida",
            ["Este é o circuito antes da transpilação."],
        )

        _pipe_display(
            circuit.draw(
                "mpl",
                scale=0.7,
            )
        )

        circuito_sem_medicao = self._remover_medicoes_finais(circuit)

        if circuito_sem_medicao.num_qubits <= max_state_qubits:
            try:
                Statevector, _ = _require_qiskit_pipeline()
                estado = Statevector.from_instruction(circuito_sem_medicao)
                _pipe_step(
                    "Vetor de estado",
                    ["Estado matemático antes da medição final."],
                )
                _pipe_display(estado.draw("latex"))
            except Exception as exc:
                _pipe_step(
                    "Vetor de estado indisponível",
                    [f"Motivo: {type(exc).__name__}"],
                )
        else:
            _pipe_step(
                "Vetor de estado não exibido",
                [
                    f"Circuito com {circuito_sem_medicao.num_qubits} qubits.",
                    "A saída ficaria grande demais para leitura didática.",
                ],
            )

    def _transpilar(
        self,
        circuit: Any,
        runtime: QuantumRuntime,
        *,
        optimization_level: int,
    ) -> Any:
        logger.info(
            "Transpilando circuito: backend=%s optimization_level=%s",
            self._backend_name(runtime.backend),
            optimization_level,
        )
        _, generate_preset_pass_manager = _require_qiskit_pipeline()
        pass_manager = generate_preset_pass_manager(
            backend=runtime.backend,
            optimization_level=optimization_level,
        )

        transpiled = self._run_unified_transpile(
            circuit,
            engine="qiskit",
            backend=runtime.backend,
            optimization_level=optimization_level,
            pass_manager=pass_manager,
        )
        logger.info(
            "Circuito transpilado: backend=%s qubits=%s",
            self._backend_name(runtime.backend),
            transpiled.num_qubits,
        )
        return transpiled

    def _extract_counts(self, result) -> dict:
        """
        Compatível com registros clássicos chamados 'meas', 'c'
        ou qualquer outro nome que exponha get_counts().
        """
        from quantum_cq._runtime.experiment import extract_counts_from_sampler_result

        return extract_counts_from_sampler_result(result)

    def _executar_modo(
        self,
        circuit: Any,
        mode: Mode,
        *,
        shots: int,
        optimization_level: int,
        queue_interval: int,
        show_transpiled: bool,
        real_timeout_seconds: int | None,
        real_max_pending_jobs: int | None,
        cancel_real_on_timeout: bool,
        cancel_real_on_queue_limit: bool,
    ) -> dict:
        runtime = self.runtimes[mode]
        logger.info(
            "Executando modo %s: backend=%s shots=%s optimization_level=%s",
            mode.value,
            self._backend_name(runtime.backend),
            shots,
            optimization_level,
        )

        _pipe_step(
            f"Modo {mode.value.upper()}",
            [
                f"Backend: {self._backend_name(runtime.backend)}",
                f"Shots: {shots}",
                f"Nível de otimização: {optimization_level}",
            ],
        )

        isa_circuit = self._transpilar(
            circuit,
            runtime,
            optimization_level=optimization_level,
        )

        if show_transpiled:
            _pipe_step(
                f"Circuito transpilado — {mode.value.upper()}",
                ["Circuito convertido para o backend selecionado."],
            )

            _pipe_display(
                isa_circuit.draw(
                    "mpl",
                    idle_wires=False,
                    scale=0.65,
                )
            )

        if mode == Mode.REAL and real_max_pending_jobs is not None:
            pendentes = self._backend_pending_jobs(runtime.backend)
            if pendentes is not None and pendentes > real_max_pending_jobs:
                linhas_fila = [
                    f"Jobs pendentes no backend: {pendentes}",
                    f"Limite configurado: {real_max_pending_jobs}",
                ]

                if cancel_real_on_queue_limit:
                    linhas_fila.append("Job real não enviado.")
                    _pipe_step("Fila IBM acima do limite", linhas_fila)
                    logger.warning(
                        "Job real não enviado: pendentes=%s limite=%s",
                        pendentes,
                        real_max_pending_jobs,
                    )
                    return {}

                linhas_fila.append("O job real será enviado mesmo assim.")
                _pipe_step("Fila IBM acima do limite", linhas_fila)

        job = runtime.sampler.run(
            [isa_circuit],
            shots=shots,
        )

        if mode == Mode.REAL:
            deve_aguardar_resultado = self._monitorar_job_real(
                job,
                runtime,
                intervalo=queue_interval,
                limite_segundos=real_timeout_seconds,
                limite_pendentes=real_max_pending_jobs,
                cancelar_por_tempo=cancel_real_on_timeout,
                cancelar_por_fila=cancel_real_on_queue_limit,
            )

            if not deve_aguardar_resultado:
                logger.warning("Execução real encerrada sem contagens")
                return {}

        result = job.result()
        counts = self._extract_counts(result)
        logger.info("Modo %s concluído com contagens: %s", mode.value, counts)

        _pipe_step(
            f"Leituras — {mode.value.upper()}",
            [str(counts)],
        )

        plot_histogram = _require_plot_histogram()
        _pipe_display(
            plot_histogram(
                counts,
                title=f"Leituras - {mode.value.upper()}",
                figsize=(8, 4),
            )
        )

        return counts

    def _executar_modos_em_paralelo(
        self,
        circuit: Any,
        *,
        shots: int,
        optimization_level: int,
        queue_interval: int,
        show_transpiled: bool,
        real_timeout_seconds: int | None,
        real_max_pending_jobs: int | None,
        cancel_real_on_timeout: bool,
        cancel_real_on_queue_limit: bool,
        max_workers: int | None,
    ) -> dict:
        worker_count = max_workers or len(self.modes)
        worker_count = max(1, min(worker_count, len(self.modes)))
        logger.info(
            "Executando %s modos em paralelo com %s workers",
            len(self.modes),
            worker_count,
        )

        resultados_por_modo = {}
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="quantum-cq-pipeline",
        ) as executor:
            futures = {
                executor.submit(
                    self._executar_modo,
                    circuit.copy(),
                    mode,
                    shots=shots,
                    optimization_level=optimization_level,
                    queue_interval=queue_interval,
                    show_transpiled=show_transpiled,
                    real_timeout_seconds=real_timeout_seconds,
                    real_max_pending_jobs=real_max_pending_jobs,
                    cancel_real_on_timeout=cancel_real_on_timeout,
                    cancel_real_on_queue_limit=cancel_real_on_queue_limit,
                ): mode
                for mode in self.modes
            }

            for future in as_completed(futures):
                mode = futures[future]
                try:
                    resultados_por_modo[mode.value] = future.result()
                except Exception:
                    logger.exception("Falha ao executar modo %s", mode.value)
                    raise

        return {
            mode.value: resultados_por_modo[mode.value]
            for mode in self.modes
        }

    def run_batch(
        self,
        circuit,
        *,
        title: str = "Execução do circuito",
        equation: str | None = None,
        shots: int | None = None,
        optimization_level: int | None = None,
        queue_interval: int | None = None,
        show_transpiled: bool | None = None,
        parallel: bool | None = None,
        max_workers: int | None = None,
        real_timeout_seconds: int | None = None,
        real_max_pending_jobs: int | None = None,
        cancel_real_on_timeout: bool | None = None,
        cancel_real_on_queue_limit: bool | None = None,
    ) -> dict:
        configure_logging()
        circuit = self._as_qiskit_circuit(circuit)
        shots = self.shots if shots is None else shots
        optimization_level = (
            self.optimization_level
            if optimization_level is None
            else optimization_level
        )
        queue_interval = (
            self.queue_interval
            if queue_interval is None
            else queue_interval
        )
        show_transpiled = (
            self.show_transpiled
            if show_transpiled is None
            else show_transpiled
        )
        real_timeout_seconds = (
            self.real_timeout_seconds
            if real_timeout_seconds is None
            else real_timeout_seconds
        )
        real_max_pending_jobs = (
            self.real_max_pending_jobs
            if real_max_pending_jobs is None
            else real_max_pending_jobs
        )
        cancel_real_on_timeout = (
            self.cancel_real_on_timeout
            if cancel_real_on_timeout is None
            else cancel_real_on_timeout
        )
        cancel_real_on_queue_limit = (
            self.cancel_real_on_queue_limit
            if cancel_real_on_queue_limit is None
            else cancel_real_on_queue_limit
        )
        logger.info(
            "Iniciando run_batch: title=%s modes=%s shots=%s",
            title,
            [mode.value for mode in self.modes],
            shots,
        )

        self._mostrar_circuito_de_partida(
            circuit,
            title=title,
            equation=equation,
        )

        resultados = {}
        use_parallel = self.parallel if parallel is None else parallel
        worker_count = max_workers or self.max_workers

        if use_parallel and len(self.modes) > 1:
            resultados = self._executar_modos_em_paralelo(
                circuit,
                shots=shots,
                optimization_level=optimization_level,
                queue_interval=queue_interval,
                show_transpiled=show_transpiled,
                real_timeout_seconds=real_timeout_seconds,
                real_max_pending_jobs=real_max_pending_jobs,
                cancel_real_on_timeout=cancel_real_on_timeout,
                cancel_real_on_queue_limit=cancel_real_on_queue_limit,
                max_workers=worker_count,
            )
        else:
            for mode in self.modes:
                counts = self._executar_modo(
                    circuit,
                    mode,
                    shots=shots,
                    optimization_level=optimization_level,
                    queue_interval=queue_interval,
                    show_transpiled=show_transpiled,
                    real_timeout_seconds=real_timeout_seconds,
                    real_max_pending_jobs=real_max_pending_jobs,
                    cancel_real_on_timeout=cancel_real_on_timeout,
                    cancel_real_on_queue_limit=cancel_real_on_queue_limit,
                )

                resultados[mode.value] = counts

        _pipe_step(
            "Execução concluída",
            ["Todos os modos selecionados foram executados."],
        )
        logger.info("run_batch concluído: %s", resultados)

        return resultados

    def run_custom(
        self,
        circuit,
        mode: Mode,
        *,
        title: str = "Execução personalizada",
        equation: str | None = None,
        shots: int | None = None,
        optimization_level: int | None = None,
        queue_interval: int | None = None,
        show_transpiled: bool | None = None,
        parallel: bool | None = None,
        max_workers: int | None = None,
        real_timeout_seconds: int | None = None,
        real_max_pending_jobs: int | None = None,
        cancel_real_on_timeout: bool | None = None,
        cancel_real_on_queue_limit: bool | None = None,
    ) -> dict:
        if isinstance(mode, str):
            mode = Mode(mode.lower())

        if mode not in self.runtimes:
            logger.info("Criando runtime sob demanda para modo %s", mode.value)
            self.runtimes[mode] = RuntimeFactory.create(
                mode,
                settings=self.runtime_settings,
            )

        old_modes = self.modes
        self.modes = [mode]

        try:
            result = self.run_batch(
                circuit,
                title=title,
                equation=equation,
                shots=shots,
                optimization_level=optimization_level,
                queue_interval=queue_interval,
                show_transpiled=show_transpiled,
                parallel=parallel,
                max_workers=max_workers,
                real_timeout_seconds=real_timeout_seconds,
                real_max_pending_jobs=real_max_pending_jobs,
                cancel_real_on_timeout=cancel_real_on_timeout,
                cancel_real_on_queue_limit=cancel_real_on_queue_limit,
            )
        finally:
            self.modes = old_modes

        return result[mode.value]
