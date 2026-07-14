# Isolated Engine Validation

Run 1 validates optional engines outside the primary Conda baseline
environment.

Run 2 repeats this validation after the engine contracts refactor. The Run 2
venvs are outside the repository at:

```text
C:\Users\Yngrid Kalinne\.codex\venvs
```

Run 2 commands:

```bash
python -m pip install -e ".[dev,<engine>]"
python -m pytest -q tests/test_multi_engine_core.py tests/adapters/test_<engine>_engine.py tests/test_run2_engine_contracts.py tests/test_run2_component_catalog.py
```

Run 2 results:

| Engine | Key engine version | Qiskit | NumPy | Result |
| --- | --- | --- | --- | --- |
| PennyLane | 0.45.1 | 2.5.0 | 2.5.1 | 20 passed, 3 skipped, 1 PennyLane shots deprecation warning |
| Cirq | 1.7.0 | 2.5.0 | 2.5.1 | 21 passed, 2 skipped |
| Amazon Braket SDK | 1.123.0.post0 | 2.5.0 | 2.4.6 | 21 passed, 2 skipped |

Braket validation remains local-simulator only. CUDA-Q remains unsupported on
native Windows unless validated in WSL or another compatible environment.

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

## Run 3 isolated validation

Run 3 venvs were created outside the repository at:

```text
C:\Users\Yngrid Kalinne\.codex\venvs
```

Commands:

```bash
python -m pip install ".[dev,<engine>]"
python -m pytest -q tests/test_multi_engine_core.py tests/test_run2_engine_contracts.py tests/test_run3_circuit_service.py tests/adapters/test_<engine>_engine.py
```

Results:

| Engine | Venv | Key engine version | Qiskit | NumPy | Result |
| --- | --- | --- | --- | --- | --- |
| PennyLane | `quantum-cq-run3-pennylane` | 0.45.1 | 2.5.0 | 2.5.1 | 23 passed, 5 skipped, 1 PennyLane shots deprecation warning |
| Cirq | `quantum-cq-run3-cirq` | 1.7.0 | 2.5.0 | 2.5.1 | 25 passed, 3 skipped |
| Amazon Braket SDK | `quantum-cq-run3-braket` | 1.123.0.post0 | 2.5.0 | 2.4.6 | 24 passed, 4 skipped |

The Run 3 isolated checks include shared multi-engine tests, Run 2 contracts,
custom circuit/unitary tests, and adapter-specific local tests. Braket remains
local-simulator only. CUDA-Q remains non-operational on native Windows in this
run.
