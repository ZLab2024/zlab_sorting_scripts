"""Adapters for raw binary and explicitly named, installed SI recording readers."""
import inspect
from pathlib import Path
import spikeinterface.extractors as extractors


def reader_arguments(path, extractor, *, reader_kwargs=None, path_argument=None, stream_id=None):
    """Resolve a built-in read_* callable and bind explicit local reader arguments.

    Arbitrary module paths/callables are not accepted. Additional file paths in
    reader_kwargs must be absolute; the runner fingerprints any existing files.
    """
    if not isinstance(extractor, str) or not extractor.isidentifier() or extractor.startswith('_'):
        raise ValueError('extractor must name a built-in SpikeInterface reader, e.g. spikeglx')
    name = extractor if extractor.startswith('read_') else 'read_' + extractor
    reader = getattr(extractors, name, None)
    if not callable(reader):
        raise ValueError(f'No installed SpikeInterface extractor named {name}')
    kwargs = dict(reader_kwargs or {})
    parameters = inspect.signature(reader).parameters
    candidates = ('folder_path', 'dirname', 'file_path', 'file_paths')
    key = path_argument or next((p for p in candidates if p in parameters), None)
    if key not in parameters or key in kwargs:
        raise ValueError('Select a valid path_argument; do not duplicate input.path in reader_kwargs')
    kwargs[key] = [str(Path(path))] if key == 'file_paths' else str(Path(path))
    if stream_id is not None:
        if 'stream_id' in kwargs:
            raise ValueError('Set stream_id once, outside reader_kwargs')
        kwargs['stream_id'] = stream_id
    inspect.signature(reader).bind(**kwargs)
    return reader, kwargs


def load_recording(path, *, extractor, reader_kwargs=None, path_argument=None, stream_id=None):
    """Use an installed SI reader without requiring another project checkout."""
    reader, kwargs = reader_arguments(path, extractor, reader_kwargs=reader_kwargs,
                                     path_argument=path_argument, stream_id=stream_id)
    recording = reader(**kwargs)
    from spikeinterface.core import BaseRecording
    if not isinstance(recording, BaseRecording):
        raise TypeError('Selected extractor did not return a SpikeInterface Recording')
    return recording
