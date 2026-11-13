"""Native Neuralynx loading; preserve extractor segments, gains and channel IDs."""
from pathlib import Path


def load_recording(path, *, stream_id=None):
    """Load a Neuralynx directory without inferring or filling discontinuities."""
    from spikeinterface.extractors import read_neuralynx
    return read_neuralynx(Path(path), **({} if stream_id is None else {'stream_id': stream_id}))
