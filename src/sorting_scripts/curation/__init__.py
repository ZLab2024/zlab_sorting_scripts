"""Explicit policies over existing automatic curation and preservation merging."""
POLICIES = ('none', 'labels_only', 'cleanup_merge', 'single_wire_merge_preserve_events')


def apply_policy(analyzer, folder, *, policy='labels_only', options=None):
    """Run an explicit policy on ONE sorting group and return its final Sorting.

    Models default off in this API. ``labels_only`` cannot delete or merge events.
    ``cleanup_merge`` may change trains; its decisions are saved by AutoCurator.
    """
    if policy not in POLICIES or policy == 'none':
        raise ValueError(f'Policy requires no execution or is unknown: {policy}')
    if policy == 'single_wire_merge_preserve_events':
        if options:
            raise ValueError('Preservation policy has fixed documented thresholds; options unsupported')
        from ..merging import merge_preserving_events
        return merge_preserving_events(analyzer, folder)
    from ..auto_curate import AutoCurationConfig, AutoCurator
    settings = dict(enable_model_labeling=False,
                    extension_params={'unit_locations': {'method': 'center_of_mass'},
                                      'random_spikes': {'max_spikes_per_unit': 500, 'seed': 0}})
    settings.update(options or {})
    if policy == 'labels_only':
        protected = dict(remove_duplicate_spikes=False, remove_redundant_units=False,
                         auto_merge=False, apply_quality_filtering=False, apply_model_filtering=False)
        if any(k in settings and settings[k] != v for k,v in protected.items()):
            raise ValueError('labels_only cannot enable cleanup, merging or filtering')
        settings.update(protected)
    config = AutoCurationConfig(**settings)
    if policy == 'labels_only':
        from .labeling import label_only
        return label_only(analyzer, folder, config)
    return AutoCurator(config).run(analyzer, folder).analyzer.sorting


def apply_manual_curation(analyzer, decisions, output):
    """Apply saved GUI decisions to any analyzer and write a new Zarr destination."""
    from .manual import apply_manual_curation as apply
    return apply(analyzer, decisions, output)
