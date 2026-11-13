# Consolidation implementation and validation

Implemented November 6, 2026. The design is in [consolidation_plan.md](consolidation_plan.md);
the supported interface and source map are in [api.md](api.md).

## Delivered

- Organized public modules for I/O, probes/wiring, preprocessing, backends,
  analysis, curation, lineage, stored inspection, GUI access and run provenance.
- Intan loading extracted from the tested legacy path; Neuralynx dispatch;
  optional corrupt-safe MED adapter with environment-based password serialization.
- Packaged DeepArray128/Neuronexus/dummy resources; BF bundle and eight-single-
  contact ProbeGroup builders. Full wiring coverage is validated before attaching,
  and acquisition channel IDs/order/gains remain intact. The legacy dummy JSON
  now also has device indices. Existing-probe replacement is explicit.
- Named KS4 and BF MountainSort5 profiles, with groups split before preprocessing
  and curation. KS4 guards/checkpoint implementation retained. New KS4 preprocessing
  is explicitly documented separately from legacy external whitening.
- Existing oSort MAT import with explicit sample-grid mapping; DHN complete-link
  single-wire merging and event-multiset lineage extracted without fixed archives.
- Strict TOML/JSON configuration; validate/run/status/resume/inspect commands;
  content/version/source identities, writer lock, unique immutable attempts,
  verified reuse of completed groups and preservation of failures.
- Raw/final sorting outputs, integer global unit IDs, local-to-global unit maps,
  group/channel/bundle provenance, group-aware final analyzer sparsity and an
  all-empty result path. Labels-only preserves empty units and duplicate events.
- Generic MemSeg waveform/metric inspection moved into the central package,
  sharing GUI-independent scaling/channel helpers. MemSeg prefers it when
  available and retains a standalone fallback for its existing locked environment.
- Clean central notebook, three everyday session templates, oSort import schema,
  channel-map example, opt-in synthetic MS5 smoke script, API guide and SAW
  configuration support. Legacy notebooks/entry points remain available.

## Verification

The existing Z-Lab Python 3.12 environment was used with SpikeInterface 0.103.0
and ProbeInterface 0.3.2. Scientific dependencies were not upgraded. The optional
MS5 0.5.8 and isosplit6 0.1.4 packages were downloaded/built only into `/tmp` for
synthetic acceptance; this does not install them into a project environment.

- Full sorting test suite: see final recorded count below; optional integrations
  retain their skip conditions. Includes synthetic group isolation, mapping,
  stale-input rejection, locks, interrupted resume, empty results, labels-only
  event preservation, oSort timestamps, lineage and read-only analyzer inspection.
- Six existing DeepArray probe tests pass.
- MemSeg's 26 analysis tests pass in its unchanged locked environment. Its seven
  stored-viewer tests pass both with the standalone fallback and with the central
  source exposed on `PYTHONPATH`.
- MED constructor/serialization/reload succeeds across fresh Python processes with
  a stubbed decoder. Serialized kwargs contain the password environment-variable
  name rather than its value. Header-hook restoration after failure is tested.
  This is adapter plumbing validation, **not real MED decoding validation**.
- Actual MountainSort5 scheme-2 CPU execution on a three-second, eight-channel,
  three-source synthetic recording completed: two output clusters and 172 spikes.
  The runner saved/reloaded the analyzer and verified labels-only preserves raw
  spike-train partitions. No biological accuracy or expected cluster-count claim
  follows from this smoke test. Reproduce with `examples/synthetic_smoke.py` after
  installing the mountainsort extra.
- The independent-wire MS5 profile also completed all eight groups on the same
  synthetic input: eight output units and 877 events, retaining wire provenance.
  Cross-wire coincident events are intentionally not deduplicated. Reproduce with
  the smoke script's `--preset bf_single8` option.
- A separate two-candidate single-wire preservation-merge smoke test retained all
  240 input events.
- A wheel was built without downloading build dependencies; packaged modules and
  probe resources imported successfully outside the checkout. Existing uncommitted
  egg-info metadata was restored byte-for-byte after build verification.
- Starter notebook schema validates; dependency consistency (`pip check`) and
  whitespace (`git diff --check`) pass.

Commands for local regression checks:

```bash
MPLCONFIGDIR=/tmp/zlab-mpl MPLBACKEND=Agg OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python -m unittest discover -s src/sorting_scripts/tests -v
MPLCONFIGDIR=/tmp/zlab-mpl MPLBACKEND=Agg \
  .venv/bin/python -m unittest discover -s Custom_Probes -p 'test_*.py' -v
```

Final suite count: **97 tests, 95 passed and two optional integrations skipped**.

## Deliberately preserved boundaries

No patient recordings, existing sortings, curation decisions, scientific results,
model artifacts or original notebooks were rewritten. Historical BF/DHN source
remains available for reproducibility; new sessions use the central API. The
MemSeg timing/statistics pipeline remains task-specific. Its extra scientific
input/QC contracts must still be checked when using a new analyzer.

No real recording sort, native MED/CSC decoding acceptance, live classifier
inference, GPU run or physical wiring validation was performed. MATLAB oSort
execution remains in its original project; importing its results is supported.
The custom-sorter notebook is a sketch, not a finished clustering backend.
Automatic retirement of historical notebooks awaits representative-recording
comparison. No scientific equivalence to old runs is implied by consolidation.
