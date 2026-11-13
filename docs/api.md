# Sorting API

For installation and current navigation start with [README.md](../README.md).
For additional readers, generation and other-repo imports see
[integration recipes](integration.md).

The supported everyday interface is `sorting_scripts.run(config)` or
`python -m sorting_scripts run --config session.toml`. The package is organized
by operation. Loading, probing, inspection and configuration validation never
start a sorter. Every public function below also has a Python docstring.

## Install and first run

Use the existing compatible sorting environment or create a separate Python 3.12
venv following [environment setup](environment.md). From the checkout:

```bash
python -m pip install --no-deps --no-build-isolation -e .
# Optional packages, only in the environment where needed:
python -m pip install -e '.[mountainsort,med]'   # BF + MED workflow
python -m pip install -e '.[sorter,gui,notebook]' # KS4 + browser workflow
```

The editable reinstall registers `zsort`; `python -m sorting_scripts` also works
without refreshing the console entry point. Optional MS5 is pinned at 0.5.8;
its preprocessing contract is described by the
[upstream release](https://pypi.org/project/mountainsort5/0.5.8/).
MED uses dhn-med-py 2.0.6 and Neo 0.14.4. SI remains 0.103.0 and PI 0.3.2.
KS4 remains 4.1.1. No optional backend is installed or downloaded by importing
this package. UnitRefine needs the separate compatibility constraints described
in [model labeling](model_labeling_audit.md).

Copy an [example configuration](../examples/), edit paths and wiring, then:

```bash
zsort validate --config session.toml
zsort run --config session.toml
zsort status --run /data/sorting_runs/sorting_RUN_ID
zsort inspect --analyzer /data/sorting_runs/sorting_RUN_ID/results_ID/analyzer
zsort inspect --analyzer /data/sorting_runs/sorting_RUN_ID/results_ID/analyzer \
  --unit 0 --output /data/unit_0.png
```

`notebooks/central_sorting.ipynb` is the clean notebook entry point. Use the
`outputs.analyzer` path from the manifest; attempt/result suffixes are unique,
not fixed folder names. The oSort example intentionally illustrates one entry:
complete its list for every selected channel before validating it.

## Source tree

```text
src/sorting_scripts/
  __init__.py, __main__.py       lazy public API and module command
  config.py                     strict session config and relative path resolution
  pipeline.py                   validation, group stages, resume and aggregation
  provenance.py                 content hashes, atomic JSON and writer locks
  io/
    intan.py                    naturally ordered, validated lazy RHD concatenation
    neuralynx.py                native CSC/Neuralynx extractor
    med.py                      corrupt-safe, serializable optional MED adapter
    osort.py                    MAT cluster import and sample-grid conversion
    generic.py                  explicit raw binary and installed SI readers
  probes/
    geometry.py                 virtual BF builders
    deeparray.py, generation.py  canonical in-memory generation and JSON export
    registry.py                 named presets and packaged physical JSONs
    wiring.py                   explicit maps and complete-coverage attachment
    resources/                  DeepArray128, dummy8 and Neuronexus JSON
  preprocessing.py              backend profiles applied within each group
  backends/
    kilosort4.py                 pinned runtime guards and checkpoint creation
    mountainsort5.py             BF scheme-2 recipe
  analysis.py                   group-aware waveforms, templates and QC
  curation/                     explicit policy dispatcher
  merging.py, lineage.py        single-wire proposals and exact event conservation
  inspection/stored.py          stored evidence; no GUI dependency
  waveform_data.py              shared sparse-channel/time/amplitude helpers
  gui/                          canonical optional interactive launcher
  legacy/                       isolated historical workflows and cloud helpers
  auto_curate.py                 retained tested curation engine
  model_labeling.py              retained tested classifier adapter
  kilosort_runtime.py            retained KS4 recovery implementation
  ensemble_gui.py                retained GUI registry/session integration
  waveform_ensemble.py           retained Panel view
  spike_snippets.py              retained Panel view
  zsort.py                      compatibility alias to legacy.zsort
  get_file.py                    legacy/shared RHD discovery
  box_managment.py               optional legacy Box tools
  create_custom_probe.py         compatibility generation wrapper
  tests/                        synthetic regression and integration tests
```

The existing curation/GUI engines retain their module paths for compatibility
with active notebooks and installed plugins. New operations use the typed module
families above. Archived evidence and task-specific analyses are not imported.

## Session APIs

| API | Return / behavior |
| --- | --- |
| `load_config(path_or_dict)` from `sorting_scripts.config` | Normalized plain dict; JSON or TOML; unknown fields fail. File-relative paths resolve against that file, mappings against the current directory. |
| `validate(config, check_backend=True)` | Header/wiring/profile/group summary. Checks backend availability by default; set false for read-only review without installed sorters. Writes nothing; no model loading. |
| `run(config)` | Absolute new run directory. Caches recording, sorts groups, applies policy, saves raw/final sortings and final analyzer. |
| `run(resume=run_dir)` | Resume failed/interrupted work only when config, full input hashes, source and runtime match. Finished groups are verified and reused. |
| `status(run_dir)` | Manifest dict without opening inputs or recomputing anything. |

```python
from sorting_scripts import validate, run, status

summary = validate('/data/config/session.toml')
print(summary['groups'])
run_dir = run('/data/config/session.toml')
result = status(run_dir)
analyzer_path = run_dir / result['outputs']['analyzer']
```

The first runner supports **one continuous segment**, sequential groups and
`job.n_jobs=1`. It rejects discontinuities represented as multiple segments;
Intan concatenation still does not infer wall-clock gaps. It caches the selected
recording as a binary folder inside the run. This costs disk space and provides
stable analyzer inputs. Moving a run does not guarantee reference portability.

Run outputs include `config.json`, `identity.json`, `manifest.json`, `run.log`,
a recording cache, immutable group attempt folders, and a `results_ID/` folder
with raw/final sortings, global unit maps, curation description and an analyzer.
An all-empty result has saved empty sortings/maps and no final analyzer.

Each final unit has `sorting_group`, `bundle`, and `source_channel_ids`
properties. Global unit IDs are deterministic sequential integers in group/unit
order. `raw_unit_map.csv` and `unit_map.csv` relate them to local group IDs;
curation decisions/lineage live in that group's successful attempt directory.
Models and thresholds are not inferred from historical datasets.

## Configuration reference

| Section | Fields |
| --- | --- |
| `input` | Required `format` (`intan`, `neuralynx`, `med`, `binary_folder`, `binary`, `spikeinterface`) and `path`; optional `stream_id`, `sampling_frequency` (MED rate check), `password_env` (default `MED_PASSWORD`), `channel_ids` (explicit subset in desired acquisition order), `extractor`, `reader_kwargs`, `path_argument` for the generic/binary adapters. |
| `probe` | `preset` (default `bf_single8`, or JSON path), optional `channel_map` CSV, `replace_existing=false`. |
| `sorting` | `backend`, matching `profile`, `params={}`, `seed=0`, `osort=[]` import entries. |
| `curation` | `policy` (default `labels_only`) and `options={}` for `AutoCurationConfig` fields in labels/cleanup modes. |
| `output` | Required `root`, outside the raw input tree. New run directories are always unique. |
| `job` | `n_jobs=1`. Parallel groups and process-global MED/KS4 hooks are intentionally not combined. |

`sorting.params` cannot override recording/output/overwrite/filter/whiten controls.
The MS5 recipe performs filtering and whitening outside the backend; KS4 performs
its own internal whitening after external bandpass filtering. This KS4 profile is
explicitly different from the legacy `zsort.sort()` external-whitening recipe;
old notebooks retain their existing behavior. New profiles require representative
recording validation before scientific equivalence claims.

## Loaders and existing sorting imports

```python
from sorting_scripts.io import load_recording
rec = load_recording('/data/session/raw', format='intan', stream_id='0')
rec = load_recording('/data/session/micros', format='neuralynx')
# Set MED_PASSWORD in the current environment before opening/reloading:
rec = load_recording('/data/session.medd', format='med',
                     password_env='MED_PASSWORD', stream_id='0',
                     sampling_frequency=32000)
```

MED deactivates name/directory-mismatched channels before Neo parses their
headers. It retains per-channel scaling through Neo, rather than adopting one
channel's gain for all traces. The password value is excluded from serialized
extractor kwargs; the same environment-variable name must resolve on reload.
The optional adapter temporarily patches the MED session class under a local
lock while parsing. External code bypassing this adapter must not concurrently
patch the same class.

`io.osort.load_osort(path, sampling_frequency=..., record_timestamps_us=...,
num_samples=...)` reads eligible `useNegative` clusters with original times and
multiplicity. Supply the retained CSC block-start grid, or `start_time_us` for a
verified continuous grid. No historical initial-block skip, MED polarity flip,
rounding or microvolt conversion is implicit. `frames_from_times` rejects gaps,
nonmonotone grids and off-grid events. The runner's oSort mode requires one MAT
entry per independent channel and a `.npy` block grid or explicit origin.

## Probes and wiring

| Preset | Contacts and grouping |
| --- | --- |
| `deeparray128` | Existing physical P1925-127/H1925-116, one 128-contact probe. Manufacturer annotations retained; open contacts are not removed automatically. |
| `bf_dummy8` | Virtual eight-contact circle per consecutive bundle; one sorting group per bundle. |
| `bf_single8` | Eight separate one-contact probes per bundle; one sorting group per wire. |
| `neuronexus16` | Existing wired 16-contact physical linear definition. |
| JSON/PRB path / `Probe` / `ProbeGroup` | Custom geometry; complete explicit device wiring or channel map required. |

```python
from sorting_scripts.probes import get_probe, attach_probe, read_channel_map
pg = get_probe('bf_single8', n_channels=24)  # 24 one-contact probes, three bundles
rec = attach_probe(rec, pg, channel_ids=read_channel_map('channels.csv'))
```

`channel_ids` lists source IDs in flattened probe/contact order. The CSV has
exactly `contact_index,channel_id`, with indices 0..N-1. Recording IDs/order,
traces and gains are preserved. Full coverage is checked **before** attachment.
An already attached probe requires `replace=True` (or config `replace_existing`).
Explicitly subset recordings and supply matching custom geometry when excluding
channels; the library does not invent wiring for a subset DeepArray. Virtual
coordinates are GUI/sorting aids, never anatomical localization estimates.

## Backends, analysis and curation

| Profile | Backend / preprocessing |
| --- | --- |
| `deeparray_ks4` | `kilosort4`; 300–6000 Hz float32 bandpass, internal KS4 whitening, guarded checkpoints. |
| `bf_bundle_ms5` | `mountainsort5`; eight-channel isolated groups, seeded local whitening, scheme 2, 110 µm virtual neighborhood. |
| `bf_single_wire` | `mountainsort5`; same recipe applied to each single wire independently. |
| `osort_import` | `osort_import`; existing spikes imported, no fresh detection/clustering. |

`preprocessing.preprocess(recording, profile, seed=0)` and
`backends.sort(recording, folder, backend=..., profile=..., params={})` are
lower-level APIs: callers must isolate groups themselves. The runner always
splits **before** whitening and curation. KS4 checkpoints contain trusted local
Torch serialization; recover explicitly with `zsort resume-clustering
--checkpoint PATH --output NEW_FOLDER`. Ordinary `resume` retries incomplete
group attempts and does not implicitly trust/load a checkpoint.

`analysis.prepare_analyzer(recording, sorting, folder, seed=0,
virtual_geometry=False, n_jobs=1)` writes a new analyzer with seeded stored
waveforms (-1/+2 ms), average/std templates, noise, correlograms, amplitude and
quality extensions. Global analyzers use each unit's sorting group as their
waveform sparsity mask. Virtual/small geometries use center of mass for display.
Waveforms come from filtered, unwhitened traces.

| Policy | Meaning |
| --- | --- |
| `none` | Save/analyze backend output without curation. |
| `labels_only` | Save threshold labels; no duplicate cleanup, redundancy removal, merges or rejection. Models default off. |
| `cleanup_merge` | Existing AutoCurator cleanup and merges; potentially changes events/IDs. Filtering remains explicitly configured. |
| `single_wire_merge_preserve_events` | Fixed DHN complete-link proposal and uncensored whole-group refractory checks on each wire; all candidate events retained. No model gates/rejection. |

`curation.apply_policy(analyzer, folder, policy=..., options={})` runs one group.
`merging.propose_merges(analyzer)` exposes proposal evidence.
`merging.merge_preserving_events(analyzer, folder)` saves sorting, unit/event
lineage and pair/group checks. This policy currently requires integer local unit
IDs and one channel/segment. `lineage.verify_lineage(before, after, mapping)`
checks exact spike multisets across every segment, including duplicates.
See [automated curation](auto_curation.md) for full legacy configuration details.

## Inspect saved results

```python
from sorting_scripts.inspection import open_analyzer, ensemble_data, unit_metrics, summary_figure
analyzer = open_analyzer(analyzer_path)
data = ensemble_data(analyzer, 0, max_waveforms=500)
metrics = unit_metrics(analyzer, 0)
figure, data, metrics = summary_figure(analyzer, 0)
```

These functions reuse stored extensions; missing data raises rather than starting
extraction. Peak-channel selection respects sparse global channel indices;
waveforms retain alignment and amplitude units, with deterministic subsampling.
`selected_units(analyzer, good_only=True)` requires saved quality labels and never
silently falls back to all units. `inspect_analyzer(path, unit_id=..., output=...)`
exports a new PNG outside the analyzer without modifying its files.

For interactive curation use `sorting_scripts.gui.launch_curation_gui(analyzer)`.
That is an explicit interactive operation and may follow upstream GUI extension
requirements; the stored-only inspection API above never computes them. Behavioral
response panels/PSTHs stay in MemSeg and are not required for generic inspection.

## Compatibility and migration

`zsort` is now an alias of `sorting_scripts.legacy.zsort`, retaining the old
module import/patch behavior. New code uses the supported typed APIs.

`zsort.load_recording` delegates to `io.intan`. `zsort.set_probe` now validates
whole groups and refuses implicit replacement. Other existing `zsort` functions
retain behavior. SAW `wrapper.main` accepts `params['config']` and optional
`params['resume']` to use the shared runner; its legacy parameter contract remains.

The original BF/DHN/MemSeg research and preserved scientific runs remain intact.
Superseded notebooks in this repo are preserved byte-for-byte under `archive/notebooks/`.
New sorting notebooks should use the central runner. Downstream analyses can use
its `outputs.analyzer`, unit maps and inspection API without rerunning sorting.
The current MemSeg analysis has additional threshold/timing/curation contracts;
a new sorting manifest does not automatically certify those experimental inputs.

## Resume and validation limits

Input files are hashed in full, so validation of resume identity can be I/O-heavy
on large recordings. Resume also requires identical executable package source and
scientific package versions. Corrupt/missing completed artifacts fail closed.
An existing `.writer.lock` blocks another writer. Remove an abandoned lock only
after confirming its recorded PID has stopped. Partial attempts are preserved.

Synthetic tests cover probes, mapping, group isolation, importing, lineage,
analyzer reload, read-only inspection, locking, interrupted resume and stale
inputs. Real MED decoding, physical wiring, GPU execution, and biological cluster
quality require separate representative recording acceptance. See
[maintenance audit](maintenance_audit.md) for the actual execution scope.

## Additional public APIs

- `io.list_streams(path, format=..., ...)`: native IDs/names without sorting.
- `io.load_recording(..., format='binary', reader_kwargs=...)`: explicit raw binary.
- `io.load_recording(..., format='spikeinterface', extractor=..., reader_kwargs=..., path_argument=None)`: installed SI acquisition readers.
- `probes.make_deeparray128()`, `probes.make_linear_probe(...)`: in-memory generation.
- `probes.save_probe(probe_or_group_or_preset, output)`: export to a new JSON.
- `curation.apply_manual_curation(analyzer_or_path, decisions_or_json, output)`: explicit new Zarr output.
- `zsort probe --preset NAME --channels N --output NEW.json` and `zsort streams --format FORMAT --input PATH`: portable CLI utilities.

See [integration recipes](integration.md) for examples and path/credential rules.
