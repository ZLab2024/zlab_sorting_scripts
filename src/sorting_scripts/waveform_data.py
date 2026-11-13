"""Pure stored-waveform coordinates/scaling helpers; no GUI imports."""
import numpy as np

def time_axis(num_samples, nbefore, sampling_frequency):
    return (np.arange(num_samples) - nbefore) * (1000.0 / sampling_frequency)

def stored_channel_indices(analyzer, unit_id):
    if analyzer.sparsity is None:
        return np.arange(analyzer.get_num_channels())
    return np.asarray(analyzer.sparsity.unit_id_to_channel_indices[unit_id])

def amplitude_label(analyzer, dtype):
    # return_in_uV is the storage contract of SI 0.103's waveform extension.
    if analyzer.return_in_uV:
        return "Amplitude (µV)"
    return "Amplitude (ADC counts)" if np.issubdtype(dtype, np.integer) else "Amplitude (recording units)"
