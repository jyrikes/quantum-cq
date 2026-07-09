"""Code-first and environment-driven settings for quantum_cq."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from os import getenv
from typing import Any


def _get_bool(name: str, default: bool) -> bool:
    value = getenv(name)
    if value is None or value.strip() == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _get_int(name: str, default: int | None = None) -> int | None:
    value = getenv(name)
    if value is None or value.strip() == "":
        return default

    return int(value)


def _get_str(name: str, default: str | None = None) -> str | None:
    value = getenv(name)
    if value is None or value.strip() == "":
        return default

    return value.strip()


def _without_none(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value is not None
    }


def _mode_name(mode: Any) -> str:
    value = getattr(mode, "value", mode)
    return str(value).lower()


@dataclass(frozen=True)
class RuntimeSettings:
    ibm_channel: str = "ibm_quantum_platform"
    ibm_token: str | None = None
    ibm_instance: str | None = None
    ibm_region: str | None = None
    ibm_plans_preference: str | None = None
    ibm_tags: tuple[str, ...] | None = None
    max_retries: int = 3
    wait_seconds: int = 2

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        return cls(
            ibm_channel=_get_str("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform") or "ibm_quantum_platform",
            ibm_token=_get_str("IBM_QUANTUM_TOKEN"),
            ibm_instance=_get_str("IBM_QUANTUM_INSTANCE"),
            ibm_region=_get_str("IBM_QUANTUM_REGION"),
            ibm_plans_preference=_get_str("IBM_QUANTUM_PLANS_PREFERENCE"),
            ibm_tags=tuple(
                tag.strip()
                for tag in (_get_str("IBM_QUANTUM_TAGS", "") or "").split(",")
                if tag.strip()
            ) or None,
            max_retries=_get_int("QUANTUM_CQ_RUNTIME_MAX_RETRIES", 3) or 3,
            wait_seconds=_get_int("QUANTUM_CQ_RUNTIME_WAIT_SECONDS", 2) or 2,
        )

    def with_overrides(
        self,
        *,
        ibm_channel: str | None = None,
        ibm_token: str | None = None,
        ibm_instance: str | None = None,
        ibm_region: str | None = None,
        ibm_plans_preference: str | None = None,
        ibm_tags: tuple[str, ...] | list[str] | None = None,
        max_retries: int | None = None,
        wait_seconds: int | None = None,
    ) -> "RuntimeSettings":
        return replace(
            self,
            **_without_none(
                {
                    "ibm_channel": ibm_channel,
                    "ibm_token": ibm_token,
                    "ibm_instance": ibm_instance,
                    "ibm_region": ibm_region,
                    "ibm_plans_preference": ibm_plans_preference,
                    "ibm_tags": tuple(ibm_tags) if ibm_tags is not None else None,
                    "max_retries": max_retries,
                    "wait_seconds": wait_seconds,
                }
            ),
        )


@dataclass(frozen=True)
class PipelineSettings:
    modes: tuple[str, ...] = ("ideal",)
    parallel: bool = True
    max_workers: int | None = None
    shots: int = 1024
    optimization_level: int = 3
    queue_interval: int = 10
    show_transpiled: bool = True
    real_timeout_seconds: int | None = None
    real_max_pending_jobs: int | None = None
    cancel_real_on_timeout: bool = False
    cancel_real_on_queue_limit: bool = False

    @classmethod
    def from_env(cls) -> "PipelineSettings":
        modes = tuple(
            mode.strip().lower()
            for mode in (_get_str("QUANTUM_CQ_MODES", "ideal") or "").split(",")
            if mode.strip()
        )

        return cls(
            modes=modes or ("ideal",),
            parallel=_get_bool("QUANTUM_CQ_PIPELINE_PARALLEL", True),
            max_workers=_get_int("QUANTUM_CQ_PIPELINE_MAX_WORKERS"),
            shots=_get_int("QUANTUM_CQ_SHOTS", 1024) or 1024,
            optimization_level=_get_int("QUANTUM_CQ_OPTIMIZATION_LEVEL", 3) or 3,
            queue_interval=_get_int("QUANTUM_CQ_QUEUE_INTERVAL", 10) or 10,
            show_transpiled=_get_bool("QUANTUM_CQ_SHOW_TRANSPILED", True),
            real_timeout_seconds=_get_int("QUANTUM_CQ_REAL_TIMEOUT_SECONDS"),
            real_max_pending_jobs=_get_int("QUANTUM_CQ_REAL_MAX_PENDING_JOBS"),
            cancel_real_on_timeout=_get_bool(
                "QUANTUM_CQ_CANCEL_REAL_ON_TIMEOUT",
                False,
            ),
            cancel_real_on_queue_limit=_get_bool(
                "QUANTUM_CQ_CANCEL_REAL_ON_QUEUE_LIMIT",
                False,
            ),
        )

    def with_overrides(
        self,
        *,
        modes: Iterable[Any] | None = None,
        parallel: bool | None = None,
        max_workers: int | None = None,
        shots: int | None = None,
        optimization_level: int | None = None,
        queue_interval: int | None = None,
        show_transpiled: bool | None = None,
        real_timeout_seconds: int | None = None,
        real_max_pending_jobs: int | None = None,
        cancel_real_on_timeout: bool | None = None,
        cancel_real_on_queue_limit: bool | None = None,
    ) -> "PipelineSettings":
        mode_values = None
        if modes is not None:
            mode_values = tuple(_mode_name(mode) for mode in modes)

        return replace(
            self,
            **_without_none(
                {
                    "modes": mode_values,
                    "parallel": parallel,
                    "max_workers": max_workers,
                    "shots": shots,
                    "optimization_level": optimization_level,
                    "queue_interval": queue_interval,
                    "show_transpiled": show_transpiled,
                    "real_timeout_seconds": real_timeout_seconds,
                    "real_max_pending_jobs": real_max_pending_jobs,
                    "cancel_real_on_timeout": cancel_real_on_timeout,
                    "cancel_real_on_queue_limit": cancel_real_on_queue_limit,
                }
            ),
        )


def get_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings.from_env()


def get_pipeline_settings() -> PipelineSettings:
    return PipelineSettings.from_env()
