"""Compatibility alias for optional, historical lab-specific Box integration."""
import sys
from .legacy import box_managment as _implementation
sys.modules[__name__] = _implementation
