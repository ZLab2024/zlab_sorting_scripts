"""Backend dispatch. The pipeline isolates groups before calling this function."""


def sort(recording, folder, *, backend, profile, params=None):
    """Invoke KS4 or MS5 on exactly one sorting group."""
    if backend == 'kilosort4':
        from .kilosort4 import sort as run
        return run(recording, folder, params=params)
    if backend == 'mountainsort5':
        from .mountainsort5 import sort as run
        return run(recording, folder, profile=profile, params=params)
    raise ValueError(f'Unknown sorting backend: {backend}')
