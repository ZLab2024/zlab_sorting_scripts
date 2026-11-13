"""Labels-only execution preserving even empty candidate units and every event."""
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from ..auto_curate import _compute_metrics, _label_units
from ..model_labeling import _preload_classifiers, label_final_units, persist_model_labels
from ..lineage import verify_lineage
from ..provenance import write_json


def label_only(analyzer, folder, config):
    """Save labels/metrics and exact identity lineage without cleanup or selection."""
    folder = Path(folder)
    if folder.exists(): raise FileExistsError(folder)
    loaded = _preload_classifiers(config)
    folder.mkdir(parents=True)
    working = analyzer.copy()
    metrics = _compute_metrics(working, config)
    labels = _label_units(working, metrics, config)
    ml, metadata = label_final_units(working, config, folder, loaded_models=loaded)
    saved = working.save_as(format='binary_folder', folder=folder/'analyzer')
    saved.set_sorting_property('auto_curation_label', labels.reindex(saved.unit_ids)['label'].to_numpy(dtype=str))
    persist_model_labels(saved, ml, config)
    mapping = {u:u for u in analyzer.unit_ids}
    verify_lineage(analyzer.sorting,saved.sorting,mapping)
    metrics.to_csv(folder/'metrics_after.csv',index_label='unit_id')
    labels.to_csv(folder/'labels.csv',index_label='unit_id')
    ml.to_csv(folder/'unit_ml_classifications.csv',index_label='unit_id')
    pd.DataFrame([dict(unit_id=u,final_unit_id=u,decision='kept',label=labels.loc[u,'label']) for u in saved.unit_ids]).to_csv(folder/'decisions.csv',index=False)
    write_json(folder/'config.json',asdict(config))
    write_json(folder/'curation.json',dict(status='curated',policy='labels_only',event_multisets_verified=True,
                                         config=asdict(config),model_metadata=metadata))
    return saved.sorting
