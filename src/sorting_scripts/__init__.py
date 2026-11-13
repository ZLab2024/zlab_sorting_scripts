"""Central Z-Lab sorting API. Imports never start processing or open a GUI.

Use ``run(config)``, ``validate(config)`` and ``status(run_dir)`` for session
workflows. See docs/api.md for typed module families and lower-level APIs.
"""
__version__ = '0.1.0'

__all__ = ['run', 'validate', 'status', 'load_recording']


def __getattr__(name):
    if name == 'load_recording':
        from .io import load_recording
        return load_recording
    if name in __all__:
        from . import pipeline
        return getattr(pipeline, name)
    raise AttributeError(name)
