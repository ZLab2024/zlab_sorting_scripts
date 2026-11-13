"""Canonical physical and virtual ProbeGroup builders; no recording mutation."""
import numpy as np
from probeinterface import Probe, ProbeGroup


def make_bf_group(n_channels=8, *, independent=False, radius_um=50., spacing_um=1000.):
    """Build explicit consecutive eight-wire bundles or one-contact probes.

    Geometry is virtual. ``independent=True`` creates eight probes per bundle,
    rather than one eight-contact probe. Device indices cover all input channels.
    """
    if isinstance(n_channels, bool) or not isinstance(n_channels, (int, np.integer)) or n_channels <= 0 or n_channels % 8:
        raise ValueError('BF presets require a positive multiple of eight channels')
    if not np.isfinite([radius_um, spacing_um]).all() or radius_um <= 0 or spacing_um <= 2 * radius_um:
        raise ValueError('Positive radius and nonoverlapping bundle spacing required')
    group = ProbeGroup()
    for bundle in range(n_channels // 8):
        angles = np.arange(8) * (2 * np.pi / 8)
        positions = radius_um * np.column_stack([np.cos(angles), np.sin(angles)])
        positions[:, 0] += bundle * spacing_um
        for indices in ([np.array([i]) for i in range(8)] if independent else [np.arange(8)]):
            probe = Probe(ndim=2, si_units='um')
            probe.set_contacts(positions[indices], shapes='circle', shape_params={'radius': 6.})
            probe.set_contact_ids([str(bundle * 8 + i) for i in indices])
            probe.set_device_channel_indices(bundle * 8 + indices)
            probe.annotate(virtual_geometry=True, bundle_index=bundle)
            group.add_probe(probe)
    return group
