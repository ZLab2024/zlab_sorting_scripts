"""Content identities, atomic JSON and exclusive writer locks for sorting runs."""
from contextlib import contextmanager
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
import hashlib
import json
import os
import numpy as np


def json_default(value):
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, Path): return str(value)
    raise TypeError(f'Not JSON serializable: {type(value).__name__}')


def write_json(path, value):
    """Atomically replace JSON in a directory owned by the current writer."""
    path = Path(path); temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, default=json_default, allow_nan=False)+'\n')
    temp.replace(path)


def sha256(path):
    """Stream a complete file content hash without loading it into RAM."""
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def tree_hashes(path):
    path = Path(path)
    return {str(p.relative_to(path)): sha256(p) for p in sorted(path.rglob('*')) if p.is_file()}


def input_identity(config):
    """Hash every selected raw source file plus custom wiring/probe/oSort inputs."""
    path = Path(config['input']['path'])
    if not path.exists(): raise FileNotFoundError(path)
    if config['input']['format'] == 'intan':
        from .get_file import get_rhd_files
        paths = get_rhd_files(path)
    else:
        paths = [path] if path.is_file() else [p for p in path.rglob('*') if p.is_file()]
    # Saved binary-folder metadata may refer to data outside its directory.
    if config['input']['format'] == 'binary_folder':
        metadata = path / 'binary.json'
        if metadata.is_file():
            info = json.loads(metadata.read_text())
            for item in info.get('kwargs', {}).get('file_paths', []):
                paths.append((path / item).resolve() if info.get('relative_paths') else Path(item))
    def referenced_files(value):
        if isinstance(value, dict):
            for item in value.values(): referenced_files(item)
        elif isinstance(value, (list, tuple)):
            for item in value: referenced_files(item)
        elif isinstance(value, str) and Path(value).is_absolute():
            candidate = Path(value)
            if candidate.is_file(): paths.append(candidate)
            elif candidate.is_dir(): paths.extend(p for p in candidate.rglob('*') if p.is_file())
    referenced_files(config['input'].get('reader_kwargs', {}))
    if config['probe']['channel_map']: paths.append(Path(config['probe']['channel_map']))
    if Path(config['probe']['preset']).is_file(): paths.append(Path(config['probe']['preset']))
    for entry in config['sorting']['osort']:
        paths += [Path(entry[k]) for k in ('mat_file','record_timestamps_file') if k in entry]
    return {str(p.resolve()): sha256(p) for p in sorted(set(paths))}


def runtime_identity():
    """Fingerprint installed scientific versions and this package's executable source."""
    packages = ['spikeinterface','probeinterface','numpy','scipy','pandas','kilosort','mountainsort5','dhn-med-py','neo','scikit-learn','torch']
    versions = {}
    for name in packages:
        try: versions[name] = version(name)
        except PackageNotFoundError: versions[name] = None
    import sys
    versions['python'] = sys.version
    root = Path(__file__).parent
    sources = {str(p.relative_to(root)): sha256(p) for p in sorted(root.rglob('*'))
               if p.is_file() and 'tests' not in p.parts and p.suffix in ('.py','.json')}
    return dict(versions=versions, sources=sources)


def identity(config):
    """Full resume identity: resolved config, input content, source and runtime."""
    return dict(config=config, inputs=input_identity(config), runtime=runtime_identity())


@contextmanager
def writer_lock(folder):
    """Refuse concurrent/stale writers; never infer permission to remove a lock."""
    path = Path(folder)/'.writer.lock'
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor,'w') as handle: handle.write(str(os.getpid()))
        yield
    finally:
        path.unlink()
