"""Single-wire complete-link merging extracted from DHN_Validation.

No classifier gates, cleanup, target unit count or event censoring. The policy
retains all existing candidate events; it does not detect or split new clusters.
"""
import numpy as np
import pandas as pd
import spikeinterface as si
from spikeinterface.curation import compute_merge_unit_groups, MergeUnitsSorting
from spikeinterface.qualitymetrics import compute_refrac_period_violations
from .lineage import verify_lineage, event_lineage

PRESETS = ("similarity_correlograms", "temporal_splits")
STEPS = {
    "num_spikes": {"min_spikes": 100},
    "remove_contaminated": {"contamination_thresh": .2, "refractory_period_ms": 1., "censored_period_ms": 0.},
    "template_similarity": {"template_diff_thresh": .25},
    "quality_score": {"firing_contamination_balance": 1.5, "refractory_period_ms": 1., "censored_period_ms": 0.},
}


def complete_link_groups(unit_ids, pair_scores, accept=lambda group: True):
    """Greedy complete-link grouping: A-B and B-C never imply A-C.

    A group must pass every original pair and an independent whole-group check.
    Scores rank only native passing pairs; no count target enters the procedure.
    """
    groups = [{int(u)} for u in unit_ids]
    edges = {tuple(sorted(map(int, pair))): float(score) for pair, score in pair_scores.items()}
    for (a, b), _ in sorted(edges.items(), key=lambda item: (-item[1], item[0])):
        ga = next(g for g in groups if a in g)
        gb = next(g for g in groups if b in g)
        if ga is gb:
            continue
        if not all(tuple(sorted((x, y))) in edges for x in ga for y in gb):
            continue
        union = sorted(ga | gb)
        if not accept(union):
            continue
        groups = [g for g in groups if g is not ga and g is not gb] + [set(union)]
    return sorted([sorted(g) for g in groups if len(g) > 1])


def metrics(analyzer):
    contamination, violations = compute_refrac_period_violations(analyzer, refractory_period_ms=1., censored_period_ms=0.)
    rows = []
    duration = analyzer.get_total_duration()
    for u in analyzer.unit_ids:
        train = analyzer.sorting.get_unit_spike_train(u)
        rows.append({"unit_id": int(u), "events": len(train), "firing_rate_hz": len(train)/duration,
                     "rp_contamination_1ms": contamination[u], "rp_violations_1ms": violations[u],
                     "exact_duplicate_events": int(np.sum(np.diff(train) == 0))})
    return pd.DataFrame(rows)


def propose_merges(analyzer):
    """Propose complete-link merges for exactly one channel, with uncensored checks."""
    if analyzer.get_num_channels() != 1 or analyzer.get_num_segments() != 1:
        raise ValueError("Preservation merge policy requires one channel and one segment")
    if not np.issubdtype(analyzer.unit_ids.dtype, np.integer):
        raise ValueError("Preservation merge policy requires integer unit IDs")
    # Copy first: SI's correlogram step modifies its correlogram array in place.
    working = analyzer.copy()
    working.compute("template_similarity", method="l1", max_lag_ms=.1, support="union")
    similarity = working.get_extension("template_similarity").get_data().copy()
    candidates = {}
    evidence = []
    for preset in PRESETS:
        pairs, outputs = compute_merge_unit_groups(
            working.copy(), preset=preset, resolve_graph=False, steps_params=STEPS,
            steps=["num_spikes", "remove_contaminated", "template_similarity",
                   "correlogram" if preset == "similarity_correlograms" else "presence_distance", "quality_score"],
            force_copy=False, extra_outputs=True, n_jobs=1, progress_bar=False)
        passing = {tuple(sorted(map(int, pair))) for pair in pairs}
        for i, a in enumerate(working.unit_ids):
            for j in range(i+1, len(working.unit_ids)):
                b = working.unit_ids[j]
                key = tuple(sorted((int(a), int(b))))
                if key in passing:
                    candidates[key] = float(similarity[i, j])
                evidence.append({"preset": preset, "unit_a": int(a), "unit_b": int(b),
                                 "l1_template_similarity": float(similarity[i, j]),
                                 "native_pair_passed": key in passing,
                                 "correlogram_difference": float(outputs.get("correlogram_diff", np.full_like(similarity, np.nan))[i, j]),
                                 "presence_distance_s": float(outputs.get("presence_distances", np.full_like(similarity, np.nan))[i, j])})
    before = metrics(working).set_index("unit_id")
    checks = []

    def accept(group):
        # Validate the actual uncensored group, including any coincident events.
        # SI's built-in quality step checks pairs and can censor exact duplicates.
        merged = MergeUnitsSorting(working.sorting, [group], new_unit_ids=[group[0]], delta_time_ms=None)
        selected = merged.select_units([group[0]])
        check = si.create_sorting_analyzer(selected, working.recording, sparse=False)
        row = metrics(check).iloc[0]
        old = before.loc[group]
        old_score = (old.firing_rate_hz * (1 - 2.5*old.rp_contamination_1ms)).max()
        score = row.firing_rate_hz * (1 - 2.5*row.rp_contamination_1ms)
        passed = bool(np.isfinite(score) and row.rp_contamination_1ms <= .2 and score >= old_score)
        checks.append({"members": "+".join(map(str, group)), "uncensored_contamination": row.rp_contamination_1ms,
                       "uncensored_score": score, "best_member_score": old_score, "accepted": passed})
        return passed

    groups = complete_link_groups(working.unit_ids, candidates, accept)
    return working, groups, pd.DataFrame(evidence), pd.DataFrame(checks, columns=["members", "uncensored_contamination", "uncensored_score", "best_member_score", "accepted"])


def merge_preserving_events(analyzer, folder):
    """Save a fresh sorting plus per-event/unit lineage and merge evidence.

    Returns the merged Sorting. Run per independent wire, before aggregation.
    """
    from pathlib import Path
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    if analyzer.get_num_units() < 2:
        groups = []; pairs = pd.DataFrame(); checks = pd.DataFrame()
        if analyzer.get_num_channels() != 1:
            raise ValueError('Preservation merge policy requires one channel')
    else:
        _, groups, pairs, checks = propose_merges(analyzer)
    original = analyzer.sorting
    mapping = {u: u for u in original.unit_ids}
    next_id = int(max(original.unit_ids)) + 1 if len(original.unit_ids) else 0
    new_ids = list(range(next_id, next_id + len(groups)))
    for group, target in zip(groups, new_ids):
        mapping.update({u: target for u in group})
    merged = MergeUnitsSorting(original, groups, new_unit_ids=new_ids, delta_time_ms=None) if groups else original
    verify_lineage(original, merged, mapping)
    merged = merged.save(folder=folder/'sorting', verbose=False)
    pd.DataFrame([{'original_unit_id': u, 'final_unit_id': v} for u, v in mapping.items()]).to_csv(folder/'unit_lineage.csv', index=False)
    event_lineage(original, mapping).to_csv(folder/'event_lineage.csv.gz', index=False)
    pairs.to_csv(folder/'pair_evidence.csv', index=False)
    checks.to_csv(folder/'group_checks.csv', index=False)
    return merged
