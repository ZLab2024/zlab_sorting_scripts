"""Exact event-multiset checks shared with the DHN single-wire merge workflow."""
import numpy as np
import pandas as pd


def verify_lineage(before, after, mapping):
    """Require every original unit/event, including coincidences, to be accounted for."""
    if set(mapping) != set(before.unit_ids) or set(mapping.values()) != set(after.unit_ids):
        raise ValueError('Lineage must cover every input and output unit')
    if before.get_num_segments() != after.get_num_segments():
        raise ValueError('Segment count changed')
    for target in after.unit_ids:
        for segment in range(before.get_num_segments()):
            expected = np.sort(np.concatenate([before.get_unit_spike_train(u, segment_index=segment)
                                               for u, v in mapping.items() if v == target]))
            if not np.array_equal(expected, after.get_unit_spike_train(target, segment_index=segment)):
                raise ValueError(f'Event multiset changed for unit {target}, segment {segment}')


def event_lineage(sorting, mapping):
    """Return one row per original event, preserving duplicate event ordinals."""
    rows = []
    for segment in range(sorting.get_num_segments()):
        for unit in sorting.unit_ids:
            for ordinal, sample in enumerate(sorting.get_unit_spike_train(unit, segment_index=segment)):
                rows.append((segment, unit, ordinal, int(sample), mapping[unit]))
    return pd.DataFrame(rows, columns=['segment_index', 'original_unit_id', 'original_event_index', 'sample_index', 'final_unit_id'])
