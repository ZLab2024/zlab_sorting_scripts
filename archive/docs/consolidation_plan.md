# Consolidating the lab sorting workflow

Investigation: November 6, 2026. The original design proposal follows.
The runner is now implemented: see [implementation status](consolidation_status.md)
and the supported [API guide](api.md). Proposed interface sketches below are
historical; the API guide describes the exact current behavior.

## Recommendation

Make `zlab_sorting_script` the canonical home for recording loading, probe and
wiring definitions, sorting, analyzer preparation, automated curation, and unit
inspection. Keep the import name `sorting_scripts` so existing notebooks keep
working. Add a small configuration-driven runner over the existing functions.
Move reusable functions into this package; migrate the other projects to consume
its saved results and public API.

Keep scientific experiments separate from the sorting engine. CSC/MED validation
and MemSeg behavioral analysis can stay in their current repositories. They
should depend on central sorting/inspection code, rather than copy it or reach
into sibling checkout paths. This centralizes the daily workflow without making
every sorting installation depend on behavioral MAT parsing and reporting.

## Source inventory and ownership

Inventoried 40 non-test Python files under the four projects' `src` trees
(6,525 lines), plus tests, packaging, probe files, relevant notebooks, validation
experiments/scripts, the MemSeg viewer, and the oSort workflow entry points.
Vendored oSort MATLAB internals were not exhaustively audited. Archived result
snapshots are evidence, not migration sources.

| Project | Existing implementation | Proposed ownership |
| --- | --- | --- |
| Z-Lab: 11 source files / 2,164 lines | `zsort.py`: Intan chunk loading, KS4, analyzer, GUI, manual curation, figures. `kilosort_runtime.py`: guarded execution/checkpoint resume. `auto_curate.py` and `model_labeling.py`: cleanup, merges, metrics, labels and audit. Ensemble/snippet GUI modules. | Central engine; preserve these implementations and their regression tests. |
| Sort_BF: 3 / 599 | `med_utils.py`: channel inventory, eager MED reading, serializable Neo-backed MED extractor, independent-wire and virtual BF8 grouping. `circular_probe.py`: circular bundle builder. Notebook: actual MountainSort5 recipe. | Move MED support into optional I/O module, probe builders into probe registry, notebook recipe into a named sorting profile. Consolidate duplicate circular builders. |
| DHN_Validation: 18 / 2,314 | `all_unit_merge.py`: complete-link merge proposals, whole-group refractory checks, exact event-multiset lineage. `legacy_curation.py`: oSort MAT import/sample-grid conversion and recording reconstruction. Comparison, prediction filtering, confidence audits, tables and reporting. | Extract generic oSort import, lineage checks and single-wire merge policy. Keep condition-specific experiments, reporting and historical reconstruction here. |
| memseg-dbs: 8 / 1,448, plus root viewer | `memseg_analysis`: timing/trials, counts, screening, prediction, figures, shortlists and provenance. `analyzer_viewer.py`: stored waveform/metrics inspection and GUI bridge. | Move generic analyzer opening, ensemble data, metrics, summaries and browsing into central inspection modules. Keep task clocks, PSTHs, statistics and response selection in MemSeg. |
| custom_sorter | One short handwritten notebook with synthetic data, filtering, whitening and peak detection; later stages are notes. | Preserve as an experimental design/example. It is not a complete clustering backend to migrate. |
| osort_sorting | MATLAB oSort, MED/CSC adapters, paired validation workflow and shell commands. | Add an optional external adapter/import path after the Python workflows work. Preserve MATLAB behavior and its own runtime dependencies. |

Other relevant reusable code is outside `src`: `experiments/cross_channel_units.py`
(bundle overlap evidence), `experiments/agreement.py`, deterministic-preprocessing
experiments, and `comp_fidelity/med_sorter_comparison.py` (oSort reading, waveform
statistics and comparison). Extract only parameterized primitives; avoid importing
their historical output roots and report-building side effects into the engine.

## Concrete integration gaps

1. `zsort.set_paths()` and `load_recording()` assume Intan `.rhd` input. MED and
   Neuralynx need separate discovery/reader adapters, plus an output directory
   independent of the raw input directory.
2. `zsort.set_probe()` uses `probegroup.probes[0]`, so it does not support a
   multi-probe group. It also returns early if any probe is already attached,
   without checking that it matches the requested definition.
3. Its contact-count check happens after attachment. In the installed SI 0.103.0,
   a synthetic 16-channel recording attached to an eight-contact wired probe
   became eight channels. The post-attachment count then equals eight and cannot
   detect the original channel loss. Validate coverage and mapping before attaching.
4. `Custom_Probes/dummy8_probe.json` has one eight-contact probe with no
   `device_channel_indices`. Attaching it in a synthetic check raised
   `AssertionError: Probe must have device_channel_indices`.
5. BF grouping already exists, but physical layout and sorting isolation are
   different choices. `attach_independent_probe()` creates one multi-contact
   probe and overwrites `group` per channel; it is not literally a group of eight
   one-contact probes. The virtual BF8 builder does create one probe per bundle.
6. `sort_independently()` defaults to deleting its destination, whereas Z-Lab
   preserves unreadable existing results. It checks for a `group` property but
   does not verify that each channel has a distinct group. Both need harmonization.
7. Z-Lab hardcodes KS4 and preprocessing. The BF notebook has the useful MS5
   recipe: 300–6000 Hz float32 filtering, seeded local whitening, scheme 2,
   explicit radii, and sorter filtering/whitening disabled. Avoid unintentional
   double preprocessing. Independent groups must be split before any operation
   that mixes channels, including whitening or common reference.
8. `zsort.analyze()` unconditionally computes monopolar unit locations. Single
   contacts and virtual BF circles need a geometry-aware extension policy;
   virtual coordinates must not be reported as anatomical localization.
9. Z-Lab reuses readable sorter/analyzer folders without checking changed input,
   wiring or settings. MemSeg's frozen configuration, fingerprints, writer lock,
   explicit completion and conservative resume are a better model for the runner.
10. `wrapper.py` is a SAW callable, not a CLI. Its `all` step expects saved manual
    GUI decisions; it does not implement unattended auto-curation. Make it a
    thin adapter to the same runner used by notebooks and CLI.
11. MemSeg's generic viewer is a root-level script dynamically imported by
    `figures.py`. It duplicates waveform helpers when the GUI import fails.
    Put shared waveform/scaling helpers in a module that has no GUI dependency.
12. MED support currently imports `dhn_med_py` at module load, temporarily patches
    its session class during Neo header parsing, and registers a custom RawIO.
    Keep this isolated, test serialization in a fresh process and restoration
    after failure, and avoid concurrent header parsing around process-global hooks.
    Validate per-channel gains, streams and discontinuities. Do not adopt the
    eager reader's first-channel scalar gain as a general multi-channel contract.

Some notebooks are exploratory or empty: `notebooks/sort_csc.ipynb` in Z-Lab and
`notebooks/memseg_dbs.ipynb` in MemSeg could not be parsed as JSON. They should
not become supported entry points. `create_custom_probe.py` also writes a
machine-specific path at import time; replace it with a callable generator/CLI.

## Canonical probes and grouping

Use a `ProbeGroup` internally even when there is only one physical probe. Store
geometry, recording channel IDs, positional device wiring, bundle membership,
sorting groups, and physical/virtual status explicitly. Never infer wiring from
matching channel counts alone or automatically group each consecutive eight
channels without an explicit mapping/preset declaration.

| Proposed preset | ProbeGroup representation | Sorting behavior |
| --- | --- | --- |
| `deeparray128` | One 128-contact probe, using the existing P1925-127 / H1925-116 definition | Joint multichannel sorting; preserve manufacturer status and require explicit exclusions/remapping. |
| `bf_dummy8` | One eight-contact virtual circular probe per declared bundle | Joint sorting within each bundle, separate sorting between bundles. |
| `bf_single8` | Eight one-contact probes for one eight-wire bundle; repeated explicitly for additional bundles | One independent sorting job per wire, with bundle identity retained separately. |
| `custom` | User-supplied ProbeInterface group plus explicit channel map | Configured grouping validated against the complete map. |

`bf_single8` is my interpretation of “single probe ... canonically as a probe
group of 8”: eight independent one-contact probes. Keep this name and structural
definition explicit so it cannot be confused with one eight-contact probe.

Validate unique/in-range device indices, complete intended channel coverage,
channel-ID/order correspondence, group membership, and explicit exclusions
before calling `set_probegroup()`. Confirm the returned recording preserves the
expected IDs, order, sample counts and gains. Replacing a probe must be explicit.
Bundle and source-channel provenance should survive aggregate unit-ID renaming.

## Target package and everyday interface

Grow `sorting_scripts` with these modules, keeping `zsort` as a compatibility
facade rather than rewriting the package all at once:

```text
sorting_scripts/
  config.py, pipeline.py, cli.py, provenance.py
  io/          intan.py, neuralynx.py, med.py, osort.py
  probes/      registry.py, geometry.py, wiring.py, resources/
  preprocessing.py
  backends/    kilosort4.py, mountainsort5.py
  analysis.py, inspection.py, waveform_data.py
  merging.py, lineage.py
  auto_curate.py, model_labeling.py, kilosort_runtime.py
  ensemble_gui.py, waveform_ensemble.py, spike_snippets.py
  zsort.py
```

Package probe resources so installed use does not depend on finding the checkout
or `Custom_Probes` relative to a notebook. Keep optional GUI, MED, MS5, KS4 and
model dependencies distinct. Retain SI 0.103.0, PI 0.3.2, GUI 0.11.0 and KS4
4.1.1 initially; test and pin MS5/MED versions before declaring their extras.
Use Python 3.12 as the first tested target. Keep MemSeg's locked environment
separate and preserve sklearn 1.4.2 compatibility for the existing models.

Proposed commands, **not available yet**:

```bash
zsort validate --config session.toml
zsort run --config session.toml
zsort status --run /data/sorting/run-id
zsort resume --run /data/sorting/run-id
zsort inspect --analyzer /data/sorting/run-id/curation/analyzer
```

Proposed configuration shape:

```toml
[input]
format = "med"                 # intan | neuralynx | med
path = "/data/session.medd"
stream_id = "0"                # chosen after stream inventory
password_env = "MED_PASSWORD"  # resolve at runtime; redact from outputs

[probe]
preset = "bf_single8"
channel_map = "channels.csv"   # source channel ID, contact, probe, bundle, group

[sorting]
backend = "mountainsort5"
profile = "bf_single_wire"     # proposed, requires acceptance validation

[curation]
policy = "single_wire_merge_preserve_events"
model_labeling = false

[output]
root = "/data/sorting"
```

Use the same `run(config)` API from a short notebook. Backend sorting includes
detection and clustering; automatic merging is a later stage, not a replacement
for clustering. Existing oSort clusters should enter through an explicit import
mode, bypassing fresh sorting without implying a new waveform reclustering.

Do not merge curation policies into one ambiguous “automatic” setting. Offer
named policies: labels-only (no unit/event changes), current cleanup/merge,
single-wire merge preserving all candidate events, and explicitly configured
quality/model rejection. The DHN complete-link policy needs parameterization
(currently integer IDs, fixed source paths, one-wire assumptions and fixed rate)
before general reuse. Cross-bundle merges must be disallowed; any cross-wire
deduplication must be a separately configured and audited operation.

Each run should have frozen redacted config, input/channel/probe/settings identity,
code/environment versions, raw and curated sortings, analyzers, decision/lineage
tables, logs and stage status. Record source chunk/sample offsets and gaps;
preserve sample-grid conversions and MED polarity as explicit input properties.
Choose a documented input fingerprint policy for large raw files; hashes may
be streamed/cached, but size/mtime alone must not be called content identity.
Reject stale cache reuse. Distinguish stage resume from KS4's specialized
pre-clustering checkpoint resume. Inspection must never silently compute missing
extensions or start sorting/curation.

MemSeg currently also expects `curation.json` beside the analyzer, saved quality
labels matching its thresholds, and the original single-segment sample clock.
Preserve that contract initially, then introduce a versioned result manifest
that downstream consumers can validate rather than infer paths and thresholds.

## Migration order and completion criteria

1. **Probe registry and channel contract.** Implement/test the three presets,
   multi-probe attachment, package resources, explicit wiring, and preservation
   checks. This resolves the immediate dummy/single/DeepArray usability problem.
2. **I/O and named backend profiles.** Extract the existing Intan/MED paths, add
   Neuralynx loading, and move the notebook MS5 settings into configuration.
   Keep KS4 guards/checkpoints. Test per-group preprocessing and persistence.
3. **One runner and notebook.** Add validate/run/status, unique output roots,
   manifests, backend-specific resume and explicit curation policies. Make SAW
   and a single parameter-cell notebook call this API.
4. **Shared analysis/inspection and merge tools.** Extract MemSeg's generic viewer
   and DHN's reusable merge/import/lineage functions, with compatibility wrappers
   at their old paths. Leave task-specific response plotting in MemSeg.
5. **Retire duplicate workflow code.** Replace BF and project notebooks with short
   central API examples; label old notebooks historical after equivalent outputs
   have been checked. Add optional MATLAB execution only if everyday oSort launch
   is needed; importing its existing results can come first.

Acceptance tests should establish: exact synthetic channel/probe/group mapping;
unchanged samples/gains/order through attachment and load; no cross-group
whitening or merges; MED fresh-process serialization; stale-cache rejection;
preserved failed outputs; known oSort timestamp-to-sample fixtures; event-multiset
lineage for preservation merges; and saved analyzer inspection without writes or
recomputation. Then separately run small representative Intan+DeepArray,
MED+BF8, and Neuralynx+independent-wire acceptance recordings. Synthetic tests
cannot validate physical wiring or biological cluster quality.

## Evidence and validation scope

Read-only source investigation, notebook code inventory, and synthetic probe
checks used the existing Z-Lab environment (SI 0.103.0 / PI 0.3.2). Verified
`run_sorter_by_property`'s installed signature and the two attachment behaviors
above. No real sorting, classifier downloads, full test-suite rerun, environment
changes, or modifications to scientific outputs were performed for this proposal.

The proposed backend interface follows the versioned
[SpikeInterface 0.103.0 sorter interface](https://spikeinterface.readthedocs.io/en/0.103.0/modules/sorters.html).
Probe APIs must be checked against installed PI 0.3.2, not assumed from rolling
documentation. Local `agent_reference.md` remains the compatibility reference.
