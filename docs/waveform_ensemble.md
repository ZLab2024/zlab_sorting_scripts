# Selected-unit waveform ensemble

The project registers `waveformensemble` and `spikesnippets`, Panel/Bokeh custom views for
SpikeInterface **0.103.0** and SpikeInterface-GUI **0.11.0**. Its implementation
is in `src/sorting_scripts/waveform_ensemble.py`; launcher integration is in
`src/sorting_scripts/ensemble_gui.py`. Installed scientific packages are not
patched and their versions are not upgraded.

## Install and launch

From this repository, in the environment used by the notebook:

```bash
python -m pip install -e '.[gui,notebook]'
python -m pip check
```

If the dependencies are already installed, register the new entry point without
changing them:

```bash
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

Restart the notebook kernel after installing. Load your existing analyzer, then:

```python
from sorting_scripts import zsort

window = zsort.launch_curation_gui(analyzer, mode="web", port=5007)
# Automated curation review can retain its ML columns and disable editing:
# window = zsort.launch_curation_gui(
#     curated_data, mode="web", curation=False,
#     **curation_result.gui_kwargs(),
# )
```

The launcher defaults to web mode. Desktop mode remains available explicitly,
without these Panel-only views. The waveform and ensemble panels are initially
visible in adjacent lower docks (`zone7` and `zone8`). The spike snippet browser
is initially visible in the upper right (`zone3`); the original continuous trace
remains available in the same dock's Trace tab. Other panels remain available,
including the heatmap tab. Explicit `layout` or `layout_preset` arguments take precedence.
Every view in GUI 0.11's registry is instantiated, so the ensemble is available
to custom layouts even when omitted from the default layout.

Click a Unit List row or use that table's existing keyboard navigation. The
view follows the selected row even if another unit's visibility checkbox remains
on. With multiple rows selected, the latest focused selected row wins; without
valid focus, the first selected row in the current table order wins. Clearing
selection clears both traces and average. The strongest stored channel is
selected initially (largest absolute average-template deflection); choose another
available physical channel with the Channel control.

Up to **500 stored waveforms**, sampled reproducibly by unit ID, are overlaid as
thin traces at **0.10 opacity** with a bold average template. The maximum and
opacity are adjustable; the control caps the maximum at 2000. The bold template
is the stored average over extracted waveforms, not a sum and not a normalized
trace. Individual waveforms are already aligned to their detected spike samples;
the view performs no additional shifting, peak alignment, normalization, or
polarity changes. True timing and amplitude variability remain visible.

The status distinguishes displayed traces, available extracted waveforms, and
the full unit spike count. Time is `(sample - nbefore) / sampling_frequency` in
milliseconds. µV is used when the analyzer's `return_in_uV` storage contract
supports it; unscaled integer data are labeled ADC counts, otherwise recording
units. Sparse waveform-local channels are explicitly mapped to global channel
indices and physical IDs. The average template uses SI 0.103's dense indexing.

Initial axes encompass all displayed traces and the average with padding. Pan,
wheel/box zoom, and Reset remain available; Reset returns to those full limits,
including sampled outliers. Unit colors come from the existing controller.

## Browse individual spikes

The installed GUI 0.11 trace toolbar offers segment, window size, and a time
slider. It seeks to an already selected spike through
`_panel_on_spike_selection_changed` / `_panel_seek_with_selected_spike`, but
selecting a unit does not select a spike. There is no per-unit next-spike button.

`spikesnippets` provides that navigation without changing installed GUI code:

- Select a Unit List row. It displays the first spike at/after the current trace
  time, or the last available spike if the current time is beyond that unit.
- **Previous spike / Next spike** move chronologically through that unit's full
  spike train, across segments. **First / Last** jump to the ends. **Spike #**
  jumps to any ordinal. End buttons disable at the boundaries; navigation does
  not wrap. Segment indices are zero-based; spike ordinals start at one.
- Each window is centered at **0 ms**, marked by a dashed line. The default
  **20 ms** window shows 10 ms on either side; adjust it between 2 and 200 ms.
  At recording edges the unavailable flank remains empty, keeping the spike
  centered. The status includes the absolute segment time and full spike count.
- It defaults to the strongest available channel; choose another channel to
  inspect spatial context. Polarity/amplitudes are preserved and each snippet
  is autoscaled. Previous/Next also update the original trace's controller time.
- Only this short window and one chosen channel are requested from the attached
  recording (which may be a lazy preprocessed recording). There is no full-file
  read or new waveform extraction. Sixteen recently displayed windows are cached
  per session. The ensemble still uses its previously stored waveform sample.

The original Waveform view retains upstream visible-unit behavior; the ensemble
and snippet browser follow Unit List selection. Visibility checkboxes can still
be used for multi-unit template comparisons in the Waveform panel.

`with_traces=False` disables snippet reads too. A missing/unreadable recording
shows a reconnect message and clears stale data. Pending removals clear the view;
pending merges show source-unit data until applied. Session cleanup releases
both custom views. These panels do not modify spike times or manual decisions.

## Compatibility and lifecycle

The [custom-view documentation](https://spikeinterface-gui.readthedocs.io/en/latest/custom_views.html)
describes a newer GUI release. Installed 0.11.0 has neither entry-point discovery
nor a unit-selection notification. The project declares the standard
`spikeinterface_gui.views` entry point; its launcher loads that entry into 0.11's
existing `possible_class_views` registry. Missing/duplicate/wrong registration
raises an actionable installation error. This bridge is gated to the pinned
versions. Calling upstream `run_mainwindow` directly does not install the bridge;
use `zsort.launch_curation_gui`.

The session-local selection adapter watches the actual
`UnitListView.table.tabulator.selection` and table value. For mouse focus it also
watches the unit-list notifier's `active_view_updated`, emitted after
`SelectableTabulator._last_selected_row` is updated. Keyboard navigation updates
the same selection property; newly selected rows are resolved immediately.
This avoids treating the controller's visible units as its selected units.

Drawing uses one Bokeh MultiLine data source plus one template line. Cached
samples are local to each view (16 unit/channel/limit entries, approximately
32 MiB budget). Existing waveform buffers are read, never full-recording traces.
Callbacks are synchronous, so no background task can overwrite a newer selection.
Changing the analyzer or its waveform/template extension objects invalidates the
cache on refresh. Curation notifications invalidate even hidden views. The
Reload stored data button invalidates after an external in-place data change.

GUI 0.11 records pending deletes/merges rather than replacing spike arrays live.
Deleted units clear the ensemble; pending merges show the selected **source**
unit with an explicit notice. Applying curation and reopening the resulting
analyzer shows recomputed merged waveforms. This version has no live split or
analyzer-replacement event; callers replacing an analyzer must refresh/reopen
the window. The view detects the replacement on its next refresh.

Missing waveform/average extensions produce an actionable message, without
computing them. Prepare an analyzer once through `zsort.analyze` or the automated
curation workflow. The upstream GUI itself may compute its own mandatory missing
extensions during startup; this plugin does not change that behavior.

Normal web serving uses a factory: each browser session receives an independent
controller, selection adapter, cache, sources, and curation decision dictionary.
Session destruction releases plugin watchers/cache. `start_app=False` returns an
unserved window as before; if serving it yourself, create a fresh window per
session and register both custom views' `close` methods for session cleanup.
The upstream GUI has no general view disposal API; the plugin's `close()` is also
available explicitly.

## Validation

```bash
python -m unittest discover -s src/sorting_scripts/tests -p 'test_waveform_ensemble.py' -v
python -m unittest discover -s src/sorting_scripts/tests -p 'test_spike_snippets.py' -v
python -m unittest discover -s src/sorting_scripts/tests -v
python -m unittest discover -s Custom_Probes -p 'test_*.py' -v
```

Focused tests construct actual sparse synthetic SI analyzers and Panel windows.
They check entry-point registration, initial visibility, explicit layout overrides,
selection independent of visibility, keyboard navigation, focus changes, empty
selection, sparse waveform channels, unchanged amplitudes/template, time zero,
full range limits, reproducible sampling, bounded cache, delete/merge notifications,
missing waveforms, analyzer replacement, callback disposal, and session isolation.
No real recordings or model services are used.

Validated in the existing Python 3.12 environment with SI 0.103.0, GUI 0.11.0,
Panel 1.9.3, Bokeh 3.9.1, and Param 2.4.1:

- Full suite after adding the spike browser: 80 tests discovered, 78 passed,
  2 optional integrations skipped.
- All 8 ensemble tests, all 8 snippet tests, and all 6 probe tests passed; `pip check` and
  `git diff --check` passed.
- A real local Panel server served an 8-second synthetic analyzer. Bokeh clients
  confirmed 500 traces, changed trace data after selecting another row, zero
  traces after deselection, and independent state in a second session.
- The updated local server served a 3-second synthetic analyzer with adjacent
  waveform/ensemble panels and the snippet view. A Bokeh client verified the
  selected unit's trace included 0 ms, changing the Spike # control changed the
  displayed recording window, and deselection cleared it. Panel tests verified
  Previous/Next, First/Last, channel switching, bounds, bounded reads, and actual
  navigation across recording segments. No real recording was processed.
- Browser backends were unavailable, so pixel-level appearance and browser
  mouse/keyboard interaction were not visually verified. Selection and keyboard
  callbacks were exercised through the actual Panel/unit-list APIs.
