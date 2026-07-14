# Isolated Engine Validation

Run 1 validates optional engines outside the primary Conda baseline
environment.

The venvs are created outside the repository at:

```text
C:\Users\Yngrid Kalinne\Documents\cq\trabalho_003\quantum_cq_engine_venvs
```

## PennyLane

Install command:

```bash
python -m pip install -e ".[dev,pennylane]"
```

Resolved key versions:

- PennyLane: `0.45.1`
- Qiskit: `2.5.0`
- NumPy: `2.5.1`

Validation:

```bash
python -m pytest -q tests/test_multi_engine_core.py tests/adapters/test_pennylane_engine.py
```

Result:

```text
4 passed, 2 skipped
```

One PennyLane deprecation warning is emitted for device-level shots.

## Cirq

Install command:

```bash
python -m pip install -e ".[dev,cirq]"
```

Resolved key versions:

- Cirq: `1.7.0`
- Qiskit: `2.5.0`
- NumPy: `2.5.1`

Validation:

```bash
python -m pytest -q tests/test_multi_engine_core.py tests/adapters/test_cirq_engine.py
```

Result:

```text
5 passed, 1 skipped
```

## Amazon Braket

Install command:

```bash
python -m pip install -e ".[dev,braket]"
```

Resolved key versions:

- Amazon Braket SDK: `1.123.0.post0`
- Qiskit: `2.5.0`
- NumPy: `2.4.6`

Validation:

```bash
python -m pytest -q tests/test_multi_engine_core.py tests/adapters/test_braket_engine.py
```

Result:

```text
5 passed, 1 skipped
```

Braket validation uses the local simulator only. No AWS credentials or paid
remote task submission are required.

## CUDA-Q

Environment:

- System: `Windows`
- Machine: `AMD64`
- Python: `3.13.12`
- `cudaq` installed: `False`

`python -m pip install --dry-run --no-deps cudaq` resolves `cudaq 0.15.0`, but
Run 1 does not mark CUDA-Q functional on native Windows. The adapter reports
CUDA-Q as unsupported with an explicit message directing Windows users to WSL or
another supported environment.
