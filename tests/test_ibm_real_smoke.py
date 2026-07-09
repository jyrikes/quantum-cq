import os

import pytest

from quantum_cq import CQ


pytestmark = pytest.mark.ibm_real


def _ibm_config():
    token = os.environ.get("IBM_QUANTUM_TOKEN", "").strip()
    if not token:
        pytest.fail("IBM_QUANTUM_TOKEN deve estar definido para testes IBM reais")

    return CQ.ibm(
        token=token,
        channel=os.getenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform"),
        instance=os.getenv("IBM_QUANTUM_INSTANCE") or None,
    )


def _backend_name() -> str:
    return os.getenv("IBM_QUANTUM_BACKEND", "least_busy")


def _shots() -> int:
    return int(os.getenv("IBM_QUANTUM_SHOTS", "32"))


def _timeout() -> int:
    return int(os.getenv("IBM_QUANTUM_TIMEOUT", "300"))


def test_real_ibm_deutsch_smoke():
    result = CQ.run(
        CQ.deutsch(case=2),
        mode="real",
        ibm=_ibm_config(),
        backend=_backend_name(),
        shots=_shots(),
        timeout=_timeout(),
        title="IBM real smoke test - Deutsch case=2",
    )

    assert result is not None
    assert result.experiments
    exp = result.experiments[0]
    assert exp.mode == "real"
    assert exp.backend_name
    assert exp.job_id
    assert exp.counts
    assert sum(exp.counts.values()) > 0
    assert exp.status in {"completed", "done", "success"}
    assert result.classify("deutsch") in {"constant", "balanced", "unknown"}


def test_real_ibm_multiple_circuits_smoke():
    result = CQ.run(
        circuits=[
            CQ.deutsch(case=1),
            CQ.deutsch(case=2),
        ],
        modes=["real"],
        ibm=_ibm_config(),
        backend=_backend_name(),
        shots=_shots(),
        timeout=_timeout(),
        title="IBM real smoke test - multiple circuits",
    )

    assert len(result.experiments) == 2
    assert all(exp.backend_name for exp in result.experiments)
    assert all(exp.job_id for exp in result.experiments)
    assert all(exp.counts for exp in result.experiments)
