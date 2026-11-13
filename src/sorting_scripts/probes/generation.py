"""Probe generation and explicit export, usable from any installed checkout/wheel."""
from pathlib import Path
import numpy as np
from probeinterface import Probe, write_probeinterface
from .registry import get_probe


def make_linear_probe(n_contacts=16, *, pitch_um=50., contact_radius_um=5.):
    """Generate a wired physical-layout linear Probe without writing a file."""
    if isinstance(n_contacts, bool) or not isinstance(n_contacts, (int, np.integer)) or n_contacts < 1:
        raise ValueError('n_contacts must be a positive integer')
    if not np.isfinite([pitch_um, contact_radius_um]).all() or pitch_um <= 0 or contact_radius_um <= 0:
        raise ValueError('Pitch and contact radius must be finite and positive')
    probe = Probe(ndim=2, si_units='um')
    probe.set_contacts(np.column_stack([np.zeros(n_contacts), np.arange(n_contacts)*pitch_um]),
                       shapes='circle', shape_params={'radius': contact_radius_um})
    probe.set_device_channel_indices(np.arange(n_contacts))
    probe.set_contact_ids([f'ch{i}' for i in range(n_contacts)])
    return probe


def save_probe(probe, output):
    """Write a Probe/ProbeGroup/preset as a NEW JSON file and return its path.

    Existing output is never replaced. Geometry creation and disk export are
    separate operations. Packaged resource definitions are never overwritten.
    """
    from tempfile import TemporaryDirectory
    path = Path(output).expanduser().resolve()
    if path.suffix.lower() != '.json':
        raise ValueError('Probe export requires a .json destination')
    group = get_probe(probe)
    with TemporaryDirectory(prefix='zlab-probe-') as directory:
        temporary = Path(directory)/'probe.json'
        write_probeinterface(temporary, group)
        with path.open('xb') as handle:
            handle.write(temporary.read_bytes())
    return path
