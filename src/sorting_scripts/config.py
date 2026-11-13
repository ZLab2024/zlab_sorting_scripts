"""Strict JSON/TOML session configuration; relative paths resolve at the file."""
from copy import deepcopy
from pathlib import Path
import json
from .preprocessing import PROFILES
from .curation import POLICIES

DEFAULTS = {
    'input': {'stream_id': None, 'password_env': 'MED_PASSWORD', 'sampling_frequency': None, 'channel_ids': None, 'extractor': None, 'reader_kwargs': {}, 'path_argument': None},
    'probe': {'preset': 'bf_single8', 'channel_map': None, 'replace_existing': False},
    'sorting': {'backend': 'mountainsort5', 'profile': 'bf_single_wire', 'params': {}, 'seed': 0, 'osort': []},
    'curation': {'policy': 'labels_only', 'options': {}},
    'output': {'root': None},
    'job': {'n_jobs': 1},
}
EXTRA_KEYS = {'input': {'format', 'path'}, 'probe': set(), 'sorting': set(), 'curation': set(), 'output': set(), 'job': set()}


def load_config(source):
    """Return a normalized configuration dict from a path or Python mapping.

    Unknown fields, inconsistent profiles and unsupported policy combinations fail
    before output creation. Secrets belong in the named environment variable.
    """
    root = Path.cwd()
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser().resolve(); root = path.parent
        if path.suffix == '.json':
            source = json.loads(path.read_text())
        else:
            try: import tomllib
            except ImportError: import tomli as tomllib
            source = tomllib.loads(path.read_text())
    if not isinstance(source, dict) or source.keys() - DEFAULTS.keys():
        raise ValueError('Configuration requires known input/probe/sorting/curation/output/job sections')
    config = deepcopy(DEFAULTS)
    for section, values in source.items():
        if not isinstance(values, dict) or values.keys() - (DEFAULTS[section].keys() | EXTRA_KEYS[section]):
            raise ValueError(f'Unknown fields in {section}')
        config[section].update(deepcopy(values))
    inp, probe, sorting, curate = [config[k] for k in ('input', 'probe', 'sorting', 'curation')]
    def reader_options(values):
        for key, value in values.items():
            if key.lower() in {'password', 'passwd', 'token', 'api_key', 'secret', 'access_key', 'client_secret'}:
                raise ValueError('Credentials cannot be stored in reader_kwargs; MED uses password_env')
            if isinstance(value, dict):
                reader_options(value)
            elif isinstance(value, str) and key.endswith(('_path', '_file', '_folder')):
                values[key] = str((root / Path(value).expanduser()).resolve())
    if isinstance(inp['reader_kwargs'], dict):
        reader_options(inp['reader_kwargs'])

    from .io import FORMATS
    if inp.get('format') not in FORMATS or not inp.get('path'):
        raise ValueError('input.format and input.path are required')
    if not isinstance(inp['reader_kwargs'], dict):
        raise ValueError('input.reader_kwargs must be a dictionary')
    if inp['format'] == 'spikeinterface' and not inp['extractor']:
        raise ValueError('spikeinterface format requires input.extractor')
    if inp['format'] not in ('binary', 'spikeinterface') and (inp['extractor'] or inp['reader_kwargs'] or inp['path_argument']):
        raise ValueError('Generic reader options require binary or spikeinterface format')
    if inp['format'] == 'binary' and not {'dtype', 'num_channels'} <= inp['reader_kwargs'].keys():
        raise ValueError('Raw binary requires dtype and num_channels in input.reader_kwargs')
    if not config['output']['root']:
        raise ValueError('output.root is required')
    for section, key in [('input','path'), ('output','root'), ('probe','channel_map')]:
        if config[section][key] is not None:
            config[section][key] = str((root / Path(config[section][key]).expanduser()).resolve())
    if not isinstance(probe['preset'], str):
        raise ValueError('probe.preset must be a registry name or JSON path')
    if probe['preset'].lower().endswith(('.json', '.prb')):
        from .probes.registry import RESOURCES
        if probe['preset'] not in RESOURCES.values() and probe['preset'] not in RESOURCES:
            probe['preset'] = str((root / Path(probe['preset']).expanduser()).resolve())
    if not isinstance(probe['replace_existing'], bool):
        raise ValueError('probe.replace_existing must be boolean')
    if PROFILES.get(sorting['profile']) != sorting['backend']:
        raise ValueError('sorting.profile and backend do not match')
    if curate['policy'] not in POLICIES:
        raise ValueError('Unknown curation.policy')
    if not isinstance(sorting['params'], dict) or not isinstance(curate['options'], dict):
        raise ValueError('Sorter params and curation options must be dictionaries')
    if isinstance(sorting['seed'], bool) or not isinstance(sorting['seed'], int) or sorting['seed'] < 0:
        raise ValueError('sorting.seed must be a nonnegative integer')
    if config['job']['n_jobs'] != 1:
        raise ValueError('The initial runner requires job.n_jobs=1 (sequential groups and MED reads)')
    if not isinstance(sorting['osort'], list):
        raise ValueError('sorting.osort must be a list of import entries')
    for entry in sorting['osort']:
        if not isinstance(entry,dict) or entry.keys() - {'channel_id','mat_file','record_timestamps_file','start_time_us'}:
            raise ValueError('Invalid oSort entry fields')
        if not {'channel_id','mat_file'} <= entry.keys() or ('record_timestamps_file' in entry) == ('start_time_us' in entry):
            raise ValueError('Each oSort entry needs channel_id,mat_file and one timestamp origin/grid')
        for key in ('mat_file', 'record_timestamps_file'):
            if key in entry: entry[key] = str((root / Path(entry[key]).expanduser()).resolve())
    if sorting['backend'] == 'osort_import' and not sorting['osort']:
        raise ValueError('osort_import requires sorting.osort entries')
    source_path = Path(inp['path']); output = Path(config['output']['root'])
    source_root = source_path if source_path.is_dir() else source_path.parent
    if output == source_root or source_root in output.parents:
        raise ValueError('output.root must be outside the input tree')
    # Ensure all remaining values are serializable and finite.
    json.dumps(config, allow_nan=False)
    return config
