"""Validate complete wiring before attachment can select or reorder channels."""
import csv
import numpy as np
from .registry import get_probe


def read_channel_map(path):
    """Read CSV columns contact_index,channel_id in global probe/contact order.

    channel_id is matched as text against recording IDs; mixed ambiguous IDs fail.
    """
    with open(path, newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows or set(rows[0]) != {'contact_index', 'channel_id'}:
        raise ValueError('Channel map requires exactly contact_index,channel_id columns')
    indices = [int(row['contact_index']) for row in rows]
    if sorted(indices) != list(range(len(rows))):
        raise ValueError('contact_index must cover 0..N-1 once')
    return [row['channel_id'] for row in sorted(rows, key=lambda row: int(row['contact_index']))]


def attach_probe(recording, spec, *, channel_ids=None, replace=False):
    """Return a wired recording preserving source order and all channels.

    channel_ids lists source IDs in flattened probe/contact order. By default,
    built-in positional wiring is used. Select exclusions on the recording first,
    then supply a matching custom group/map. Existing probes require replace=True.
    """
    existing = recording.get_property('contact_vector')
    if existing is not None and not replace:
        raise ValueError('Probe already attached; explicitly use replace=True')
    group = get_probe(spec, n_channels=recording.get_num_channels())
    count = sum(p.get_contact_count() for p in group.probes)
    if count != recording.get_num_channels():
        raise ValueError(f'Probe contacts ({count}) != original recording channels ({recording.get_num_channels()})')
    if channel_ids is not None:
        lookup = {str(uid): i for i, uid in enumerate(recording.channel_ids)}
        if len(lookup) != count or len(channel_ids) != count or len(set(map(str, channel_ids))) != count:
            raise ValueError('Channel map must contain each unambiguous recording ID once')
        try: indices = np.asarray([lookup[str(uid)] for uid in channel_ids])
        except KeyError as error: raise ValueError(f'Unknown channel ID: {error}') from error
        from probeinterface import Probe, ProbeGroup
        remapped = ProbeGroup()
        start = 0
        for old in group.probes:
            p = Probe.from_dict(old.to_dict())
            n = p.get_contact_count()
            p.set_device_channel_indices(indices[start:start+n])
            remapped.add_probe(p)
            start += n
        group = remapped
    wires = [p.device_channel_indices for p in group.probes]
    if any(w is None for w in wires):
        raise ValueError('Every probe must have device_channel_indices or an explicit channel map')
    wires = np.concatenate(wires)
    if not np.array_equal(np.sort(wires), np.arange(count)):
        raise ValueError('Wiring must cover every recording position once, with no disconnected contacts')
    # SI 0.103's NumpyRecording.clone() can reset custom channel IDs. Use a
    # channel view and attach in place to that view, preserving the source object.
    view = recording.select_channels(recording.channel_ids)
    result = view.set_probegroup(group, group_mode='by_probe', in_place=True)
    if not np.array_equal(result.channel_ids, recording.channel_ids):
        raise ValueError('Attachment changed source channel identities')
    for key in ('gain_to_uV', 'offset_to_uV'):
        if not np.array_equal(result.get_property(key), recording.get_property(key)):
            raise ValueError(f'Attachment changed {key}')
    bundles = np.zeros(count, dtype=int)
    for index, p in enumerate(group.probes):
        bundles[p.device_channel_indices] = p.annotations.get('bundle_index', index)
    result.set_property('bundle', bundles)
    result.annotate(virtual_geometry=any(p.annotations.get('virtual_geometry', False) for p in group.probes))
    return result
