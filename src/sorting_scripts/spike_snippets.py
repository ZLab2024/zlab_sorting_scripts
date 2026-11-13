"""Small continuous-recording windows centered on selected-unit spike samples."""

from collections import OrderedDict
from html import escape

import numpy as np
from spikeinterface_gui.view_base import ViewBase

from .waveform_ensemble import SelectionAdapter, amplitude_label, stored_channel_indices


def locate_spike(trains, ordinal):
    """Map a zero-based chronological ordinal across segments to (segment, sample)."""
    counts = np.asarray([len(train) for train in trains], dtype=np.int64)
    cumulative = np.cumsum(counts)
    if not cumulative.size or not cumulative[-1]:
        raise ValueError("The selected unit has no spikes.")
    ordinal = int(np.clip(ordinal, 0, cumulative[-1] - 1))
    segment = int(np.searchsorted(cumulative, ordinal, side="right"))
    offset = int(cumulative[segment - 1]) if segment else 0
    return segment, int(trains[segment][ordinal - offset])


def snippet_bounds(sample, sampling_frequency, window_ms, num_samples):
    half = max(1, round(window_ms * sampling_frequency / 2000.))
    return max(0, sample - half), min(num_samples, sample + half + 1), half


class SpikeSnippetsView(ViewBase):
    id = "spikesnippets"
    _supported_backend = ["panel"]
    _depend_on = None
    _settings = None
    _gui_help_txt = (
        "Previous/Next steps through ALL spikes of the selected unit in chronological order, "
        "across recording segments. Each continuous-recording window is centered at the "
        "detected spike sample (0 ms). Select a channel or change the window width for context. "
        "Only the small displayed window is read; no new waveform extraction is performed."
    )

    def _panel_make_layout(self):
        import panel as pn
        from bokeh.models import ColumnDataSource, Range1d, Span
        from bokeh.plotting import figure

        self._adapter = None
        self._source = None
        self._current_unit = None
        self._trains = []
        self._total = 0
        self._cache = OrderedDict()
        self._closed = False
        self._updating = False
        self._watchers = []
        self._location = None
        self.status = pn.pane.Markdown("Select a unit in the **Unit List**.", sizing_mode="stretch_width")
        self.previous = pn.widgets.Button(name="← Previous spike", width=145, disabled=True)
        self.next = pn.widgets.Button(name="Next spike →", width=130, disabled=True)
        self.first = pn.widgets.Button(name="First", width=60, disabled=True)
        self.last = pn.widgets.Button(name="Last", width=60, disabled=True)
        self.spike_number = pn.widgets.IntInput(name="Spike #", value=1, start=1, end=1, width=110, disabled=True)
        self.window_ms = pn.widgets.FloatInput(name="Window (ms)", value=20., start=2., end=200., step=2., width=125)
        self.channel = pn.widgets.Select(name="Channel", options={}, width=130, disabled=True)
        self.trace_source = ColumnDataSource(dict(time_ms=[], amplitude=[]))
        self.plot = figure(
            title="Spike-centered trace", x_axis_label="Time relative to selected spike (ms)",
            y_axis_label="Amplitude", sizing_mode="stretch_both", min_height=240,
            x_range=Range1d(-10, 10), y_range=Range1d(-1, 1),
            tools="pan,wheel_zoom,box_zoom,reset,save", active_scroll="wheel_zoom",
            background_fill_color="#151b26", border_fill_color="#151b26",
        )
        self.plot.title.text_color = "#e5eaf2"
        self.plot.axis.axis_label_text_color = "#d2dbea"
        self.plot.axis.major_label_text_color = "#d2dbea"
        self.plot.grid.grid_line_alpha = .12
        self.renderer = self.plot.line(
            x="time_ms", y="amplitude", source=self.trace_source, line_color="#6bc6ff", line_width=1.2,
        )
        self.plot.add_layout(Span(location=0, dimension="height", line_color="#e5eaf2", line_dash="dashed", line_alpha=.6))
        for button, callback in ((self.previous, lambda e: self._move(-1)),
                                 (self.next, lambda e: self._move(1)),
                                 (self.first, lambda e: self._go(1)),
                                 (self.last, lambda e: self._go(self._total))):
            self._watchers.append((button, button.on_click(callback)))
        for widget, callback in ((self.spike_number, self._ordinal_changed),
                                 (self.window_ms, self._control_changed),
                                 (self.channel, self._control_changed)):
            self._watchers.append((widget, widget.param.watch(callback, "value")))
        self.layout = pn.Column(
            self.status,
            pn.FlexBox(self.first, self.previous, self.next, self.last,
                       self.spike_number, self.window_ms, self.channel),
            pn.pane.Bokeh(self.plot, sizing_mode="stretch_both"),
            sizing_mode="stretch_both", min_height=330,
        )

    def _attach_selection(self):
        unitlist = next((v for v in self.controller.views if v.__class__.__name__ == "UnitListView"), None)
        if self._adapter is not None and self._adapter.unitlist is not unitlist:
            self._adapter.close()
            self._adapter = None
        if self._adapter is None and unitlist is not None:
            self._adapter = SelectionAdapter(unitlist, self.refresh)

    def _clear(self, message):
        self.trace_source.data = dict(time_ms=[], amplitude=[])
        self.status.object = message
        self.plot.title.text = "Spike-centered trace"
        self._current_unit = None
        self._location = None
        self._trains = []
        self._total = 0
        for control in (self.previous, self.next, self.first, self.last, self.spike_number, self.channel):
            control.disabled = True

    def _move(self, delta):
        self._go(self.spike_number.value + delta)

    def _go(self, number):
        if self._total:
            self.spike_number.value = int(np.clip(number, 1, self._total))

    def _ordinal_changed(self, event):
        if not self._updating:
            self.refresh()
            if self._location is not None:
                segment, sample = self._location
                self.controller.set_time(time=sample / self.controller.analyzer.sampling_frequency,
                                         segment_index=segment)
                self.notify_time_info_updated()

    def _control_changed(self, event):
        if not self._updating:
            self.refresh()

    def on_manual_curation_updated(self):
        self._source = None
        self._cache.clear()
        self.refresh()

    def _panel_refresh(self):
        if self._closed:
            return
        self._attach_selection()
        analyzer = self.controller.analyzer
        unit = self._adapter.selected_unit() if self._adapter else None
        if unit is None or unit not in analyzer.unit_ids:
            self._clear("Select a unit in the **Unit List** to browse its spikes.")
            return
        if not self.controller.with_traces:
            self._clear("Trace reading is disabled. Relaunch with **with_traces=True** to browse spike snippets.")
            return
        if not (analyzer.has_recording() or analyzer.has_temporary_recording()):
            self._clear("The original/preprocessed recording is unavailable. Reconnect it when launching the GUI.")
            return
        curation = getattr(self.controller, "curation_data", {})
        if unit in curation.get("removed_units", []):
            self._clear(f"Unit **{escape(str(unit))}** is marked for removal. Restore it or select another unit.")
            return
        recording = analyzer.recording
        templates = analyzer.get_extension("templates")
        source = (analyzer, recording, analyzer.sorting, templates)
        changed = self._source != source or self._current_unit != unit
        if self._source != source:
            self._cache.clear()
        self._source = source
        channels = stored_channel_indices(analyzer, unit)
        if not len(channels):
            self._clear("The selected unit has no available channels.")
            return
        if changed:
            self._trains = [analyzer.sorting.get_unit_spike_train(unit, segment_index=i)
                            for i in range(analyzer.get_num_segments())]
            self._total = sum(len(train) for train in self._trains)
        if not self._total:
            self._clear("The selected unit has no spikes.")
            return
        self._updating = True
        try:
            old_channel = self.channel.value
            self.channel.options = {str(analyzer.channel_ids[i]): int(i) for i in channels}
            if changed or old_channel not in channels:
                if templates is not None and "average" in templates.data:
                    template = templates.data["average"][analyzer.sorting.id_to_index(unit)]
                    magnitudes = np.max(np.where(np.isfinite(template[:, channels]),
                                                 np.abs(template[:, channels]), -np.inf), axis=0)
                    self.channel.value = int(channels[np.argmax(magnitudes)])
                else:
                    self.channel.value = int(channels[0])
            else:
                self.channel.value = old_channel
            self.spike_number.end = self._total
            if changed:
                # Start near the continuous trace's current position. No manual
                # search is needed when changing units late in the recording.
                time, segment = self.controller.get_time()
                segment = min(max(int(segment), 0), len(self._trains) - 1)
                index = np.searchsorted(self._trains[segment], round(time * analyzer.sampling_frequency))
                ordinal = sum(len(t) for t in self._trains[:segment]) + index
                self.spike_number.value = min(int(ordinal) + 1, self._total)
            else:
                self.spike_number.value = min(max(int(self.spike_number.value or 1), 1), self._total)
        finally:
            self._updating = False
        segment, sample = locate_spike(self._trains, self.spike_number.value - 1)
        width = float(np.clip(self.window_ms.value or 20., 2., 200.))
        start, stop, half = snippet_bounds(sample, analyzer.sampling_frequency, width,
                                            recording.get_num_samples(segment_index=segment))
        channel = self.channel.value
        key = (unit, segment, sample, channel, width)
        scaled = bool(analyzer.return_in_uV and recording.has_scaleable_traces())
        try:
            if key not in self._cache:
                values = recording.get_traces(
                    segment_index=segment, start_frame=start, end_frame=stop,
                    channel_ids=[analyzer.channel_ids[channel]], return_in_uV=scaled,
                )[:, 0].copy()
                self._cache[key] = values
                while len(self._cache) > 16:
                    self._cache.popitem(last=False)
            self._cache.move_to_end(key)
        except (OSError, ValueError, RuntimeError) as error:
            self._clear(f"Could not read this recording snippet: {escape(str(error))}. Reconnect the recording and retry.")
            return
        values = self._cache[key]
        self.trace_source.data = dict(
            time_ms=(np.arange(start, stop) - sample) * 1000. / analyzer.sampling_frequency,
            amplitude=values,
        )
        self.renderer.glyph.line_color = self.get_unit_color(unit)[:7]
        self.plot.yaxis.axis_label = amplitude_label(analyzer, values.dtype)
        finite = values[np.isfinite(values)]
        low, high = (float(finite.min()), float(finite.max())) if finite.size else (-1., 1.)
        padding = max((high - low) * .10, 1e-6)
        for axis, lower, upper in ((self.plot.x_range, -half * 1000. / analyzer.sampling_frequency,
                                    half * 1000. / analyzer.sampling_frequency),
                                   (self.plot.y_range, low - padding, high + padding)):
            axis.start = axis.reset_start = lower
            axis.end = axis.reset_end = upper
        self._current_unit = unit
        self._location = (segment, sample)
        self.previous.disabled = self.first.disabled = self.spike_number.value <= 1
        self.next.disabled = self.last.disabled = self.spike_number.value >= self._total
        self.spike_number.disabled = self.channel.disabled = False
        self.plot.title.text = f"Unit {unit} · Spike {self.spike_number.value:,} / {self._total:,}"
        pending = any(unit in group for group in curation.get("merge_unit_groups", []))
        self.status.object = (
            f"**Unit {escape(str(unit))}** · **Spike {self.spike_number.value:,} / {self._total:,}** · "
            f"Segment **{segment}** · **{sample / analyzer.sampling_frequency:.6f} s** · "
            f"Channel **{escape(str(analyzer.channel_ids[channel]))}** · Dashed line = selected spike"
            + (" · Pending merge: showing this source unit." if pending else "")
        )

    def close(self, session_context=None):
        self._closed = True
        if self._adapter:
            self._adapter.close()
        for obj, watcher in self._watchers:
            obj.param.unwatch(watcher)
        self._watchers.clear()
        self._cache.clear()
