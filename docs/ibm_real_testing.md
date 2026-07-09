# IBM real testing

IBM real execution is an external integration test. It can submit a real job,
enter a queue, take time to finish, and consume quota or credits. Never commit
an IBM Quantum token to the repository.

## Pytest opt-in

Set environment variables before running the real tests:

```bash
export IBM_QUANTUM_TOKEN="..."
export IBM_QUANTUM_CHANNEL="ibm_quantum_platform"
export IBM_QUANTUM_INSTANCE=""
export IBM_QUANTUM_BACKEND="least_busy"
export IBM_QUANTUM_SHOTS="32"
export IBM_QUANTUM_TIMEOUT="300"
```

Then run:

```bash
python -m pytest -q -m ibm_real --run-ibm-real
```

Without `--run-ibm-real`, tests marked with `ibm_real` are skipped.

## Notebook smoke test

Open:

```text
notebooks/quantum_cq_ibm_real_smoke.ipynb
```

Edit:

```python
IBM_QUANTUM_TOKEN = "..."
```

Keep:

```python
RUN_REAL_IBM = True
```

The notebook is enabled by default, but it fails early if the token is still the
placeholder `COLE_SEU_TOKEN_AQUI`.

## Instance auto-discovery

`IBM_QUANTUM_INSTANCE=""` or `IBM_QUANTUM_INSTANCE` unset means `instance=None`.
This is the recommended default when IBM should resolve the runtime instance at
execution time.

Both channels are accepted:

```bash
export IBM_QUANTUM_CHANNEL="ibm_quantum_platform"
```

or the legacy channel:

```bash
export IBM_QUANTUM_CHANNEL="ibm_cloud"
```

If IBM returns `No matching instances found for the following filters: .`, the
library tried auto-discovery but IBM did not return a compatible instance for
that token/channel. Try the other channel first. Only set
`IBM_QUANTUM_INSTANCE` if your account requires a specific CRN or instance name.
Do not set `IBM_QUANTUM_INSTANCE="ibm_cloud"`; `ibm_cloud` is a channel, not an
instance.

## Expected logs

Logs should show:

- channel
- instance or auto-discovery
- selected backend
- transpilation start/end
- job_id
- status
- received result
- counts

The token must never appear in logs, repr, safe summaries, dataframes, or
controlled exception messages.
