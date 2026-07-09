# Notebook original preservado

Fonte: `003_execucao_com_modulo_qc_pipeline_original_limpo(3).ipynb`

## Mapa de células

| Célula | Tipo | Arquivo/Resumo |
|---:|---|---|
| 0 | markdown | # Algoritmos de Deutsch-Jozsa e Bernstein-Vazirani |
| 1 | markdown | ## 1. Configuracao do Ambiente |
| 2 | code | `src/quantum_cq/extracted/cell_002_setup_environment.py` |
| 3 | markdown | ## 2. RuntimeFactory |
| 4 | code | `src/quantum_cq/extracted/cell_004_runtime_factory.py` |
| 5 | markdown | ## 3. BenchmarkingPipeline |
| 6 | code | `src/quantum_cq/extracted/cell_006_benchmarking_pipeline.py` |
| 7 | code | `src/quantum_cq/extracted/cell_007_execution_config.py` |
| 8 | markdown | ## 3.1. Módulo compacto para circuitos tabulares |
| 9 | code | `src/quantum_cq/extracted/cell_009_cq_compact_module.py` |
| 10 | markdown | ## 4. Paralelismo Quantico |
| 11 | code | `src/quantum_cq/extracted/cell_011_quantum_parallelism.py` |
| 12 | markdown | ## 5. Algoritmo de Deutsch |
| 13 | code | `src/quantum_cq/extracted/cell_013_deutsch_algorithm.py` |
| 14 | markdown | ## 6. Algoritmo de Deutsch-Jozsa |
| 15 | code | `src/quantum_cq/extracted/cell_015_deutsch_jozsa_algorithm.py` |
| 16 | markdown | ## 7. Algoritmo de Bernstein-Vazirani |
| 17 | code | `src/quantum_cq/extracted/cell_017_bernstein_vazirani_algorithm.py` |
| 18 | markdown | ## 8. Conclusao |
| 19 | code | `src/quantum_cq/extracted/cell_019_cq_embedded_backup.py` |
| 20 | code | `src/quantum_cq/extracted/cell_020_cq_embedded.py` |

## Conteúdo textual e blocos

### Célula 0 (markdown)

# Algoritmos de Deutsch-Jozsa e Bernstein-Vazirani

| Informacao | Valor |
|------------|-------|
| Aluno | Jose Yrikes |
| Disciplina | Computacao Quantica |
| Professor | Fabio Novaes |
| Instituicao | UFRPE/UABJ |

### Célula 1 (markdown)

## 1. Configuracao do Ambiente

### Célula 2 (code)

Código preservado em `src/quantum_cq/extracted/cell_002_setup_environment.py`.

### Célula 3 (markdown)

## 2. RuntimeFactory

### Célula 4 (code)

Código preservado em `src/quantum_cq/extracted/cell_004_runtime_factory.py`.

### Célula 5 (markdown)

## 3. BenchmarkingPipeline

### Célula 6 (code)

Código preservado em `src/quantum_cq/extracted/cell_006_benchmarking_pipeline.py`.

### Célula 7 (code)

Código preservado em `src/quantum_cq/extracted/cell_007_execution_config.py`.

### Célula 8 (markdown)

## 3.1. Módulo compacto para circuitos tabulares

Este módulo trata o circuito como uma peça isolada: uma matriz de qubits por momentos lógicos, com suporte a subcircuitos, bits clássicos, pontos de observação sem colapso, separadores e portas customizadas.

### Célula 9 (code)

Código preservado em `src/quantum_cq/extracted/cell_009_cq_compact_module.py`.

### Célula 10 (markdown)

## 4. Paralelismo Quantico

O paralelismo quantico permite avaliar uma funcao em multiplas entradas usando superposicao.

### Célula 11 (code)

Código preservado em `src/quantum_cq/extracted/cell_011_quantum_parallelism.py`.

### Célula 12 (markdown)

## 5. Algoritmo de Deutsch

Determina se f eh constante ou balanceada com 1 consulta.

### Célula 13 (code)

Código preservado em `src/quantum_cq/extracted/cell_013_deutsch_algorithm.py`.

### Célula 14 (markdown)

## 6. Algoritmo de Deutsch-Jozsa

Extensao para n qubits.

### Célula 15 (code)

Código preservado em `src/quantum_cq/extracted/cell_015_deutsch_jozsa_algorithm.py`.

### Célula 16 (markdown)

## 7. Algoritmo de Bernstein-Vazirani

Recupera string secreta s com 1 consulta.

### Célula 17 (code)

Código preservado em `src/quantum_cq/extracted/cell_017_bernstein_vazirani_algorithm.py`.

### Célula 18 (markdown)

## 8. Conclusao

- Deutsch: 1 consulta vs 2
- Deutsch-Jozsa: 1 consulta vs 2^(n-1)+1
- Bernstein-Vazirani: 1 consulta vs n

### Célula 19 (code)

Código preservado em `src/quantum_cq/extracted/cell_019_cq_embedded_backup.py`.

### Célula 20 (code)

Código preservado em `src/quantum_cq/extracted/cell_020_cq_embedded.py`.

