"""Portable recording readers; optional format libraries are imported on demand."""
from pathlib import Path

FORMATS = ('intan', 'neuralynx', 'med', 'binary_folder', 'binary', 'spikeinterface')


def load_recording(path, *, format, stream_id=None, password_env='MED_PASSWORD',
                   sampling_frequency=None, extractor=None, reader_kwargs=None, path_argument=None):
    """Load a recording without sorting, caching or computing extensions.

    binary needs dtype, num_channels and sampling_frequency (in reader_kwargs or
    the named argument). spikeinterface needs an installed extractor name and
    explicit options. Native readers preserve their original sample segments.
    """
    if format not in FORMATS:
        raise ValueError(f'Unknown recording format: {format}; choose {FORMATS}')
    if format not in ('binary', 'spikeinterface') and (extractor or reader_kwargs or path_argument):
        raise ValueError('Generic reader options require binary or spikeinterface format')
    if format == 'binary_folder':
        import spikeinterface as si
        from spikeinterface.core import BaseRecording
        recording = si.load(path)
        if not isinstance(recording, BaseRecording):
            raise TypeError('binary_folder must contain a Recording, not a Sorting/analyzer')
        return recording
    if format in ('binary', 'spikeinterface'):
        from .generic import load_recording as load
        options = dict(reader_kwargs or {})
        if format == 'binary':
            if extractor not in (None, 'binary', 'read_binary') or stream_id is not None:
                raise ValueError('Raw binary uses the binary reader and has no stream_id')
            if sampling_frequency is not None:
                if 'sampling_frequency' in options and options['sampling_frequency'] != sampling_frequency:
                    raise ValueError('Conflicting binary sampling frequencies')
                options['sampling_frequency'] = sampling_frequency
            extractor = 'binary'
        return load(path, extractor=extractor, reader_kwargs=options, path_argument=path_argument, stream_id=stream_id)
    if format == 'intan':
        from .intan import load_recording as load
        return load(path, stream_id='0' if stream_id is None else stream_id)
    if format == 'neuralynx':
        from .neuralynx import load_recording as load
        return load(path, stream_id=stream_id)
    from .med import read_med_recording
    return read_med_recording(path, password_env=password_env, stream_id=stream_id, sampling_frequency=sampling_frequency)


def list_streams(path, *, format, password_env='MED_PASSWORD', extractor=None, reader_kwargs=None, path_argument=None):
    """Return stream IDs/names from headers, without reading traces or sorting."""
    if format in ('binary', 'binary_folder'):
        return [{'stream_id': None, 'name': 'single recording'}]
    if format == 'med':
        from .med import MedRecordingExtractor, _password
        if MedRecordingExtractor is None:
            raise ImportError('Install the med extra for MED stream discovery')
        names, ids = MedRecordingExtractor.get_streams(str(path), password=_password(password_env))
    else:
        from spikeinterface.extractors import get_neo_streams
        if format == 'intan':
            from ..get_file import get_rhd_files
            names, ids = get_neo_streams('intan', file_path=get_rhd_files(path)[0])
        elif format == 'neuralynx':
            names, ids = get_neo_streams('neuralynx', folder_path=Path(path))
        elif format == 'spikeinterface':
            from .generic import reader_arguments
            _, kwargs = reader_arguments(path, extractor, reader_kwargs=reader_kwargs, path_argument=path_argument)
            name = extractor.removeprefix('read_')
            names, ids = get_neo_streams(name, **kwargs)
        else:
            raise ValueError(f'Unknown recording format: {format}')
    return [{'stream_id': str(sid), 'name': str(name)} for name, sid in zip(names, ids)]
