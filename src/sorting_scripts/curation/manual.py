"""Apply saved manual GUI decisions to any analyzer, with explicit new outputs."""
import json
from pathlib import Path
import spikeinterface as si


def apply_manual_curation(analyzer, decisions, output):
    """Apply a curation dictionary/JSON to an analyzer object/path; save a new Zarr.

    Source analyzers and decisions remain intact. The caller chooses the exact
    output path, avoiding patient/session naming assumptions from legacy helpers.
    Hard merges recompute extensions against the attached recording.
    """
    if isinstance(analyzer, (str, Path)):
        analyzer = si.load_sorting_analyzer(Path(analyzer).expanduser())
    destination = Path(output).expanduser().resolve()
    source = Path(analyzer.folder).resolve() if analyzer.folder else None
    if destination.exists():
        raise FileExistsError(destination)
    if source and source in destination.parents:
        raise ValueError('Curation output must be outside the source analyzer')
    if isinstance(decisions, (str, Path)):
        decisions = json.loads(Path(decisions).expanduser().read_text())
    from spikeinterface.curation import apply_curation
    curated = apply_curation(analyzer, curation_dict_or_model=decisions, merging_mode='hard')
    return curated.save_as(format='zarr', folder=destination)
