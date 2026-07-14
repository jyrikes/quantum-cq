# Installation

`quantum-cq` is installed from PyPI as:

```bash
pip install quantum-cq
```

The Python import is:

```python
from quantum_cq import CQ
```

## Base Dependencies

The base package installs:

- `qiskit`
- `numpy`
- `packaging`

This is enough to build encodings, construct navigation circuits, export to
Qiskit and collect structural metrics.

## Optional Extras

```bash
pip install "quantum-cq[aer]"
pip install "quantum-cq[ibm]"
pip install "quantum-cq[pennylane]"
pip install "quantum-cq[cirq]"
pip install "quantum-cq[braket]"
pip install "quantum-cq[cudaq]"
pip install "quantum-cq[notebook]"
pip install "quantum-cq[all]"
```

| Extra | Adds | Use case |
| --- | --- | --- |
| `aer` | `qiskit-aer` | Local simulation paths that need Aer. |
| `ibm` | `qiskit-ibm-runtime` | IBM Quantum Runtime execution. |
| `pennylane` | `pennylane` | Optional PennyLane emission and local execution. |
| `cirq` | `cirq` | Optional Cirq emission and local execution. |
| `braket` | `amazon-braket-sdk` | Optional Amazon Braket local simulator integration. |
| `cudaq` | `cudaq` | Optional CUDA-Q experiments in supported environments. |
| `notebook` | `pandas`, `matplotlib`, `pylatexenc`, `ipython`, `ipywidgets` | Notebook display, figures and dataframes. |
| `all` | Aer, IBM Runtime and notebook extras | Existing Qiskit runtime/notebook bundle; it does not install all optional engines. |

Qiskit is a required dependency in `0.2.0` and remains the default reference
engine. There is no `quantum-cq[qiskit]` extra.

PennyLane, Cirq and Braket should be installed only when those engines are
needed. CUDA-Q support depends on the operating system and Python environment;
on native Windows, use WSL or another CUDA-Q-supported environment.

## Notebook Display

For rich circuit drawings in notebooks or Colab, install:

```bash
pip install "quantum-cq[notebook]"
```

Then:

```python
from quantum_cq import CQ

encoded = CQ.state([1, 0, 1], encoding="basis")
CQ.show(encoded)
```

The maintained introductory notebook is:

```text
notebooks/quantum_cq_getting_started.ipynb
```

## IBM Runtime

IBM execution is optional and requires `quantum-cq[ibm]`. Credentials are
managed by the user environment and should never be committed to source control
or notebooks.

## Minimal Smoke Test

```bash
python -c "import quantum_cq; from quantum_cq import CQ; print(CQ)"
```
