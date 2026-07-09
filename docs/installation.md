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
pip install "quantum-cq[notebook]"
pip install "quantum-cq[all]"
```

| Extra | Adds | Use case |
| --- | --- | --- |
| `aer` | `qiskit-aer` | Local simulation paths that need Aer. |
| `ibm` | `qiskit-ibm-runtime` | IBM Quantum Runtime execution. |
| `notebook` | `pandas`, `matplotlib`, `pylatexenc`, `ipython`, `ipywidgets` | Notebook display, figures and dataframes. |
| `all` | all optional extras | Full local experimentation. |

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

## IBM Runtime

IBM execution is optional and requires `quantum-cq[ibm]`. Credentials are
managed by the user environment and should never be committed to source control
or notebooks.

## Minimal Smoke Test

```bash
python -c "import quantum_cq; from quantum_cq import CQ; print(CQ)"
```
