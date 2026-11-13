"""Validated lazy concatenation of naturally ordered Intan RHD chunks."""
from pathlib import Path
import numpy as np
import spikeinterface.full as si
from .. import get_file

def load_recording(source: str | Path | dict, *, stream_id: str = "0"):
    """Read amplifier chunks as one lazy recording, with exact compatibility checks.

    Accept a directory, file, or the dictionary returned by ``set_paths``.
    Stream 0 is Intan's amplifier stream; pass another stream explicitly if needed.
    Missing/invalid inputs and extractor integrity errors propagate to the caller.
    """
    if isinstance(source, dict):
        source = source["recording_source"]
    files = get_file.get_rhd_files(source)
    recordings = []
    sample_counts = []
    for path in files:
        recording = si.read_intan(path, stream_id=stream_id)
        if recording.get_num_segments() != 1:
            raise ValueError(f"Expected one segment in RHD chunk: {path}")
        count = recording.get_num_samples()
        if count == 0:
            raise ValueError(f"RHD chunk has no samples: {path}")
        if recordings:
            reference = recordings[0]
            if recording.get_sampling_frequency() != reference.get_sampling_frequency():
                raise ValueError(f"Sampling frequency differs from {files[0]}: {path}")
            if not np.array_equal(recording.channel_ids, reference.channel_ids):
                raise ValueError(f"Channel IDs/order differ from {files[0]}: {path}")
            if recording.get_dtype() != reference.get_dtype():
                raise ValueError(f"Recording dtype differs from {files[0]}: {path}")
            for property_name in ("gain_to_uV", "offset_to_uV"):
                actual = recording.get_property(property_name)
                expected = reference.get_property(property_name)
                if not np.array_equal(actual, expected):
                    raise ValueError(f"{property_name} differs from {files[0]}: {path}")
        recordings.append(recording)
        sample_counts.append(count)

    recording = (
        recordings[0] if len(recordings) == 1
        else si.concatenate_recordings(recordings, ignore_times=True)
    )
    recording.annotate(
        intan_source_files=[str(path) for path in files],
        intan_source_sample_counts=sample_counts,
        intan_source_start_samples=np.cumsum([0, *sample_counts[:-1]]).tolist(),
        intan_concatenation_note=(
            "Natural filename order; consecutive sample clock; "
            "inter-file gaps are not inferred or filled."
        ),
    )
    print(
        f"[zsort] Loaded {len(files)} RHD file(s): {recording.get_num_channels()} channels, "
        f"{recording.get_sampling_frequency():g} Hz, {sum(sample_counts)} samples, "
        f"{sum(sample_counts) / recording.get_sampling_frequency():.3f} seconds."
    )
    return recording
