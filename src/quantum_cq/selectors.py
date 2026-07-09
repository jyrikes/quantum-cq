from importlib import import_module
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quantum_cq._core.selectors import *

_module = import_module("quantum_cq._core.selectors")
sys.modules[__name__] = _module
