# Importing and extending the central package

The distribution name is `sorting-scripts`; Python imports use `sorting_scripts`.
Install it into the environment of each consuming project. A wheel/normal install
is independent of this checkout, while an editable install follows local edits.
Neither requires `Sort_BF`, `DHN_Validation` or `memseg-dbs` to be on `sys.path`.

```bash
# Run with the consuming project's interpreter:
python -m pip install -e '/path/to/zlab_sorting_script[mountainsort,med]'
python -m pip check
```

Keep research-project lock files/environments separate. Resolve the documented
SI/PI/model constraints deliberately; do not upgrade a working environment just
to make an optional feature import. For a preconfigured compatible environment,
`pip install --no-deps --no-build-isolation -e /path/to/zlab_sorting_script`
refreshes only this package's registration. It does not install missing extras.

## Load native sources and inspect streams

```python
from sorting_scripts import load_recording
from sorting_scripts.io import list_streams

streams = list_streams('/data/session/raw', format='intan')
recording = load_recording('/data/session/raw', format='intan', stream_id='0')
recording = load_recording('/data/session/micros', format='neuralynx')
# Set the MED_PASSWORD environment variable locally before opening/reloading:
recording = load_recording('/data/session.medd', format='med',
                          password_env='MED_PASSWORD', stream_id='0')
```

Stream IDs are acquisition-specific; inspect before selecting. MED credentials
are resolved at open time and serialized as an environment-variable reference.
Native discontinuities remain segments. The pipeline rejects multiple segments
until an explicit continuous-clock policy has been chosen. Direct loader use is
still available for inspection of multisegment recordings.

## Raw binary

Dtype, channel count, byte layout and sampling rate are required knowledge;
file size alone does not establish them. Gains/offsets must reflect acquisition
units if microvolt output is desired.

```python
recording = load_recording(
    '/data/session/traces.raw', format='binary', sampling_frequency=30000,
    reader_kwargs={'dtype': 'int16', 'num_channels': 8,
                   'gain_to_uV': 0.195, 'offset_to_uV': 0.0})
```

Equivalent configuration:

```toml
[input]
format = "binary"
path = "/data/session/traces.raw"
sampling_frequency = 30000
[input.reader_kwargs]
dtype = "int16"
num_channels = 8
gain_to_uV = 0.195
offset_to_uV = 0.0

[probe]
preset = "bf_single8"
[sorting]
backend = "mountainsort5"
profile = "bf_single_wire"
[curation]
policy = "labels_only"
[output]
root = "/data/sorting_runs"
```

See `examples/raw_binary.toml`. A SpikeInterface binary cache uses
`format='binary_folder'`; this is different from a raw interleaved file.

## Other acquisition formats

The explicit `spikeinterface` adapter resolves only built-in `read_*` functions
from the installed `spikeinterface.extractors` module. It does not import arbitrary
modules. Reader-specific optional libraries still need to be installed.

```python
recording = load_recording('/data/imec_session', format='spikeinterface',
                          extractor='spikeglx', stream_id='imec0.ap')
recording = load_recording('/data/openephys', format='spikeinterface',
                          extractor='openephys', reader_kwargs={})
```

`input.extractor`, `input.reader_kwargs`, and optional `input.path_argument`
provide the equivalent config interface. The adapter inspects the reader's
signature and chooses `folder_path`, `dirname`, `file_path`, or `file_paths`.
For a reader with a different named source argument set `path_argument` explicitly.
Input paths cannot also be supplied in reader kwargs. Raw binary always uses
`read_binary`, not an arbitrary extractor.

Use absolute paths for additional files in direct Python calls. Config keys
ending in `_path`, `_file`, or `_folder` are resolved relative to the config;
existing absolute file/directory references in reader kwargs are fingerprinted.
Do not put passwords/tokens in kwargs: config rejects common credential keys.
The generic reader must return a Recording; sorting/analyzer loaders are separate.

A reader being callable does not certify real-device decoding or backend
suitability. Use a representative source fixture before treating a new format as
validated. The API is designed to extend acquisition coverage without copying
another project or changing the supported sorting profiles.

## Generate, load, wire and save probes

```python
from sorting_scripts.probes import (
    make_bf_group, make_linear_probe, make_deeparray128,
    get_probe, attach_probe, read_channel_map, save_probe,
)

physical = make_deeparray128()             # exact documented DA128L geometry
linear = make_linear_probe(16, pitch_um=50)
bundles = make_bf_group(24)                # 3 virtual eight-contact probes
single_wires = make_bf_group(24, independent=True)  # 24 one-contact probes
custom = get_probe('/data/probes/custom.json')     # or a trusted local .prb
save_probe(single_wires, '/data/probes/bf24.json')  # destination must be new

recording = attach_probe(recording, 'bf_single8',
                         channel_ids=read_channel_map('/data/channels.csv'))
```

The map lists source channel IDs in global contact order with CSV columns
`contact_index,channel_id`. Full coverage/uniqueness are checked before any
attachment can discard channels. Wire/bundle geometry is virtual; groups control
sorting isolation independently from plotting. Select channels deliberately
before attachment and use matching geometry. `replace=True` explicitly replaces
existing geometry. PRB is a Python-based format: load only trusted local files.
Use JSON for portable probe exchange.

The installed `zsort probe` CLI exports presets; it never replaces an existing
file. DeepArray and linear factories generate geometry in memory; no import-time
file writes occur. `Custom_Probes/` contains compatibility assets and tests;
packaged resources and `probes/` generators are canonical.

## Sort and inspect

```python
from sorting_scripts import validate, run, status
from sorting_scripts.inspection import open_analyzer, summary_figure

validation = validate('/data/config/session.toml')
run_dir = run('/data/config/session.toml')
manifest = status(run_dir)
if manifest['outputs']['analyzer'] is not None:
    analyzer = open_analyzer(run_dir / manifest['outputs']['analyzer'])
    figure, stored_waveforms, metrics = summary_figure(analyzer, analyzer.unit_ids[0])
```

For a custom in-memory Recording, explicitly save it to a new SI binary cache,
then point `input.format='binary_folder'` at that cache. For lower-level use,
`preprocessing.preprocess`, `backends.sort`, `analysis.prepare_analyzer`, and
`curation.apply_policy` are available. Their caller is responsible for isolating
sorting groups; use the runner when possible. Saved analyzers may contain source
paths; normal imports working anywhere does not imply data archives can be moved
without repairing references.

## Manual curation on any analyzer

```python
from sorting_scripts.gui import launch_curation_gui
from sorting_scripts.curation import apply_manual_curation

launch_curation_gui(analyzer)  # make decisions and explicitly click Save
curated = apply_manual_curation(
    analyzer, '/data/analyzer/spikeinterface_gui/curation_data.json',
    '/data/curated/new_analyzer.zarr')
```

The source may also be an analyzer path. Output must be new and outside the
source analyzer. This avoids legacy patient/session path assumptions and applies
hard merges against the attached recording. Stored-only inspection never starts
these operations implicitly.

## Migration map

| Original source | Canonical API | What remains separate |
| --- | --- | --- |
| Sort_BF MED helpers/circular probes/notebook recipe | `io.med`, `probes`, `bf_bundle_ms5` / `bf_single_wire` | Historical source/notebook retained for reproducibility. |
| DHN validation merge/import primitives | `io.osort`, `merging`, `lineage` | Dataset-specific reconstruction, comparisons, reports and preserved evidence. |
| MemSeg analyzer waveform/metric viewer | `inspection`, `waveform_data`, `gui` | Behavioral timing/trials/PSTHs/statistics; standalone legacy fallback. |
| Former `zsort` workflow | `run/validate/status`, typed modules | `legacy.zsort`, aliased at the original import path. |
| Former DeepArray script | `probes.make_deeparray128` | Small command wrapper and artifact tests in `Custom_Probes`. |
| MATLAB oSort workflow | `io.osort` for result import | External MATLAB execution remains in its source project. |

Archived notebooks/docs are indexed in `archive/README.md`; original bytes are
verified against its manifest. Do not run archived notebooks as the current
workflow. Their original relative paths and saved outputs have been preserved.
