from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.sdist import sdist as _sdist


class sdist(_sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        egg_info = Path(base_dir) / "src" / "quantum_cq.egg-info"
        if egg_info.exists():
            shutil.rmtree(egg_info)


setup(cmdclass={"sdist": sdist})
