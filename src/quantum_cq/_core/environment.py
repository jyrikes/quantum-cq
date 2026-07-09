"""Setup explicito para Google Colab ou ambiente local."""

from __future__ import annotations

import logging
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from subprocess import run
from sys import executable

from packaging.version import Version

from quantum_cq._core.logging_config import configure_logging


logger = logging.getLogger(__name__)


REQUIREMENTS = {
    "numpy": "2.0.0",
    "scipy": "1.15.0",
    "matplotlib": "3.8.0",
    "qiskit": "2.1.0",
    "qiskit-aer": "0.17.0",
    "qiskit-ibm-runtime": "0.40.1",
    "pylatexenc": "2.10",
    "ipywidgets": "8.0.0",
}


def in_colab():
    try:
        import_module("google.colab")
        return True
    except ModuleNotFoundError:
        return False


def installed_version(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def needs_install(package, min_version):
    current = installed_version(package)
    return current is None or Version(current) < Version(min_version)


def setup_environment(auto_install=None):
    configure_logging()
    colab = in_colab()
    auto_install = colab if auto_install is None else auto_install

    logger.info("Ambiente detectado: %s", "Google Colab" if colab else "local")
    print("Ambiente:", "Google Colab" if colab else "local")

    missing = {
        package: min_version
        for package, min_version in REQUIREMENTS.items()
        if needs_install(package, min_version)
    }

    if missing:
        logger.warning("Pacotes ausentes ou desatualizados: %s", missing)
        print("\nPacotes ausentes ou desatualizados:")
        for package, min_version in missing.items():
            current = installed_version(package) or "nao instalado"
            logger.warning(
                "Pacote %s requer ajuste: atual=%s minimo=%s",
                package,
                current,
                min_version,
            )
            print(f"- {package}: {current} -> >= {min_version}")

        if not auto_install:
            logger.info("Instalacao automatica desativada")
            print("\nInstalacao automatica desativada.")
            return

        logger.info("Instalando dependencias automaticamente")
        run(
            [
                executable,
                "-m",
                "pip",
                "install",
                "-q",
                "--upgrade",
                *[f"{pkg}>={ver}" for pkg, ver in missing.items()],
            ],
            check=True,
        )

        if colab:
            logger.info("Dependencias atualizadas no Colab; reinicio necessario")
            raise SystemExit(
                "Dependencias atualizadas. Reinicie o runtime e rode novamente."
            )

    logger.info("Versoes instaladas verificadas")
    print("\nVersoes:")
    for package, min_version in REQUIREMENTS.items():
        current = installed_version(package)
        status = "OK" if current and Version(current) >= Version(min_version) else "AJUSTAR"
        logger.info(
            "Dependencia %s: atual=%s minimo=%s status=%s",
            package,
            current or "nao instalado",
            min_version,
            status,
        )
        print(f"{package}: {current or 'nao instalado'} | >= {min_version} | {status}")

    logger.info("Ambiente OK")
    print("\nAmbiente OK.")


if __name__ == "__main__":
    setup_environment(auto_install=True)
