import logging
import warnings
from collections.abc import Iterable, Sized
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from os import getenv
from time import sleep
from typing import Any, Protocol, cast

from quantum_cq._core.logging_config import configure_logging
from quantum_cq._core.settings import RuntimeSettings, get_runtime_settings


logger = logging.getLogger(__name__)


DEFAULT_RUNTIME_SETTINGS = RuntimeSettings()

# Pontos de injecao para testes sem carregar qiskit-ibm-runtime no import.
QiskitRuntimeService: Any | None = None
SamplerV2: Any | None = None
IBMInputValueError: type[Exception] | None = None


class Mode(Enum):
    IDEAL = "ideal"
    NOISY = "noisy"
    REAL = "real"


class QuantumJobLike(Protocol):
    def result(self) -> Any:
        ...

    def job_id(self) -> str:
        ...

    def status(self) -> Any:
        ...

    def cancel(self) -> Any:
        ...


class SamplerLike(Protocol):
    def run(self, pubs: Any, *, shots: int | None = None) -> QuantumJobLike:
        ...


@dataclass
class QuantumRuntime:
    backend: Any
    sampler: SamplerLike
    service: Any | None = None
    noise_model: Any | None = None


def _require_aer() -> tuple[Any, Any, Any]:
    try:
        from qiskit.primitives import BackendSamplerV2
        from qiskit_aer import AerSimulator
        from qiskit_aer.noise import NoiseModel
    except ImportError as exc:
        raise ImportError(
            "Para usar runtime ideal/noisy, instale quantum-cq[aer]."
        ) from exc

    return AerSimulator, NoiseModel, BackendSamplerV2


def _require_ibm_runtime() -> tuple[Any, Any, type[Exception]]:
    global QiskitRuntimeService, SamplerV2, IBMInputValueError

    if QiskitRuntimeService is not None or SamplerV2 is not None:
        return QiskitRuntimeService, SamplerV2, IBMInputValueError or Exception

    try:
        from qiskit_ibm_runtime import QiskitRuntimeService as service_cls
        from qiskit_ibm_runtime import SamplerV2 as sampler_cls
        from qiskit_ibm_runtime.exceptions import IBMInputValueError as input_error_cls
    except ImportError as exc:
        raise ImportError(
            "Para usar IBM Runtime real ou runtime noisy baseado em backend IBM, "
            "instale quantum-cq[ibm]."
        ) from exc

    QiskitRuntimeService = service_cls
    SamplerV2 = sampler_cls
    IBMInputValueError = input_error_cls
    return QiskitRuntimeService, SamplerV2, IBMInputValueError


@dataclass(frozen=True)
class IBMRuntimeConfig:
    token: str
    channel: str = "ibm_quantum_platform"
    instance: str | None = None
    region: str | None = None
    plans_preference: str | None = None
    tags: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        normalized_instance = None if self.instance == "" else self.instance
        if normalized_instance == "ibm_cloud":
            raise ValueError("ibm_cloud e um channel, nao um instance IBM")
        object.__setattr__(self, "instance", normalized_instance)
        if self.channel == "ibm_cloud":
            warnings.warn(
                "channel='ibm_cloud' e legado; prefira 'ibm_quantum_platform'",
                DeprecationWarning,
                stacklevel=2,
            )
        if self.tags is not None:
            object.__setattr__(self, "tags", tuple(self.tags))

    def safe_summary(self) -> dict[str, Any]:
        return {
            "token_configured": bool(self.token),
            "channel": self.channel,
            "instance": "configured" if self.instance else "auto_discovery",
            "region": self.region,
            "plans_preference": self.plans_preference,
            "tags": self.tags,
        }

    def to_runtime_settings(self) -> RuntimeSettings:
        return RuntimeSettings(
            ibm_channel=self.channel,
            ibm_token=self.token,
            ibm_instance=self.instance,
            ibm_region=self.region,
            ibm_plans_preference=self.plans_preference,
            ibm_tags=self.tags,
        )

    def __repr__(self) -> str:
        return f"IBMRuntimeConfig({self.safe_summary()!r})"


class RuntimeFactory:
    MAX_RETRIES = DEFAULT_RUNTIME_SETTINGS.max_retries
    WAIT_SECONDS = DEFAULT_RUNTIME_SETTINGS.wait_seconds

    @staticmethod
    def _normalize_mode(mode: Mode | str) -> Mode:
        if isinstance(mode, str):
            return Mode(mode.lower())

        return mode

    @staticmethod
    def _resolve_settings(
        settings: RuntimeSettings | None = None,
        *,
        ibm_channel: str | None = None,
        ibm_token: str | None = None,
        ibm_instance: str | None = None,
        ibm_region: str | None = None,
        ibm_plans_preference: str | None = None,
        ibm_tags: tuple[str, ...] | list[str] | None = None,
        max_retries: int | None = None,
        wait_seconds: int | None = None,
    ) -> RuntimeSettings:
        return (settings or get_runtime_settings()).with_overrides(
            ibm_channel=ibm_channel,
            ibm_token=ibm_token,
            ibm_instance=ibm_instance,
            ibm_region=ibm_region,
            ibm_plans_preference=ibm_plans_preference,
            ibm_tags=ibm_tags,
            max_retries=max_retries,
            wait_seconds=wait_seconds,
        )

    @staticmethod
    def create(
        mode: Mode | str = Mode.IDEAL,
        *,
        settings: RuntimeSettings | None = None,
        ibm_channel: str | None = None,
        ibm_token: str | None = None,
        ibm_instance: str | None = None,
        ibm_region: str | None = None,
        ibm_plans_preference: str | None = None,
        ibm_tags: tuple[str, ...] | list[str] | None = None,
        backend_name: str | None = None,
        max_retries: int | None = None,
        wait_seconds: int | None = None,
    ) -> QuantumRuntime:
        configure_logging()
        settings = RuntimeFactory._resolve_settings(
            settings,
            ibm_channel=ibm_channel,
            ibm_token=ibm_token,
            ibm_instance=ibm_instance,
            ibm_region=ibm_region,
            ibm_plans_preference=ibm_plans_preference,
            ibm_tags=ibm_tags,
            max_retries=max_retries,
            wait_seconds=wait_seconds,
        )
        mode = RuntimeFactory._normalize_mode(mode)
        logger.info("Criando runtime para modo %s", mode.value)

        if mode == Mode.IDEAL:
            AerSimulator, _, BackendSamplerV2 = _require_aer()
            ideal_backend = AerSimulator()
            sampler = BackendSamplerV2(backend=ideal_backend)
            logger.info("Runtime ideal criado com backend %s", ideal_backend.name)
            return QuantumRuntime(backend=ideal_backend, sampler=cast(SamplerLike, sampler))

        service = RuntimeFactory._service(settings)
        if backend_name is None:
            real_backend = RuntimeFactory._get_real_backend(service, settings=settings)
        else:
            real_backend = RuntimeFactory._get_real_backend(
                service,
                settings=settings,
                backend_name=backend_name,
            )

        if mode == Mode.REAL:
            _, SamplerV2, _ = _require_ibm_runtime()
            sampler = SamplerV2(mode=real_backend)
            logger.info("Runtime real criado com backend %s", real_backend.name)
            return QuantumRuntime(
                backend=real_backend,
                sampler=cast(SamplerLike, sampler),
                service=service,
            )

        if mode == Mode.NOISY:
            AerSimulator, NoiseModel, BackendSamplerV2 = _require_aer()
            noise_model = NoiseModel.from_backend(real_backend)
            backend = AerSimulator(noise_model=noise_model)
            sampler = BackendSamplerV2(backend=backend)
            logger.info("Runtime noisy criado a partir do backend %s", real_backend.name)

            return QuantumRuntime(
                backend=backend,
                sampler=cast(SamplerLike, sampler),
                service=service,
                noise_model=noise_model,
            )

        raise ValueError(f"Modo inválido: {mode}")

    @staticmethod
    def create_many(
        modes: Iterable[Mode | str],
        *,
        parallel: bool = True,
        max_workers: int | None = None,
        settings: RuntimeSettings | None = None,
        ibm_channel: str | None = None,
        ibm_token: str | None = None,
        ibm_instance: str | None = None,
        runtime_max_retries: int | None = None,
        runtime_wait_seconds: int | None = None,
    ) -> dict[Mode, QuantumRuntime]:
        configure_logging()
        settings = RuntimeFactory._resolve_settings(
            settings,
            ibm_channel=ibm_channel,
            ibm_token=ibm_token,
            ibm_instance=ibm_instance,
            max_retries=runtime_max_retries,
            wait_seconds=runtime_wait_seconds,
        )

        normalized_modes = []
        for mode in modes:
            normalized = RuntimeFactory._normalize_mode(mode)
            if normalized not in normalized_modes:
                normalized_modes.append(normalized)

        if not normalized_modes:
            return {}

        worker_count = max_workers or len(normalized_modes)
        worker_count = max(1, min(worker_count, len(normalized_modes)))

        if not parallel or worker_count == 1:
            return {
                mode: RuntimeFactory.create(mode, settings=settings)
                for mode in normalized_modes
            }

        logger.info(
            "Criando %s runtimes em paralelo com %s workers",
            len(normalized_modes),
            worker_count,
        )

        runtimes = {}
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="quantum-cq-runtime",
        ) as executor:
            futures = {
                executor.submit(RuntimeFactory.create, mode, settings=settings): mode
                for mode in normalized_modes
            }

            for future in as_completed(futures):
                mode = futures[future]
                try:
                    runtimes[mode] = future.result()
                except Exception:
                    logger.exception("Falha ao criar runtime para modo %s", mode.value)
                    raise

        return {
            mode: runtimes[mode]
            for mode in normalized_modes
        }

    @staticmethod
    def _service(settings: RuntimeSettings | None = None) -> Any:
        QiskitRuntimeService, _, IBMInputValueError = _require_ibm_runtime()
        settings = settings or get_runtime_settings()

        if settings.ibm_token:
            ibm_instance = RuntimeFactory._resolve_ibm_instance(settings)
            if settings.ibm_channel == "ibm_cloud":
                logger.warning("Usando channel legado ibm_cloud")
            logger.info(
                "Criando serviço IBM Quantum: token_configurado=%s channel=%s instance=%s",
                True,
                settings.ibm_channel,
                "configured" if ibm_instance else "auto_discovery",
            )
            kwargs = RuntimeFactory._service_kwargs(settings, ibm_instance)
            try:
                service = QiskitRuntimeService(**kwargs)
            except IBMInputValueError as exc:
                raise RuntimeFactory._ibm_autodiscovery_error(settings, exc) from exc
            RuntimeFactory._log_service_details(service)
            return service

        logger.info("Criando serviço IBM Quantum com configuração padrão")
        try:
            return QiskitRuntimeService()
        except IBMInputValueError as exc:
            raise RuntimeFactory._ibm_autodiscovery_error(settings, exc) from exc

    @staticmethod
    def _validate_ibm_account_settings(settings: RuntimeSettings) -> None:
        RuntimeFactory._resolve_ibm_instance(settings)

    @staticmethod
    def _resolve_ibm_instance(settings: RuntimeSettings) -> str | None:
        instance = (settings.ibm_instance or getenv("IBM_QUANTUM_INSTANCE") or "").strip()
        if instance in {"ibm_cloud", "ibm_quantum_platform"}:
            raise ValueError(
                "ibm_instance deve ser o CRN ou nome real da instancia. "
                "Nao use 'ibm_cloud' como instance; tambem nao use 'ibm_quantum_platform'. "
                "Esses valores sao channels."
            )
        return instance or None

    @staticmethod
    def _ibm_autodiscovery_error(settings: RuntimeSettings, exc: Exception) -> RuntimeError:
        message = str(exc)
        if "No matching instances found" not in message:
            return RuntimeError(
                "Falha ao criar servico IBM Quantum Runtime. "
                f"channel={settings.ibm_channel}; "
                f"instance={'configured' if settings.ibm_instance else 'auto_discovery'}."
            )

        return RuntimeError(
            "A biblioteca tentou deixar a IBM resolver a instancia automaticamente "
            "(instance=None), mas a IBM nao retornou nenhuma instancia compativel "
            f"para channel='{settings.ibm_channel}'. "
            "Tente alternar o channel entre 'ibm_quantum_platform' e 'ibm_cloud'. "
            "Se a sua conta exigir, informe IBM_QUANTUM_INSTANCE com o CRN ou nome real "
            "da instancia; isso nao e obrigatorio pela biblioteca. "
            "Nao use 'ibm_cloud' como instance, pois ele e um channel."
        )

    @staticmethod
    def _service_kwargs(settings: RuntimeSettings, instance: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "channel": cast(Any, settings.ibm_channel),
            "token": settings.ibm_token,
        }
        if instance:
            kwargs["instance"] = instance
        if settings.ibm_region:
            kwargs["region"] = settings.ibm_region
        if settings.ibm_plans_preference:
            kwargs["plans_preference"] = settings.ibm_plans_preference
        if settings.ibm_tags:
            kwargs["tags"] = list(settings.ibm_tags)
        return kwargs

    @staticmethod
    def _log_service_details(service: Any) -> None:
        try:
            instances = getattr(service, "instances", None)
            if callable(instances):
                found = instances()
                count: int | str = len(found) if isinstance(found, Sized) else "desconhecido"
                logger.info("Instâncias IBM encontradas: %s", count)
        except Exception:
            logger.info("Instâncias IBM não listadas")

        try:
            active_instance = getattr(service, "active_instance", None)
            active = active_instance() if callable(active_instance) else active_instance
            logger.info("IBM active_instance: %s", active or "auto_discovery")
        except Exception:
            logger.info("IBM active_instance indisponível")

        try:
            backends = service.backends()
            names = [getattr(backend, "name", str(backend)) for backend in backends]
            logger.info("Backends IBM disponíveis: %s", names)
        except Exception:
            logger.info("Backends IBM não listados")

    @staticmethod
    def _get_real_backend(
        service: Any,
        *,
        settings: RuntimeSettings | None = None,
        backend_name: str | None = None,
    ) -> Any:
        settings = settings or get_runtime_settings()
        last_error = None

        for attempt in range(1, settings.max_retries + 1):
            try:
                if backend_name and backend_name != "least_busy":
                    selected_backend = service.backend(backend_name)
                else:
                    selected_backend = service.least_busy(
                        operational=True,
                        simulator=False,
                    )

                logger.info("Backend real selecionado: %s", selected_backend.name)
                return selected_backend

            except Exception as error:
                last_error = error
                logger.warning(
                    "Tentativa %s falhou ao conectar ao backend real",
                    attempt,
                    exc_info=True,
                )

                if attempt < settings.max_retries:
                    sleep(settings.wait_seconds)

        raise RuntimeError(
            "Não foi possível conectar a um backend real da IBM "
            f"após {settings.max_retries} tentativas."
        ) from last_error


def health_check(
    *,
    settings: RuntimeSettings | None = None,
    ibm_channel: str | None = None,
    ibm_token: str | None = None,
    ibm_instance: str | None = None,
    max_retries: int | None = None,
    wait_seconds: int | None = None,
):
    """Verifica apenas a conexao com o servico IBM."""
    configure_logging()
    settings = RuntimeFactory._resolve_settings(
        settings,
        ibm_channel=ibm_channel,
        ibm_token=ibm_token,
        ibm_instance=ibm_instance,
        max_retries=max_retries,
        wait_seconds=wait_seconds,
    )
    logger.info("Iniciando health check IBM Quantum")
    print('=== Health Check ===')

    print('[1/2] Testando conexao IBM...')
    if not settings.ibm_token:
        logger.warning("IBM_QUANTUM_TOKEN nao configurado")
        print('      SKIP - IBM_QUANTUM_TOKEN nao configurado.')
    else:
        try:
            service = RuntimeFactory._service(settings)
            backend = RuntimeFactory._get_real_backend(service, settings=settings)
            logger.info(
                "Health check IBM OK: backend=%s qubits=%s",
                backend.name,
                backend.num_qubits,
            )
            print(f'      OK - conectado ao computador {backend.name} ({backend.num_qubits} qubits).')
        except Exception as e:
            logger.exception("Health check IBM falhou")
            print(f'      FALHA - {e}')

    # 2. Resumo
    logger.info("Health check concluido")
    print('[2/2] Health check concluido.')
    print('===================')


if __name__ == "__main__":
    health_check()
