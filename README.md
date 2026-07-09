# quantum_cq

Biblioteca Python extraida de um notebook de computacao quantica, com uma
camada compacta de circuitos (`QC`), encoders classicos, algoritmos basicos e
interop com Qiskit.

## Instalacao

```powershell
pip install quantum-cq
```

Extras opcionais:

```powershell
pip install "quantum-cq[aer]"       # simuladores Aer
pip install "quantum-cq[ibm]"       # IBM Quantum Runtime
pip install "quantum-cq[notebook]"  # pandas, matplotlib, IPython e widgets
pip install "quantum-cq[all]"       # todos os extras opcionais
```

## Uso rapido

```python
from quantum_cq import CQ

encoded_basis = CQ.encode([1, 0, 1])
encoded_angle = CQ.encode([0.1, 0.2])
```

```python
deutsch = CQ.algorithm("deutsch").with_case(2).build()
bv = CQ.algorithm("bernstein_vazirani").with_secret("1011").build()
dj = CQ.algorithm("deutsch_jozsa").with_num_qubits(3).with_kind("balanced").build()
grover = CQ.algorithm("grover").with_marked_state("11").build()
qpe = CQ.algorithm("phase_estimation").with_phase(0.25).with_precision(3).build()
```

```python
qft = CQ.primitive("qft").build(num_qubits=3)
diffuser = CQ.primitive("standard_diffuser").build(num_qubits=3)
phase_rotation = CQ.operator("phase_rotation").with_phase(0.25).build()
```

```python
memory = CQ.memory([3, 5, 7, 9])
nav = CQ.encode(memory, role="navigation")
qram_like = CQ.encode(memory, role="navigation", engine="qram_like")
print(CQ.metrics(nav))
print(CQ.to_qiskit(nav).draw())
```

```python
graph = CQ.graph(edges=[(0, 1), (1, 2), (2, 3)], num_vertices=4)
neighbor_oracle = CQ.encode(graph, role="navigation")

cycle = CQ.graph(edges=[(0, 1), (1, 2), (2, 3), (3, 0)], num_vertices=4)
walk = CQ.primitive("coined_quantum_walk").build(cycle, steps=1)
```

## QC como circuito oficial

```python
from quantum_cq import CQ
from quantum_cq.algorithms import twobit_block
from quantum_cq.compact import QC, m, obs, sep

uf0 = twobit_block(2)
qc = QC(
    "Deutsch",
    [
        [0, "-", "H", obs("pre_oracle"), uf0, sep("after_oracle"), "H", m(0)],
        [0, "X", "H", obs("pre_oracle"), uf0, "-", "-", "-"],
    ],
    c=1,
)

same_qc = CQ.from_qc(qc)
qiskit_circuit = CQ.to_qiskit(qc)
metrics = CQ.metrics(qc)
```

## Exportacao

```python
qiskit_circuit = CQ.export(qc, target="qiskit")
```

Exportadores futuros como `mqt` e `openqasm` ainda levantam
`NotImplementedError`; eles nao fingem implementacao parcial.

## Encodings generalizados

A arquitetura separa os papeis:

- `StateEncoding`: dados classicos para estado quantico.
- `OracleEncoding`: funcao ou predicado para oraculo.
- `OperatorEncoding`: operador ou unitario reutilizavel.
- `NavigationEncoding`: memoria enderecada ou grafo para acesso coerente.
- `QuantumWalk`: dinamica unitaria sobre uma estrutura navegavel.

`engine="qram_like"` simula a semantica logica de acesso QRAM-like, mas nao e
QRAM fisico. A metadata marca `physical_qram=False`.

## Logging

A biblioteca escreve eventos operacionais no terminal por padrao.

```python
from quantum_cq import configure_logging

configure_logging(level="INFO")
```

## Testes

```powershell
python -m pytest -q
```
