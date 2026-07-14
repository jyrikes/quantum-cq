# Run 1 Baseline

Run 1 starts from the current `0.1.x` Qiskit-reference architecture.

## Git

- Initial branch: `run-4-next-layer`
- Run branch: `run-1-navigation-v1-multi-engine`
- Initial commit: `f00cc1c`
- Preexisting local change: `notebooks/quantum_cq_simple_api_lab.ipynb`

The notebook change is user work and must remain outside Run 1 commits.

## Environment

- Python: `3.13.12`
- Qiskit: `2.4.1`
- NumPy: `2.4.3`
- Qiskit Aer: `0.17.2`
- Qiskit IBM Runtime: `0.47.0`

PennyLane, Cirq, Amazon Braket and CUDA-Q were not installed in the primary
Conda baseline environment.

## Baseline Commands

```bash
python -m pytest -q
python -m compileall -q src tests
python -m build
```

Baseline result before implementation:

- `167 passed, 3 skipped`
- `compileall` passed
- package build passed

After Navigation v1 contract tests were added, the main suite increased by the
new contract coverage while preserving the original tests.
