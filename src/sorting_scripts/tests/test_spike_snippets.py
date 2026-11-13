"""Chronological navigation, bounded recording reads, and real Panel callbacks."""

import unittest
from unittest.mock import patch

import numpy as np

from sorting_scripts import zsort
from sorting_scripts.spike_snippets import locate_spike, snippet_bounds
from test_waveform_ensemble import make_analyzer


class SnippetNavigationTests(unittest.TestCase):
    def test_chronological_navigation_across_empty_segments_and_boundaries(self):
        trains = [np.array([0, 99]), np.array([], dtype=int), np.array([10, 40])]
        self.assertEqual(locate_spike(trains, 0), (0, 0))
        self.assertEqual(locate_spike(trains, 1), (0, 99))
        self.assertEqual(locate_spike(trains, 2), (2, 10))
        self.assertEqual(locate_spike(trains, 3), (2, 40))
        self.assertEqual(locate_spike(trains, -1), (0, 0))
        self.assertEqual(locate_spike(trains, 99), (2, 40))
        with self.assertRaisesRegex(ValueError, "no spikes"):
            locate_spike([np.array([])], 0)

    def test_snippet_bounds_keep_spike_center_at_recording_edges(self):
        self.assertEqual(snippet_bounds(500, 30000, 20, 1000), (200, 801, 300))
        self.assertEqual(snippet_bounds(0, 30000, 20, 1000), (0, 301, 300))
        self.assertEqual(snippet_bounds(999, 30000, 20, 1000), (699, 1000, 300))


class SnippetPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = make_analyzer()

    def setUp(self):
        self.window = zsort.launch_curation_gui(
            self.analyzer, mode="web", curation=True, start_app=False, with_traces=True,
        )
        self.view = self.window.views["spikesnippets"]
        self.unitlist = self.window.views["unitlist"]
        self.addCleanup(self.view.close)
        self.addCleanup(self.window.views["waveformensemble"].close)

    def test_both_waveform_panels_and_snippets_are_initially_visible(self):
        for name in ("waveform", "waveformensemble", "spikesnippets"):
            self.assertTrue(self.window.views[name].is_view_visible())
        self.assertFalse(self.window.views["trace"].is_view_visible())

    def test_selected_unit_next_previous_jump_and_channel_read(self):
        recording = self.analyzer.recording
        with patch.object(recording, "get_traces", wraps=recording.get_traces) as read:
            self.unitlist.table.selection = [1]
            self.assertEqual(self.view._current_unit, self.analyzer.unit_ids[1])
            segment, sample = self.view._location
            self.assertEqual(segment, 0)
            self.assertEqual(sample, self.analyzer.sorting.get_unit_spike_train(self.analyzer.unit_ids[1])[0])
            args = read.call_args.kwargs
            self.assertLessEqual(args["end_frame"] - args["start_frame"], 601)
            self.assertEqual(len(args["channel_ids"]), 1)
            channel = self.view.channel.value
            x = np.asarray(self.view.trace_source.data["time_ms"])
            self.assertIn(0., x)
            expected = recording.get_traces(**args)[:, 0]
            np.testing.assert_array_equal(self.view.trace_source.data["amplitude"], expected)
            self.assertAlmostEqual(self.view.plot.x_range.start, -10.)
            self.assertAlmostEqual(self.view.plot.x_range.end, 10.)
            self.assertTrue(self.view.previous.disabled)
            self.view.next.clicks += 1
            self.assertEqual(self.view.spike_number.value, 2)
            self.assertGreater(self.view._location[1], sample)
            self.assertEqual(self.window.controller.get_time()[0], self.view._location[1] / self.analyzer.sampling_frequency)
            self.view.previous.clicks += 1
            self.assertEqual(self.view.spike_number.value, 1)
            self.view.last.clicks += 1
            self.assertEqual(self.view.spike_number.value, self.view._total)
            self.assertTrue(self.view.next.disabled)
            self.view.first.clicks += 1
            self.view.spike_number.value = 3
            self.assertEqual(self.view._location[1], self.view._trains[0][2])
            self.view.channel.value = next(i for i in self.view.channel.options.values() if i != channel)
            self.assertNotEqual(self.view.channel.value, channel)
            self.view.window_ms.value = 10.
            self.assertEqual(self.view.plot.x_range.start, -5.)
            self.assertEqual(self.view.plot.x_range.end, 5.)

    def test_no_selection_deletion_and_closed_callbacks(self):
        self.unitlist.table.selection = [0]
        unit = self.analyzer.unit_ids[0]
        self.window.controller.make_manual_delete_if_possible([unit])
        self.unitlist.notify_manual_curation_updated()
        self.assertEqual(len(self.view.trace_source.data["amplitude"]), 0)
        self.assertIn("removal", self.view.status.object)
        self.window.controller.make_manual_restore([unit])
        self.unitlist.table.selection = [2]
        self.assertEqual(self.view._current_unit, self.analyzer.unit_ids[2])
        self.unitlist.table.selection = []
        self.assertEqual(len(self.view.trace_source.data["amplitude"]), 0)
        self.assertTrue(self.view.next.disabled)
        self.view.close()
        self.unitlist.table.selection = [1]
        self.assertEqual(len(self.view.trace_source.data["amplitude"]), 0)

    def test_trace_opt_out_missing_recording_and_read_failure(self):
        self.window.controller.with_traces = False
        self.unitlist.table.selection = [0]
        self.assertIn("with_traces=True", self.view.status.object)
        self.window.controller.with_traces = True
        with patch.object(self.analyzer, "has_recording", return_value=False), \
             patch.object(self.analyzer, "has_temporary_recording", return_value=False):
            self.view.refresh()
        self.assertIn("unavailable", self.view.status.object)
        with patch.object(self.analyzer.recording, "get_traces", side_effect=OSError("missing source file")):
            self.view.refresh()
        self.assertIn("missing source file", self.view.status.object)
        self.assertEqual(len(self.view.trace_source.data["amplitude"]), 0)

    def test_cache_bounds_and_pending_merge(self):
        self.unitlist.table.selection = [0]
        for number in range(1, 20):
            self.view.spike_number.value = number
        self.assertLessEqual(len(self.view._cache), 16)
        self.window.controller.make_manual_merge_if_possible(list(self.analyzer.unit_ids[:2]))
        self.unitlist.notify_manual_curation_updated()
        self.assertIn("Pending merge", self.view.status.object)

    def test_actual_segment_boundary_navigation(self):
        analyzer = make_analyzer(duration=[.5, .5])
        window = zsort.launch_curation_gui(analyzer, mode="web", start_app=False, with_traces=True)
        view = window.views["spikesnippets"]
        self.addCleanup(view.close)
        self.addCleanup(window.views["waveformensemble"].close)
        window.views["unitlist"].table.selection = [0]
        view.spike_number.value = len(view._trains[0])
        self.assertEqual(view._location[0], 0)
        view.next.clicks += 1
        self.assertEqual(view._location, (1, int(view._trains[1][0])))
        self.assertEqual(window.controller.get_time()[1], 1)
        view.previous.clicks += 1
        self.assertEqual(view._location, (0, int(view._trains[0][-1])))


if __name__ == "__main__":
    unittest.main()
