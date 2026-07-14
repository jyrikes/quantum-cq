# Engine Capability Matrix

Capability states are limited to:

- `supported`
- `lowered`
- `experimental`
- `unsupported`
- `not_tested`

Every `supported` capability is covered by a test. Every `lowered` capability is
covered by lowering plus semantic behavior tests for the supported subset.

| Capability | Qiskit | PennyLane | Cirq | Braket | CUDA-Q on native Windows |
| --- | --- | --- | --- | --- | --- |
| X | supported | supported | supported | supported | unsupported |
| Y | supported | supported | supported | supported | unsupported |
| Z | supported | supported | supported | supported | unsupported |
| H | supported | supported | supported | supported | unsupported |
| RX | supported | supported | supported | supported | unsupported |
| RY | supported | supported | supported | supported | unsupported |
| RZ | supported | supported | supported | supported | unsupported |
| CX | supported | supported | supported | supported | unsupported |
| CZ | supported | supported | supported | supported | unsupported |
| SWAP | supported | supported | supported | supported | unsupported |
| Measurement | supported | supported | supported | supported | unsupported |
| Parameterized gates | supported | supported | supported | supported | unsupported |
| MCX | supported | lowered | lowered | lowered | unsupported |
| CCX / Toffoli | supported | supported | supported | supported | unsupported |
| Observables | supported | not_tested | not_tested | not_tested | not_tested |
| Gradients | not_tested | not_tested | unsupported | unsupported | not_tested |
| Local execution | supported | supported | supported | supported | unsupported |
| Remote execution | supported | unsupported | unsupported | unsupported | unsupported |
| Async jobs | supported | unsupported | unsupported | unsupported | unsupported |

## Notes

- Qiskit is the default and reference engine in `0.1.x`.
- PennyLane, Cirq and Braket are optional extras and are validated in isolated
  virtual environments.
- Braket support is local-simulator only in Run 1; tests must not require AWS
  credentials or submit paid remote tasks.
- CUDA-Q is not declared functional on native Windows. NVIDIA documents Windows
  usage through WSL and native support on Linux and Apple-silicon macOS.
