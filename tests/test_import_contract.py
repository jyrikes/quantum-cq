import os
import subprocess
import sys
import textwrap


def _run_import_snippet(snippet: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    src = os.path.abspath("src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else os.pathsep.join([src, existing])
    return subprocess.run(
        [sys.executable, "-c", snippet],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_root_import_and_cq_contract_work_from_src():
    result = _run_import_snippet(
        "import quantum_cq; from quantum_cq import CQ; print(CQ)"
    )

    assert result.returncode == 0, result.stderr
    assert "CQ" in result.stdout


def test_root_import_does_not_require_optional_heavy_dependencies():
    blocked = (
        "qiskit_aer",
        "qiskit_ibm_runtime",
        "pandas",
        "matplotlib",
        "IPython",
        "ipywidgets",
    )
    snippet = textwrap.dedent(
        f"""
        import builtins

        blocked = {blocked!r}
        original_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if any(name == item or name.startswith(item + ".") for item in blocked):
                raise ImportError("blocked optional dependency: " + name)
            return original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import

        import quantum_cq
        from quantum_cq import CQ
        print(CQ)
        """
    )

    result = _run_import_snippet(snippet)

    assert result.returncode == 0, result.stderr
    assert "CQ" in result.stdout


def test_benchmarking_pipeline_import_does_not_require_notebook_extra():
    snippet = textwrap.dedent(
        """
        import builtins

        blocked = ("IPython", "matplotlib", "ipywidgets", "pandas")
        original_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if any(name == item or name.startswith(item + ".") for item in blocked):
                raise ImportError("blocked optional dependency: " + name)
            return original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import

        from quantum_cq.pipeline import BenchmarkingPipeline
        print(BenchmarkingPipeline)
        """
    )

    result = _run_import_snippet(snippet)

    assert result.returncode == 0, result.stderr
    assert "BenchmarkingPipeline" in result.stdout


def test_embedded_notebook_helpers_import_without_notebook_extra():
    snippet = textwrap.dedent(
        """
        import builtins

        blocked = ("IPython", "matplotlib", "ipywidgets", "pandas")
        original_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if any(name == item or name.startswith(item + ".") for item in blocked):
                raise ImportError("blocked optional dependency: " + name)
            return original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import

        import quantum_cq.cq_embedded
        print("cq_embedded")
        """
    )

    result = _run_import_snippet(snippet)

    assert result.returncode == 0, result.stderr
    assert "cq_embedded" in result.stdout
