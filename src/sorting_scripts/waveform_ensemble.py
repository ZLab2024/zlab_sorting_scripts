"""Stored-waveform ensemble for SpikeInterface-GUI's Panel backend.

No waveform extraction, per-spike normalization, or temporal realignment occurs.
GUI 0.11's row selection is separate from its visible-unit list; the small
SelectionAdapter below listens to the actual Tabulator and focus notifier.
"""

from collections import OrderedDict
from html import escape
import hashlib

import numpy as np
from .waveform_data import time_axis, stored_channel_indices, amplitude_label
from spikeinterface_gui.view_base import ViewBase


def resolve_selected_unit(index, rows, focused_row=None):
    """Prefer the focused selected row; otherwise the first selected table row."""
    rows = sorted({int(row) for row in rows if 0 <= row < len(index)})
    if not rows:
        return None
    return index[focused_row if focused_row in rows else rows[0]]








class SelectionAdapter:
    """Session-local 0.11 adapter; never patches a GUI class or controller.

    Mouse clicks and keyboard shortcuts both update table.tabulator.selection.
    Clicks additionally emit active_view_updated *after* updating the wrapper's
    _last_selected_row. Watch both to catch focus changes within a multi-selection.
    """

    def __init__(self, unitlist, changed):
        self.unitlist = unitlist
        self.changed = changed
        self.focused_row = None
        self._watchers = []
        self._watch(unitlist.table.tabulator, "selection", self._selection_changed)
        self._watch(unitlist.table.tabulator, "value", self._table_changed)
        self._watch(unitlist.notifier, "active_view_updated", self._focus_changed)

    def _watch(self, obj, name, callback):
        self._watchers.append((obj, obj.param.watch(callback, name)))

    def _selection_changed(self, event):
        added = sorted(set(event.new) - set(event.old))
        self.focused_row = added[-1] if added else self.unitlist.table._last_selected_row
        self.changed()

    def _focus_changed(self, event):
        self.focused_row = self.unitlist.table._last_selected_row
        self.changed()

    def _table_changed(self, event):
        # Row order may change when sorting/filtering. Resolve against current IDs.
        self.changed()

    def selected_unit(self):
        table = self.unitlist.table
        return resolve_selected_unit(table.value.index, table.selection, self.focused_row)

    def close(self):
        for obj, watcher in self._watchers:
            obj.param.unwatch(watcher)
        self._watchers.clear()


class WaveformEnsembleView(ViewBase):
    id = "waveformensemble"
    _supported_backend = ["panel"]
    # Keep the panel visible with an actionable message when data are missing.
    _depend_on = None
    _settings = None
    _gui_help_txt = (
        "Selected unit's stored spike waveforms on one channel, with its average template. "
        "Time zero is the stored spike alignment; amplitudes and polarity are preserved. "
        "Multiple selected rows follow the focused row, then the first selected table row. "
        "Visibility checkboxes do not determine selection. Pan/zoom and Reset include outliers."
    )

    def _panel_make_layout(self):
        import panel as pn
        from bokeh.models import ColumnDataSource, Range1d, Span
        from bokeh.plotting import figure

        self._cache = OrderedDict()
        self._source = None
        self._adapter = None
        self._closed = False
        self._updating_controls = False
        self._current_unit = None
        self._last_plot_key = None
        self._watchers = []
        self.waveform_source = ColumnDataSource(dict(xs=[], ys=[]))
        self.template_source = ColumnDataSource(dict(x=[], y=[]))
        self.plot = figure(
            title="Waveform ensemble", sizing_mode="stretch_both", min_height=280,
            x_axis_label="Time relative to spike (ms)", y_axis_label="Amplitude",
            x_range=Range1d(-1, 2), y_range=Range1d(-1, 1),
            tools="pan,wheel_zoom,box_zoom,reset,save", active_scroll="wheel_zoom",
            background_fill_color="#151b26", border_fill_color="#151b26",
        )
        self.plot.title.text_color = "#e5eaf2"
        self.plot.axis.axis_label_text_color = "#d2dbea"
        self.plot.axis.major_label_text_color = "#d2dbea"
        self.plot.grid.grid_line_alpha = .12
        self.waveform_renderer = self.plot.multi_line(
            xs="xs", ys="ys", source=self.waveform_source,
            line_width=.7, line_alpha=.10, line_color="#6bc6ff",
        )
        self.template_renderer = self.plot.line(
            x="x", y="y", source=self.template_source, line_width=3, line_color="#6bc6ff",
        )
        self.plot.add_layout(Span(location=0, dimension="height", line_color="#cbd5e1", line_alpha=.3))
        self.status = pn.pane.Markdown("Select a unit in the Unit List.", sizing_mode="stretch_width")
        self.channel = pn.widgets.Select(name="Channel", options={}, width=130, disabled=True)
        self.max_waveforms = pn.widgets.IntInput(name="Max waveforms", value=500, start=1, end=2000, width=140)
        self.opacity = pn.widgets.FloatSlider(name="Trace opacity", value=.10, start=.01, end=.4, step=.01, width=175)
        self.reload_button = pn.widgets.Button(name="Reload stored data", width=150)
        for widget, callback in ((self.channel, self._control_changed),
                                 (self.max_waveforms, self._control_changed),
                                 (self.opacity, self._opacity_changed)):
            self._watchers.append((widget, widget.param.watch(callback, "value")))
        self._watchers.append((self.reload_button, self.reload_button.on_click(self._reload)))
        self.layout = pn.Column(
            self.status,
            pn.FlexBox(self.channel, self.max_waveforms, self.opacity, self.reload_button),
            pn.pane.Bokeh(self.plot, sizing_mode="stretch_both"),
            sizing_mode="stretch_both", min_height=360,
        )

    def _attach_selection(self):
        unitlist = next((view for view in self.controller.views
                         if view.__class__.__name__ == "UnitListView"), None)
        if self._adapter is not None and self._adapter.unitlist is not unitlist:
            self._adapter.close()
            self._adapter = None
        if self._adapter is None and unitlist is not None:
            self._adapter = SelectionAdapter(unitlist, self.refresh)

    def _clear(self, message):
        self.waveform_source.data = dict(xs=[], ys=[])
        self.template_source.data = dict(x=[], y=[])
        self.status.object = message
        self.plot.title.text = "Waveform ensemble"
        self._last_plot_key = None
        self._current_unit = None
        self._updating_controls = True
        try:
            self.channel.options = {}
            self.channel.value = None
            self.channel.disabled = True
        finally:
            self._updating_controls = False

    def invalidate(self):
        self._cache.clear()
        self._source = None
        self._last_plot_key = None

    def _reload(self, event=None):
        self.invalidate()
        self.refresh()

    def _control_changed(self, event):
        if not self._updating_controls:
            self.refresh()

    def _opacity_changed(self, event):
        self.waveform_renderer.glyph.line_alpha = event.new

    def on_manual_curation_updated(self):
        # Invalidate even if a custom layout currently hides this tab.
        self._reload()

    def _panel_refresh(self):
        if self._closed:
            return
        self._attach_selection()
        analyzer = self.controller.analyzer
        waveform_ext = analyzer.get_extension("waveforms")
        template_ext = analyzer.get_extension("templates")
        source = (analyzer, waveform_ext, template_ext)
        if self._source != source:
            self.invalidate()
            self._source = source
        unit_id = self._adapter.selected_unit() if self._adapter else None
        if unit_id is None or unit_id not in analyzer.unit_ids:
            self._clear("Select a unit in the **Unit List** to display its stored waveforms.")
            return
        curation = getattr(self.controller, "curation_data", {})
        if unit_id in curation.get("removed_units", []):
            self._clear(f"Unit **{escape(str(unit_id))}** is marked for removal. Select another unit or restore it.")
            return
        if waveform_ext is None or template_ext is None or "average" not in template_ext.data:
            self._clear(
                "Stored **waveforms** and an **average template** are required. "
                "Prepare them once using the repository's `zsort.analyze` / auto-curation workflow, "
                "then reopen this analyzer. No recording extraction was started."
            )
            return
        channels = stored_channel_indices(analyzer, unit_id)
        if not len(channels):
            self._clear("This unit has no stored waveform channels.")
            return
        unit_index = analyzer.sorting.id_to_index(unit_id)
        template = template_ext.data["average"][unit_index]
        # Templates are dense even when the waveform buffer is sparse in SI 0.103.
        magnitudes = np.max(np.where(np.isfinite(template[:, channels]),
                                     np.abs(template[:, channels]), -np.inf), axis=0)
        strongest = int(channels[np.argmax(magnitudes)])
        changed_unit = unit_id != self._current_unit
        self._updating_controls = True
        try:
            previous = self.channel.value
            self.channel.options = {str(analyzer.channel_ids[i]): int(i) for i in channels}
            self.channel.value = strongest if changed_unit or previous not in channels else previous
            self.channel.disabled = False
        finally:
            self._updating_controls = False
        channel_index = self.channel.value
        count = min(2000, max(1, int(self.max_waveforms.value or 500)))
        key = (unit_id, channel_index, count)
        if key not in self._cache:
            waveforms = waveform_ext.get_waveforms_one_unit(unit_id, force_dense=False)
            local_channel = int(np.flatnonzero(channels == channel_index)[0])
            seed = int.from_bytes(hashlib.sha256(str(unit_id).encode()).digest()[:8], "little")
            indices = np.random.default_rng(seed).permutation(len(waveforms))[:count]
            traces = np.array(waveforms[indices, :, local_channel], copy=True)
            average = np.array(template[:, channel_index], copy=True)
            if traces.shape[1] != average.size or waveform_ext.nbefore != template_ext.nbefore:
                self._clear("Stored waveform and template time windows differ. Recompute matching extensions before viewing.")
                return
            self._cache[key] = (traces, average, len(waveforms))
            while len(self._cache) > 16 or (len(self._cache) > 1 and sum(
                item[0].nbytes + item[1].nbytes for item in self._cache.values()
            ) > 32 * 1024**2):
                self._cache.popitem(last=False)
        self._cache.move_to_end(key)
        traces, average, available = self._cache[key]
        x = time_axis(len(average), waveform_ext.nbefore, analyzer.sampling_frequency)
        if self._last_plot_key != key:
            self.waveform_source.data = dict(xs=[x] * len(traces), ys=list(traces))
            self.template_source.data = dict(x=x, y=average)
            finite = np.concatenate((traces.ravel(), average))
            finite = finite[np.isfinite(finite)]
            low, high = (float(finite.min()), float(finite.max())) if finite.size else (-1., 1.)
            padding = max((high - low) * .08, max(abs(low), abs(high)) * .02, 1e-6)
            self._set_range(self.plot.y_range, low - padding, high + padding)
            self._set_range(self.plot.x_range, float(x[0]), float(x[-1]))
        color = self.get_unit_color(unit_id)[:7]
        self.waveform_renderer.glyph.line_color = color
        self.template_renderer.glyph.line_color = color
        self.plot.yaxis.axis_label = amplitude_label(analyzer, traces.dtype)
        self.plot.title.text = f"Unit {unit_id} · Channel {analyzer.channel_ids[channel_index]}"
        total = sum(analyzer.sorting.get_unit_spike_train(unit_id, segment_index=i).size
                    for i in range(analyzer.get_num_segments()))
        pending_merge = any(unit_id in group for group in curation.get("merge_unit_groups", []))
        self.status.object = (
            f"**Unit {escape(str(unit_id))}** · Channel **{escape(str(analyzer.channel_ids[channel_index]))}** · "
            f"**{len(traces)}** displayed / **{available}** stored waveforms · **{total:,}** total spikes"
            + (" · Pending merge: showing this source unit until curation is applied." if pending_merge else "")
            + (" · No individual waveforms were stored." if not available else "")
        )
        self._current_unit = unit_id
        self._last_plot_key = key

    @staticmethod
    def _set_range(axis_range, low, high):
        axis_range.start = axis_range.reset_start = low
        axis_range.end = axis_range.reset_end = high

    def close(self, session_context=None):
        self._closed = True
        if self._adapter:
            self._adapter.close()
        for obj, watcher in self._watchers:
            obj.param.unwatch(watcher)
        self._watchers.clear()
        self._cache.clear()

