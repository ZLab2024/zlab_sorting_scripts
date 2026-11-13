"""Compatibility alias. New sessions use sorting_scripts.run and typed subpackages.

The module alias preserves legacy monkey-patching/import behavior for notebooks.
"""
import sys
from .legacy import zsort as _implementation
sys.modules[__name__] = _implementation
