"""Real SI/Panel integration using only small synthetic recordings."""

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import spikeinterface as si

from sorting_scripts import zsort
from sorting_scripts.ensemble_gui import default_ensemble_layout, register_ensemble_view
from sorting_scripts.waveform_ensemble import (
    WaveformEnsembleView, amplitude_label, resolve_selected_unit,
    stored_channel_indices, time_axis,
)


def make_analyzer(duration=2., rate=80.):
    recording, sorting = si.generate_ground_truth_recording(
        durations=duration if isinstance(duration, list) else [duration], num_channels=4, num_units=3, seed=42,
        generate_sorting_kwargs={"firing_rates": rate, "refractory_period_ms": 3.},
    )
    sparsity = si.ChannelSparsity(
        np.array([[False, True, False, True], [True, False, True, False], [False, True, True, False]]),
        sorting.unit_ids, recording.channel_ids,
    )
    analyzer = si.create_sorting_analyzer(sorting, recording, sparsity=sparsity)
    analyzer.compute("random_spikes", max_spikes_per_unit=500, seed=11)
    analyzer.compute("waveforms", progress_bar=False)
    analyzer.compute("templates", operators=["average", "std"])
    analyzer.compute("noise_levels", num_chunks_per_segment=2)
    analyzer.compute("unit_locations", method="center_of_mass")
    analyzer.compute("template_similarity")
    return analyzer


class EnsembleDataTests(unittest.TestCase):
    def test_selection_uses_focus_then_first_selected_row(self):
        ids = ["a", "b", "c"]
        self.assertEqual(resolve_selected_unit(ids, [0, 2], 2), "c")
        self.assertEqual(resolve_selected_unit(ids, [2, 0], 1), "a")
        self.assertIsNone(resolve_selected_unit(ids, [], 0))
        self.assertEqual(resolve_selected_unit(ids, [99, 1]), "b")

    def test_time_and_units(self):
        np.testing.assert_allclose(time_axis(4, 1, 20000), [-.05, 0., .05, .1])
        self.assertEqual(amplitude_label(SimpleNamespace(return_in_uV=True), np.float32), "Amplitude (µV)")
        self.assertEqual(amplitude_label(SimpleNamespace(return_in_uV=False), np.int16), "Amplitude (ADC counts)")
        self.assertIn("recording units", amplitude_label(SimpleNamespace(return_in_uV=False), np.float32))


class EnsemblePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = make_analyzer()

    def setUp(self):
        self.window = zsort.launch_curation_gui(
            self.analyzer, mode="web", curation=True, start_app=False, with_traces=False,
        )
        self.view = self.window.views["waveformensemble"]
        self.unitlist = self.window.views["unitlist"]
        self.addCleanup(self.view.close)
        self.addCleanup(self.window.views["spikesnippets"].close)

    def select(self, rows, focus=None):
        self.unitlist.table.selection = rows
        if focus is not None:
            self.unitlist.table._last_selected_row = focus
            self.unitlist.notifier.notify_active_view_updated()

    def test_actual_panel_layout_registration_and_selection(self):
        self.assertIsInstance(self.view, WaveformEnsembleView)
        self.assertTrue(self.view.is_view_visible())
        self.assertEqual(default_ensemble_layout()["zone7"][0], "waveform")
        self.assertEqual(default_ensemble_layout()["zone8"][0], "waveformensemble")
        self.assertTrue(self.window.views["waveform"].is_view_visible())
        visible = list(self.window.controller.get_visible_unit_ids())
        self.select([1])
        self.assertEqual(self.view._current_unit, self.analyzer.unit_ids[1])
        self.assertEqual(self.window.controller.get_visible_unit_ids(), visible)
        self.select([0, 2], focus=2)
        self.assertEqual(self.view._current_unit, self.analyzer.unit_ids[2])
        self.select([0, 2], focus=0)
        self.assertEqual(self.view._current_unit, self.analyzer.unit_ids[0])
        # Exercise the real upstream keyboard handler, not a guessed signal.
        self.unitlist._panel_view_is_active = True
        self.unitlist.table._handle_shortcut(SimpleNamespace(data="next"))
        self.assertEqual(self.view._current_unit, self.analyzer.unit_ids[1])
        self.select([])
        self.assertEqual(len(self.view.waveform_source.data["ys"]), 0)
        self.assertEqual(len(self.view.template_source.data["y"]), 0)
        self.assertIn("Select a unit", self.view.status.object)

    def test_sparse_mapping_template_time_amplitude_and_repeatability(self):
        self.select([0])
        unit = self.analyzer.unit_ids[0]
        channels = stored_channel_indices(self.analyzer, unit)
        np.testing.assert_array_equal(channels, [1, 3])
        self.view.max_waveforms.value = 17
        self.view.channel.value = 3
        raw = self.analyzer.get_extension("waveforms").get_waveforms_one_unit(unit)
        shown = np.asarray(self.view.waveform_source.data["ys"])
        self.assertEqual(shown.shape, (17, raw.shape[1]))
        for trace in shown:
            self.assertTrue(any(np.array_equal(trace, original) for original in raw[:, :, 1]))
        expected = self.analyzer.get_extension("templates").data["average"][0, :, 3]
        np.testing.assert_array_equal(self.view.template_source.data["y"], expected)
        ext = self.analyzer.get_extension("waveforms")
        self.assertEqual(self.view.template_source.data["x"][ext.nbefore], 0.)
        self.assertLess(self.view.plot.y_range.start, np.min(shown))
        self.assertGreater(self.view.plot.y_range.end, np.max(shown))
        self.view.invalidate()
        self.view.refresh()
        np.testing.assert_array_equal(self.view.waveform_source.data["ys"], shown)
        self.assertEqual(self.view.waveform_renderer.glyph.line_color, self.view.get_unit_color(unit)[:7])

    def test_curation_invalidation_missing_data_and_replacement(self):
        self.select([0])
        unit = self.analyzer.unit_ids[0]
        self.assertTrue(self.view._cache)
        self.window.controller.make_manual_delete_if_possible([unit])
        self.unitlist.notify_manual_curation_updated()
        self.assertFalse(self.view._cache)
        self.assertEqual(len(self.view.template_source.data["y"]), 0)
        self.window.controller.make_manual_restore([unit])
        self.window.controller.make_manual_merge_if_possible(list(self.analyzer.unit_ids[:2]))
        self.unitlist.notify_manual_curation_updated()
        self.assertIn("Pending merge", self.view.status.object)
        replacement = self.analyzer.select_units(self.analyzer.unit_ids)
        replacement.delete_extension("waveforms")
        self.window.controller.analyzer = replacement
        self.view.refresh()
        self.assertIn("required", self.view.status.object)
        self.assertEqual(len(self.view.waveform_source.data["ys"]), 0)

    def test_cache_bound_and_session_independence(self):
        other = zsort.launch_curation_gui(self.analyzer, mode="web", curation=True, start_app=False, with_traces=False)
        other_view = other.views["waveformensemble"]
        self.addCleanup(other_view.close)
        self.select([0])
        self.assertEqual(len(other_view.waveform_source.data["ys"]), 0)
        self.assertIsNot(self.view._cache, other_view._cache)
        self.assertIsNot(self.window.controller.curation_data["removed_units"],
                         other.controller.curation_data["removed_units"])
        for count in range(1, 20):
            self.view.max_waveforms.value = count
        self.assertLessEqual(len(self.view._cache), 16)
        old = self.view._current_unit
        self.view.close()
        self.select([1])
        self.assertEqual(self.view._current_unit, old)


class EnsembleLauncherTests(unittest.TestCase):
    def test_missing_entry_point_is_actionable(self):
        with patch("sorting_scripts.ensemble_gui.entry_points", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "pip install.*restart"):
                register_ensemble_view()

    def test_explicit_layout_and_session_factory(self):
        from sorting_scripts.ensemble_gui import launch_web_ensemble
        options = {"layout": {"zone1": ["unitlist"]}, "port": 5019, "address": "localhost"}
        original = deepcopy(options)
        created = []

        def make_window(**kwargs):
            view = SimpleNamespace(close=lambda context: None)
            win = SimpleNamespace(main_layout=object(), views={"waveformensemble": view})
            created.append((win, kwargs))
            return win

        def serve(routes, **kwargs):
            first, second = routes["/"](), routes["/"]()
            self.assertIsNot(first, second)
            self.assertEqual(kwargs["port"], 5019)

        with patch("spikeinterface_gui.run_mainwindow", side_effect=make_window), \
             patch("spikeinterface_gui.backend_panel.start_server", side_effect=serve), \
             patch("panel.state.on_session_destroyed"):
            launch_web_ensemble(object(), True, options)
        self.assertEqual(options, original)
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0][1]["layout"], options["layout"])
        self.assertIsNot(created[0][1]["curation_dict"], created[1][1]["curation_dict"])


if __name__ == "__main__":
    unittest.main()
