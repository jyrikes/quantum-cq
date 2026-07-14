# Repository layout

## Biblioteca

Arquivos que fazem parte da biblioteca Python:

- `src/quantum_cq/`
- `pyproject.toml`
- `requirements.txt`
- `requirements/`
- `README.md`

Esses arquivos definem a API, runtime, pipeline, encoders, algorithms,
navigation, walks, tests e configuracao de pacote.

## Testes

Testes versionaveis:

- `tests/`

Os testes IBM reais ficam opt-in com `--run-ibm-real` e nao devem rodar no
pytest padrao.

## Documentacao e notebooks oficiais

Documentacao versionavel:

- `docs/`

Notebooks oficiais pequenos e mantidos:

- `notebooks/quantum_cq_getting_started.ipynb`
- `notebooks/quantum_cq_full_pipeline_navigation.ipynb`
- `notebooks/quantum_cq_teoria_biblioteca_demo.ipynb`
- `notebooks/quantum_cq_simple_api_lab.ipynb`
- `notebooks/quantum_cq_ibm_real_smoke.ipynb`

Esses notebooks nao devem conter token real nem outputs grandes.

## Artefatos locais nao essenciais

Arquivos locais que nao fazem parte da biblioteca:

- `logs/`
- `results/`
- `notebooks/experiments/`
- `.pytest_cache/`
- `__pycache__/`
- `*.egg-info/`
- notebooks executados gerados por `nbconvert`

Esses arquivos podem ser recriados por execucoes locais e estao no `.gitignore`.
