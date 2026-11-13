"""Stored analyzer inspection, independent of task analyses and optional GUIs."""
from .stored import open_analyzer, selected_units, ensemble_data, unit_metrics, summary_figure


def inspect_analyzer(path, *, unit_id=None, output=None):
    """Return an analyzer, or export one unit's waveform/QC PNG to a new path."""
    from pathlib import Path
    analyzer = open_analyzer(path)
    if output is not None:
        output = Path(output).expanduser().resolve()
        source = Path(path).expanduser().resolve()
        if output.exists() or source == output or source in output.parents:
            raise FileExistsError('Inspection output must be new and outside the source analyzer')
        if unit_id is None:
            raise ValueError('Select unit_id when exporting a summary')
        matches = [u for u in analyzer.unit_ids if str(u) == str(unit_id)]
        if len(matches) != 1:
            raise ValueError(f'Unknown/ambiguous unit: {unit_id}')
        import matplotlib.pyplot as plt
        figure, _, _ = summary_figure(analyzer, matches[0])
        try:
            with output.open('xb') as handle:
                figure.savefig(handle, format='png', dpi=150)
        finally:
            plt.close(figure)
    return analyzer
