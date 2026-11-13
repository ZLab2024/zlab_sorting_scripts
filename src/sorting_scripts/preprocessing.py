"""Named preprocessing recipes. Always call on an already isolated sorting group."""
import numpy as np
import spikeinterface.preprocessing as sp

PROFILES = {
    'deeparray_ks4': 'kilosort4',
    'bf_bundle_ms5': 'mountainsort5',
    'bf_single_wire': 'mountainsort5',
    'osort_import': 'osort_import',
}


def signed_recording(recording):
    """Convert unsigned ADC storage using SI's offset-aware converter."""
    return sp.unsigned_to_signed(recording) if np.issubdtype(recording.get_dtype(), np.unsignedinteger) else recording


def preprocess(recording, profile, *, seed=0):
    """Return a lazy filtered recording; no channels from other groups are used.

    KS4 owns its internal whitening. MS5 profiles use seeded local whitening and
    disable the backend's filter/whiten switches. Imported spikes are not sorted.
    """
    if profile not in PROFILES:
        raise ValueError(f'Unknown preprocessing profile: {profile}')
    recording = signed_recording(recording)
    recording = sp.bandpass_filter(recording, freq_min=300, freq_max=6000, dtype='float32')
    if profile in ('bf_bundle_ms5', 'bf_single_wire'):
        recording = sp.whiten(recording, mode='local', radius_um=110., dtype='float32', seed=seed)
    return recording
