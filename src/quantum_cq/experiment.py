from importlib import import_module
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quantum_cq._runtime.experiment import *
    from quantum_cq._runtime.runtime import RuntimeFactory

_module = import_module("quantum_cq._runtime.experiment")
sys.modules[__name__] = _module
