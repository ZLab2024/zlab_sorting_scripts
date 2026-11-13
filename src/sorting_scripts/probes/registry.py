"""Named probe resources independent of checkout location."""
from importlib.resources import files, as_file
from pathlib import Path
from probeinterface import Probe, ProbeGroup, read_probeinterface
from .geometry import make_bf_group

PRESETS = ('deeparray128', 'bf_dummy8', 'bf_single8', 'neuronexus16')
RESOURCES = {'deeparray128': 'deeparray128_P1925-127_H1925-116.json',
             'neuronexus16': 'neuronexus-A16x1_2mm_50_177_A16.json',
             'dummy8_probe.json': 'dummy8_probe.json'}


def get_probe(spec, *, n_channels=None):
    """Return a fresh ProbeGroup from a preset, JSON path, Probe, or ProbeGroup.

    BF presets explicitly declare consecutive groups of eight. Use a channel map
    when the acquisition order differs. The returned geometry does not prove wiring.
    """
    if isinstance(spec, Probe):
        group = ProbeGroup(); group.add_probe(Probe.from_dict(spec.to_dict())); return group
    if isinstance(spec, ProbeGroup):
        return ProbeGroup.from_dict(spec.to_dict())
    spec = str(spec)
    if spec in ('bf_dummy8', 'bf_single8'):
        return make_bf_group(8 if n_channels is None else n_channels, independent=spec == 'bf_single8')
    name = RESOURCES.get(spec, spec)
    resource = files('sorting_scripts.probes.resources').joinpath(name)
    if name in RESOURCES.values() or name in ('deeparray128_P1925-127_H1925-116.json', 'neuronexus-A16x1_2mm_50_177_A16.json'):
        with as_file(resource) as path:
            return read_probeinterface(path)
    path = Path(spec).expanduser()
    if path.suffix.lower() == '.prb':
        from probeinterface import read_prb
        return read_prb(path)
    return read_probeinterface(path)
