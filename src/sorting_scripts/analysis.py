"""Geometry-aware preparation of persisted SortingAnalyzers."""
from pathlib import Path
import spikeinterface as si
import numpy as np
from .preprocessing import signed_recording
import spikeinterface.preprocessing as sp


def prepare_analyzer(recording, sorting, folder, *, seed=0, virtual_geometry=False, n_jobs=1):
    """Create a new analyzer with stored waveforms, templates, timing and QC.

    No monopolar localization is attempted for virtual or single-contact geometry.
    Virtual locations use center of mass only as a GUI coordinate, not anatomy.
    Waveforms use filtered, unwhitened traces; defaults match lab -1/+2 ms windows.
    """
    if Path(folder).exists():
        raise FileExistsError(f'Analyzer destination exists: {folder}')
    filtered = sp.bandpass_filter(signed_recording(recording), freq_min=300, freq_max=6000, dtype='float32')
    groups = sorting.get_property('sorting_group')
    sparsity = None
    if groups is not None:
        mask = np.asarray([recording.get_property('group') == group for group in groups])
        sparsity = si.ChannelSparsity(mask, sorting.unit_ids, recording.channel_ids)
    analyzer = si.create_sorting_analyzer(sorting, filtered, format='binary_folder', folder=folder,
                                         sparse=sparsity is not None, sparsity=sparsity, return_in_uV=recording.has_scaleable_traces())
    job = dict(n_jobs=n_jobs, chunk_duration='1s', progress_bar=False)
    analyzer.compute({'random_spikes': dict(max_spikes_per_unit=500, seed=seed),
                      'waveforms': dict(ms_before=1., ms_after=2.),
                      'templates': dict(operators=['average', 'std']), 'noise_levels': {},
                      'correlograms': dict(window_ms=100., bin_ms=1.),
                      'template_similarity': dict(method='l1'),
                      'spike_amplitudes': {},
                      'quality_metrics': dict(metric_names=['snr', 'firing_rate', 'isi_violation'])}, **job)
    analyzer.compute('unit_locations', method='center_of_mass' if virtual_geometry or recording.get_num_channels() < 4 else 'monopolar_triangulation')
    return analyzer
