import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-ibm-real",
        action="store_true",
        default=False,
        help="executa testes opt-in que submetem jobs reais na IBM Quantum",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-ibm-real"):
        return

    skip_real = pytest.mark.skip(reason="use --run-ibm-real para executar testes IBM reais")
    for item in items:
        if "ibm_real" in item.keywords:
            item.add_marker(skip_real)
