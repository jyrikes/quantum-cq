from importlib import import_module
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quantum_cq._core.environment import *

_module = import_module("quantum_cq._core.environment")
sys.modules[__name__] = _module
