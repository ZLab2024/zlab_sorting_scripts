# Consolidation and portability audit

Audited November 13, 2026, following the initial November 6 consolidation.
The [README](../README.md) is the human entry point; [AGENTS.md](../AGENTS.md)
is the sole maintainer instruction source. Earlier implementation reports are
preserved under [archive/docs](../archive/README.md).

## Findings and fixes

| Finding | Result |
| --- | --- |
| README simultaneously directed users to old manual workflows and the central runner | One canonical `README.md`, one central notebook, detailed API/integration guides. Lowercase README and agent reference are compatibility pointers. |
| Historical plans and workstation notes mixed with current instructions | Nineteen files moved into an indexed archive with original paths, sizes and SHA-256. Existing notebook edits/outputs preserved byte-for-byte. |
| Legacy workflow and cloud assumptions mixed with the main package | Historical implementations isolated under `legacy/`; old imports alias the same modules so existing patch/import behavior remains usable. |
| Public GUI wrapper depended on the legacy workflow module | Launcher now owned by `gui/`; legacy `zsort` imports it. |
| DeepArray generator lived outside the distribution | Scientific geometry moved unchanged into `probes.deeparray`; the original command is a compatibility wrapper and existing artifact tests still apply. |
| No portable probe generation/export API | Added in-memory linear/DeepArray factories, non-overwriting JSON export, custom PRB loading, preset export CLI. |
| Only Intan, Neuralynx, MED and cached binary loaders | Added explicit raw-binary options and a controlled adapter to installed SI `read_*` acquisition readers. Added stream discovery API/CLI. |
| Generic readers could hide additional file dependencies | Config normalizes named reader-side paths, input identities include existing referenced files/directories, and saved binary caches fingerprint external raw paths. |
| Resume verified existing artifacts but could miss extra injected/stale files | Exact completed-stage file sets are now compared, including added files. |
| SAW wrapper always inserted the checkout into sys.path | Normal installed import is preferred; checkout fallback remains only when the package is absent. |
| GUI installation error contained a developer's absolute path | Message uses a generic install location. No developer/sibling absolute paths remain in supported package code. Legacy home-directory fallbacks are isolated. |
| Starter notebook default assumed notebook-relative cwd | One explicit user configuration path, independent of kernel working directory. |
| Manual curation helper assumed patient/session output layout | New `curation.apply_manual_curation` accepts any analyzer and explicit decisions/new output. |

## Package boundaries

Supported APIs load no code from the BF, DHN, MemSeg or MATLAB repositories.
Their generic loaders, geometry, merge/lineage and stored inspection primitives
are central. Research-specific comparisons, behavior/statistics, preserved runs
and external MATLAB execution remain separate. Those projects can install this
package rather than modify `sys.path`. Historical sources have not been deleted.

The source layout is documented in [API reference](api.md). Root compatibility
modules intentionally remain. `Custom_Probes` copies remain for former scripts;
package resources/generators are canonical. Legacy public module paths for GUI
plugins, classifier/curation engines and KS4 checkpoints are retained.

Archives contain prior notebook outputs as well as edits. They are preserved
local artifacts, not automatically sanitized for publication. No upload or
publication was performed.

## Validation performed

- Existing Z-Lab Python 3.12 environment, SI 0.103.0 / PI 0.3.2; no scientific
  dependency upgrades or environment replacement.
- Original 97-test suite passed after legacy/module reorganization (two optional
  integration skips). Nine new portability tests passed: real synthetic binary
  read/scaling, reader signature/type contracts, stream dispatch, reader-side
  file fingerprints, probe generation/JSON/PRB/CLI, manual-curation argument/output
  contracts, archive integrity, legacy aliases and added-artifact rejection.
- All six existing DeepArray tests passed, including exact generated artifact
  bytes, geometry, annotations, wiring and compatibility CLI from another cwd.
- Built a wheel from a clean temporary source tree, leaving the user's existing
  egg-info/build edits untouched. Tests are excluded from the distribution.
  Extracted wheel imports, raw-binary read/config validation, preset generation
  and legacy imports passed from an unrelated consumer directory. Every loaded
  `sorting_scripts` module was checked to originate in the wheel, not the
  editable checkout or a sibling repository.
- `pip check`, compilation and whitespace checks pass. Archive manifest hashes
  and active documentation links are checked separately.

Final combined suite: **106 tests, 104 passed, two optional integrations skipped**.
The six separate DeepArray tests also pass. All active Markdown file links
resolve, all 19 archive content hashes match, and the sole active starter
notebook has clear outputs and syntactically valid code. `git diff --check` passes.

## Limits and next acceptance

The current runner has pinned KS4/MS5 recipes and explicit curation policies;
it is an extensible package, not a promise that every SI reader/sorter or probe
is scientifically validated. Generic-reader tests use a signature-compatible
fixture; SpikeGLX/Open Ephys native files were not decoded in this audit.
The raw-binary adapter was exercised on actual synthetic bytes.

The prior audit exercised actual MS5 CPU sorting on synthetic BF bundles and
independent wires, as recorded in the archived implementation report. This audit
retains those profiles and runs the synthetic regression suite; it does not
claim a new GPU or real-recording sorting trial. No native MED/CSC decoding,
model download/inference, cloud transfer, patient sorting or biological/wiring
validation was performed. Multi-segment continuity and relocation of data-backed
analyzers still require an explicit policy.

Source/config identities necessarily change with this refactor. An older failed
run must not bypass identity checks to resume under new code: use its preserved
original environment/code or start a new run. Existing completed results are
preserved.
