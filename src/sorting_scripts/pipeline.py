"""One validated load/sort/cluster/analyze/curate workflow for notebooks and CLI."""
from datetime import datetime, timezone
from pathlib import Path
from importlib.util import find_spec
import json
import uuid
import numpy as np
import pandas as pd
import spikeinterface as si
from .config import load_config
from . import io, backends
from .probes import attach_probe, read_channel_map
from .preprocessing import preprocess
from .analysis import prepare_analyzer
from .curation import apply_policy
from .provenance import identity, input_identity, write_json, tree_hashes, writer_lock


def _recording(config):
    inp = config['input']
    recording = io.load_recording(inp['path'], format=inp['format'], stream_id=inp['stream_id'],
                                  password_env=inp['password_env'], sampling_frequency=inp['sampling_frequency'],
                                  extractor=inp['extractor'], reader_kwargs=inp['reader_kwargs'], path_argument=inp['path_argument'])
    if inp['channel_ids'] is not None:
        recording = recording.select_channels(inp['channel_ids'])
    if recording.get_num_segments() != 1 or recording.get_num_samples() == 0:
        raise ValueError('Runner requires one nonempty continuous segment; resolve gaps explicitly first')
    if recording.get_sampling_frequency() <= 12000:
        raise ValueError('300–6000 Hz profiles require sampling frequency greater than 12000 Hz')
    probe = config['probe']
    recording = attach_probe(recording, probe['preset'],
                              channel_ids=read_channel_map(probe['channel_map']) if probe['channel_map'] else None,
                              replace=probe['replace_existing'])
    return recording


def _groups(recording):
    groups = recording.get_property('group')
    return [(int(g), recording.channel_ids[groups == g]) for g in np.unique(groups)]


def validate(source, *, check_backend=True):
    """Validate config, open headers, verify wiring and report groups; write nothing.

    No sorting, model loading, caching or analyzer-extension computation occurs.
    check_backend=False is useful for read-only configuration review on CPU hosts.
    """
    config = load_config(source)
    backend = config['sorting']['backend']
    if check_backend and backend != 'osort_import' and find_spec(backend) is None:
        raise ImportError(f'Backend {backend} is unavailable; install the corresponding sorting extra')
    reserved = {'recording','folder','sorter_name','remove_existing_folder','delete_recording_dat','filter','whiten'}
    if reserved & config['sorting']['params'].keys():
        raise ValueError('Reserved backend/preprocessing options cannot be overridden')
    if config['curation']['policy'] in ('labels_only','cleanup_merge'):
        from .auto_curate import AutoCurationConfig, _validate_config
        options = config['curation']['options']
        candidate = AutoCurationConfig(enable_model_labeling=False)
        for k,v in options.items():
            if k not in candidate.__dataclass_fields__: raise ValueError(f'Unknown curation option: {k}')
            setattr(candidate,k,v)
        _validate_config(candidate)  # checks configuration, never loads models
        if config['curation']['policy'] == 'labels_only' and any(options.get(k,False) for k in
                ('remove_duplicate_spikes','remove_redundant_units','auto_merge','apply_quality_filtering','apply_model_filtering')):
            raise ValueError('labels_only cannot change events or reject units')
    elif config['curation']['options']:
        raise ValueError('This curation policy does not accept options')
    recording = _recording(config)
    groups = _groups(recording)
    if config['sorting']['profile'] == 'bf_single_wire' and any(len(ids) != 1 for _,ids in groups):
        raise ValueError('bf_single_wire requires one sorting group per channel (use bf_single8)')
    if config['sorting']['profile'] == 'bf_bundle_ms5' and any(len(ids) != 8 for _,ids in groups):
        raise ValueError('bf_bundle_ms5 requires eight channels per sorting group')
    if config['curation']['policy'] == 'single_wire_merge_preserve_events' and any(len(ids) != 1 for _,ids in groups):
        raise ValueError('Event-preservation merging requires independent single-wire groups')
    if backend == 'osort_import':
        entries = config['sorting']['osort']
        expected = [str(ids[0]) for _,ids in groups if len(ids) == 1]
        actual = [str(e['channel_id']) for e in entries]
        if len(expected) != len(groups) or len(actual) != len(set(actual)) or set(actual) != set(expected):
            raise ValueError('oSort import needs exactly one entry per independent source channel')
        # Validate timestamp mapping and bounds before creating run outputs.
        for _, ids in groups: _import_osort(recording.select_channels(ids), config)
    return dict(config=config, channels=recording.channel_ids.tolist(),
                sampling_frequency=recording.get_sampling_frequency(), samples=recording.get_num_samples(),
                groups=[{'group': g, 'channel_ids': ids.tolist()} for g,ids in groups],
                virtual_geometry=recording.get_annotation('virtual_geometry'))


def _import_osort(recording, config):
    from .io.osort import load_osort
    entry = next(e for e in config['sorting']['osort'] if str(e['channel_id']) == str(recording.channel_ids[0]))
    grid = np.load(entry['record_timestamps_file'], allow_pickle=False) if 'record_timestamps_file' in entry else None
    return load_osort(entry['mat_file'], sampling_frequency=recording.get_sampling_frequency(),
                      num_samples=recording.get_num_samples(), record_timestamps_us=grid,
                      start_time_us=entry.get('start_time_us'))


def _load_json(path):
    return json.loads(Path(path).read_text())


def status(folder):
    """Read run status without opening a recording or executing a stage."""
    return _load_json(Path(folder)/'manifest.json')


def _check_artifacts(folder, hashes, root=None):
    if root is not None:
        actual = {str((Path(root)/name).relative_to(folder)):digest for name,digest in tree_hashes(root).items()}
        if actual != hashes:
            raise ValueError("Saved stage artifact set changed or is missing")
        return
    for name, digest in hashes.items():
        from .provenance import sha256
        path = Path(folder)/name
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f'Saved stage artifact changed or is missing: {name}')


def run(source=None, *, resume=None):
    """Run a new session, or resume an identical interrupted/failed run.

    Returns its absolute run directory. Completed group stages are verified/reused;
    failed attempts remain untouched and retry in new attempt directories. KS4
    pre-clustering resume remains an explicit separate API/CLI operation.
    """
    if resume is not None:
        folder = Path(resume).expanduser().resolve()
        state = status(folder)
        if state['status'] == 'complete': raise ValueError('Completed runs cannot resume')
        config = load_config(source if source is not None else folder/'config.json')
        expected = _load_json(folder/'identity.json')
    else:
        config = load_config(source)
        folder = None; expected = None
    # Configuration/header checks precede all mutations and expensive computation.
    validate(config)
    frozen = identity(config)
    if expected is not None and frozen != expected:
        raise ValueError('Resume identity differs (configuration, input, code or environment); create a new run')
    if folder is None:
        root = Path(config['output']['root']); root.mkdir(parents=True, exist_ok=True)
        folder = root/('sorting_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8])
        folder.mkdir(exist_ok=False)
        state = dict(schema=1, status='pending', groups={}, config='config.json', outputs={})
        write_json(folder/'config.json', config); write_json(folder/'identity.json', frozen)
        write_json(folder/'manifest.json', state)
    with writer_lock(folder):
        state['status'] = 'running'; write_json(folder/'manifest.json', state)
        def log(message):
            with (folder/'run.log').open('a') as handle:
                handle.write(datetime.now(timezone.utc).isoformat()+' '+message+'\n')
        try:
            if config['curation']['options'].get('enable_model_labeling', False):
                from .auto_curate import AutoCurationConfig, preflight
                options = dict(config['curation']['options'])
                preflight(AutoCurationConfig(**options))
            log('load and wire recording')
            recording = _recording(config)
            # MED is read sequentially and all analyzers reference a stable local cache.
            if 'recording' in state:
                _check_artifacts(folder, state['recording']['hashes'], folder/state['recording']['path'])
                recording = si.load(folder/state['recording']['path'])
            else:
                cache = folder/('recording_'+uuid.uuid4().hex[:8])
                recording = recording.save(folder=cache, format='binary', n_jobs=1, chunk_duration='1s', progress_bar=False)
                state['recording'] = dict(path=str(cache.relative_to(folder)), hashes={str(p.relative_to(folder)):v for p,v in
                    [(cache/name, digest) for name,digest in tree_hashes(cache).items()]})
                write_json(folder/'manifest.json', state)
            raw_parts, curated_parts, raw_rows, curated_rows = [], [], [], []
            for group_id, ids in _groups(recording):
                key = str(group_id)
                if key in state['groups']:
                    record = state['groups'][key]
                    _check_artifacts(folder, record['hashes'], (folder/record['raw_sorting']).parent)
                    raw = si.load(folder/record['raw_sorting']); final = si.load(folder/record['sorting'])
                    log(f'reuse group {key}')
                else:
                    log(f'process group {key}')
                    attempt = folder/'groups'/key/('attempt_'+uuid.uuid4().hex[:8]); attempt.mkdir(parents=True)
                    isolated = recording.select_channels(ids)
                    settings = config['sorting']
                    if settings['backend'] == 'osort_import':
                        raw = _import_osort(isolated, config)
                    else:
                        prepared = preprocess(isolated, settings['profile'], seed=settings['seed'])
                        raw = backends.sort(prepared, attempt/'sorter', backend=settings['backend'],
                                            profile=settings['profile'], params=settings['params'])
                    if raw.get_sampling_frequency() != recording.get_sampling_frequency() or raw.get_num_segments() != 1:
                        raise ValueError('Backend sorting has incompatible sampling coordinates')
                    for uid in raw.unit_ids:
                        spikes = raw.get_unit_spike_train(uid)
                        if np.any(spikes < 0) or np.any(spikes >= recording.get_num_samples()) or np.any(np.diff(spikes) < 0):
                            raise ValueError('Backend returned out-of-bounds or unsorted events')
                    raw = raw.save(folder=attempt/'raw_sorting', verbose=False)
                    policy = config['curation']['policy']
                    if policy == 'none' or raw.get_num_units() == 0:
                        final = raw
                    else:
                        analyzer = prepare_analyzer(isolated, raw, attempt/'analyzer', seed=settings['seed'],
                                                    virtual_geometry=recording.get_annotation('virtual_geometry'))
                        final = apply_policy(analyzer, attempt/'curation', policy=policy, options=config['curation']['options'])
                    final = final.save(folder=attempt/'sorting', verbose=False)
                    record = dict(raw_sorting=str((attempt/'raw_sorting').relative_to(folder)),
                                  sorting=str((attempt/'sorting').relative_to(folder)),
                                  hashes={str((attempt/name).relative_to(folder)):digest for name,digest in tree_hashes(attempt).items()})
                    state['groups'][key] = record; write_json(folder/'manifest.json', state)
                bundles = np.unique(recording.get_property('bundle')[recording.ids_to_indices(ids)])
                for part, rows in ((raw,raw_rows),(final,curated_rows)):
                    part.set_property('sorting_group', np.full(part.get_num_units(), group_id))
                    part.set_property('source_channel_ids', np.full(part.get_num_units(), json.dumps(ids.tolist())))
                    part.set_property('bundle', np.full(part.get_num_units(), int(bundles[0])))
                    offset = len(rows)
                    rows.extend({'unit_id':offset+j,'group':group_id,'group_unit_id':str(uid),
                                 'channel_ids':json.dumps(ids.tolist()),'bundle':int(bundles[0])} for j,uid in enumerate(part.unit_ids))
                raw_parts.append(raw); curated_parts.append(final)
            log('aggregate results and prepare final analyzer')
            destination = folder/('results_'+uuid.uuid4().hex[:8]); destination.mkdir()
            raw_aggregate = si.aggregate_units(raw_parts, renamed_unit_ids=np.arange(sum(p.get_num_units() for p in raw_parts)))
            final_aggregate = si.aggregate_units(curated_parts, renamed_unit_ids=np.arange(sum(p.get_num_units() for p in curated_parts)))
            raw_aggregate.save(folder=destination/'raw_sorting', verbose=False)
            final_aggregate = final_aggregate.save(folder=destination/'sorting', verbose=False)
            columns = ['unit_id','group','group_unit_id','channel_ids','bundle']
            pd.DataFrame(raw_rows,columns=columns).to_csv(destination/'raw_unit_map.csv', index=False)
            pd.DataFrame(curated_rows,columns=columns).to_csv(destination/'unit_map.csv', index=False)
            if final_aggregate.get_num_units():
                prepare_analyzer(recording, final_aggregate, destination/'analyzer', seed=config['sorting']['seed'],
                                 virtual_geometry=recording.get_annotation('virtual_geometry'))
            write_json(destination/'curation.json', dict(status='curated' if config['curation']['policy'] != 'none' else 'uncurated',
                        policy=config['curation']['policy'], thresholds=config['curation']['options'].get('thresholds'),
                        groups=state['groups'], note='Group-local curation; see each attempt for decisions and lineage'))
            if input_identity(config) != frozen['inputs']:
                raise ValueError('Input content changed during execution; results are not complete')
            state['outputs'] = dict(results=str(destination.relative_to(folder)),
                                   analyzer=str((destination/'analyzer').relative_to(folder)) if final_aggregate.get_num_units() else None,
                                   sorting=str((destination/'sorting').relative_to(folder)),
                                   raw_sorting=str((destination/'raw_sorting').relative_to(folder)))
            state['output_hashes'] = {str((destination/name).relative_to(folder)):digest for name,digest in tree_hashes(destination).items()}
            state['status'] = 'complete'; state.pop('error_type',None)
            log('complete'); write_json(folder/'manifest.json', state)
        except BaseException as error:
            state['status'] = 'failed'; state['error_type'] = type(error).__name__
            # Persist stage/type only; upstream exceptions may include credentials.
            log('failed: '+type(error).__name__); write_json(folder/'manifest.json', state)
            raise
    return folder
