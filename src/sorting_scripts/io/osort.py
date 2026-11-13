"""Import existing oSort negative clusters onto an explicit recording sample grid."""
import numpy as np
from scipy.io import loadmat
from spikeinterface.core import NumpySorting


def frames_from_times(times_us, record_timestamps_us, sampling_frequency, *, samples_per_record=512, tolerance_samples=.01):
    """Map timestamps using block starts; reject gaps and off-grid events.

    record_timestamps_us must describe exactly the retained recording blocks,
    starting with sample zero. No historic first-block trimming is implicit.
    """
    times = np.asarray(times_us, dtype=float).ravel()
    starts = np.asarray(record_timestamps_us, dtype=float).ravel()
    if not len(starts) or not np.isfinite(starts).all() or np.any(np.diff(starts) <= 0):
        raise ValueError('Record timestamps must be finite and strictly increasing')
    if not np.isfinite(times).all() or sampling_frequency <= 0 or samples_per_record <= 0:
        raise ValueError('Finite times and positive sampling grid required')
    blocks = np.searchsorted(starts, times, side='right') - 1
    if np.any(blocks < 0):
        raise ValueError('Timestamp precedes recording')
    offsets = (times - starts[blocks]) * sampling_frequency / 1e6
    rounded = np.rint(offsets)
    if np.any(np.abs(offsets-rounded) > tolerance_samples) or np.any(rounded < 0) or np.any(rounded >= samples_per_record):
        raise ValueError('Timestamp lies in a gap or off the sample grid')
    return blocks * samples_per_record + rounded.astype('int64')


def load_osort(path, *, sampling_frequency, record_timestamps_us=None, start_time_us=None, num_samples=None):
    """Read useNegative/assignedNegative/newTimestampsNegative without reclustering.

    Provide either retained CSC record starts or an explicit continuous-clock origin.
    Excludes only oSort sentinels 0 and 99999999; preserves event multiplicity.
    """
    data = loadmat(path)
    required = ('useNegative', 'assignedNegative', 'newTimestampsNegative')
    if not all(k in data for k in required):
        raise ValueError(f'oSort MAT requires {required}')
    units = np.asarray(data['useNegative']).ravel()
    labels = np.asarray(data['assignedNegative']).ravel()
    times = np.asarray(data['newTimestampsNegative']).ravel()
    if len(labels) != len(times) or not np.isfinite(labels).all() or not np.isfinite(units).all():
        raise ValueError('Invalid oSort labels/timestamps')
    if np.any(labels != np.rint(labels)) or np.any(units != np.rint(units)):
        raise ValueError('oSort unit IDs must be integers')
    units = np.setdiff1d(units.astype('int64'), [0, 99999999])
    selected = np.isin(labels, units)
    if (record_timestamps_us is None) == (start_time_us is None):
        raise ValueError('Provide exactly one of record_timestamps_us or start_time_us')
    if record_timestamps_us is not None:
        frames = frames_from_times(times[selected], record_timestamps_us, sampling_frequency)
    else:
        values = (times[selected] - start_time_us) * sampling_frequency / 1e6
        if not np.isfinite(values).all() or np.any(np.abs(values - np.rint(values)) > .01):
            raise ValueError('oSort events are off the continuous sample grid')
        frames = np.rint(values).astype('int64')
    if np.any(frames < 0) or (num_samples is not None and np.any(frames >= num_samples)):
        raise ValueError('oSort event outside retained recording')
    sorting = NumpySorting.from_unit_dict({int(u): np.sort(frames[labels[selected] == u]) for u in units}, sampling_frequency)
    sorting.annotate(osort_source=str(path), osort_import='negative candidates, no reclustering')
    return sorting
