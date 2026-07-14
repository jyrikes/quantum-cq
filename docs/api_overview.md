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

## 7. Public Logical Circuits

```python
from quantum_cq import CQ

bell = CQ.circuit(2, 2, name="bell")
bell.h(0)
bell.cx(0, 1)
bell.measure(0, 0)
bell.measure(1, 1)

ir = bell.build()
qc = CQ.emit(ir, engine="qiskit")

print(ir.name)
print(qc.num_qubits, qc.depth())
```

`CQ.circuit(...)` builds a SDK-free logical circuit first. Emission to Qiskit,
PennyLane, Cirq or Braket is handled by the engine layer when the requested
engine is installed and supports the required operations.

## 8. Operators And Primitives

```python
from quantum_cq import CQ

qft = CQ.qft(3)
iqft = CQ.iqft(3)
diffuser = CQ.diffuser(3)
phase_rotation = CQ.phase_rotation(0.25)

print(CQ.metrics(qft))
print(CQ.metrics(phase_rotation))
```

## 9. Engine APIs

```python
from quantum_cq import CQ

print(CQ.engines())
print(CQ.engine_capabilities("qiskit"))

circuit = CQ.circuit(1, 1)
circuit.h(0)
circuit.measure(0, 0)

compiled = CQ.compile(circuit, engine="qiskit")
print(compiled.engine)
```

The legacy exporter registry remains separate:

```python
assert CQ.available_exporters() == ["qiskit"]
```

## 10. Unified Pipeline

```python
from quantum_cq import CQ

legacy = CQ.pipeline([1, 0, 1], encoding="basis").build()
enriched = CQ.pipeline(equation="|psi> := H[q0] * |0>").transpile()

print(legacy.encoding_name)
print(enriched.scenario_results[0].status)
```

Legacy `data + encoding` build/run calls preserve their historical return
types. Enriched calls such as `transpile()`, builder `compile()` and builder
`run_engine()` return `PipelineResult`.

## 11. Navigation Encoding V2

```python
from quantum_cq import CQ, StructuralField, StructuralHeap, StructuralNode, StructuralSelector, StructuralType

node_type = StructuralType(
    "Node",
    (
        StructuralField("payload", "uint", bit_width=2, semantic_role="value"),
        StructuralField("link", "reference", nullable=True, semantic_role="next"),
    ),
)
heap = StructuralHeap(
    (node_type,),
    (
        StructuralNode("tail", "Node", {"payload": 2, "link": None}),
        StructuralNode("head", "Node", {"payload": 1, "link": "tail"}),
    ),
    roots=("head",),
)

result = CQ.navigation_v2(heap, operation="read", selector=StructuralSelector.value("payload"))
print(result.plan.equivalence_class.equivalence_fingerprint)
print(result.circuit_format)
```

Navigation V2 is explicit and finite. It does not replace the V1 addressed
memory path.

## 12. Hardware Descriptors

```python
from quantum_cq import CQ

target = CQ.manual_target(
    target_id="ideal-two-qubit",
    qubits=2,
    operations=("h", "cx", "measure"),
    topology=(("q0", "q1"),),
    target_type="simulator_ideal",
)

print(target.descriptor.target_id)
```

Manual targets are SDK-free descriptors. They do not imply remote execution or
backend selection.

## 13. Experiment Pipeline

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

## 14. Notebook Display

```python
from quantum_cq import CQ

encoded = CQ.state([1, 0, 1], encoding="basis")
CQ.show(encoded)
```

For rich drawings, install:

```bash
pip install "quantum-cq[notebook]"
```

For a step-by-step walkthrough, open:

```text
notebooks/quantum_cq_getting_started.ipynb
```

For a full pipeline walkthrough with navigation and data recovery, open:

```text
notebooks/quantum_cq_full_pipeline_navigation.ipynb
```

For a presentation-oriented theory and library demo with perceptron, pipeline
snapshots, measurements and Navigation V2 qubit mapping, open:

```text
notebooks/quantum_cq_teoria_biblioteca_demo.ipynb
```
