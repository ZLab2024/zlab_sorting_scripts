"""Read stored analyzer evidence; never extract, compute extensions or curate."""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
import spikeinterface as si

def open_analyzer(path):
    """Return a saved SortingAnalyzer; never create or compute one."""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f'Analyzer not found: {path}. Select a saved analyzer folder, not a sorter-output folder.')
    analyzer = si.load_sorting_analyzer(path, load_extensions=False)
    for name in ('waveforms', 'templates'):
        if analyzer.get_extension(name) is None:
            raise ValueError(f'Saved {name} are missing in {path}. No extraction was started. Choose an analyzer with stored waveforms/templates.')
    if 'average' not in analyzer.get_extension('templates').data:
        raise ValueError('Stored average templates are required. No extensions were computed.')
    return analyzer

def selected_units(analyzer, good_only=True):
    ids = np.asarray(analyzer.unit_ids)
    if not good_only:
        return ids
    labels = analyzer.sorting.get_property('auto_curation_label')
    if labels is None:
        raise ValueError('This analyzer has no auto_curation_label. Choose good_only=False to inspect all retained units explicitly.')
    chosen = ids[np.asarray(labels) == 'good']
    if not len(chosen):
        raise ValueError('No quality-good units in this analyzer. Choose good_only=False explicitly to inspect all units.')
    return chosen

def ensemble_data(analyzer, unit_id, max_waveforms=500):
    """Same stored-channel, peak-channel, unit scaling, and sampling contract as the ensemble view."""
    from ..waveform_data import amplitude_label, stored_channel_indices, time_axis
    if unit_id not in analyzer.unit_ids:
        raise KeyError(f'Unit {unit_id} is not present in this analyzer')
    if not 1 <= int(max_waveforms) <= 2000:
        raise ValueError('max_waveforms must be between 1 and 2000')
    wf = analyzer.get_extension('waveforms')
    templates = analyzer.get_extension('templates')
    if wf is None or templates is None or 'average' not in templates.data:
        raise ValueError('Stored waveforms and average templates are required; nothing was computed')
    channels = stored_channel_indices(analyzer, unit_id)
    if not len(channels):
        raise ValueError(f'Unit {unit_id} has no stored waveform channels')
    dense = templates.data['average'][analyzer.sorting.id_to_index(unit_id)]
    magnitudes = np.max(np.where(np.isfinite(dense[:, channels]), np.abs(dense[:, channels]), -np.inf), axis=0)
    if not np.isfinite(magnitudes).any():
        raise ValueError(f'Unit {unit_id} has no finite average template')
    peak = int(channels[np.argmax(magnitudes)])
    local = int(np.flatnonzero(channels == peak)[0])
    waveforms = wf.get_waveforms_one_unit(unit_id, force_dense=False)
    if waveforms.shape[1] != dense.shape[0] or wf.nbefore != templates.nbefore:
        raise ValueError('Stored waveform/template windows disagree; no recomputation was attempted')
    seed = int.from_bytes(hashlib.sha256(str(unit_id).encode()).digest()[:8], 'little')
    indices = np.random.default_rng(seed).permutation(len(waveforms))[:int(max_waveforms)]
    traces = np.array(waveforms[indices, :, local], copy=True)
    return dict(unit_id=unit_id, channel_index=peak, channel_id=analyzer.channel_ids[peak],
                time_ms=time_axis(dense.shape[0], wf.nbefore, analyzer.sampling_frequency),
                traces=traces, average=np.array(dense[:, peak], copy=True),
                waveform_indices=indices, stored_waveforms=len(waveforms),
                amplitude_label=amplitude_label(analyzer, traces.dtype))

def unit_metrics(analyzer, unit_id):
    """Return stored quality metrics and properties; no metrics are estimated or recomputed."""
    count = sum(len(analyzer.sorting.get_unit_spike_train(unit_id, segment_index=s))
                for s in range(analyzer.get_num_segments()))
    values = {'unit_id': unit_id, 'total_spikes': count}
    quality = analyzer.get_extension('quality_metrics')
    if quality is not None:
        frame = quality.get_data()
        if unit_id in frame.index:
            values.update(frame.loc[unit_id].to_dict())
    index = analyzer.sorting.id_to_index(unit_id)
    for name in ('auto_curation_label', 'KSLabel', 'ml_noise_label', 'ml_sua_label',
                 'ml_noise_probability', 'ml_sua_probability', 'ContamPct', 'is_merged'):
        prop = analyzer.sorting.get_property(name)
        if prop is not None:
            values[name] = prop[index]
    return values

def format_metric(value):
    if value is None:
        return 'not stored'
    if isinstance(value, (float, np.floating)):
        return f'{value:.4g}' if np.isfinite(value) else 'not available'
    return str(value)

def summary_figure(analyzer, unit_id, max_waveforms=500):
    """Peak channel ensemble plus stored metrics, preserving alignment/amplitudes."""
    import matplotlib.pyplot as plt
    data = ensemble_data(analyzer, unit_id, max_waveforms)
    metrics = unit_metrics(analyzer, unit_id)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), gridspec_kw={'width_ratios': [1.7, 1]})
    ax, panel = axes
    for trace in data['traces']:
        ax.plot(data['time_ms'], trace, color='#267db3', alpha=.10, lw=.6)
    ax.plot(data['time_ms'], data['average'], color='#072f56', lw=2.7, label='Stored average template')
    ax.axvline(0, color='gray', ls='--', lw=.8)
    ax.set(xlabel='Time relative to spike (ms)', ylabel=data['amplitude_label'],
           title=f"Unit {unit_id} · Peak stored channel {data['channel_id']}")
    ax.legend(loc='best', fontsize=8)
    panel.axis('off')
    shown = ['total_spikes', 'firing_rate', 'snr', 'isi_violations_ratio', 'presence_ratio',
             'amplitude_cutoff', 'auto_curation_label', 'KSLabel', 'ml_noise_label', 'ml_sua_label', 'is_merged']
    labels = {'firing_rate':'Firing rate (Hz)', 'isi_violations_ratio':'ISI violation ratio',
              'presence_ratio':'Presence ratio', 'amplitude_cutoff':'Amplitude cutoff',
              'total_spikes':'Total spikes', 'snr':'SNR'}
    text = '\n'.join(f'{labels.get(k, k)}: {format_metric(metrics.get(k))}' for k in shown)
    panel.text(0, .98, text, va='top', fontsize=10, linespacing=1.7, transform=panel.transAxes)
    fig.suptitle(f"{len(data['traces'])} displayed / {data['stored_waveforms']} stored waveforms · Unit {unit_id}")
    fig.text(.02, .025, 'Stored spike alignment; no normalization or realignment. Model labels are not proof of single-unit isolation.', fontsize=8)
    fig.tight_layout(rect=(0, .06, 1, .94))
    return fig, data, metrics
