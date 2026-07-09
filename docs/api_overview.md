# API Overview

The public API is centered on:

```python
from quantum_cq import CQ
```

This document lists the common workflows in a practical order.

## 1. State Encoding

```python
from quantum_cq import CQ

basis = CQ.state([1, 0, 1], encoding="basis")
angle = CQ.state([0.1, 0.2, 0.3], encoding="angle")
auto = CQ.encode([0.1, 0.2, 0.3])

print(basis.encoding_name)
print(angle.encoding_name)
print(auto.encoding_name)
```

## 2. Export To Qiskit

```python
from quantum_cq import CQ

encoded = CQ.state([1, 0, 1], encoding="basis")
qc = CQ.to_qiskit(encoded)

print(qc.num_qubits, qc.depth())
```

## 3. Metrics

```python
from quantum_cq import CQ

encoded = CQ.state([1, 0, 1], encoding="basis")
metrics = CQ.metrics(encoded)

print(metrics["num_qubits"])
print(metrics["depth"])
print(metrics["count_ops"])
```

## 4. Addressed Memory Navigation

```python
from quantum_cq import CQ

memory = CQ.memory([3, 5, 7, 9])
nav = CQ.nav(memory, engine="explicit")

qc = CQ.to_qiskit(nav)
print(qc.num_qubits, qc.depth())
print(CQ.metrics(nav))
```

The logical semantics are:

```text
U_D |a>|b> = |a>|b xor D[a]>
```

## 5. Graph Navigation

```python
from quantum_cq import CQ

graph = CQ.graph(edges=[(0, 1), (1, 2), (2, 3)], vertices=4)
nav = CQ.graph_nav(graph, engine="explicit")

print(CQ.metrics(nav))
```

## 6. Algorithms

```python
from quantum_cq import CQ

deutsch = CQ.deutsch(case=2)
bv = CQ.bv("1011")
dj = CQ.dj(kind="balanced", qubits=3)
grover = CQ.grover("11")
qpe = CQ.qpe(phase=0.25, precision=3)

for item in (deutsch, bv, dj, grover, qpe):
    print(item.algorithm_name, CQ.metrics(item))
```

## 7. Operators And Primitives

```python
from quantum_cq import CQ

qft = CQ.qft(3)
iqft = CQ.iqft(3)
diffuser = CQ.diffuser(3)
phase_rotation = CQ.phase_rotation(0.25)

print(CQ.metrics(qft))
print(CQ.metrics(phase_rotation))
```

## 8. Experiment Pipeline

```python
from quantum_cq import CQ

result = CQ.run(
    data=[0.1, 0.2, 0.3],
    encoders=["angle", "phase"],
    modes=["ideal"],
    shots=128,
)

print(result.summary())
```

Local simulation may require:

```bash
pip install "quantum-cq[aer]"
```

## 9. Notebook Display

```python
from quantum_cq import CQ

encoded = CQ.state([1, 0, 1], encoding="basis")
CQ.show(encoded)
```

For rich drawings, install:

```bash
pip install "quantum-cq[notebook]"
```
