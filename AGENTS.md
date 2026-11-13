# Working on Z-Lab sorting

## Read first

[README.md](README.md) is the single human entry point. Read
[docs/api.md](docs/api.md), [docs/integration.md](docs/integration.md) and
[docs/environment.md](docs/environment.md) for implementation work. Historical
plans/reviews are in [archive/](archive/README.md), not current specifications.
This file is the single maintainer/agent instruction source; `agent_reference.md`
is a compatibility pointer.

## Source ownership

- `config.py`, `pipeline.py`, `provenance.py`: strict configuration, isolated group
  stages, cache identities, writer locking and manifests.
- `io/`: Intan, Neuralynx, optional MED, raw/cached binary, explicit built-in SI
  reader adapters and oSort imports. Do not introduce sibling-repository imports.
- `probes/`: canonical geometry generation, packaged resources, full-group wiring
  and export. No checkout-relative resources in supported APIs.
- `preprocessing.py`, `backends/`, `analysis.py`: profiles, KS4/MS5, stored analyzer
  extensions. Split groups before channel-mixing operations.
- `curation/`, `auto_curate.py`, `model_labeling.py`, `merging.py`, `lineage.py`:
  explicit policies and provenance. Keep existing model/class import paths stable.
- `inspection/`, `waveform_data.py`: stored-only inspection, no GUI dependency.
  `gui/`, `ensemble_gui.py`, `waveform_ensemble.py`, `spike_snippets.py`: optional GUI.
- `legacy/`: frozen compatibility workflows/lab cloud assumptions; root `zsort.py`
  and `box_managment.py` alias these modules. Preserve old scientific behavior;
  use the central runner for new work.
- `Custom_Probes/`: compatibility files/tests; canonical generators/resources
  live inside the package. `wrapper.py`: SAW host adapter only.

## Scientific and data invariants

Preserve raw recordings, source ordering, sample counts, channel IDs, gains/offsets,
and source annotations. Never infer wiring from channel count or fill time gaps
implicitly. DeepArray manufacturer status does not exclude contacts. Virtual BF
coordinates are not anatomical measurements. The runner currently requires one
nonempty segment, sequential groups, and the documented passband/sample rate.

Models default off in the runner. Labels-only cannot remove units/events; cleanup,
merging and rejection must be explicit. Keep human labels and each classifier's
namespaced properties separate. Label merged units after merging. Preserve
unit/event lineage and failed runs; no count quotas or undocumented censoring.

SI `remove_units` takes IDs; `merge_units(..., merging_mode='hard')` returns a new
analyzer and recomputes extensions. Apply GUI dictionaries with `apply_curation`.
Do not modify installed packages, bypass model guards, silently upgrade scientific
APIs, or claim completion before writing and checking the success manifest.

## Compatibility baseline

Python 3.12 is the tested target (declared range 3.10–3.12). Keep SpikeInterface
**0.103.0**, ProbeInterface **0.3.2**, GUI **0.11.0**, KS4 **4.1.1**;
MS5 **0.5.8**, isosplit6 **0.1.4**, optional MED **2.0.6** / Neo **0.14.4**.
UnitRefine's documented sklearn **1.4.2** and NumPy <2 constraints are deliberate.
Inspect installed signatures/source before using examples from newer releases.
Authoritative versioned references:
[SI API](https://spikeinterface.readthedocs.io/en/0.103.0/api.html),
[PI source](https://github.com/SpikeInterface/probeinterface/tree/0.3.2),
[GUI source](https://github.com/SpikeInterface/spikeinterface-gui/tree/0.11.0),
[KS4 source](https://github.com/MouseLand/Kilosort/tree/v4.1.1).

## Change and verification workflow

1. Inspect `git status`/diff first. Preserve existing uncommitted work and notebooks.
   Archive superseded files reversibly, recording original paths/content hashes.
   Never archive raw data or scientific outputs as a cleanup shortcut.
2. Keep dependencies in `pyproject.toml`; requirements select extras. Public
   imports must work from an installed wheel, from an unrelated cwd, with no
   sibling checkout, `sys.path` edits, network call or computation at import time.
3. Use synthetic data. Do not invoke real sorting, model downloads/inference or
   cloud transfers as part of code review. HF integration stays opt-in.
4. Run `python -m pip check`, then:

   ```bash
   MPLBACKEND=Agg OPENBLAS_NUM_THREADS=1 python -m unittest discover -s src/sorting_scripts/tests -v
   python -m unittest discover -s Custom_Probes -p 'test_*.py' -v
   ```

   For packaging/path changes, build a wheel, inspect package resources and test
   imports outside the checkout. Preserve pre-existing egg-info edits during builds.
   Check `git diff --check`. Do not rerun expensive checks without a change/failure.
5. Update the README only for user-facing workflow changes; API details belong in
   `docs/api.md`/`docs/integration.md`. Record actual validation in
   `docs/maintenance_audit.md`, distinguishing synthetic tests from native decoding,
   GPU, physical wiring and biological validity. Do not duplicate instruction files.
