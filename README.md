# Z-Lab sorting

One installable Python package for loading recordings, generating and wiring
probes, sorting/clustering, preparing analyzers, curation and stored-unit inspection.
Import it as **`sorting_scripts`** from any project; no sibling checkout is required.

## Start here

Use Python **3.12**. The supported dependency baseline is SpikeInterface 0.103.0,
ProbeInterface 0.3.2, optional Kilosort 4.1.1 and GUI 0.11.0. From this repository:

```bash
python -m pip install -e '.[mountainsort,med,notebook]'
python -m pip check
```

For KS4 add `.[sorter]` after configuring the appropriate CUDA/PyTorch installation;
for interactive curation add `.[gui]`. [Environment setup](docs/environment.md)
explains CPU/GPU and optional model environments. Imports never install packages,
start sorting, download models or open a GUI. A base install is `pip install -e .`.

1. Open [central_sorting.ipynb](notebooks/central_sorting.ipynb).
2. Copy a [session template](examples/) and edit input/output paths and probe wiring.
3. Validate the configuration, review channel IDs/groups, then run it:

```bash
python -m sorting_scripts validate --config session.toml
python -m sorting_scripts run --config session.toml
```

The same commands are installed as `zsort`. Every run creates a unique directory;
use the returned manifest's `outputs.analyzer` rather than guessing a folder name.

## Supported inputs and sorting

| Input | How to load | Notes |
| --- | --- | --- |
| Intan RHD | `format='intan'` | Single file or naturally ordered compatible chunks; lazy concatenation. |
| Neuralynx CSC | `format='neuralynx'` | Native channel IDs, scaling and segments. |
| MED | `format='med'` | Optional corrupt-safe Neo adapter; password from an environment variable. |
| Saved SI binary recording | `format='binary_folder'` | Reload an already cached recording. |
| Raw interleaved binary | `format='binary'` | Explicit dtype, channel count and sample rate required. |
| Other installed SI readers | `format='spikeinterface', extractor='spikeglx'` | Explicit reader options; also supports installed readers such as Open Ephys. Optional format dependencies must be installed. |
| Existing oSort MAT results | `sorting.backend='osort_import'` | Import clusters on an explicit sample grid; no fresh clustering. |

The runner supports **KS4** and **MountainSort5** with named preprocessing profiles.
It splits sorting groups before whitening, sorting and merging. Other acquisition
formats can use these same backends once loaded; backend compatibility with a
particular probe/data type still needs validation. It requires one nonempty
continuous segment and a sample rate above 12 kHz for the current 300–6000 Hz
profiles. It never infers/fills recording gaps.

## Use from another repository

Install this package into that repository's environment (or install a built wheel):

```bash
python -m pip install -e /path/to/zlab_sorting_script
```

Then use normal imports, without editing `sys.path` or changing working directory:

```python
from sorting_scripts import load_recording, run, validate, status
from sorting_scripts.probes import attach_probe, get_probe, make_deeparray128, save_probe
from sorting_scripts.inspection import open_analyzer, summary_figure

recording = load_recording('/data/session/raw', format='intan', stream_id='0')
recording = attach_probe(recording, 'deeparray128')  # verify acquisition wiring first

# Or run the complete session using one configuration:
validation = validate('/data/config/session.toml')
run_dir = run('/data/config/session.toml')
manifest = status(run_dir)
analyzer = open_analyzer(run_dir / manifest['outputs']['analyzer'])
```

The low-level loader/probe APIs do not sort. The complete runner reloads the input
specified by its config; it does not implicitly use an unrelated `recording`
variable. See [cross-project integration](docs/integration.md) for raw binary,
additional readers, probes, manual curation and installation examples.

## Probes

| Preset | Structure and sorting groups |
| --- | --- |
| `deeparray128` | Physical DA128L P1925-127/H1925-116; one 128-contact probe. |
| `bf_dummy8` | One virtual eight-contact circle per declared consecutive bundle; joint sorting within each bundle. |
| `bf_single8` | Eight one-contact probes per bundle; independent wire sorting. |
| `neuronexus16` | Existing wired 16-contact linear definition. |

`get_probe()` loads packaged presets, custom JSON, PRB, `Probe` or `ProbeGroup`.
`make_bf_group()`, `make_linear_probe()` and `make_deeparray128()` generate
geometry in memory; `save_probe()` writes a new JSON without overwriting files.
Packaged definitions work from wheels, outside the checkout.

```bash
zsort probe --preset bf_single8 --channels 24 --output /data/probes/three_bundles.json
zsort streams --format intan --input /data/session/raw
```

Full device coverage, uniqueness and channel mapping are checked before attachment.
Acquisition IDs/order/gains are preserved. Existing probes require explicit
replacement. Geometry does not prove wiring. DeepArray open-contact annotations
do not remove contacts automatically; virtual BF locations are not anatomy.

## Results, curation and recovery

Runs save input/code/environment identities, recording cache, raw and curated
sortings, analyzers, unit maps, decision tables and logs. Raw recordings are never
rewritten. Output must be outside the input tree. Caching costs disk space;
analyzers can retain absolute source paths and are not guaranteed movable archives.

Curation defaults to **`labels_only`**, preserving candidate units/events with
models off. `none`, `cleanup_merge` and `single_wire_merge_preserve_events` are
explicit alternatives; cleanup/merging/rejection have different effects. Model
labels and automatic merge proposals do not establish neuronal identity.

```bash
zsort status --run /data/sorting_runs/RUN
zsort resume --run /data/sorting_runs/RUN
zsort inspect --analyzer /data/sorting_runs/RUN/results_ID/analyzer
```

Resume requires matching config, input content, source and scientific environment.
Completed artifacts are verified; failed attempts are retained and retried in new
folders. A writer lock prevents concurrent writes. KS4 checkpoint recovery is a
separate `resume-clustering` command. Stored inspection never computes missing
extensions. Manual GUI curation requires an explicit save and application step.

## Navigation

- [API reference and source tree](docs/api.md)
- [Cross-project integration and input/probe recipes](docs/integration.md)
- [Environment setup](docs/environment.md)
- [Curation](docs/auto_curation.md), [model labeling](docs/model_labeling_audit.md)
- [KS4 recovery](docs/sorting_recovery.md), [GUI views](docs/waveform_ensemble.md)
- [Current audit/validation](docs/maintenance_audit.md)
- [Agent/maintainer instructions](AGENTS.md)
- [Archive index and provenance](archive/README.md)

Historical notebooks, plans and workstation notes are archived with content hashes.
The old `zsort` and Box module names remain compatibility imports under `legacy/`;
new code uses the typed APIs. Sibling BF/DHN/MemSeg research evidence stays in its
original repository; generic sorting utilities are here.

## Validation

```bash
python -m pip check
MPLBACKEND=Agg OPENBLAS_NUM_THREADS=1 python -m unittest discover -s src/sorting_scripts/tests -v
python -m unittest discover -s Custom_Probes -p 'test_*.py' -v
```

Synthetic tests cover loaders, wiring, grouping, lineage, caching/resume, inspection
and packaging contracts. `examples/synthetic_smoke.py` is an opt-in real CPU MS5
run on synthetic data. GPU execution, native format decoding, physical wiring and
scientific quality need separate recording-specific acceptance; see the audit for
what was actually exercised. Do not commit recordings, passwords or patient outputs.
