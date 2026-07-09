from quantum_cq._runtime.runtime import Mode
from quantum_cq._core.settings import PipelineSettings, RuntimeSettings, get_pipeline_settings

# ==========================================
# CONFIGURAÇÃO PADRÃO DE EXECUÇÃO
# Cada seção cria um circuito e chama esta pipeline.
# ==========================================

# Para deixar o notebook rápido e seguro durante estudo,
# o padrão usa apenas o simulador ideal. Configure
# QUANTUM_CQ_MODES=ideal,noisy ou QUANTUM_CQ_MODES=ideal,noisy,real
# para incluir simulador com ruído ou hardware real.
MODOS_PADRAO = [
    Mode(mode)
    for mode in get_pipeline_settings().modes
]

# Para incluir hardware real, use:
# MODOS_PADRAO = [Mode.IDEAL, Mode.NOISY, Mode.REAL]

def create_pipeline(
    settings: PipelineSettings | None = None,
    runtime_settings: RuntimeSettings | None = None,
    **overrides,
):
    from quantum_cq._runtime.pipeline import BenchmarkingPipeline

    settings = settings or get_pipeline_settings()
    return BenchmarkingPipeline(
        settings=settings,
        runtime_settings=runtime_settings,
        **overrides,
    )
