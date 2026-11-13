"""Sorting helpers with automatic discovery of chunked Intan recordings.

Directory workflow (no notebook changes are required in this module):

    paths = zsort.set_paths("/path/to/subject/session_with_rhd_files")
    rec = zsort.load_recording(paths)
    rec = zsort.set_probe(rec, paths, "your_probe.json")
    sorting = zsort.sort(rec, paths)

``set_paths(patient, session)`` still resolves the existing data-root layout,
including session/raw. ``set_paths(recording_path=...)`` also accepts a file.
Patient/session labels default to the recording directory's parent/name when
an explicit source is given; keyword labels can override these defaults.

Chunks are concatenated lazily in natural filename order into one segment.
Raw files are never rewritten, and no merged .rhd is produced. The resulting
sample clock starts at zero; source wall-clock timestamps are not preserved,
and inter-file gaps are neither inferred nor filled. Use only chunks from the
same continuous acquisition. Filenames/sample boundaries are retained in the
recording annotations for audit. Verify Intan channel order before attaching
a probe; discovery does not infer physical wiring. When serializing with
``to_dict``, use ``include_annotations=True`` to retain source provenance.
"""

import json
from pathlib import Path

from sorting_scripts import get_file

import spikeinterface.full as si
import probeinterface as pi
import spikeinterface.sorters as ss
from spikeinterface.sorters import run_sorter
from spikeinterface.curation import apply_curation

import numpy as np

import os
from pathlib import Path
import time


def _ensure_signed_recording(recording):
    """
    SpikeInterface preprocessing (e.g., bandpass_filter) does not support unsigned dtypes
    (common for Intan: uint16). Convert to signed if needed.
    """
    try:
        if hasattr(recording, "get_dtype"):
            dtype = recording.get_dtype()
            if np.issubdtype(dtype, np.unsignedinteger):
                print(f"[zsort] recording dtype is unsigned ({dtype}); converting to signed")
                return si.unsigned_to_signed(recording)
    except Exception as e:
        # If dtype introspection fails for any reason, keep going with original recording.
        print(f"[zsort] warning: could not inspect/convert dtype: {e}")
    return recording



def _find_repo_root(start: Path) -> Path:
    """
    Find the sorting_script repo root by walking upward until we find pyproject.toml
    (or .git as a fallback).
    """
    start = start.resolve()
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists():
            return p
        if (p / ".git").exists():
            return p
    return Path(__file__).resolve().parents[1]  # installed package resources are resolved separately


def _resolve_data_root(repo_root: Path) -> Path:
    """
    Resolve the data root in a way that matches your REALTIME_SORTING layout.

    Priority:
      1) SORTING_DATA_ROOT / DATA_ROOT env var (portable across machines)
      2) sibling data/ folder (REALTIME_SORTING/data)  <-- your screenshot layout
      3) repo-local data/ folder (sorting_script/data)
      4) legacy fallback ~/codespace/data (optional)
    """
    env = os.environ.get("SORTING_DATA_ROOT") or os.environ.get("DATA_ROOT")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p.resolve()
        raise FileNotFoundError(f"Data root from env var does not exist: {p}")

    sibling = repo_root.parent / "data"
    if sibling.exists():
        return sibling.resolve()

    inside = repo_root / "data"
    if inside.exists():
        return inside.resolve()

    legacy = Path.home() / "codespace" / "data"
    if legacy.exists():
        return legacy.resolve()

    raise FileNotFoundError(
        "Could not find a data root. Create a 'data/' folder next to the repo, "
        "or set SORTING_DATA_ROOT (or DATA_ROOT)."
    )


def set_paths(
    patient: str | Path | None = None,
    session: str | None = None,
    *,
    recording_path: str | Path | None = None,
) -> dict:
    """Resolve outputs and all inputs, accepting either a directory or legacy labels.

    For multiple chunks, ``intan_file`` is None rather than silently selecting
    one file. Use ``load_recording(paths)`` for both single and chunked inputs.
    """
    try:
        here = Path(__file__)
    except NameError:
        here = Path.cwd()

    repo_root = _find_repo_root(here)
    if recording_path is None and session is None:
        if patient is None:
            raise ValueError("Provide a recording path or both patient and session.")
        recording_path = patient
        patient = None

    if recording_path is not None:
        source = Path(recording_path).expanduser().resolve()
        intan_files = get_file.get_rhd_files(source)
        session_location = source.parent if source.is_file() else source
        patient = str(patient) if patient is not None else session_location.parent.name
        session = session if session is not None else session_location.name
        data_root = session_location.parent.parent
    else:
        if patient is None or session is None:
            raise ValueError("Both patient and session are required without a recording path.")
        patient = str(patient)
        data_root = _resolve_data_root(repo_root)
        session_location = data_root / patient / session
        source = session_location
        intan_files = get_file.get_rhd_files(source)

    sorted_data = session_location / f"{patient}-{session}-sorted"
    sorter_output_folder = sorted_data / f"{patient}-{session}-sorter_folder"
    analyzer_folder = sorted_data / f"{patient}-{session}-analyzer_folder"

    sorted_data.mkdir(parents=True, exist_ok=True)

    return {
        "patient": patient,
        "session": session,
        "repo_root": repo_root,
        "data_root": data_root,
        "session_location": session_location,
        "sorted_data": sorted_data,
        "sorter_output_folder": sorter_output_folder,
        "analyzer_folder": analyzer_folder,
        "recording_source": source,
        "intan_files": intan_files,
        "intan_file": intan_files[0] if len(intan_files) == 1 else None,
    }


def load_recording(source: str | Path | dict, *, stream_id: str = "0"):
    """Compatibility entry point for :func:`sorting_scripts.io.intan.load_recording`."""
    from ..io.intan import load_recording as load
    return load(source, stream_id=stream_id)



def set_probe(recording, path_dict: dict, custom_probe_name, *, replace=False):
    """Attach a complete, validated ProbeGroup; existing geometry requires replace=True."""
    from ..probes import attach_probe
    name = str(custom_probe_name)
    candidate = Path(name).expanduser()
    if not candidate.is_absolute():
        candidate = Path(path_dict["repo_root"]) / "Custom_Probes" / name
    return attach_probe(recording, str(candidate) if candidate.exists() else name, replace=replace)



def sort(recording, path_dict: dict, *, checkpoint: bool = True,
         batch_size: int = 60000, clear_cache: bool = False):
    """
    Reuse a readable sorting, or start KS4 in a new destination.

    Existing unreadable/failed folders are never replaced. By default save a
    pre-clustering checkpoint and retain recording.dat for recovery/inspection.
    See docs/sorting_recovery.md for the scoped Kilosort 4.1.1 guard and resume.
    For CUDA memory errors, try batch_size=15000 and clear_cache=True in a
    new output folder. Batch size is in samples; smaller batches can change
    drift estimation and sorting results. Cache clearing can slow sorting.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, (int, np.integer)) or batch_size <= 0:
        raise ValueError("batch_size must be a positive integer number of samples")
    if not isinstance(clear_cache, bool):
        raise ValueError("clear_cache must be a bool")
    sorter_output_folder = Path(path_dict["sorter_output_folder"])
    if sorter_output_folder.exists():
        try:
            return ss.read_sorter_folder(sorter_output_folder)
        except Exception as error:
            raise RuntimeError(
                f"Existing sorter output could not be loaded; preserved: {sorter_output_folder}. "
                "Inspect its log or resume a checkpoint. For a full rerun choose a NEW "
                "path_dict['sorter_output_folder']; no output was deleted."
            ) from error

    from ..kilosort_runtime import kilosort_runtime

    rec = _ensure_signed_recording(recording)
    rec = si.bandpass_filter(rec, freq_min=300, freq_max=6000)
    rec = si.center(rec)
    rec = si.whiten(rec)
    checkpoint_path = sorter_output_folder / "precluster_checkpoint.pt" if checkpoint else None
    with kilosort_runtime(checkpoint_path):
        return run_sorter(
            sorter_name="kilosort4",
            recording=rec,
            folder=sorter_output_folder,
            remove_existing_folder=False,
            delete_recording_dat=not checkpoint,
            batch_size=int(batch_size),
            clear_cache=clear_cache,
            verbose=True,
        )


def analyze(recording, sorting, path_dict: dict):
    """
    Load a SortingAnalyzer if it exists; otherwise create + compute extensions.
    Returns a SortingAnalyzer.
    """
    analyzer_folder = Path(path_dict["analyzer_folder"])
    if analyzer_folder.exists():
        try:
            return si.load_sorting_analyzer(analyzer_folder)
        except Exception as error:
            raise RuntimeError(
                f"Existing analyzer could not be loaded; preserved: {analyzer_folder}. "
                "Inspect it or choose a NEW path_dict['analyzer_folder']."
            ) from error

    recording = _ensure_signed_recording(recording)
    recording_filtered = si.bandpass_filter(recording, freq_min=300, freq_max=6000)

    job_kwargs = dict(n_jobs=-1, progress_bar=True, chunk_duration="1s")

    sorting_analyzer = si.create_sorting_analyzer(
        sorting=sorting,  # IMPORTANT: pass the Sorting object, not the folder path
        recording=recording_filtered,
        folder=analyzer_folder,
        overwrite=False,
        format="binary_folder",
        **job_kwargs,
    )

    sorting_analyzer.compute(
        {
            "random_spikes": dict(method="uniform", max_spikes_per_unit=500),
            "waveforms": {},
            "templates": {},
            "noise_levels": {},
            "unit_locations": dict(method="monopolar_triangulation"),
            "isi_histograms": {},
            "correlograms": dict(window_ms=100, bin_ms=5),
            "principal_components": dict(
                n_components=3,
                mode="by_channel_global",
                whiten=True,
            ),
            "quality_metrics": dict(metric_names=["snr", "firing_rate"]),
            "spike_amplitudes": {},
            "template_similarity": dict(method="l1"),
        },
        **job_kwargs,
    )

    return sorting_analyzer


from ..gui import launch_curation_gui


def save_curated_data(patient: str, session: str, sorting_analyzer, path_dict: dict):
    """
    Apply GUI curation_data.json to the analyzer and save a new curated analyzer as zarr.
    Returns the saved curated analyzer.
    """
    curation_filepath = (
        path_dict["analyzer_folder"] / "spikeinterface_gui" / "curation_data.json"
    )
    
    base_out = path_dict["sorted_data"] / f"{patient}-{session}-curated_analyzer.zarr"

    if not curation_filepath.exists():
        raise FileNotFoundError(
            f"Missing curation file: {curation_filepath}\n"
            "Run the GUI curation and click Save first."
        )

    out = base_out
    if out.exists():
        stem = out.name.replace(".zarr", "")
        parent = out.parent
        k = 2
        while True:
            candidate = parent / f"{stem}-v{k}.zarr"
            if not candidate.exists():
                out = candidate
                break
            k += 1

    with open(curation_filepath, "r") as f:
        curation_dict = json.load(f)

    sorting_analyzer = si.load_sorting_analyzer(path_dict["analyzer_folder"])
    clean_analyzer = apply_curation(sorting_analyzer, curation_dict_or_model=curation_dict, merging_mode = "hard")
    saved = clean_analyzer.save_as(format="zarr", folder=out)

    print(f"Wrote: {out}")
    return saved



def generate_figures(analyzer_obj, path_dict, close_figures: bool = True):
    """
    Generate per-unit summary figures and save them to disk.

    Note: In Jupyter, matplotlib will auto-render any open figures created in a cell.
    Setting close_figures=True prevents notebook rendering while still saving files.
    """
    import matplotlib.pyplot as plt
    import spikeinterface.widgets as sw

    fig_dir = path_dict["sorted_data"] / "figs"
    fig_dir.mkdir(parents = True, exist_ok = True)

    sorting_obj = analyzer_obj.sorting
    unit_ids = sorting_obj.unit_ids

    for id in unit_ids:
        w = sw.plot_unit_summary(
            analyzer_obj,
            unit_id=id,
            backend="matplotlib",
            ncols=5,
            figsize=(16, 9),
            figtitle=f"Unit summary: {id}"
            )

        w.figure.savefig(
            Path(fig_dir, f"{id}-figure.png")
        )

        if close_figures:
            plt.close(w.figure)
